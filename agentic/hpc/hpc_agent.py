"""
MD Workflow HPC Agent

Handles job submission, monitoring, and result download from HPC clusters.
Uses LLM for decision guidance and graceful fallbacks when remote access
is unavailable.
"""
import os
import logging
from typing import Dict, Any, Optional

from ..state import MDState
from ..llm import LLMClient
from ..utils import log_supervisor_routing

logger = logging.getLogger(__name__)

try:
    import paramiko  # type: ignore
except Exception:
    paramiko = None


class MDHPCAgent:
    """
    HPC agent that performs cluster operations based on supervisor prompts.
    Main tasks: job submission, monitoring, and downloading results.
    """

    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        self.llm = llm_client
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config = self._load_config()
        logger.info("MD HPC Agent initialized")

    def _load_config(self) -> Dict[str, Any]:
        import yaml
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"HPC config {self.config_path} not found; using defaults")
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "ssh": {
                "host": None,
                "user": None,
                "port": 22,
                "key_path": None,
            },
            "paths": {
                "remote_work_dir": "~/md_jobs",
                "local_download_dir": "./working_dir",
            },
            "commands": {
                "submit": "sbatch {job_script}",
                "status": "squeue -j {job_id}",
                "cancel": "scancel {job_id}",
            },
            "download": {
                "patterns": ["*.xtc", "*.gro", "*.log", "*.out"]
            },
        }

    def hpc_node(self, state: MDState) -> MDState:
        """
        Entry point: interpret supervisor intent and execute HPC task.
        Expects `state['hpc_action']` in {submit_job, monitor_job, download_results}.
        Falls back to submit if job_script present and no job_id.
        """
        action = (state.get("hpc_action") or "").strip().lower()
        if not action:
            if state.get("job_script") and not state.get("job_id"):
                action = "submit_job"
            elif state.get("job_id"):
                action = "monitor_job"
            else:
                action = "download_results" if state.get("trajectory_path") else "submit_job"

        logger.info(f"HPC agent executing action: {action}")

        try:
            if action == "submit_job":
                self._handle_submit(state)
            elif action == "monitor_job":
                self._handle_monitor(state)
            elif action == "download_results":
                self._handle_download(state)
            else:
                state["warnings"].append(f"Unknown HPC action '{action}', no operation performed")
        except Exception as e:
            msg = f"HPC action '{action}' failed: {e}"
            logger.exception(msg)
            state["errors"].append(msg)

        # Route back to supervisor with an update
        state["next_node"] = "supervisor"
        log_supervisor_routing(state, "supervisor", f"HPC agent completed '{action}'")
        return state

    def _handle_submit(self, state: MDState) -> None:
        job_script = state.get("job_script")
        if not job_script:
            # try planner/programmer produced scripts
            gen = state.get("generated_scripts", {})
            job_info = gen.get("slurm_job_script") or {}
            job_script = job_info.get("file_path")
        if not job_script:
            raise RuntimeError("No job_script available for submission")

        ssh = self.config.get("ssh", {})
        remote_dir = self.config.get("paths", {}).get("remote_work_dir", "~/md_jobs")
        submit_cmd_tpl = self.config.get("commands", {}).get("submit", "sbatch {job_script}")

        if paramiko and ssh.get("host") and ssh.get("user"):
            job_id = self._ssh_submit(job_script, remote_dir, submit_cmd_tpl, ssh)
            state["job_id"] = job_id
            state["job_status"] = "SUBMITTED"
        else:
            # Mock submission when SSH not configured
            state["warnings"].append("SSH not configured; mocking job submission")
            state["job_id"] = "MOCK-12345"
            state["job_status"] = "SUBMITTED"

        logger.info(f"Job submitted. ID: {state['job_id']}")

    def _ssh_submit(self, job_script: str, remote_dir: str, submit_cmd_tpl: str, ssh_cfg: Dict[str, Any]) -> str:
        # Establish SSH
        client = self._connect_ssh(ssh_cfg)
        sftp = client.open_sftp()
        try:
            # Ensure remote dir exists
            try:
                sftp.stat(remote_dir)
            except Exception:
                client.exec_command(f"mkdir -p {remote_dir}")
            # Upload script
            remote_path = f"{remote_dir}/job.sh"
            sftp.put(job_script, remote_path)
            # Submit
            submit_cmd = submit_cmd_tpl.format(job_script=remote_path)
            _, stdout, stderr = client.exec_command(submit_cmd)
            out = stdout.read().decode("utf-8").strip()
            err = stderr.read().decode("utf-8").strip()
            logger.debug(f"submit stdout: {out}\nstderr: {err}")
            # Parse job id heuristically
            job_id = self._extract_job_id(out) or self._extract_job_id(err) or "UNKNOWN"
            return job_id
        finally:
            sftp.close()
            client.close()

    def _handle_monitor(self, state: MDState) -> None:
        job_id = state.get("job_id")
        if not job_id:
            raise RuntimeError("No job_id available to monitor")

        ssh = self.config.get("ssh", {})
        status_cmd_tpl = self.config.get("commands", {}).get("status", "squeue -j {job_id}")

        if paramiko and ssh.get("host") and ssh.get("user"):
            status = self._ssh_status(job_id, status_cmd_tpl, ssh)
            state["job_status"] = status
        else:
            # Mock monitoring
            state["warnings"].append("SSH not configured; mocking job status as COMPLETED")
            state["job_status"] = "COMPLETED"

        logger.info(f"Job status: {state['job_status']}")

    def _ssh_status(self, job_id: str, status_cmd_tpl: str, ssh_cfg: Dict[str, Any]) -> str:
        client = self._connect_ssh(ssh_cfg)
        try:
            cmd = status_cmd_tpl.format(job_id=job_id)
            _, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode("utf-8").strip()
            err = stderr.read().decode("utf-8").strip()
            logger.debug(f"status stdout: {out}\nstderr: {err}")
            # Heuristic: if squeue returns empty, assume completed
            if not out and not err:
                return "COMPLETED"
            if " PD " in out or "PENDING" in out:
                return "PENDING"
            if " R " in out or "RUNNING" in out:
                return "RUNNING"
            return "UNKNOWN"
        finally:
            client.close()

    def _handle_download(self, state: MDState) -> None:
        ssh = self.config.get("ssh", {})
        remote_dir = self.config.get("paths", {}).get("remote_work_dir", "~/md_jobs")
        local_dir = self.config.get("paths", {}).get("local_download_dir", "./working_dir")
        patterns = self.config.get("download", {}).get("patterns", ["*.xtc", "*.gro"]) 

        if paramiko and ssh.get("host") and ssh.get("user"):
            self._ssh_download(remote_dir, local_dir, patterns, ssh)
            # Update state trajectory path if downloaded
            state["trajectory_path"] = self._find_local_file(local_dir, [".xtc", ".trr"]) or state.get("trajectory_path")
        else:
            state["warnings"].append("SSH not configured; skipping download")

    def _ssh_download(self, remote_dir: str, local_dir: str, patterns: Any, ssh_cfg: Dict[str, Any]) -> None:
        client = self._connect_ssh(ssh_cfg)
        sftp = client.open_sftp()
        try:
            os.makedirs(local_dir, exist_ok=True)
            # Simple download: fetch all files in remote_dir (pattern matching can be added)
            for attr in sftp.listdir_attr(remote_dir):
                fname = attr.filename
                remote_path = f"{remote_dir}/{fname}"
                local_path = os.path.join(local_dir, fname)
                sftp.get(remote_path, local_path)
                logger.info(f"Downloaded {remote_path} -> {local_path}")
        finally:
            sftp.close()
            client.close()

    def _connect_ssh(self, ssh_cfg: Dict[str, Any]):
        if not paramiko:
            raise RuntimeError("Paramiko not available")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        key_path = ssh_cfg.get("key_path")
        client.connect(
            hostname=ssh_cfg.get("host"),
            port=int(ssh_cfg.get("port", 22)),
            username=ssh_cfg.get("user"),
            key_filename=key_path if key_path else None,
        )
        return client

    def _extract_job_id(self, text: str) -> Optional[str]:
        import re
        m = re.search(r"Submitted batch job (\d+)", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{6,})", text)
        return m.group(1) if m else None

