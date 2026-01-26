"""
MD Workflow Analysis Agent

Performs analysis of simulation outputs based on supervisor prompts.
Uses LLM to plan analysis steps and selects appropriate tools; includes
fallbacks when data or dependencies are unavailable.
"""
import os
import logging
from typing import Dict, Any, Optional

from ..state import MDState
from ..llm import LLMClient
from ..utils import log_supervisor_routing

logger = logging.getLogger(__name__)

# Optional heavy deps (graceful fallback)
try:
    import MDAnalysis as mda  # type: ignore
    HAS_MDA = True
except Exception:
    HAS_MDA = False


class MDAnalysisAgent:
    """LLM-driven analysis agent that plans and executes analysis tasks."""

    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        self.llm = llm_client
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config = self._load_config()
        logger.info("MD Analysis Agent initialized")

    def _load_config(self) -> Dict[str, Any]:
        import yaml
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Analysis config {self.config_path} not found; using defaults")
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "metrics": ["rmsd", "rmsf", "energy"],
            "plots": True,
            "output_dir": "./working_dir/analysis",
            "use_mdanalysis": True,
        }

    def analysis_node(self, state: MDState) -> MDState:
        """
        Entry point: build an LLM-guided analysis plan then execute what is feasible.
        Expects `state['analysis_action']` or infers from availability of trajectory.
        """
        action = (state.get("analysis_action") or "plan_and_run").lower()
        logger.info(f"Analysis agent executing action: {action}")

        try:
            if action == "plan_and_run":
                plan = self._create_analysis_plan(state)
                state.setdefault("analysis_results", {})["plan"] = plan
                self._execute_basic_analysis(state, plan)
            elif action == "plan_only":
                plan = self._create_analysis_plan(state)
                state.setdefault("analysis_results", {})["plan"] = plan
            elif action == "run_basic":
                plan = {"metrics": self.config.get("metrics", [])}
                self._execute_basic_analysis(state, plan)
            else:
                state["warnings"].append(f"Unknown analysis action '{action}'")
        except Exception as e:
            msg = f"Analysis action '{action}' failed: {e}"
            logger.exception(msg)
            state["errors"].append(msg)

        # Route back to supervisor
        state["next_node"] = "supervisor"
        log_supervisor_routing(state, "supervisor", f"Analysis agent completed '{action}'")
        return state

    def _create_analysis_plan(self, state: MDState) -> Dict[str, Any]:
        traj = state.get("trajectory_path")
        coords = state.get("coordinates")
        request = state.get("analysis_request") or "General stability and energy analysis"
        prompt = f"""
You are an expert MD analysis agent. Draft a practical analysis plan.

INPUTS:
- Trajectory: {traj}
- Coordinates: {coords}
- Request: {request}
- Preferred metrics: {self.config.get('metrics')}

RESPONSE FORMAT:
Metrics: [comma separated list]
Steps:
- Step 1: description
- Step 2: description
Outputs: [files/plots]
Notes: [assumptions/fallbacks]
"""
        resp = self.llm.prompt(prompt, system="You plan MD analysis tasks and ensure reproducible outputs.")
        return {"raw": resp}

    def _execute_basic_analysis(self, state: MDState, plan: Dict[str, Any]) -> None:
        out_dir = self.config.get("output_dir", "./working_dir/analysis")
        os.makedirs(out_dir, exist_ok=True)
        traj = state.get("trajectory_path")
        coords = state.get("coordinates") or state.get("topology")

        results = state.setdefault("analysis_results", {})
        if not traj or not os.path.exists(traj):
            results["summary"] = "No trajectory available; stored analysis plan only."
            state["warnings"].append("Trajectory missing; analysis not executed")
            return

        # Minimal, dependency-light analysis placeholder
        if not HAS_MDA or not self.config.get("use_mdanalysis", True):
            results["summary"] = "MDAnalysis unavailable; minimal placeholder analysis done."
            results["metrics"] = {"frames": self._count_lines(traj)}
            return

        # Basic RMSD using MDAnalysis
        try:
            import numpy as np
            u = mda.Universe(coords, traj) if coords else mda.Universe(traj)
            ref = u.select_atoms("protein").positions.copy() if u.atoms.n_atoms > 0 else None
            rmsds = []
            for ts in u.trajectory:
                sel = u.select_atoms("protein")
                if sel.n_atoms == 0 or ref is None:
                    continue
                pos = sel.positions
                diff = pos - ref
                rmsd = (np.sqrt((diff * diff).sum(axis=1).mean()))
                rmsds.append(float(rmsd))
            results["metrics"] = {"rmsd_mean": float(np.mean(rmsds)) if rmsds else None,
                                   "rmsd_max": float(np.max(rmsds)) if rmsds else None,
                                   "frames": len(rmsds)}
            results["summary"] = "Computed simple RMSD over protein selection."
        except Exception as e:
            logger.exception("Error during MDAnalysis RMSD")
            state["errors"].append(f"RMSD analysis failed: {e}")

    def _count_lines(self, path: str) -> int:
        try:
            with open(path, "rb") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

