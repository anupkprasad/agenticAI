"""Async HPC agent moved into the hpc subpackage."""
from __future__ import annotations

from typing import Optional, Dict
from agentic.async_utils import run_in_thread


class AsyncHPCJobAgent:
    """Async wrapper around the blocking HPCJobAgent.

    Uses a lazy import of the blocking implementation to avoid import-time
    cycles and to keep the module lightweight when only the async interface
    is needed by orchestration code.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        # Lazy import of the blocking agent implementation
        from agentic.hpc.hpc_blocking import HPCJobAgent

        self._agent = HPCJobAgent(config_path=config_path)

    async def submit_job(self, local_job_script: str) -> Dict:
        return await run_in_thread(self._agent.submit_job, local_job_script)

    async def download_results(self, job_id: str, remote_path: Optional[str] = None, local_dir: Optional[str] = None) -> Dict:
        return await run_in_thread(self._agent.download_results, job_id, remote_path, local_dir)
