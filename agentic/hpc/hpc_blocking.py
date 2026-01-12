"""Blocking HPC job agent implementations (moved into hpc subpackage)."""
from __future__ import annotations

import os
from typing import Dict, Optional
import yaml


class HPCJobAgent:
    """Handles job submission and retrieval from HPC via SSH/SFTP.

    This class contains minimal, safe examples. For real usage, ensure keys
    and credentials are stored securely and connections are hardened.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as fh:
            self.config = yaml.safe_load(fh)

    def submit_job(self, local_job_script: str) -> Dict:
        """Stub for job submission: returns a mock job id.

        Replace with real SSH submission (e.g., ssh user@host sbatch job.sh).
        """
        print(f"Would submit {local_job_script} to {self.config['hpc']['host']}")
        # Safe mock response
        return {"status": "submitted", "job_id": "MOCK-12345"}

    def download_results(self, job_id: str, remote_path: Optional[str] = None, local_dir: Optional[str] = None) -> Dict:
        """Stub for result download: create a placeholder file and return path.

        Replace with SFTP/rsync logic.
        """
        local_dir = local_dir or self.config.get("paths", {}).get("local_results_dir", "results/")
        os.makedirs(local_dir, exist_ok=True)
        out_file = os.path.join(local_dir, f"{job_id}_results.tar.gz")
        with open(out_file, "wb") as fh:
            fh.write(b"MOCK_RESULTS")
        return {"status": "downloaded", "path": out_file}
