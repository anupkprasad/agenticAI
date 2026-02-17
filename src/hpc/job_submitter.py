"""
HPC Job Submitter - Submit SLURM jobs to HPC systems
"""
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def submit_job(
    script_path: str,
    remote_host: Optional[str] = None,
    remote_user: Optional[str] = None,
    remote_dir: Optional[str] = None,
    ssh_key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit SLURM job to HPC system.
    
    Args:
        script_path: Path to SLURM script
        remote_host: Remote HPC hostname (optional, for SSH submission)
        remote_user: Remote username (optional)
        remote_dir: Remote working directory (optional)
        ssh_key_path: SSH key path (optional)
        
    Returns:
        Dict with job_id and submission status
        
    Note:
        If remote_host is not provided, assumes local submission via sbatch.
        For remote submission, uses SSH to transfer script and submit.
    """
    try:
        script_file = Path(script_path)
        if not script_file.exists():
            return {
                "success": False,
                "error": f"Script file not found: {script_path}"
            }
        
        # Local submission
        if not remote_host:
            result = subprocess.run(
                ["sbatch", str(script_file)],
                capture_output=True,
                text=True,
                cwd=script_file.parent
            )
            
            if result.returncode == 0:
                # Parse job ID from "Submitted batch job 12345"
                import re
                match = re.search(r"Submitted batch job (\d+)", result.stdout)
                job_id = match.group(1) if match else "UNKNOWN"
                
                return {
                    "success": True,
                    "job_id": job_id,
                    "status": "SUBMITTED",
                    "message": f"Job submitted successfully: {job_id}",
                    "stdout": result.stdout
                }
            else:
                return {
                    "success": False,
                    "error": f"sbatch failed: {result.stderr}",
                    "returncode": result.returncode
                }
        
        # Remote submission via SSH
        else:
            try:
                import paramiko
            except ImportError:
                return {
                    "success": False,
                    "error": "paramiko not installed - cannot submit to remote host"
                }
            
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect
            connect_kwargs = {
                "hostname": remote_host,
                "username": remote_user,
                "port": 22
            }
            if ssh_key_path:
                connect_kwargs["key_filename"] = ssh_key_path
            
            client.connect(**connect_kwargs)
            
            # Upload script
            sftp = client.open_sftp()
            remote_script = f"{remote_dir}/{script_file.name}"
            sftp.put(str(script_file), remote_script)
            sftp.close()
            
            # Submit job
            stdin, stdout, stderr = client.exec_command(f"sbatch {remote_script}")
            output = stdout.read().decode("utf-8").strip()
            error = stderr.read().decode("utf-8").strip()
            
            client.close()
            
            # Parse job ID
            import re
            match = re.search(r"Submitted batch job (\d+)", output)
            job_id = match.group(1) if match else "UNKNOWN"
            
            return {
                "success": True,
                "job_id": job_id,
                "status": "SUBMITTED",
                "message": f"Remote job submitted: {job_id}",
                "stdout": output,
                "remote_host": remote_host
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Job submission failed: {e}"
        }
