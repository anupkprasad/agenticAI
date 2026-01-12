"""Blocking SimulationSetupAgent (blocking/stub version) moved into setup subpackage.
"""
from __future__ import annotations

import os
import textwrap
from typing import Dict, Optional
import yaml


class SimulationSetupAgent:
    """Prepare simulation inputs and generate job scripts.

    This is the blocking version intended for simple scripts or for
    callers that don't require async behavior.
    """

    def __init__(self, config_path: str = "config/config.yaml", llm_client: object = None):
        with open(config_path) as fh:
            self.config = yaml.safe_load(fh)
        # Optional LLM client (instance of LLMClient or LangGraph agent)
        self.llm = llm_client

    def plan_simulation(self, pdb_path: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        sim = {
            "pdb": pdb_path,
            "engine": params.get("engine", self.config.get("simulation", {}).get("engine", "gromacs")),
            "steps": params.get("steps", self.config.get("simulation", {}).get("md_steps", 10000)),
        }
        if self.llm and (params.get("use_llm") or params.get("prompt")):
            prompt = params.get("prompt") or f"Prepare MD parameters for PDB at {pdb_path} with defaults {self.config.get('simulation', {})}"
            try:
                llm_out = self.llm.prompt(prompt)
                sim["llm_suggestion"] = llm_out
            except Exception as e:
                sim["llm_error"] = str(e)
        job_script = self._render_slurm_script(sim)
        out_path = os.path.abspath("jobs/run_sim.sh")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as fh:
            fh.write(job_script)
        return {"plan": sim, "job_script": out_path}

    def _render_slurm_script(self, sim: Dict) -> str:
        template = textwrap.dedent(
            """
            #!/bin/bash
            #SBATCH --job-name=md_run
            #SBATCH --time=02:00:00
            #SBATCH --nodes=1
            #SBATCH --ntasks-per-node=16
            #SBATCH --partition=compute

            echo "Starting simulated job for {sim_pdb}"
            # TODO: Load modules and run your MD engine here (GROMACS/ NAMD / OpenMM)
            """
        )
        return template.format(sim_pdb=sim.get("pdb", "UNKNOWN"))
