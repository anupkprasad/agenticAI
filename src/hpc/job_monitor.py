"""
HPC Job Monitor - Check status of submitted SLURM jobs
"""
import subprocess
import logging
from typing import Dict, Any, Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def check_job_status(
    job_id: str,
    remote_host: Optional[str] = None,
    remote_user: Optional[str] = None,
    ssh_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check status of submitted SLURM job.
    
    Args:
        job_id: SLURM job ID
        remote_host: Remote HPC hostname (optional)
        remote_user: Remote username (optional)
        ssh_key_path: SSH key path (optional)
        
    Returns:
        Dict with job status information
    """
    try:
        # Local status check
        if not remote_host:
            result = subprocess.run(
                ["squeue", "-j", job_id, "-o", "%.18i %.9P %.8T %.10M %.6D %R"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # Job not in queue - might be completed or failed
                # Check sacct for completed jobs
                sacct_result = subprocess.run(
                    ["sacct", "-j", job_id, "-o", "State", "-n"],
                    capture_output=True,
                    text=True
                )
                
                if sacct_result.returncode == 0:
                    status_text = sacct_result.stdout.strip().split()[0] if sacct_result.stdout.strip() else "UNKNOWN"
                    return {
                        "success": True,
                        "job_id": job_id,
                        "status": status_text,
                        "message": f"Job {job_id} status: {status_text}"
                    }
                
                return {
                    "success": False,
                    "job_id": job_id,
                    "status": "NOT_FOUND",
                    "error": "Job not found in queue or history"
                }
            
            # Parse squeue output
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                fields = lines[1].split()
                status = fields[2] if len(fields) > 2 else "UNKNOWN"
                elapsed = fields[3] if len(fields) > 3 else "N/A"
                
                return {
                    "success": True,
                    "job_id": job_id,
                    "status": status,
                    "elapsed_time": elapsed,
                    "message": f"Job {job_id} is {status}"
                }
        
        # Remote status check
        else:
            try:
                import paramiko
            except ImportError:
                return {
                    "success": False,
                    "error": "paramiko not installed - cannot check remote job"
                }
            
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                "hostname": remote_host,
                "username": remote_user,
                "port": 22
            }
            if ssh_key_path:
                connect_kwargs["key_filename"] = ssh_key_path
            
            client.connect(**connect_kwargs)
            
            stdin, stdout, stderr = client.exec_command(f"squeue -j {job_id} -o '%.18i %.9P %.8T %.10M'")
            output = stdout.read().decode("utf-8").strip()
            
            client.close()
            
            if not output or len(output.split('\n')) < 2:
                return {
                    "success": True,
                    "job_id": job_id,
                    "status": "COMPLETED_OR_FAILED",
                    "message": "Job not in queue - likely completed or failed"
                }
            
            lines = output.split('\n')
            fields = lines[1].split()
            status = fields[2] if len(fields) > 2 else "UNKNOWN"
            
            return {
                "success": True,
                "job_id": job_id,
                "status": status,
                "remote_host": remote_host,
                "message": f"Remote job {job_id} is {status}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Status check failed: {e}"
        }


def _parse_sq_me_output(stdout: str) -> list:
    """Parse ``sq --me`` or similar tabular SLURM queue output."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].upper()
    jobs = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        job_id = parts[0]
        state = "UNKNOWN"
        name = parts[1] if len(parts) > 1 else ""
        if "STATE" in header:
            try:
                state_idx = header.split().index("STATE")
                if state_idx < len(parts):
                    state = parts[state_idx]
            except ValueError:
                pass
        else:
            for token in parts:
                if token in (
                    "RUNNING", "PENDING", "COMPLETING", "COMPLETED",
                    "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL",
                ):
                    state = token
                    break
        jobs.append({"job_id": job_id, "name": name, "state": state, "raw": line})
    return jobs


@tool
def list_my_slurm_jobs(
    remote_host: Optional[str] = None,
    remote_user: Optional[str] = None,
    ssh_key_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List current user's SLURM jobs (``sq --me`` alias or ``squeue -u $USER``).

    Returns:
        Dict with ``success``, ``jobs`` (list of {job_id, name, state}), ``command``.
    """
    import os
    import shutil

    commands = []
    if shutil.which("sq"):
        commands.append(["sq", "--me"])
    commands.append(["squeue", "-u", os.environ.get("USER", ""), "-o", "%.18i %.9P %.8j %.8T %.10M %.6D %R"])

    last_err = ""
    for cmd in commands:
        if not cmd[0] or (cmd[0] == "squeue" and not cmd[2]):
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and result.stdout.strip():
                jobs = _parse_sq_me_output(result.stdout)
                return {
                    "success": True,
                    "jobs": jobs,
                    "command": " ".join(cmd),
                    "message": f"Found {len(jobs)} job(s) in queue",
                }
            last_err = result.stderr.strip() or f"exit {result.returncode}"
        except Exception as exc:
            last_err = str(exc)
            logger.warning("list_my_slurm_jobs %s failed: %s", cmd, exc)

    return {
        "success": False,
        "jobs": [],
        "error": last_err or "Could not list SLURM jobs",
    }
