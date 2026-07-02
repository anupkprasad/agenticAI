"""
Clean and Simple LLM-Powered MD Workflow Supervisor

Responsibilities:
1. Analyze PDB structure and validate components
2. Enrich user prompt ONCE with all context (Single LLM call for entire workflow)  
3. Validate input feasibility (PDB files, parameters, user intent)
4. Collaborate with planner to create execution plans
5. Route tasks to field agents in STRICT ORDER: preprocessing → simsetup → hpc → analysis → reporter
6. Multi-simulation orchestration: loop through per-sim prompts, then combined analysis + reporter
"""

import json
import logging
import shutil
import yaml
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state import MDState
from ..utils import log_supervisor_routing, log_agent_action
from ..utils.plan_persistence import save_plan_artifacts
from ..utils.conversation_logger import set_log_file
from ..llm import LLMClient
from ..planner import MDPlanner
from .tools import (
    parse_component_selection,
    validate_feasibility,
    detect_task_required_inputs,
)
from src.supervisor.component_parser import (
    parse_sim_case_requirements,
    validate_sim_case_components,
)

# Import PDB analyzer
from src.utils.pdb_analyzer import analyze_pdb

# Import unified enrichment
from src.supervisor.unified_enricher import enrich_prompt_unified, get_agent_execution_order

logger = logging.getLogger(__name__)


def _coerce_plan_text(value: Any, default: str = "") -> str:
    """Normalize LLM plan fields (str, list, or dict) to a markdown-safe string."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, list):
        parts = [_coerce_plan_text(item, default="") for item in value]
        parts = [p for p in parts if p]
        return "\n".join(parts) if parts else default
    if isinstance(value, dict):
        for key in ("prompt", "goal", "text", "description", "plan"):
            if key in value and value[key]:
                return _coerce_plan_text(value[key], default=default)
        return json.dumps(value, indent=2, default=str)
    return str(value).strip() or default


# Agents that run before trajectories exist (preprocess → HPC).
_SIMULATION_STAGE_AGENTS = frozenset({"preprocess", "simsetup", "hpcjob"})


def _is_post_simulation_subtask(state: Dict[str, Any]) -> bool:
    """
    True when the workflow only runs analysis and/or reporter on existing data.

    Example: ``--subtask analysis reporter`` after simulations are already complete.
    """
    subtask_type = state.get("subtask_type")
    if subtask_type in ("analysis_only", "reporter_only"):
        return True
    if subtask_type == "multi_agent":
        agents = set(state.get("agent_list") or [])
        return not bool(agents & _SIMULATION_STAGE_AGENTS)
    return False


def _should_run_combined_analysis(state: Dict[str, Any]) -> bool:
    """
    True when multi-sim should run cross-simulation analysis + reporter at basepath.

    Respects the planner's master-plan intent decision and ``--subtask``.
    """
    if state.get("combined_only"):
        return True
    if state.get("run_combined_analysis") is False:
        return False
    if state.get("run_combined_analysis") is True:
        return True

    subtask_type = state.get("subtask_type")
    if subtask_type == "multi_agent":
        agents = set(state.get("agent_list") or [])
        return bool(agents & {"analysis", "reporter"})
    if subtask_type in ("analysis_only", "reporter_only", "full_task", None):
        return True
    return False


def _build_per_sim_prep_prompt(
    entry: Dict[str, Any],
    *,
    original_goal: str,
    enriched_prompt: str,
) -> str:
    """Fallback per-simulation prompt when the master plan has no ``prompt`` text."""
    protein = entry.get("protein_name") or entry.get("label", "system")
    label = entry.get("label", "simulation")
    case = entry.get("case_description", "default system")
    wdir = entry.get("working_dir", "")
    requirements = (original_goal or enriched_prompt or "").strip()

    return (
        f"Prepare MD simulation for {protein} (label: {label}; case: {case}). "
        f"Source structure is in {wdir}. "
        f"Run preprocessing and simsetup only — build topology, solvate/ionize as needed, "
        f"and generate MDP inputs for production MD. Do not submit SLURM/HPC jobs. "
        f"Project requirements: {requirements}"
    )


def _upsert_completed_sim_snapshot(
    completed: List[Dict[str, Any]], snapshot: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Replace an existing per-sim snapshot or append a new one."""
    label = snapshot.get("label")
    sim_index = snapshot.get("sim_index")
    for i, existing in enumerate(completed):
        if existing.get("label") == label or existing.get("sim_index") == sim_index:
            completed[i] = snapshot
            return completed
    completed.append(snapshot)
    return completed


def _dedupe_completed_sim_states(
    completed: List[Dict[str, Any]],
    sim_prompts: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Keep one snapshot per simulation label (last wins), in master-plan order."""
    by_label: Dict[str, Dict[str, Any]] = {}
    for snap in completed:
        label = snap.get("label")
        if label:
            by_label[label] = snap
    if sim_prompts:
        ordered: List[Dict[str, Any]] = []
        for sp in sim_prompts:
            label = sp.get("label")
            if label and label in by_label:
                ordered.append(by_label[label])
        return ordered
    return list(by_label.values())


def _pool_prep_simsetup_ready(state: Dict[str, Any], wd: str) -> bool:
    """True when simsetup outputs exist on disk or valid coordinates are in state."""
    from agentic.multi_sim_hpc_pool import _sim_setup_ready

    if wd and _sim_setup_ready(wd):
        return True
    coords = state.get("coordinates")
    return bool(coords and _artifact_in_sim_dir(str(coords), wd))


def _resolve_per_sim_goal(
    state: Dict[str, Any],
    sim_info: Dict[str, Any],
    *,
    phase: str,
) -> str:
    """Pick the per-simulation user goal from the master plan when available."""
    if phase == "hpc_pool_prep":
        master = (sim_info.get("prompt") or sim_info.get("setup_prompt") or "").strip()
        if master:
            return (
                "HPC pool — phase 1/3 (preprocess + simsetup only for this simulation). "
                "Full pipeline continues with parallel HPC (phase 2) then per-sim "
                "analysis/reporter (phase 3) and combined analysis.\n\n"
                "Workflow scope for this phase: preprocessing and simulation setup only. "
                "Do not run HPC submission, MD production, analysis, or reporting yet — "
                "the cross-simulation pool handles HPC and post-production work.\n\n"
                f"{master}"
            )
        return _build_per_sim_prep_prompt(
            {
                "protein_name": sim_info.get("protein_name") or sim_info.get("label"),
                "label": sim_info.get("label"),
                "case_description": sim_info.get("case_description", ""),
                "working_dir": sim_info.get("working_dir", ""),
            },
            original_goal=state.get("user_goal_original") or state.get("user_goal", ""),
            enriched_prompt=state.get("master_enriched_prompt")
            or state.get("enriched_prompt", ""),
        )
    # Prefer analysis_prompt for post-simulation runs; it is the dedicated
    # per-simulation goal generated by the master planner.
    master = (sim_info.get("analysis_prompt") or sim_info.get("prompt") or "").strip()
    if master:
        return master
    return sim_info.get("prompt") or ""


def _build_per_sim_analysis_prompt(
    entry: Dict[str, Any],
    *,
    original_goal: str,
    enriched_prompt: str,
    agents_desc: str,
) -> str:
    """Deterministic per-simulation prompt for post-simulation analysis/reporter runs."""
    protein = entry.get("protein_name") or entry.get("label", "system")
    label = entry.get("label", "simulation")
    case = entry.get("case_description", "default system")
    wdir = entry.get("working_dir", "")
    requirements = (original_goal or enriched_prompt or "").strip()

    return (
        f"Perform post-simulation analysis and scientific reporting for {protein} "
        f"(simulation label: {label}; system case: {case}). "
        f"Completed MD outputs are in {wdir}/hpc/ (e.g. md.gro, md.xtc, md.edr). "
        f"Run only these workflow steps: {agents_desc}. "
        f"Apply the following project analysis and reporting requirements to this "
        f"specific system (respecting apo vs holo case where relevant): {requirements}"
    )


def _artifact_in_sim_dir(path: Optional[str], working_dir: Optional[str]) -> bool:
    """True when *path* lives under the active simulation working directory."""
    if not path or not working_dir:
        return False
    p = str(Path(path).resolve())
    wd = str(Path(working_dir).resolve())
    return p == wd or p.startswith(wd + os.sep)


def _get_multi_sim_base_dir(state: Dict[str, Any]) -> str:
    """Return the canonical base directory for multi-simulation orchestration."""
    from agentic.multi_sim_paths import resolve_multi_sim_base_dir

    return resolve_multi_sim_base_dir(state)


def _set_base_conversation_log(state: Dict[str, Any]) -> None:
    """Route conversation logging to {base}/agent_conversation.log."""
    log_path = str(Path(_get_multi_sim_base_dir(state)) / "agent_conversation.log")
    set_log_file(log_path)


def _normalize_multi_sim_paths(state: MDState) -> None:
    """Rewrite sim_prompts paths to sit under the current multi_sim_base_dir."""
    base = Path(_get_multi_sim_base_dir(state))
    state["multi_sim_base_dir"] = str(base)
    sim_prompts = state.get("sim_prompts") or []
    for sp in sim_prompts:
        label = sp.get("label")
        if label:
            sp["working_dir"] = str((base / label).resolve())
        pdb_name = Path(sp.get("pdb") or "").name
        if pdb_name:
            sp["pdb"] = str((base / pdb_name).resolve())
    if sim_prompts:
        state["sim_working_dirs"] = [sp["working_dir"] for sp in sim_prompts]


def _expected_sim_working_dir(state: MDState) -> Optional[str]:
    """Return the working_dir for the active simulation (progress-aware)."""
    from agentic.multi_sim_progress import resolve_active_sim_label

    label = resolve_active_sim_label(state)
    if label:
        progress = state.get("multi_sim_progress") or {}
        rec = (progress.get("sims") or {}).get(label) or {}
        wd = rec.get("working_dir")
        if wd:
            return wd
        sim_prompts = state.get("sim_prompts") or []
        for sp in sim_prompts:
            if sp.get("label") == label:
                return sp.get("working_dir")
    sim_prompts = state.get("sim_prompts") or []
    idx = state.get("current_sim_index", 0)
    if 0 <= idx < len(sim_prompts):
        return sim_prompts[idx].get("working_dir")
    return None


def _build_combined_analysis_plan_fallback(
    state: Dict[str, Any],
    expanded_entries: List[Dict[str, Any]],
) -> str:
    """Fallback combined plan when LLM decomposition is unavailable."""
    original = (state.get("user_goal_original") or state.get("user_goal") or "").strip()
    labels = ", ".join(e.get("label", "") for e in expanded_entries)
    base = (
        "Perform only the combined cross-simulation analysis requested by the user "
        f"across these completed trajectories: {labels}. Compare the requested "
        "metrics across systems, generate aggregate plots or tables only when they "
        "support the stated goal, and avoid adding unrelated calculations. Produce "
        "a consolidated report that explains shared trends, meaningful differences, "
        "and limitations."
    )
    if original:
        return f"{base}\nOriginal study goal for reference:\n{original}"
    return base


# Base-level agent folders — not per-simulation directories.
_BASE_AGENT_SUBDIRS = frozenset({
    "analysis", "reporter", "supervisor", "planner", "preprocess",
    "simsetup", "hpc", "programmer", "combinedAnalysis",
})


def _has_per_sim_analysis_summaries(base_dir: str) -> bool:
    """True when *base_dir* has child sim folders with analysis_summary.jsonl."""
    base = Path(base_dir).resolve()
    if not base.is_dir():
        return False
    for child in base.iterdir():
        if not child.is_dir() or child.name in _BASE_AGENT_SUBDIRS:
            continue
        jsonl = child / "analysis" / "analysis_summary.jsonl"
        if jsonl.is_file() and jsonl.stat().st_size > 0:
            return True
    return False


def _resolve_multi_sim_base_dir(state: Dict[str, Any]) -> str:
    """
    Resolve the project base directory for combined-only discovery.

    Saved checkpoints often leave ``working_directory`` pointing at a per-sim
    folder (e.g. ``.../o15197``). Prefer a base that actually contains multiple
    per-sim ``analysis/analysis_summary.jsonl`` files.
    """
    candidates: List[str] = []
    for key in ("multi_sim_base_dir", "working_directory"):
        val = (state.get(key) or "").strip()
        if not val:
            continue
        resolved = str(Path(val).resolve())
        if resolved not in candidates:
            candidates.append(resolved)

    for path_str in candidates:
        if _has_per_sim_analysis_summaries(path_str):
            return path_str
        per_sim_jsonl = Path(path_str) / "analysis" / "analysis_summary.jsonl"
        if per_sim_jsonl.is_file() and per_sim_jsonl.stat().st_size > 0:
            parent = str(Path(path_str).parent)
            if _has_per_sim_analysis_summaries(parent):
                return parent

    return candidates[0] if candidates else ""


class MDSupervisor:
    """
    LLM-powered supervisor that orchestrates the MD workflow.
    
    Handles input validation, PDB analysis, planning collaboration, and agent routing.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        """
        Initialize supervisor with LLM and configuration.

        Args:
            llm_client: LLMClient instance for LLM operations
            config_path: Path to config.yaml (auto-detected if None)
        """
        if llm_client is None:
            raise ValueError("llm_client is required for supervisor operation")

        self.llm = llm_client
        self.planner = None  # Lazy-load planner on first use

        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.supervisor_config = self.config.get("supervisor", {})
        self.agents_registry = self.config.get("agents", {})
        self.workflow_config = self.config.get("workflow", {})

        logger.info(
            f"MDSupervisor initialized with {len(self.agents_registry)} agents "
            f"from {config_path}"
        )

    def _extract_pdb_filename(self, user_goal: str) -> Optional[str]:
        """Extract PDB filename (.pdb) from user goal."""
        goal_lower = user_goal.lower()
        pdb_match = re.search(r'(\w+\.pdb)', goal_lower)
        if pdb_match:
            filename = pdb_match.group(1)
            logger.info(f"Extracted PDB filename: {filename}")
            return filename
        
        # Try explicit file pattern
        file_match = re.search(r'file\s+(?:is|:)?\s*(\w+\.pdb)', goal_lower)
        if file_match:
            return file_match.group(1)
        return None

    def supervisor_node(self, state: MDState) -> MDState:
        """
        Main supervisor routing logic with unified enrichment and strict agent ordering.

        Pipeline (regular mode):
        1. Input Validation → PDB analysis and feasibility check
        2. Unified Enrichment → SINGLE LLM call to enrich prompt
        3. Create Execution Plan → Collaborate with planner
        4. Execute Agents → Route to field agents in STRICT ORDER
        5. Generate Final Report

        Pipeline (multi-simulation mode):
        1-3. Same (enrichment of overall goal, master plan creates per-sim prompts)
        4. Per-Sim Loop → For each sim: full pipeline in {basepath}/{label}/
        5. Combined Analysis → analysis + reporter at {basepath}/ level
        6. Final Report
        """
        if self.planner is None:
            self.planner = MDPlanner(llm_client=self.llm)

        logger.info("=" * 60)
        logger.info("SUPERVISOR: Analyzing workflow state and routing decision")
        logger.info("=" * 60)

        multi_sim_phase = state.get("multi_sim_phase")

        if state.get("is_multi_simulation"):
            from agentic.multi_sim_hpc_pool import reconcile_post_hpc_with_pool

            if reconcile_post_hpc_with_pool(state):
                multi_sim_phase = state.get("multi_sim_phase")

        # ── Cross-sim HPC pool (prep sequential, SLURM jobs parallel) ───
        if multi_sim_phase == "hpc_pool":
            self._ensure_hpc_pool_prep_context(state)
            if state.get("hpc_pool_prep_only") or state.get("post_hpc_analysis_only"):
                from agentic.multi_sim_progress import ensure_per_sim_working_directory

                ensure_per_sim_working_directory(state)

            if state.get("plan_executed") and (
                state.get("hpc_pool_prep_only") or not state.get("post_hpc_analysis_only")
            ):
                return self._finish_hpc_pool_prep_sim(state)

            if state.get("hpc_pool_prep_only") and not state.get("plan_executed"):
                logger.info(
                    "SUPERVISOR [hpc_pool]: Per-sim prep in progress — continuing pipeline"
                )
            elif not state.get("execution_plan") or state.get("plan_executed"):
                return self._apply_hpc_pool_tick(state)

        if state.pop("_hitl_start_combined", None):
            logger.info("SUPERVISOR [multi-sim]: HITL continue — starting combined analysis")
            return self._setup_combined_analysis(state)

        if state.pop("_hitl_resume_combined_reporter", None):
            logger.info("SUPERVISOR [multi-sim]: Resuming combined reporter")
            state["next_node"] = "reporter"
            return state

        if state.pop("_hitl_start_next_sim", None):
            logger.info("SUPERVISOR [multi-sim]: HITL continue — starting next simulation")
            return self._start_next_sim(state)

        if state.get("is_multi_simulation"):
            if not state.get("multi_sim_base_dir"):
                state["multi_sim_base_dir"] = str(
                    Path(state.get("working_directory", ".")).resolve()
                )
            # Overall orchestration (enrichment, master plan, combined analysis, HPC pool)
            # is logged at the base working directory — except during active per-sim prep.
            if multi_sim_phase in (None, "combined_analysis", "hpc_pool"):
                if (
                    (state.get("hpc_pool_prep_only") or state.get("post_hpc_analysis_only"))
                    and multi_sim_phase not in ("combined_analysis", "combined_reporter")
                ):
                    from agentic.multi_sim_progress import ensure_per_sim_working_directory

                    ensure_per_sim_working_directory(state)
                    wd = _expected_sim_working_dir(state) or state.get("working_directory")
                    if wd:
                        set_log_file(str(Path(wd) / "agent_conversation.log"))
                else:
                    _set_base_conversation_log(state)
            # Resume mid-loop with a mismatched working_directory (e.g. after
            # --working-dir changed or stale checkpoint) — re-bind current sim.
            if (
                multi_sim_phase in ("executing_sims", "hpc_pool")
                and state.get("sim_prompts")
                and not state.get("combined_only")
            ):
                _normalize_multi_sim_paths(state)
                expected_wd = _expected_sim_working_dir(state)
                current_wd = state.get("working_directory")
                if (
                    expected_wd
                    and current_wd
                    and Path(expected_wd).resolve() != Path(current_wd).resolve()
                ):
                    if state.get("execution_plan") and not state.get("plan_executed"):
                        logger.warning(
                            "SUPERVISOR [multi-sim]: working_directory mismatch "
                            f"(current={current_wd}, expected={expected_wd}) — "
                            "restoring active simulation context (HITL chat may have "
                            "temporarily pointed at project base)"
                        )
                        state["working_directory"] = str(Path(expected_wd).resolve())
                        wd = Path(expected_wd)
                        state["analysis_dir"] = str(wd / "analysis")
                        state["reporter_dir"] = str(wd / "reporter")
                        state["hpc_dir"] = str(wd / "hpc")
                        state["hitl_agent_working_directory"] = str(wd.resolve())
                    else:
                        logger.warning(
                            "SUPERVISOR [multi-sim]: working_directory mismatch "
                            f"(current={current_wd}, expected={expected_wd}) — "
                            "reinitializing current simulation context"
                        )
                        return self._start_next_sim(state)

        # ── Combined-only fast path (before any per-sim routing) ─────────
        # Per-simulation analysis/report already lives under {base}/{label}/.
        # Combined outputs belong in {base}/analysis/ and {base}/reporter/.
        # When --combined-only is set, discover sims from per-sim
        # analysis_summary.jsonl files and jump straight to combined mode.
        if state.get("is_multi_simulation") and state.get("combined_only"):
            if multi_sim_phase != "combined_analysis":
                activated = self._activate_combined_only_mode(state)
                if activated is not None:
                    return activated
                multi_sim_phase = state.get("multi_sim_phase")

        # ── Subtask type initialisation (once) ───────────────────────────
        if not state.get("subtask_type_initialized"):
            subtask_type = state.get("subtask_type")
            if subtask_type:
                logger.info(f"SUPERVISOR: Subtask type: {subtask_type}")
                if subtask_type == "multi_agent":
                    logger.info(f"SUPERVISOR: Agent list: {state.get('agent_list', [])}")
            required_inputs = detect_task_required_inputs(subtask_type, state.get("agent_list"))
            state["required_inputs"] = required_inputs
            state["subtask_type_initialized"] = True

        # ── Debug log ─────────────────────────────────────────────────────
        has_plan = bool(state.get("execution_plan"))
        current_agent_idx = state.get("current_agent_idx", 0)
        subtask_type = state.get("subtask_type", "full_task")
        required_agents = get_agent_execution_order(subtask_type, state)
        logger.info(
            f"SUPERVISOR: plan={has_plan}, phase={multi_sim_phase}, "
            f"agent_idx={current_agent_idx}/{len(required_agents)}, "
            f"plan_executed={state.get('plan_executed')}"
        )

        # ── Per-sim or combined workflow complete ─────────────────────────
        # Must check BEFORE step 1 so that plan_executed=True routes correctly.
        if state.get("plan_executed"):
            if multi_sim_phase == "hpc_pool" and not state.get("post_hpc_analysis_only"):
                return self._finish_hpc_pool_prep_sim(state)
            if multi_sim_phase == "executing_sims":
                logger.info("SUPERVISOR [multi-sim]: Per-sim cycle complete — advancing")
                return self._advance_multi_sim(state)
            elif multi_sim_phase == "combined_reporter":
                logger.info("SUPERVISOR [multi-sim]: Combined workflow complete — final report")
                state["next_node"] = "final_report"
                log_supervisor_routing(state, "final_report", "Combined multi-sim workflow complete")
                return state
            else:
                logger.info("SUPERVISOR: All tasks complete — final report")
                state["next_node"] = "final_report"
                log_supervisor_routing(state, "final_report", "All workflow tasks complete")
                return state

        # ── Step 1: Input validation ──────────────────────────────────────
        if (not state.get("input_validated")
                and state.get("user_goal")
                and not state.get("combined_only")):
            logger.info(f"SUPERVISOR: Routing to input validation (subtask={subtask_type})")
            state["next_node"] = "input_validation"
            return state

        # ── Step 2: Prompt enrichment (single call per sim/phase) ─────────
        if state.get("input_validated") and not state.get("enriched_prompt"):
            if state.get("hpc_pool_prep_only"):
                logger.info("SUPERVISOR [hpc_pool]: Using prep-only goal (skip full enrichment)")
                state["enriched_prompt"] = state.get("user_goal", "")
                state["rephrased_goal"] = state["enriched_prompt"]
            else:
                logger.info("SUPERVISOR: Input validated, enriching prompt")
                enriched = enrich_prompt_unified(state, self.llm, self.supervisor_config)
                state["enriched_prompt"] = enriched
                state["rephrased_goal"] = enriched
                # Persist per-sim enriched text so analysis agent can use it after state churn.
                if state.get("is_multi_simulation"):
                    idx = state.get("current_sim_index", 0)
                    sim_prompts = state.get("sim_prompts") or []
                    if 0 <= idx < len(sim_prompts):
                        sim_prompts[idx]["enriched_prompt"] = enriched
                        state["sim_prompts"] = sim_prompts
                # For multi-sim: save master prompt once so it survives per-sim state resets.
                # The combined reporter uses this to show the user's actual goal, not the
                # combined_analysis_plan dump.
                if state.get("is_multi_simulation") and not state.get("master_enriched_prompt"):
                    state["master_enriched_prompt"] = enriched
                logger.info(f"SUPERVISOR: Enrichment complete ({len(enriched)} chars)")

        # ── Step 2.5: Multi-sim master planning (planner owns tools context) ─
        # Build sim_prompts plus an optional combined_analysis_plan right after
        # enrichment.  The supervisor requests the master plan, but the planner
        # decides from user intent and available tools whether combined analysis
        # is part of this run.
        # Regenerate when a prior full-pipeline master plan is reused for analysis-only.
        if (state.get("is_multi_simulation")
                and state.get("sim_prompts")
                and multi_sim_phase is None
                and _is_post_simulation_subtask(state)):
            _scopes = {
                (s or {}).get("task_scope") for s in (state.get("sim_prompts") or [])
            }
            if _scopes and _scopes != {"analysis_reporter"}:
                logger.info(
                    "SUPERVISOR [multi-sim]: Replacing stale full-pipeline sim_prompts "
                    "with post-simulation analysis/reporter prompts"
                )
                state["sim_prompts"] = None
                state["combined_analysis_plan"] = None
                state["run_combined_analysis"] = None

        if (state.get("is_multi_simulation")
                and state.get("enriched_prompt")
                and not state.get("sim_prompts")
                and multi_sim_phase is None
                and not state.get("combined_only")):
            logger.info("SUPERVISOR [multi-sim]: Requesting planner master plan")
            _set_base_conversation_log(state)
            state = self.planner.create_multi_sim_master_plan(state)
            # Fall through to the detection block below which will start the per-sim loop.

        # ── Multi-sim: resume interrupted run from saved progress ─────────
        if (
            state.get("is_multi_simulation")
            and state.get("sim_prompts")
            and state.get("resume_failed_only")
            and multi_sim_phase is None
            and not state.get("combined_only")
        ):
            from agentic.multi_sim_progress import (
                multisim_workflow_incomplete,
                prepare_multisim_resume_state,
            )

            if multisim_workflow_incomplete(state.get("multi_sim_progress")):
                logger.info("SUPERVISOR [multi-sim]: Resuming from saved multi_sim_progress")
                resumed = prepare_multisim_resume_state(state)
                if resumed == "__combined__":
                    return self._setup_combined_analysis(state)
                if resumed == "__combined_reporter__":
                    return state
                return self._start_next_sim(state)

        # ── Multi-sim: master plan present (sim_prompts set, no exec plan) ─
        # Either just built above or restored from a checkpoint — start the
        # per-sim loop when we have sim_prompts but no execution_plan yet.
        if (state.get("is_multi_simulation")
                and state.get("sim_prompts")
                and not state.get("execution_plan")
                and multi_sim_phase is None
                and not state.get("combined_only")):
            logger.info("SUPERVISOR [multi-sim]: Master plan ready — starting workflow")
            from agentic.multi_sim_hpc_pool import (
                should_use_hpc_pool,
                init_hpc_pool,
            )
            from agentic.multi_sim_progress import init_multi_sim_progress

            if should_use_hpc_pool(state):
                logger.info("SUPERVISOR [multi-sim]: Using cross-sim HPC pool")
                state["multi_sim_phase"] = "hpc_pool"
                init_hpc_pool(state)
                return self._apply_hpc_pool_tick(state)

            state["multi_sim_phase"] = "executing_sims"
            if state.get("resume_failed_only"):
                from agentic.multi_sim_progress import (
                    multisim_workflow_incomplete,
                    prepare_multisim_resume_state,
                )

                if multisim_workflow_incomplete(state.get("multi_sim_progress")):
                    prepare_multisim_resume_state(state)
                else:
                    state = self._setup_resume_mode(state)
            else:
                state["current_sim_index"] = 0
                state["completed_sim_states"] = []
            init_multi_sim_progress(state)
            return self._start_next_sim(state)

        # Post-HPC analysis loop after cross-sim pool completes
        if (
            state.get("is_multi_simulation")
            and state.get("sim_prompts")
            and state.get("post_hpc_analysis_only")
            and state.get("hpc_pool_phase_complete")
            and multi_sim_phase == "executing_sims"
        ):
            from agentic.multi_sim_progress import (
                all_post_hpc_artifacts_on_disk,
                bind_workflow_to_sim,
                first_incomplete_post_hpc_sim,
                sync_post_hpc_progress_from_disk,
            )

            sync_post_hpc_progress_from_disk(state)
            sim_prompts = state.get("sim_prompts") or []
            current_idx = state.get("current_sim_index", 0)

            if current_idx >= len(sim_prompts) or all_post_hpc_artifacts_on_disk(state):
                if _should_run_combined_analysis(state):
                    logger.info(
                        "SUPERVISOR [multi-sim]: All per-sim post-HPC work complete "
                        "— starting combined analysis"
                    )
                    return self._setup_combined_analysis(state)

            if (
                not state.get("execution_plan")
                and not state.get("plan_executed")
                and not state.get("input_validated")
            ):
                next_label = first_incomplete_post_hpc_sim(state)
                if next_label:
                    bind_workflow_to_sim(state, next_label)
                logger.info(
                    "SUPERVISOR [multi-sim]: Post-HPC pool — starting analysis/reporter "
                    "at sim %s (index %s)",
                    next_label or "?",
                    state.get("current_sim_index"),
                )
                return self._start_next_sim(state)

        # ── Step 3: Create execution plan ────────────────────────────────
        if not state.get("execution_plan") and state.get("enriched_prompt"):
            logger.info("SUPERVISOR: Routing to planner for execution plan")
            state["next_node"] = "planner"
            return state

        # ── Step 4: Extract agent-specific sub-plans ─────────────────────
        if state.get("execution_plan") and not state.get("preprocessing_instructions"):
            logger.info("SUPERVISOR: Extracting agent-specific plans")
            state = self._extract_agent_specific_plans(state)

        # ── Step 5: Assign field agents ───────────────────────────────────
        if state.get("execution_plan") and not state.get("plan_executed"):
            logger.info("SUPERVISOR: Assigning field agents")
            state = self._assign_field_agent_tasks(state)

            # "_assign_field_agent_tasks" sets next_node="supervisor" when all
            # per-sim (or combined-analysis) agents complete, to signal that the
            # multi-sim loop should advance.  But "supervisor" is not a valid
            # target in _route_from_supervisor — handle the advancement here so
            # the returned state always carries a valid next_node for LangGraph.
            if state.get("plan_executed"):
                if state.get("multi_sim_phase") == "hpc_pool" and not state.get(
                    "post_hpc_analysis_only"
                ):
                    logger.info(
                        "SUPERVISOR [hpc_pool]: Per-sim prep cycle complete — "
                        "returning to pool"
                    )
                    return self._finish_hpc_pool_prep_sim(state)
                if state.get("multi_sim_phase") == "executing_sims":
                    logger.info(
                        "SUPERVISOR [multi-sim]: Per-sim cycle complete — "
                        "advancing multi-sim loop inline"
                    )
                    return self._advance_multi_sim(state)
                # combined_analysis done (multi_sim_phase was just set to
                # "combined_reporter" by _assign_field_agent_tasks), or any
                # other case where next_node was left as "supervisor".
                if state.get("next_node") == "supervisor":
                    logger.info(
                        "SUPERVISOR: plan_executed with next_node=supervisor — "
                        "redirecting to final_report"
                    )
                    state["next_node"] = "final_report"
            return state

        # ── Fallback ──────────────────────────────────────────────────────
        if state.get("errors"):
            logger.error(f"SUPERVISOR: {len(state['errors'])} errors — final report")
        else:
            logger.info("SUPERVISOR: Workflow complete")
        state["next_node"] = "final_report"
        return state

    # ── Multi-Simulation Orchestration ───────────────────────────────────

    # ── Resume / retry helpers ────────────────────────────────────────────

    def _discover_sim_dirs_from_analysis_summaries(
        self,
        base_dir: str,
        allowed_labels: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Locate per-simulation directories by scanning for analysis_summary.jsonl.

        Each child of *base_dir* that contains ``analysis/analysis_summary.jsonl``
        is treated as a completed per-simulation run.  Base-level agent folders
        (``analysis/``, ``reporter/``, etc.) are excluded.

        When *allowed_labels* is set (e.g. from goal PDB list), only matching
        simulation folder names are returned.
        """
        base = Path(base_dir).resolve()
        entries: List[Dict[str, Any]] = []
        allowed = {lbl.lower() for lbl in (allowed_labels or [])}
        if not base.is_dir():
            return entries
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name in _BASE_AGENT_SUBDIRS:
                continue
            if allowed and child.name.lower() not in allowed:
                continue
            analysis_dir = child / "analysis"
            jsonl = analysis_dir / "analysis_summary.jsonl"
            if jsonl.is_file() and jsonl.stat().st_size > 0:
                entries.append({
                    "label": child.name,
                    "working_dir": str(child.resolve()),
                    "analysis_directory": str(analysis_dir.resolve()),
                    "analysis_summary": str(jsonl.resolve()),
                })
        return entries

    def _clear_combined_only_stale_state(self, state: MDState) -> None:
        """Remove restored per-sim / single-sim routing that would hijack combined-only."""
        state["multi_sim_phase"] = None
        state["plan_executed"] = False
        state["execution_plan"] = None
        state["current_agent_idx"] = 0
        state["current_sim_index"] = 0
        state["sim_prompts"] = None
        state["run_combined_analysis"] = None
        state["completed_sim_states"] = None
        state["enriched_prompt"] = None
        state["rephrased_goal"] = None
        state["analysis_results"] = {}
        state["reporter_output"] = None
        state["figures"] = []
        state["conclusions"] = None
        state["raw_pdb"] = None
        state["trajectory_path"] = None
        state["topology"] = None
        state["coordinates"] = None
        state["job_id"] = None
        state["analysis_instructions"] = None
        state["reporter_instructions"] = None
        state["preprocessing_instructions"] = None
        state["input_validated"] = True

    def _activate_combined_only_mode(self, state: MDState) -> Optional[MDState]:
        """Skip per-sim loop; run combined analysis + report from existing outputs."""
        base_dir = _resolve_multi_sim_base_dir(state)
        if not base_dir:
            logger.error("SUPERVISOR [combined_only]: no working_directory set")
            state["errors"].append("combined_only: working_directory is not set")
            state["next_node"] = "final_report"
            return state

        state["multi_sim_base_dir"] = base_dir
        state["working_directory"] = base_dir

        self._clear_combined_only_stale_state(state)

        allowed_labels: Optional[List[str]] = None
        pdb_list = state.get("pdb_list") or []
        if pdb_list:
            allowed_labels = [Path(p).stem for p in pdb_list]

        discovered = self._discover_sim_dirs_from_analysis_summaries(
            base_dir, allowed_labels=allowed_labels
        )
        if not discovered:
            logger.error(
                f"SUPERVISOR [combined_only]: no per-simulation analysis_summary.jsonl "
                f"found under {base_dir}"
            )
            state["errors"].append(
                "combined_only: no per-simulation analysis_summary.jsonl files found. "
                "Run per-simulation analysis first, or check --working-dir."
            )
            state["next_node"] = "final_report"
            return state

        state["multi_sim_base_dir"] = base_dir
        state["sim_prompts"] = [
            {
                "label": entry["label"],
                "working_dir": entry["working_dir"],
                "task_scope": "analysis_reporter",
            }
            for entry in discovered
        ]
        state["completed_sim_states"] = [
            {
                "sim_index": idx,
                "label": entry["label"],
                "working_directory": entry["working_dir"],
                "analysis_directory": entry["analysis_directory"],
                "analysis_summary": entry["analysis_summary"],
                "success": True,
                "skipped": False,
                "_source": "analysis_summary_discovery",
            }
            for idx, entry in enumerate(discovered)
        ]
        state["sim_working_dirs"] = [entry["working_dir"] for entry in discovered]
        state["current_sim_index"] = len(discovered)
        state["combined_only"] = True
        state["run_combined_analysis"] = True

        if not state.get("combined_analysis_plan"):
            state["combined_analysis_plan"] = _build_combined_analysis_plan_fallback(
                state, state["sim_prompts"]
            )

        logger.info(
            f"SUPERVISOR [combined_only]: discovered {len(discovered)} simulation(s) "
            f"with analysis_summary.jsonl — entering combined analysis + report"
        )
        log_supervisor_routing(
            state, "analysis",
            f"combined_only: {len(discovered)} simulations from analysis_summary.jsonl "
            "(per-sim analysis skipped)",
        )
        return self._setup_combined_analysis(state)

    def _rebuild_completed_states_from_disk(self, state: MDState) -> List[Dict]:
        """
        Scan per-simulation supervisor/state.jsonl files and reconstruct a
        completed_sim_states list.  Used when the base state.jsonl is missing
        or contains fewer entries than the planned sim_prompts.
        """
        sim_prompts = state.get("sim_prompts") or []
        base_dir = state.get("multi_sim_base_dir") or state.get("working_directory", "")
        reconstructed: List[Dict] = []

        for idx, sp in enumerate(sim_prompts):
            label = sp.get("label", f"sim_{idx}")
            sim_dir = sp.get("working_dir") or str(Path(base_dir) / label)
            state_file = Path(sim_dir) / "supervisor" / "state.jsonl"

            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    s = data.get("state", {})
                    _success = bool(
                        s.get("job_id")
                        or s.get("trajectory_path")
                        or s.get("topology")
                        or s.get("coordinates")
                        or s.get("analysis_results")
                        or s.get("reporter_output")
                    )
                    snapshot = {
                        "sim_index": idx,
                        "label": label,
                        "case_description": sp.get("case_description"),
                        "working_directory": sim_dir,
                        "success": _success,
                        "skipped": False,
                        "job_id": s.get("job_id"),
                        "job_status": s.get("job_status"),
                        "trajectory_path": s.get("trajectory_path"),
                        "topology": s.get("topology"),
                        "energy_file": s.get("energy_file"),
                        "analysis_directory": s.get("analysis_directory")
                        or s.get("analysis_dir")
                        or str(Path(sim_dir) / "analysis"),
                        "analysis_results": s.get("analysis_results"),
                        "reporter_output": s.get("reporter_output"),
                        "figures": list(s.get("figures") or []),
                        "errors": list(s.get("errors", [])),
                        "_source": "disk_rebuild",
                    }
                    reconstructed.append(snapshot)
                    logger.info(
                        f"[resume] Reconstructed state for '{label}': "
                        f"success={_success}, job_id={s.get('job_id')}"
                    )
                except Exception as exc:
                    logger.warning(f"[resume] Could not read state for '{label}': {exc}")
                    reconstructed.append({
                        "sim_index": idx,
                        "label": label,
                        "working_directory": sim_dir,
                        "success": False,
                        "skipped": False,
                        "errors": [f"State reconstruction failed: {exc}"],
                        "_source": "disk_rebuild_failed",
                    })
            else:
                logger.info(f"[resume] No state file for '{label}' — will re-run")
                reconstructed.append({
                    "sim_index": idx,
                    "label": label,
                    "working_directory": sim_dir,
                    "success": False,
                    "skipped": False,
                    "errors": ["No per-sim state.jsonl found"],
                    "_source": "not_started",
                })

        return reconstructed

    def _setup_resume_mode(self, state: MDState) -> MDState:
        """
        Prepare state for a --resume run:
        1. Rebuild completed_sim_states from disk if missing or incomplete.
        2. Determine which labels are already succeeded (excluding retry_labels).
        3. Set current_sim_index to the first sim that still needs to run.
        4. Log the full skip / re-run plan.
        """
        _normalize_multi_sim_paths(state)
        sim_prompts = state.get("sim_prompts") or []
        retry_labels: set = set(state.get("retry_labels") or [])
        existing = list(state.get("completed_sim_states") or [])

        # Rebuild from disk when saved state is incomplete
        if len(existing) < len(sim_prompts):
            logger.info(
                f"[resume] completed_sim_states has {len(existing)} entries "
                f"but {len(sim_prompts)} sims planned — rebuilding from disk"
            )
            existing = self._rebuild_completed_states_from_disk(state)
            state["completed_sim_states"] = existing

        # Build set of labels confirmed as succeeded (not in retry_labels)
        succeeded_labels: set = set()
        for snap in existing:
            label = snap.get("label")
            if snap.get("success") and not snap.get("skipped") and label not in retry_labels:
                succeeded_labels.add(label)

        # Log the plan
        logger.info("[resume] === Retry plan ===")
        first_to_run = len(sim_prompts)
        for idx, sp in enumerate(sim_prompts):
            label = sp.get("label", f"sim_{idx}")
            if label in succeeded_labels:
                logger.info(f"  SKIP   [{idx}] {label} (already succeeded)")
            else:
                reason = "in --retry-labels" if label in retry_labels else "failed / not completed"
                logger.info(f"  RERUN  [{idx}] {label} ({reason})")
                if first_to_run == len(sim_prompts):
                    first_to_run = idx

        if first_to_run == len(sim_prompts):
            logger.info("[resume] All simulations already succeeded — skipping to combined analysis")

        state["_resume_succeeded_labels"] = list(succeeded_labels)
        state["current_sim_index"] = first_to_run
        return state

    def _mark_post_hpc_agent_done(self, state: MDState, agent: str) -> None:
        """Record per-sim agent completion in multi_sim_progress during post-HPC loop."""
        if not state.get("post_hpc_analysis_only"):
            return
        from agentic.multi_sim_progress import mark_agent_status, workflow_sim_label_for_hitl

        label = workflow_sim_label_for_hitl(state)
        if label:
            mark_agent_status(state, label, agent, "done")

    def _ensure_hpc_pool_prep_context(self, state: MDState) -> None:
        """Limit per-sim work to preprocess + simsetup while in ``hpc_pool`` phase."""
        if state.get("multi_sim_phase") != "hpc_pool" or state.get("post_hpc_analysis_only"):
            return
        state["hpc_pool_prep_only"] = True
        state["hpc_pool_agent_filter"] = ["preprocessing", "simsetup"]
        state["subtask_type"] = "multi_agent"
        state["agent_list"] = ["preprocess", "simsetup"]

    def _clear_stale_cross_sim_artifacts(self, state: MDState) -> None:
        """Drop completion markers from another simulation directory."""
        wd = state.get("working_directory")
        for key in (
            "cleaned_pdb", "coordinates", "topology", "job_id", "job_script",
            "trajectory_path",
        ):
            val = state.get(key)
            if val and not _artifact_in_sim_dir(str(val), wd):
                state[key] = None

        # analysis_results is a dict (tool outputs), not a file path — validate via directory.
        if state.get("analysis_results"):
            analysis_dir = state.get("analysis_directory") or state.get("analysis_dir")
            if analysis_dir and wd and not _artifact_in_sim_dir(analysis_dir, wd):
                state["analysis_results"] = {}
                state["analysis_directory"] = None
                state["analysis_dir"] = None

        # reporter_output is a dict — validate via report file path when present.
        reporter_out = state.get("reporter_output")
        if isinstance(reporter_out, dict):
            report_path = (
                reporter_out.get("html_report")
                or reporter_out.get("report_path")
                or reporter_out.get("output_file")
            )
            if report_path and wd and not _artifact_in_sim_dir(str(report_path), wd):
                state["reporter_output"] = None
        elif reporter_out and wd:
            if not _artifact_in_sim_dir(str(reporter_out), wd):
                state["reporter_output"] = None

    def _finish_hpc_pool_prep_sim(self, state: MDState) -> MDState:
        """Mark prep done for the active sim and return to the cross-sim pool."""
        from agentic.multi_sim_hpc_pool import mark_prep_done, _sim_setup_ready

        sim_label = (state.get("sim_case") or {}).get("label")
        wd = state.get("working_directory")
        if not sim_label:
            idx = state.get("current_sim_index", 0)
            sim_prompts = state.get("sim_prompts") or []
            if sim_prompts and 0 <= idx < len(sim_prompts):
                sim_label = sim_prompts[idx].get("label")
                wd = wd or sim_prompts[idx].get("working_dir")
        if sim_label and wd and not _pool_prep_simsetup_ready(state, wd):
            logger.warning(
                "SUPERVISOR [hpc_pool]: Prep incomplete for %s (simsetup not ready) — "
                "retrying simsetup with existing plan",
                sim_label,
            )
            state["plan_executed"] = False
            pool_agents = state.get("hpc_pool_agent_filter") or ["preprocessing", "simsetup"]
            if "simsetup" in pool_agents:
                state["current_agent_idx"] = pool_agents.index("simsetup")
            elif "preprocessing" in pool_agents:
                state["current_agent_idx"] = pool_agents.index("preprocessing")
            else:
                state["current_agent_idx"] = 0
            self._ensure_hpc_pool_prep_context(state)
            self._clear_stale_cross_sim_artifacts(state)
            state["next_node"] = "supervisor"
            return state
        if sim_label:
            mark_prep_done(state, sim_label)
            logger.info("SUPERVISOR [hpc_pool]: Prep complete for %s", sim_label)
        state["plan_executed"] = False
        state["execution_plan"] = None
        state["current_agent_idx"] = 0
        state.pop("hpc_pool_agent_filter", None)
        state.pop("hpc_pool_prep_only", None)
        base = state.get("multi_sim_base_dir") or state.get("working_directory")
        if base:
            state["working_directory"] = str(Path(base).resolve())
        _set_base_conversation_log(state)
        return self._apply_hpc_pool_tick(state)

    def _apply_hpc_pool_tick(self, state: MDState) -> MDState:
        """
        Run HPC pool tick and resolve internal supervisor hand-offs.

        ``hpc_pool_supervisor_tick`` may set ``next_node='supervisor'`` when the
        next step is prep start or post-HPC analysis. LangGraph cannot route to
        the supervisor node, so those transitions are handled here.
        """
        from agentic.multi_sim_hpc_pool import hpc_pool_supervisor_tick

        state = hpc_pool_supervisor_tick(state)
        while state.get("next_node") == "supervisor":
            prep_label = state.pop("hpc_pool_needs_prep_start", None)
            if prep_label:
                sim_prompts = state.get("sim_prompts") or []
                idx = next(
                    (i for i, sp in enumerate(sim_prompts) if sp.get("label") == prep_label),
                    0,
                )
                state["current_sim_index"] = idx
                state["hpc_pool_prep_only"] = True
                state["hpc_pool_agent_filter"] = ["preprocessing", "simsetup"]
                logger.info("HPC pool: starting prep for %s", prep_label)
                return self._start_next_sim(state)
            if state.pop("hpc_pool_post_hpc_start", None):
                logger.info("HPC pool: all jobs done — starting post-HPC analysis")
                return self._start_next_sim(state)
            logger.error(
                "HPC pool tick returned next_node=supervisor with no hand-off flag"
            )
            state["next_node"] = "hpc_pool_wait"
            break
        return state

    # ── Per-simulation loop ───────────────────────────────────────────────

    def _start_next_sim(self, state: MDState) -> MDState:
        """
        Reset state for the current sim_index and route to input_validation.
        Called when starting (or restarting) a per-sim pipeline.
        """
        if not state.get("multi_sim_base_dir"):
            state["multi_sim_base_dir"] = state.get("working_directory")

        sim_prompts = state.get("sim_prompts", [])
        current_idx = state.get("current_sim_index", 0)

        sim_info = sim_prompts[current_idx]
        sim_label = sim_info.get("label", f"sim_{current_idx}")
        sim_pdb = sim_info.get("pdb", "")
        post_sim_subtask = _is_post_simulation_subtask(state) or state.get("post_hpc_analysis_only")
        sim_working_dir = sim_info.get("working_dir", "")
        sim_goal = (
            sim_info.get("analysis_prompt")
            or sim_info.get("prompt")
            or ""
        )
        goal_source = (
            "master_analysis_prompt"
            if (sim_info.get("analysis_prompt") or "").strip()
            else "master_prompt"
            if (sim_info.get("prompt") or "").strip()
            else "fallback_generated"
        )
        if state.get("hpc_pool_prep_only"):
            sim_goal = _resolve_per_sim_goal(state, sim_info, phase="hpc_pool_prep")
            goal_source = "hpc_pool_resolved"

        # ── Resume mode: skip sims that already succeeded ─────────────────
        if state.get("resume_failed_only"):
            succeeded = set(state.get("_resume_succeeded_labels") or [])
            if sim_label in succeeded:
                logger.info(
                    f"SUPERVISOR [resume]: Skipping already-succeeded sim "
                    f"{current_idx + 1}/{len(sim_prompts)}: {sim_label}"
                )
                current_idx += 1
                state["current_sim_index"] = current_idx
                if current_idx >= len(sim_prompts):
                    if _should_run_combined_analysis(state):
                        return self._setup_combined_analysis(state)
                    return self._finish_multi_sim_pipeline(state)
                return self._start_next_sim(state)

        logger.info(
            f"SUPERVISOR [multi-sim]: Starting sim {current_idx + 1}/"
            f"{len(sim_prompts)}: {sim_label}  pdb={sim_pdb}"
        )

        # Post-sim subtasks need the full per-sim analysis goal, not a metadata stub.
        # Keep the exact per-simulation goal from the master plan whenever it exists.
        # Only synthesize a fallback when the prompt is truly missing/empty.
        if post_sim_subtask and not (sim_goal or "").strip():
            sim_goal = _build_per_sim_analysis_prompt(
                {
                    "protein_name": sim_info.get("protein_name") or sim_label,
                    "label": sim_label,
                    "case_description": sim_info.get("case_description", ""),
                    "working_dir": sim_working_dir,
                },
                original_goal=state.get("user_goal_original") or state.get("user_goal", ""),
                enriched_prompt=state.get("master_enriched_prompt")
                or state.get("enriched_prompt", ""),
                agents_desc=" -> ".join(state.get("agent_list") or ["analysis", "reporter"]),
            )
            goal_source = "fallback_generated"

        try:
            log_agent_action(
                agent_name="supervisor",
                action="Per-Simulation Goal Resolution",
                details={
                    "simulation_label": sim_label,
                    "goal_source": goal_source,
                    "goal_preview": (sim_goal or "")[:600],
                },
            )
        except Exception:
            # Non-critical logging only.
            pass

        # Reset per-sim state, set working_directory to {basepath}/{label}/
        state = self._reset_state_for_new_sim(state, sim_goal, sim_working_dir, sim_pdb)

        if state.get("post_hpc_analysis_only"):
            state.pop("hpc_pool_prep_only", None)
            state.pop("hpc_pool_agent_filter", None)
            state["subtask_type"] = "multi_agent"
            state["agent_list"] = ["analysis", "reporter"]

        if state.get("hpc_pool_prep_only"):
            for key in (
                "job_id", "job_script", "job_status", "trajectory_path", "energy_file",
                "hpc_report", "hpc_output_directory", "analysis_results", "figures",
                "conclusions", "reporter_output", "enriched_prompt", "execution_plan",
                "preprocessing_instructions", "setup_instructions", "hpc_instructions",
                "analysis_instructions", "reporter_instructions",
                "cleaned_pdb", "coordinates", "topology",
            ):
                state[key] = None
            state["hpc_pool_prep_only"] = True
            state["hpc_pool_agent_filter"] = ["preprocessing", "simsetup"]
            state["subtask_type"] = "multi_agent"
            state["agent_list"] = ["preprocess", "simsetup"]
            self._clear_stale_cross_sim_artifacts(state)

        from agentic.multi_sim_hpc_pool import _sim_setup_ready

        if state.get("hpc_pool_prep_only") and sim_working_dir and not _sim_setup_ready(
            sim_working_dir
        ):
            progress = state.get("multi_sim_progress") or {}
            rec = (progress.get("sims") or {}).get(sim_label)
            if rec:
                pool_agents = state.get("hpc_pool_agent_filter") or [
                    "preprocessing",
                    "simsetup",
                ]
                rec.setdefault("agents", {})
                for agent in pool_agents:
                    rec["agents"][agent] = "pending"
                rec["status"] = "pending"
                state["multi_sim_progress"] = progress
            state["plan_executed"] = False
            state["current_agent_idx"] = 0

        from agentic.multi_sim_progress import ensure_multi_sim_progress, sync_state_from_progress

        progress = ensure_multi_sim_progress(state)
        if progress:
            progress["active_sim_label"] = sim_label
            if state.get("hpc_pool_prep_only"):
                progress["phase"] = "hpc_pool"
                state["multi_sim_phase"] = "hpc_pool"
            from agentic.multi_sim_progress import _next_pending_agent

            next_agent = _next_pending_agent(progress, sim_label)
            if state.get("hpc_pool_prep_only") and state.get("hpc_pool_agent_filter"):
                pool_agents = state["hpc_pool_agent_filter"]
                next_agent = next(
                    (a for a in pool_agents if (progress.get("sims") or {})
                     .get(sim_label, {}).get("agents", {}).get(a) != "done"),
                    pool_agents[0] if pool_agents else next_agent,
                )
            progress["active_agent"] = next_agent
            state["multi_sim_progress"] = progress
            sync_state_from_progress(state)
            if state.get("hpc_pool_prep_only"):
                state["multi_sim_phase"] = "hpc_pool"
            from agentic.multi_sim_progress import ensure_per_sim_working_directory

            ensure_per_sim_working_directory(state)

        # Copy PDB into per-sim directory so validator can find it (setup stages only).
        pdb_name = Path(sim_pdb).name if sim_pdb else ""
        resolved_pdb = sim_pdb
        if sim_pdb and not post_sim_subtask:
            dest = Path(sim_working_dir) / pdb_name
            if os.path.isfile(sim_pdb):
                if not dest.exists():
                    Path(sim_working_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sim_pdb, dest)
                    logger.info(f"Copied PDB {sim_pdb} → {dest}")
                resolved_pdb = str(dest)
            else:
                # Try shared copy at multi-sim base directory
                base_dir = state.get("multi_sim_base_dir") or state.get("working_directory")
                base_candidate = Path(base_dir) / pdb_name
                if base_candidate.is_file():
                    Path(sim_working_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(base_candidate, dest)
                    resolved_pdb = str(dest)
                    logger.info(f"Copied shared PDB {base_candidate} → {dest}")

            state["raw_pdb"] = resolved_pdb if os.path.isfile(resolved_pdb) else None
            state["user_goal"] = sim_goal.replace(sim_pdb, pdb_name)
        elif post_sim_subtask:
            # Analysis/reporter-only: trajectory lives in hpc/; keep full analysis goal.
            state["user_goal"] = sim_goal
            if sim_pdb and os.path.isfile(sim_pdb):
                state["raw_pdb"] = sim_pdb
            else:
                state["raw_pdb"] = None
        else:
            state["user_goal"] = sim_goal

        # Per-sim loops must not carry the full pdb_list (triggers master validation).
        state["pdb_list"] = []
        state["all_pdb_analyses"] = []

        # Propagate per-structure download metadata for preprocess agent
        structure_requests = state.get("structure_requests") or {}
        uid_key = Path(sim_pdb).stem.lower() if sim_pdb else ""
        if uid_key in structure_requests:
            state["structure_request"] = structure_requests[uid_key]
        elif state.get("structure_request"):
            pass  # keep master-level request
        elif uid_key:
            state["structure_request"] = {
                "uniprot_id": uid_key.upper(),
                "needs_download": not bool(state.get("raw_pdb")),
                "structure_source": "auto",
            }

        state["sim_case"] = {
            "label": sim_label,
            "case_id": sim_info.get("case_id"),
            "case_description": sim_info.get("case_description"),
            "case_directive": sim_info.get("case_directive"),
        }

        skipped = self._validate_and_maybe_skip_sim_case(state, sim_pdb, sim_goal)
        if skipped:
            return skipped

        state["next_node"] = "input_validation"
        return state

    def _validate_and_maybe_skip_sim_case(
        self,
        state: MDState,
        sim_pdb: str,
        sim_goal: str,
    ) -> Optional[MDState]:
        """
        Skip holo/component-specific simulations when required ligands/ions
        are absent from the source structure (e.g. AlphaFold protein-only PDB).
        """
        # Analysis/reporter-only runs operate on existing trajectories in hpc/,
        # not on the source PDB — never skip based on source structure components.
        if _is_post_simulation_subtask(state):
            return None

        sim_case = state.get("sim_case") or {}
        requirements = parse_sim_case_requirements(
            label=sim_case.get("label", ""),
            case_description=sim_case.get("case_description", ""),
            case_directive=sim_case.get("case_directive", ""),
            user_goal=sim_goal,
        )
        if requirements.get("case_type") in ("default", "protein_only"):
            return None

        source_pdb = sim_pdb
        if source_pdb and not os.path.isfile(source_pdb):
            base_dir = state.get("multi_sim_base_dir") or state.get("working_directory")
            candidate = Path(base_dir) / Path(source_pdb).name
            if candidate.is_file():
                source_pdb = str(candidate)

        if not source_pdb or not os.path.isfile(source_pdb):
            return None

        analysis_result = analyze_pdb.invoke({"pdb_file": source_pdb})
        if not analysis_result.get("success"):
            return None

        validation = validate_sim_case_components(
            analysis_result.get("analysis", {}),
            requirements,
        )
        if validation.get("is_feasible"):
            return None

        label = sim_case.get("label", "simulation")
        for err in validation.get("errors", []):
            msg = f"Skipping {label}: {err}"
            state["errors"].append(msg)
            state["warnings"].append(msg)
            logger.error(msg)

        return self._skip_current_sim(state, reason="; ".join(validation.get("errors", [])))

    def _skip_current_sim(self, state: MDState, reason: str) -> MDState:
        """Record a failed sim snapshot and advance to the next simulation."""
        sim_prompts = state.get("sim_prompts", [])
        current_idx = state.get("current_sim_index", 0)
        sim_label = (state.get("sim_case") or {}).get("label", f"sim_{current_idx}")

        sim_case = state.get("sim_case") or {}
        snapshot = {
            "sim_index": current_idx,
            "label": sim_label,
            "case_description": sim_case.get("case_description"),
            "working_directory": state.get("working_directory"),
            "user_goal": state.get("user_goal"),
            "success": False,
            "skipped": True,
            "skip_reason": reason,
            "errors": list(state.get("errors", [])),
            "warnings": list(state.get("warnings", [])),
        }
        completed = list(state.get("completed_sim_states") or [])
        completed = _upsert_completed_sim_snapshot(completed, snapshot)
        state["completed_sim_states"] = completed

        current_idx += 1
        state["current_sim_index"] = current_idx
        logger.warning(
            "SUPERVISOR [multi-sim]: Skipped sim %s (%s)",
            sim_label,
            reason,
        )

        if state.get("multi_sim_phase") == "hpc_pool" and state.get("hpc_pool_prep_only"):
            pool = state.get("hpc_pool") or {}
            rec = (pool.get("sims") or {}).get(sim_label)
            if rec:
                rec["prep_status"] = "failed"
                rec["error"] = reason
            pool["awaiting_hitl"] = True
            pool["hitl_reason"] = f"Prep failed for {sim_label}: {reason}"
            state["hpc_pool"] = pool
            state.pop("hpc_pool_prep_only", None)
            state["plan_executed"] = False
            state["execution_plan"] = None
            state["current_agent_idx"] = 0
            state.pop("hpc_pool_agent_filter", None)
            base = state.get("multi_sim_base_dir") or state.get("working_directory")
            if base:
                state["working_directory"] = str(Path(base).resolve())
            _set_base_conversation_log(state)
            return self._apply_hpc_pool_tick(state)

        if current_idx >= len(sim_prompts):
            if _should_run_combined_analysis(state):
                return self._setup_combined_analysis(state)
            return self._finish_multi_sim_pipeline(state)
        return self._start_next_sim(state)

    def _advance_multi_sim(self, state: MDState) -> MDState:
        """
        Save current sim state, increment index, start next sim or combined analysis.
        Called when plan_executed=True in executing_sims phase.
        """
        sim_prompts = state.get("sim_prompts", [])
        current_idx = state.get("current_sim_index", 0)

        # Save snapshot of completed sim
        self._save_sim_state(state, current_idx)

        from agentic.multi_sim_progress import ensure_multi_sim_progress, mark_agent_status

        progress = ensure_multi_sim_progress(state)
        if progress and sim_prompts:
            finished_label = sim_prompts[current_idx].get("label", f"sim_{current_idx}")
            for agent in progress.get("required_agents") or []:
                mark_agent_status(state, finished_label, agent, "done")
            rec = (progress.get("sims") or {}).get(finished_label)
            if rec:
                rec["status"] = "done"

        current_idx += 1
        state["current_sim_index"] = current_idx

        logger.info(
            f"SUPERVISOR [multi-sim]: Sim {current_idx}/{len(sim_prompts)} saved"
        )

        if current_idx >= len(sim_prompts):
            if _should_run_combined_analysis(state):
                logger.info(
                    "SUPERVISOR [multi-sim]: All sims complete — combined analysis"
                )
                return self._setup_combined_analysis(state)
            return self._finish_multi_sim_pipeline(state)

        # Start next sim
        return self._start_next_sim(state)

    def _finish_multi_sim_pipeline(self, state: MDState) -> MDState:
        """End multi-sim after per-simulation agents without combined analysis."""
        logger.info(
            "SUPERVISOR [multi-sim]: All per-simulation agents complete — "
            "skipping combined analysis (not in --subtask)"
        )
        state["plan_executed"] = True
        state["multi_sim_phase"] = "complete"
        state["next_node"] = "final_report"
        log_supervisor_routing(
            state,
            "final_report",
            "Multi-sim pipeline complete (preprocess/setup/hpc only)",
        )
        return state

    def _setup_combined_analysis(self, state: MDState) -> MDState:
        """
        Prepare state for combined analysis at basepath level.

        After this, the regular supervisor flow handles everything:
          enrichment is skipped (enriched_prompt is set)
          planner creates a combined execution plan
          analysis and reporter agents run in {basepath}/
        """
        basepath = _get_multi_sim_base_dir(state)
        state["multi_sim_base_dir"] = basepath

        # Idempotent: combined analysis already finished — go to reporter.
        if (
            state.get("multi_sim_phase") == "combined_analysis"
            and state.get("analysis_results")
        ):
            logger.info(
                "SUPERVISOR [multi-sim]: Combined analysis already complete — "
                "routing to combined reporter"
            )
            state["multi_sim_phase"] = "combined_reporter"
            state["working_directory"] = basepath
            state["post_hpc_analysis_only"] = False
            state["current_agent_idx"] = 1
            state["plan_executed"] = False
            state["subtask_type"] = "analysis_only"
            state["agent_list"] = ["analysis", "reporter"]
            state["reporter_dir"] = str(Path(basepath) / "reporter")
            state["analysis_dir"] = str(Path(basepath) / "analysis")
            state["analysis_directory"] = str(Path(basepath) / "analysis")
            _set_base_conversation_log(state)
            state["next_node"] = "reporter"
            log_supervisor_routing(
                state, "reporter", "Combined analysis done — starting combined report"
            )
            return state

        completed = state.get("completed_sim_states", [])
        sim_prompts = state.get("sim_prompts") or []
        from agentic.multi_sim_progress import sync_post_hpc_progress_from_disk

        sync_post_hpc_progress_from_disk(state)
        completed = _dedupe_completed_sim_states(completed, sim_prompts)
        if len(completed) < len(sim_prompts):
            logger.info(
                "SUPERVISOR [multi-sim]: completed_sim_states has %s/%s entries — "
                "rebuilding from per-sim state on disk",
                len(completed),
                len(sim_prompts),
            )
            completed = self._rebuild_completed_states_from_disk(state)
            completed = _dedupe_completed_sim_states(completed, sim_prompts)
            state["completed_sim_states"] = completed

        logger.info(f"SUPERVISOR [multi-sim]: Combined analysis at basepath={basepath}")

        _set_base_conversation_log(state)

        # Build combined instructions
        sim_data_summary = self._build_sim_data_summary(completed)
        combined_plan = state.get("combined_analysis_plan", "")
        original_goal = (state.get("user_goal_original") or "").strip()
        combined_instructions = ""
        if original_goal:
            combined_instructions += (
                f"## Original Study Goal\n\n{original_goal}\n\n"
            )
        combined_instructions += (
            f"## Combined Multi-Simulation Analysis\n\n"
            f"{combined_plan}\n\n"
            f"## Simulation Data\n\n{sim_data_summary}\n\n"
            f"Save all combined plots and reports to the analysis and reporter "
            f"directories under: {basepath}"
        )

        # Preserve multi-sim bookkeeping + config
        preserved_keys = {
            "is_multi_simulation", "sim_prompts", "run_combined_analysis", "combined_analysis_plan",
            "sim_working_dirs", "pdb_list", "completed_sim_states",
            "multi_sim_base_dir", "combined_only",
            "md_engine", "force_field", "water_model", "human_in_loop",
            "subtask_type", "subtask_type_initialized", "agent_list",
            "required_inputs",
            "pipeline_subtask_type",
            "hpc_pool", "hpc_pool_phase_complete",
            # Master prompt — preserved so combined reporter shows supervisor's rephrased goal
            "master_enriched_prompt",
            # Original --goal text — shown verbatim in the combined report
            "user_goal_original",
        }
        if not state.get("pipeline_subtask_type"):
            if state.get("hpc_pool"):
                state["pipeline_subtask_type"] = "full_task"
            elif state.get("subtask_type") and state.get("subtask_type") != "analysis_only":
                state["pipeline_subtask_type"] = state["subtask_type"]
        preserved = {k: state[k] for k in preserved_keys if k in state}

        # Reset per-sim artifacts
        for key in [
            "raw_pdb", "cleaned_pdb", "preprocessing_report", "pdb_analysis",
            "pdb_summary", "component_selection", "system_info",
            "ligand_files", "ligand_resnames", "ion_files", "ion_resnames",
            "topology", "coordinates", "mdp_files", "setup_report",
            "hpc_action", "hpc_output_directory", "job_script", "job_id",
            "job_status", "trajectory_path", "energy_file", "hpc_report",
            "analysis_action", "analysis_request", "analysis_results",
            "figures", "conclusions", "analysis_directory",
            "reporter_output", "reporter_plan", "reporter_instructions",
            "reporter_file_info", "execution_plan", "plan_executed",
            "preprocessing_instructions", "setup_instructions",
            "hpc_instructions", "analysis_instructions",
            "final_report", "workflow_status",
            "file_registry", "generated_files",
            "human_feedback", "human_recommendation", "error_triggered_hitl",
        ]:
            if key in ("mdp_files", "file_registry", "generated_files", "component_selection"):
                state[key] = {}
            elif key in ("figures",):
                state[key] = []
            elif key == "plan_executed":
                state[key] = False
            elif key == "error_triggered_hitl":
                state[key] = False
            elif key == "analysis_action":
                state[key] = "full_analysis"
            else:
                state[key] = None

        state.update(preserved)
        state["completed_sim_states"] = completed
        state["post_hpc_analysis_only"] = False

        # Set up combined analysis context
        state["multi_sim_phase"] = "combined_analysis"
        state["current_sim_index"] = len(state.get("sim_prompts", []))  # mark sims done
        state["working_directory"] = basepath
        state["user_goal"] = combined_instructions
        state["enriched_prompt"] = combined_instructions  # skip enrichment
        state["rephrased_goal"] = combined_instructions
        state["input_validated"] = True
        state["analysis_instructions"] = combined_instructions
        state["current_agent_idx"] = 0
        state["preprocess_retry_count"] = 0
        state["setup_retry_count"] = 0
        state["hpc_retry_count"] = 0
        state["analysis_retry_count"] = 0
        state["reporter_retry_count"] = 0
        state["errors"] = []
        state["warnings"] = []
        state["execution_path"] = []
        state["preprocessing_issues"] = []
        state["setup_issues"] = []

        # Ensure basepath agent dirs exist
        for sub in ("analysis", "reporter", "supervisor", "planner"):
            Path(basepath, sub).mkdir(parents=True, exist_ok=True)

        # State update preserves dir fields for combined (SecureFileManager will
        # create them at basepath level when agents run)
        state["analysis_dir"] = str(Path(basepath) / "analysis")
        state["analysis_directory"] = str(Path(basepath) / "analysis")
        state["reporter_dir"] = str(Path(basepath) / "reporter")
        state["preprocess_dir"] = str(Path(basepath) / "preprocess")
        state["simsetup_dir"] = str(Path(basepath) / "simsetup")
        state["hpc_dir"] = str(Path(basepath) / "hpc")

        # Override subtask type so only analysis + reporter agents run
        state["subtask_type"] = "analysis_only"
        state["subtask_type_initialized"] = True

        # Inject a minimal execution plan stub — bypasses the LLM planner
        # entirely.  Analysis and reporter agents detect combined_analysis mode
        # and run their deterministic combined-mode paths directly.
        state["execution_plan"] = {
            "format": "combined_analysis",
            "title": "Combined Multi-Simulation Analysis",
            "full_plan": combined_instructions,
            "agent_plans": {},
            "agent_sequence": ["analysis", "reporter"],
        }
        state["preprocessing_instructions"] = "N/A"  # skip step-4 extraction

        # Route directly to analysis — no extra supervisor round-trip needed
        state["next_node"] = "analysis"
        log_supervisor_routing(
            state, "analysis",
            f"Multi-sim combined analysis: starting for {len(completed)} sims at {basepath}"
        )
        return state

    def _handle_multi_sim_phase(self, state: MDState) -> MDState:
        """Legacy shim — delegates to the appropriate method."""
        phase = state.get("multi_sim_phase")
        if phase == "executing_sims":
            return self._start_next_sim(state)
        elif phase == "combined_analysis":
            logger.warning(
                "SUPERVISOR [multi-sim]: _handle_multi_sim_phase(combined_analysis) "
                "— delegating to normal supervisor routing"
            )
            state["next_node"] = "supervisor"
            return state
        else:
            logger.error(f"SUPERVISOR [multi-sim]: Unknown phase '{phase}'")
            state["next_node"] = "final_report"
            return state

    def _reset_state_for_new_sim(
        self, state: MDState, new_goal: str, new_working_dir: str, raw_pdb: str
    ) -> MDState:
        """
        Reset per-simulation fields while keeping multi-sim bookkeeping.

        Preserved: is_multi_simulation, multi_sim_phase, sim_prompts,
                   run_combined_analysis, combined_analysis_plan, current_sim_index,
                   completed_sim_states, sim_working_dirs, pdb_list,
                   md_engine, force_field, water_model, human_in_loop,
                   subtask_type, subtask_type_initialized, agent_list,
                   required_inputs
        """
        # Fields to keep across simulations
        preserved_keys = {
            # Multi-sim bookkeeping
            "is_multi_simulation", "multi_sim_phase", "sim_prompts",
            "run_combined_analysis", "combined_analysis_plan", "current_sim_index",
            "completed_sim_states", "sim_working_dirs",
            "multi_sim_base_dir", "multi_sim_progress",
            "structure_requests",
            # NOTE: pdb_list and all_pdb_analyses are NOT preserved - each per-sim
            # iteration should only see its own PDB via raw_pdb, not the full list.
            # This prevents input validation from treating per-sim as multi-sim.
            # Global config
            "md_engine", "force_field", "water_model", "human_in_loop",
            "subtask_type", "subtask_type_initialized", "agent_list",
            "required_inputs",
            # Master prompt — preserved so combined reporter shows supervisor's rephrased goal
            "master_enriched_prompt",
            # Original --goal text — shown verbatim in the combined report
            "user_goal_original",
            # HPC pool prep context (must survive per-sim reset)
            "hpc_pool_prep_only", "hpc_pool_agent_filter", "hpc_pool",
            "allowed_hpc_jobs", "hpc_check_interval_sec", "hpc_check_interval",
            "max_concurrent", "production_ns",
        }

        # Save values to preserve
        preserved = {k: state[k] for k in preserved_keys if k in state}

        # Reset all per-sim fields to their defaults
        state["user_goal"] = new_goal
        state["raw_pdb"] = raw_pdb if os.path.isfile(raw_pdb) else None
        state["working_directory"] = str(Path(new_working_dir).resolve())

        # Create per-sim agent directories
        wd = Path(state["working_directory"])
        wd.mkdir(parents=True, exist_ok=True)
        for subdir in ("preprocess", "simsetup", "hpc", "analysis",
                        "reporter", "supervisor", "planner", "programmer"):
            (wd / subdir).mkdir(parents=True, exist_ok=True)
        state["preprocess_dir"] = str(wd / "preprocess")
        state["simsetup_dir"] = str(wd / "simsetup")
        state["hpc_dir"] = str(wd / "hpc")
        state["analysis_dir"] = str(wd / "analysis")

        # Clear all per-sim artifacts
        per_sim_clear = [
            "enriched_prompt", "rephrased_goal", "structured_prompt",
            "input_validated", "pdb_analysis", "pdb_summary",
            "all_pdb_analyses",  # Clear multi-sim master planning data
            "component_selection", "system_info",
            "cleaned_pdb", "preprocessing_report",
            "ligand_files", "ligand_resnames", "ion_files", "ion_resnames",
            "topology", "coordinates", "mdp_files", "setup_report",
            "hpc_action", "hpc_output_directory", "job_script", "job_id",
            "job_status", "trajectory_path", "energy_file", "hpc_report",
            "analysis_action", "analysis_request", "analysis_results",
            "figures", "conclusions", "analysis_directory",
            "reporter_output", "reporter_plan", "reporter_instructions",
            "reporter_file_info",
            "execution_plan", "plan_executed",
            "preprocessing_instructions", "setup_instructions",
            "hpc_instructions", "analysis_instructions",
            "final_report", "workflow_status",
            "file_registry", "generated_files", "file_info",
            "human_feedback", "human_recommendation", "error_triggered_hitl",
            "sim_case",
        ]
        for key in per_sim_clear:
            if key in ("mdp_files",):
                state[key] = {}
            elif key in ("figures", "preprocessing_issues", "setup_issues"):
                state[key] = []
            elif key in ("file_registry", "generated_files", "component_selection"):
                state[key] = {}
            elif key in ("plan_executed",):
                state[key] = False
            elif key in ("error_triggered_hitl",):
                state[key] = False
            else:
                state[key] = None

        # Reset retry counters & agent index
        state["current_agent_idx"] = 0
        state["preprocess_retry_count"] = 0
        state["setup_retry_count"] = 0
        state["hpc_retry_count"] = 0
        state["analysis_retry_count"] = 0
        state["reporter_retry_count"] = 0
        state["execution_path"] = []
        state["errors"] = []
        state["warnings"] = []
        state["preprocessing_issues"] = []
        state["setup_issues"] = []
        state["next_node"] = None

        # Restore preserved multi-sim and global fields
        state.update(preserved)

        logger.info(
            f"SUPERVISOR [multi-sim]: State reset for new simulation "
            f"(working_dir={state['working_directory']})"
        )

        # Redirect conversation log into the per-sim directory
        sim_log = str(Path(state["working_directory"]) / "agent_conversation.log")
        set_log_file(sim_log)
        logger.info(f"SUPERVISOR [multi-sim]: Log file switched to {sim_log}")

        return state

    def _save_sim_state(self, state: MDState, sim_index: int):
        """Save a snapshot of the current per-sim state before resetting."""
        completed = state.get("completed_sim_states") or []

        # Collect the important per-sim outputs
        _errors = list(state.get("errors", []))
        # A simulation is considered successful when at least one key workflow
        # artifact was produced.  Non-fatal errors (e.g. validation warnings
        # that were recovered) do NOT mark a sim as failed.
        _success = bool(
            state.get("job_id")
            or state.get("trajectory_path")
            or state.get("topology")
            or state.get("coordinates")
            or state.get("analysis_results")
            or state.get("reporter_output")
        )
        sim_case = state.get("sim_case") or {}
        snapshot = {
            "sim_index": sim_index,
            "label": (state.get("sim_prompts") or [{}])[sim_index].get("label", f"sim_{sim_index}"),
            "case_description": sim_case.get("case_description"),
            "working_directory": state.get("working_directory"),
            "user_goal": state.get("user_goal"),
            "success": _success,
            "skipped": False,
            "job_id": state.get("job_id"),
            "job_script": state.get("job_script"),
            "job_status": state.get("job_status"),
            "analysis_results": state.get("analysis_results", {}),
            "analysis_directory": state.get("analysis_directory") or state.get("analysis_dir"),
            "trajectory_path": state.get("trajectory_path"),
            "topology": state.get("topology"),
            "coordinates": state.get("coordinates"),
            "energy_file": state.get("energy_file"),
            "reporter_output": state.get("reporter_output"),
            "figures": list(state.get("figures", [])),
            "errors": _errors,
            "warnings": list(state.get("warnings", [])),
            "file_registry": dict(state.get("file_registry", {})),
        }

        completed = _upsert_completed_sim_snapshot(completed, snapshot)
        state["completed_sim_states"] = completed

        # Also persist state.jsonl in per-sim supervisor/ directory
        try:
            sup_dir = Path(state["working_directory"]) / "supervisor"
            sup_dir.mkdir(parents=True, exist_ok=True)
            state_path = sup_dir / "state.jsonl"
            serializable = {}
            for k, v in state.items():
                try:
                    json.dumps(v, default=str)
                    serializable[k] = v
                except (TypeError, ValueError):
                    serializable[k] = str(v)
            state_path.write_text(
                json.dumps({"sim_index": sim_index, "state": serializable}, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            logger.info(f"Saved per-sim state to {state_path}")
        except Exception as e:
            logger.warning(f"Failed to save per-sim state: {e}")

    # Old combined methods removed — _setup_combined_analysis handles both analysis + reporter

    # ──────────────────────────────────────────────────────────────────────
    # Multi-simulation master planning (moved from planner — no tools context)
    # ──────────────────────────────────────────────────────────────────────

    def _detect_component_cases(self, prompt: str) -> List[Dict[str, str]]:
        """Infer component-specific simulation cases from user goal text."""
        p = (prompt or "").lower()
        # Normalize common unicode variants from LLM responses.
        p = (
            p.replace("\u2011", "-")
            .replace("\u2012", "-")
            .replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("\u2212", "-")
        )

        has_protein_only = bool(re.search(r"\bprotein[\s\-]*(only|alone)\b", p))
        has_atp = "atp" in p
        has_holo = "holo" in p
        has_mg = bool(re.search(r"\bmg(?:2\+?|\u00b2\+?)?\b", p))
        has_case_language = bool(
            re.search(
                r"two\s+different\s+cases?|two\s+systems\s+per\s+file|"
                r"case\s*[:\-]|\bcase\s*1\b|\bcase\s*2\b|"
                r"\(\s*1\s*\)|\(\s*2\s*\)|\b1\.\b|\b2\.\b",
                p,
            )
        )

        # Common request pattern: same PDB run in multiple component conditions.
        if has_case_language and has_protein_only and (has_atp or has_holo):
            full_suffix = "ATP_MG" if has_mg else "ATP"
            full_desc = "protein + ATP + MG" if has_mg else "protein + ATP"
            full_directive = (
                "Keep protein with ATP ligand and Mg ions from the source PDB."
                if has_mg else
                "Keep protein with ATP ligand from the source PDB."
            )
            return [
                {
                    "case_id": "protein_only",
                    "suffix": "",
                    "description": "protein only",
                    "directive": "Use protein-only system. Remove ATP, ligands, and non-essential ions.",
                },
                {
                    "case_id": "protein_with_ligand",
                    "suffix": full_suffix,
                    "description": full_desc,
                    "directive": full_directive,
                },
            ]

        # Default behavior: one simulation per PDB using full detected system.
        return [
            {
                "case_id": "default",
                "suffix": "",
                "description": "default system from input PDB",
                "directive": "Use the full biologically relevant system present in the input PDB.",
            }
        ]

    def _create_multi_sim_master_plan(self, state: MDState) -> MDState:
        """Deprecated compatibility wrapper; planner owns multi-sim master plans."""
        logger.warning(
            "SUPERVISOR [multi-sim]: _create_multi_sim_master_plan is deprecated; "
            "delegating to planner"
        )
        if self.planner is None:
            self.planner = MDPlanner(llm_client=self.llm)
        return self.planner.create_multi_sim_master_plan(state)

        import re as _re_nm
        from pathlib import Path as _Path

        enriched_prompt = state.get("enriched_prompt") or state.get("user_goal", "")
        original_goal = (
            state.get("user_goal_original")
            or state.get("user_goal")
            or enriched_prompt
        )
        from src.utils.pdb_paths import unique_pdb_paths

        pdb_list = unique_pdb_paths(state.get("pdb_list") or [])
        state["pdb_list"] = pdb_list
        base_working_dir = state.get("working_directory", "working_dir")
        agent_list = state.get("agent_list") or []
        post_sim_subtask = _is_post_simulation_subtask(state)

        if not pdb_list:
            logger.warning("SUPERVISOR [multi-sim]: No pdb_list - cannot create master plan")
            return state

        # Parse protein ID -> human-readable name mappings from goal text.
        _protein_name_map: Dict[str, str] = {}
        for _m in _re_nm.finditer(
            r'\b([A-Za-z0-9]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})',
            enriched_prompt,
        ):
            _k, _v = _m.group(1).lower(), _m.group(2).strip()
            if any(c.isdigit() for c in _k) and _v[0].isupper():
                _protein_name_map[_k] = _v
        if _protein_name_map:
            logger.info(f"SUPERVISOR [multi-sim]: Protein name map: {_protein_name_map}")

        # Expand each PDB into one or more component-specific simulation cases.
        component_cases = self._detect_component_cases(enriched_prompt)
        expanded_entries: List[Dict[str, Any]] = []
        for pdb in pdb_list:
            uid = _Path(pdb).stem
            uid_l = uid.lower()
            prot_name = _protein_name_map.get(uid_l, uid.upper())
            for case in component_cases:
                suffix = case.get("suffix", "")
                sim_label = f"{uid}_{suffix}" if suffix else uid
                sim_dir = str((_Path(base_working_dir) / sim_label).resolve())
                expanded_entries.append(
                    {
                        "pdb": pdb,
                        "uid": uid,
                        "protein_name": prot_name,
                        "label": sim_label,
                        "working_dir": sim_dir,
                        "case_description": case.get("description", "default system"),
                        "case_directive": case.get("directive", "Use full system from PDB."),
                    }
                )

        state["sim_working_dirs"] = [e["working_dir"] for e in expanded_entries]

        # Build simulation context lines.
        all_pdb_analyses = state.get("all_pdb_analyses") or []
        pdb_analysis_map: Dict[str, Dict[str, Any]] = {}
        for idx, pdb in enumerate(pdb_list):
            if idx < len(all_pdb_analyses):
                pdb_analysis_map[_Path(pdb).name] = all_pdb_analyses[idx]

        sim_context_lines: List[str] = []
        for i, e in enumerate(expanded_entries, 1):
            pdb_name = _Path(e["pdb"]).name
            line = (
                f"  {i}. label={e['label']} | source={pdb_name} | "
                f"case={e['case_description']} | dir={e['working_dir']}"
            )
            analysis = pdb_analysis_map.get(pdb_name)
            if analysis:
                n_atoms = analysis.get("total_atoms", 0)
                comps = analysis.get("components_available", {})
                comp_desc = []
                if comps.get("protein"):
                    comp_desc.append("protein")
                if comps.get("ligand"):
                    ligands = analysis.get("ligand", {}).get("residue_names", [])
                    comp_desc.append(f"ligand({','.join(ligands[:2])})" if ligands else "ligand")
                if comps.get("ions"):
                    comp_desc.append("ions")
                if n_atoms:
                    line += f" | source_components={','.join(comp_desc)} | atoms={n_atoms}"
            sim_context_lines.append(line)

        agents_desc = (
            " -> ".join(agent_list) if agent_list
            else (state.get("subtask_type") or "full pipeline")
        )

        name_map_lines = ""
        if _protein_name_map:
            name_map_lines = (
                "PROTEIN MAPPINGS:\n"
                + "\n".join(f"  {uid}: {name}" for uid, name in _protein_name_map.items())
                + "\n\n"
            )

        if post_sim_subtask:
            decomposition_prompt = (
                "You are an expert MD trajectory analysis planner. "
                "All simulations are ALREADY COMPLETE — trajectories exist under each "
                "entry's working_dir/hpc/ folder.\n\n"
                f"OVERALL PROJECT (full user analysis goals):\n{original_goal}\n\n"
                f"ENRICHED CONTEXT:\n{enriched_prompt}\n\n"
                f"COMPLETED SIMULATION ENTRIES ({len(expanded_entries)} total):\n"
                + "\n".join(sim_context_lines)
                + "\n\n"
                + name_map_lines
                + f"WORKFLOW PIPELINE (ONLY these steps): {agents_desc}\n\n"
                "TASK: Return JSON with keys:\n"
                f"1) sim_prompts: list of {len(expanded_entries)} prompts, same order as entries.\n"
                "2) combined_analysis_plan: cross-simulation comparative analysis + reporting plan.\n\n"
                "CRITICAL prompt requirements for sim_prompts:\n"
                "- Each prompt must be a complete natural-language ANALYSIS + REPORTING goal "
                "(typically 4–10 sentences), NOT a one-line metadata string.\n"
                "- Do NOT mention preprocessing, system setup, force-field choice, box size, "
                "HPC submission, or simulation length — those stages are finished.\n"
                "- Do NOT use comma-separated key=value format like "
                "'label: source=..., case=..., dir=...'.\n"
                "- Include ALL analysis metrics from OVERALL PROJECT that apply to that system "
                "(RMSD, RMSF, Rg, COM distance, DCCM, DSSP, literature, etc.).\n"
                "- State protein name, simulation label, apo/holo case, and that data is in "
                "working_dir/hpc/.\n"
                f"- Mention only these workflow steps: {agents_desc}.\n\n"
                "Return only valid JSON."
            )
        else:
            decomposition_prompt = (
                "You are an expert MD simulation planner creating natural, varied per-simulation goals.\n\n"
                f"OVERALL PROJECT:\n{enriched_prompt}\n\n"
                f"SIMULATION ENTRIES ({len(expanded_entries)} total):\n"
                + "\n".join(sim_context_lines)
                + "\n\n"
                + name_map_lines
                + f"WORKFLOW PIPELINE: {agents_desc}\n\n"
                "TASK: Return JSON with keys:\n"
                f"1) sim_prompts: list of {len(expanded_entries)} prompts, same order as entries.\n"
                "2) combined_analysis_plan: comparative analysis plan across all entries.\n\n"
                "Prompt requirements:\n"
                "- Mention source PDB and target label directory context.\n"
                "- Enforce the case objective (for example protein only vs protein+ATP+MG).\n"
                "- Keep each prompt concise and not repetitive.\n"
                f"- Mention only these workflow steps: {agents_desc}.\n\n"
                "Return only valid JSON."
            )

        sim_prompts_list = None
        combined_plan = None
        try:
            response = self.llm.prompt(decomposition_prompt, temperature=0.4, max_tokens=3200)
            from ..utils import log_llm_interaction
            log_llm_interaction("supervisor.multi_sim_master", decomposition_prompt, response)
            parsed = self._extract_json_from_response(response)
            if parsed and "sim_prompts" in parsed:
                sim_prompts_list = [
                    _coerce_plan_text(item, default="")
                    for item in parsed["sim_prompts"]
                ]
                combined_plan = _coerce_plan_text(
                    parsed.get("combined_analysis_plan", ""),
                    default="",
                )
                logger.info(
                    f"SUPERVISOR [multi-sim]: LLM generated {len(sim_prompts_list)} per-sim prompts"
                )

                # Detect truly duplicated outputs only.
                if len(sim_prompts_list) > 1:
                    _keys = [
                        re.sub(r"\s+", " ", (_coerce_plan_text(_txt) or "").strip().lower())
                        for _txt in sim_prompts_list
                    ]
                    if len(set(_keys)) == 1:
                        logger.warning(
                            "SUPERVISOR [multi-sim]: LLM sim_prompts are identical; "
                            "switching to deterministic per-entry prompts"
                        )
                        sim_prompts_list = None
        except Exception as e:
            logger.warning(f"SUPERVISOR [multi-sim]: LLM decomposition failed: {e}")

        # Fallback: deterministic prompts per expanded entry.
        if not sim_prompts_list or len(sim_prompts_list) != len(expanded_entries):
            logger.info(
                "SUPERVISOR [multi-sim]: Using deterministic prompt decomposition "
                f"(post_sim_subtask={post_sim_subtask})"
            )
            sim_prompts_list = []
            if post_sim_subtask:
                for e in expanded_entries:
                    sim_prompts_list.append(
                        _build_per_sim_analysis_prompt(
                            e,
                            original_goal=original_goal,
                            enriched_prompt=enriched_prompt,
                            agents_desc=agents_desc,
                        )
                    )
                combined_plan = _build_combined_analysis_plan_fallback(
                    state, expanded_entries
                )
            else:
                _styles = ["Prepare", "Process", "Set up", "Generate setup for"]
                for i, e in enumerate(expanded_entries):
                    pdb_name = _Path(e["pdb"]).name
                    name = e["protein_name"]
                    lead = _styles[i % len(_styles)]
                    uniprot_hint = ""
                    structure_requests = state.get("structure_requests") or {}
                    uid_key = _Path(e["pdb"]).stem.lower()
                    req = structure_requests.get(uid_key)
                    if req and req.get("uniprot_id"):
                        src = req.get("structure_source", "auto")
                        uniprot_hint = (
                            f" Download structure from {src} for UniProt "
                            f"{req['uniprot_id']} if {pdb_name} is not present."
                        )
                    sim_prompts_list.append(
                        (
                            f"{lead} simulation for {name} using source structure {pdb_name}. "
                            f"Simulation label is {e['label']} under {e['working_dir']}. "
                            f"Case requirement: {e['case_description']}. {e['case_directive']}"
                            f"{uniprot_hint} "
                            f"Run workflow steps: {agents_desc}."
                        ).strip()
                    )
                combined_plan = _build_combined_analysis_plan_fallback(
                    state, expanded_entries
                )

        sim_prompts = []
        for entry, prompt_text in zip(expanded_entries, sim_prompts_list):
            pdb = entry["pdb"]
            prompt_body = _coerce_plan_text(prompt_text, default="")
            # Preserve master-plan prompts; only synthesize when prompt is missing.
            if post_sim_subtask and not prompt_body.strip():
                prompt_body = _build_per_sim_analysis_prompt(
                    entry,
                    original_goal=original_goal,
                    enriched_prompt=enriched_prompt,
                    agents_desc=agents_desc,
                )
            sim_prompts.append(
                {
                    "pdb": str(_Path(pdb).resolve()) if _Path(pdb).exists() else pdb,
                    "label": entry["label"],
                    "prompt": prompt_body,
                    "analysis_prompt": prompt_body if post_sim_subtask else None,
                    "task_scope": "analysis_reporter" if post_sim_subtask else "full_pipeline",
                    "working_dir": entry["working_dir"],
                    "case_id": entry.get("case_id"),
                    "case_description": entry["case_description"],
                    "case_directive": entry.get("case_directive"),
                    "protein_name": entry.get("protein_name"),
                }
            )

        state["sim_prompts"] = sim_prompts
        state["combined_analysis_plan"] = _coerce_plan_text(combined_plan, default="")

        logger.info(
            f"SUPERVISOR [multi-sim]: Master plan ready - {len(sim_prompts)} simulations, "
            f"labels: {[s['label'] for s in sim_prompts]}"
        )
        log_agent_action(
            agent_name="supervisor",
            action="Generated Multi-Simulation Master Plan",
            details={
                "num_simulations": len(sim_prompts),
                "labels": [s["label"] for s in sim_prompts],
                "component_cases": [c.get("description") for c in component_cases],
                "agents": agents_desc,
                "combined_plan_preview": (combined_plan or "")[:300],
            },
        )
        self._save_multi_sim_master_plan(
            base_working_dir=base_working_dir,
            sim_prompts=sim_prompts,
            combined_plan=combined_plan or "",
            enriched_prompt=enriched_prompt,
            agents_desc=agents_desc,
        )
        return state

    def _save_multi_sim_master_plan(
        self,
        *,
        base_working_dir: str,
        sim_prompts: List[Dict[str, Any]],
        combined_plan: str,
        enriched_prompt: str,
        agents_desc: str,
    ) -> None:
        """Persist overall multi-simulation master plan to {base}/planner/."""
        from datetime import datetime

        plan_data = {
            "title": "Multi-Simulation Master Plan",
            "format": "master_plan",
            "phase": "master",
            "workflow_pipeline": agents_desc,
            "task_scope": (
                "analysis_reporter"
                if any(s.get("task_scope") == "analysis_reporter" for s in sim_prompts)
                else "full_pipeline"
            ),
            "enriched_prompt": enriched_prompt,
            "sim_prompts": sim_prompts,
            "num_combined_prompts": 1 if _coerce_plan_text(combined_plan, default="") else 0,
            "combined_prompt": combined_plan,
            "combined_analysis_plan": combined_plan,
            "num_simulations": len(sim_prompts),
            "labels": [s.get("label") for s in sim_prompts],
        }

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_lines = [
            "# Multi-Simulation Master Plan",
            "",
            f"**Generated:** {ts}",
            f"**Simulations:** {len(sim_prompts)}",
            f"**Pipeline:** {agents_desc}",
            f"**Task scope:** {plan_data.get('task_scope', 'full_pipeline')}",
            "",
            "## Overall Goal",
            "",
            enriched_prompt or "_N/A_",
            "",
            "## Per-Simulation Prompts",
            "",
        ]
        for idx, sim in enumerate(sim_prompts, 1):
            md_lines += [
                f"### {idx}. {sim.get('label', f'sim_{idx}')}",
                "",
                f"- **PDB:** {sim.get('pdb', 'N/A')}",
                f"- **Directory:** {sim.get('working_dir', 'N/A')}",
                f"- **Case:** {sim.get('case_description', 'N/A')}",
                "",
                _coerce_plan_text(sim.get("prompt"), default="_No prompt text._"),
                "",
            ]
        md_lines += [
            "## Combined Analysis Plan",
            "",
            _coerce_plan_text(combined_plan, default="_No combined analysis plan._"),
        ]

        save_plan_artifacts(
            base_working_dir,
            "planner",
            json_filename="master_plan.json",
            md_filename="master_plan.md",
            history_filename="execution_plans.jsonl",
            plan_data=plan_data,
            md_content="\n".join(md_lines),
            phase="master",
            label="overall",
        )

    def _extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract the first JSON object from an LLM response using brace counting."""
        import json as _json

        start = response.find("{")
        if start == -1:
            return None
        depth = 0
        for i, ch in enumerate(response[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(response[start : i + 1])
                    except _json.JSONDecodeError:
                        return None
        return None

    def _build_sim_data_summary(self, completed_sims: List[Dict[str, Any]]) -> str:
        """Build a text summary of all completed simulation data paths for LLM context."""
        lines = []
        for sim in completed_sims:
            label = sim.get("label", "unknown")
            wd = sim.get("working_directory", "?")
            analysis_dir = sim.get(
                "analysis_directory", str(Path(wd) / "analysis") if wd != "?" else "?"
            )
            summary = sim.get(
                "analysis_summary", str(Path(analysis_dir) / "analysis_summary.jsonl")
            )
            traj = sim.get("trajectory_path", "N/A")
            topo = sim.get("topology", "N/A")
            energy = sim.get("energy_file", "N/A")
            n_figs = len(sim.get("figures", []))
            n_errors = len(sim.get("errors", []))
            lines.append(
                f"### Simulation: {label}\n"
                f"- Working directory: {wd}\n"
                f"- Analysis directory: {analysis_dir}\n"
                f"- Analysis summary: {summary}\n"
                f"- Trajectory: {traj}\n"
                f"- Topology: {topo}\n"
                f"- Energy: {energy}\n"
                f"- Figures generated: {n_figs}\n"
                f"- Errors: {n_errors}\n"
            )
        return "\n".join(lines)

    def input_validation_node(self, state: MDState) -> MDState:
        """
        Universal input validation node for all task types.
        
        Uses the unified validate_and_enrich_inputs() function from tools.py
        to handle both PDB-based tasks and analysis-only tasks.
        """
        from .tools import validate_and_enrich_inputs

        from agentic.multi_sim_progress import ensure_per_sim_working_directory

        ensure_per_sim_working_directory(state)
        
        subtask_type = state.get("subtask_type", "full_task")
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action=f"Starting Unified Input Validation ({subtask_type})",
            details={
                "user_goal": state.get("user_goal", ""),
                "agent_list": state.get("agent_list") or [],
                "task_type": subtask_type,
            },
        )
        
        # Call unified validation function for all task types
        state = validate_and_enrich_inputs(
            state=state,
            subtask_type=subtask_type,
            llm_client=self.llm,
            config=self.supervisor_config,
            analyze_pdb_tool=analyze_pdb,
            logger=logger
        )
        
        log_supervisor_routing(
            state, "supervisor",
            f"Input validation complete for {subtask_type}, returning to supervisor for planning"
        )
        
        return state

    def _extract_agent_specific_plans(self, state: MDState) -> MDState:
        """
        Extract agent-specific instructions from the full execution plan.
        
        Prefers the pre-extracted `agent_plans` dict from the planner (deterministic).
        Falls back to regex extraction from full_plan prose if dict is unavailable.
        """
        import re
        
        execution_plan = state.get("execution_plan", {})
        agent_plans = execution_plan.get("agent_plans", {})
        full_plan = execution_plan.get("full_plan", "")
        
        if not full_plan and not agent_plans:
            logger.warning("No full_plan or agent_plans found in execution_plan, skipping extraction")
            return state
        
        # Map from agent_plans keys to state keys
        _agent_to_state = {
            "preprocessing_agent": "preprocessing_instructions",
            "setup_agent": "setup_instructions",
            "hpc_agent": "hpc_instructions",
            "analysis_agent": "analysis_instructions",
            "reporter_agent": "reporter_instructions",
        }
        
        # Strategy 1: Use pre-extracted agent_plans dict from planner (preferred)
        if agent_plans:
            logger.info(f"Using pre-extracted agent_plans from planner: {list(agent_plans.keys())}")
            for agent_key, instructions in agent_plans.items():
                state_key = _agent_to_state.get(agent_key)
                if state_key and instructions:
                    state[state_key] = instructions
                    logger.info(f"Set {state_key} from agent_plans ({len(instructions)} chars)")
            
            logger.info(
                f"Agent-specific extraction complete (from agent_plans). Keys set: "
                f"{[sk for sk in _agent_to_state.values() if state.get(sk)]}"
            )
            return state
        
        # Strategy 2: Fallback to regex extraction from full_plan prose
        logger.info(f"No agent_plans dict found, falling back to regex extraction from {len(full_plan)} char plan")
        
        # Define agent mappings: (state_key, agent_names_to_search)
        agent_mappings = {
            "preprocessing_instructions": [
                "Preprocessing Agent",
                "PDB Preprocessing Agent", 
                "Preprocess Agent"
            ],
            "setup_instructions": [
                "Simulation Setup Agent",
                "SimSetup Agent",
                "Setup Agent"
            ],
            "hpc_instructions": [
                "HPC Agent",
                "HPC Submission Agent",
                "Job Submission Agent"
            ],
            "analysis_instructions": [
                "Analysis Agent",
                "MD Analysis Agent",
                "Trajectory Analysis Agent"
            ],
            "reporter_instructions": [
                "Reporter Agent",
                "Report Generation Agent",
                "Scientific Reporter Agent"
            ]
        }
        
        # Extract instructions for each agent
        for state_key, agent_names in agent_mappings.items():
            extracted = None
            
            # Try each agent name variant
            for agent_name in agent_names:
                # Try multiple heading patterns (all anchored to line start)
                patterns = [
                    # Bold header with colon: **Agent Name:** (at line start)
                    rf'^\*\*{re.escape(agent_name)}(?:\s*:?\s*\*\*|:\*\*)\s*\n(.*?)(?=^\*\*[A-Z]|\Z)',
                    # Markdown ### heading
                    rf'^###\s*{re.escape(agent_name)}.*?\n(.*?)(?=^###|\Z)',
                    # Markdown ## heading  
                    rf'^##\s*{re.escape(agent_name)}.*?\n(.*?)(?=^##|\Z)',
                    # Numbered section: 1. **Agent Name** (at line start)
                    rf'^\d+\.\s*\*\*{re.escape(agent_name)}\*\*.*?\n(.*?)(?=^\d+\.\s*\*\*|^\*\*[A-Z]|\Z)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE | re.MULTILINE)
                    if match:
                        instructions = match.group(1).strip()
                        if len(instructions) > 50:  # Ensure substantial content
                            extracted = instructions
                            logger.info(
                                f"Extracted {len(instructions)} chars for {state_key} "
                                f"using agent name '{agent_name}'"
                            )
                            break
                
                if extracted:
                    break
            
            # Store extracted instructions (or fallback to full plan)
            if extracted:
                state[state_key] = extracted
            else:
                # Fallback: provide full plan so agent has context
                logger.warning(
                    f"Could not extract specific section for {state_key}, "
                    f"agent will receive full plan as fallback"
                )
                state[state_key] = full_plan
        
        logger.info(
            f"Agent-specific extraction complete. Keys set: "
            f"{[k for k in agent_mappings.keys() if state.get(k)]}"
        )
        
        return state

    def _assign_field_agent_tasks(self, state: MDState) -> MDState:
        """
        Route to appropriate field agents using STRICT EXECUTION ORDER.
        
        Order is ALWAYS: preprocessing → simsetup → hpc → analysis → reporter
        Agents are skipped based on:
        - Task type (e.g., analysis_only skips preprocessing/simsetup/hpc)
        - User exclusions (e.g., "no hpc")
        - Already completed work (e.g., cleaned_pdb exists)
        
        This enforces predictable, sequential execution regardless of plan.
        """
        logger.info("FIELD_AGENT_ASSIGNMENT: Using strict agent execution order")

        self._ensure_hpc_pool_prep_context(state)
        self._clear_stale_cross_sim_artifacts(state)
        
        # Get the required agents in strict order for this task
        subtask_type = state.get("subtask_type") or "full_task"
        required_agents = get_agent_execution_order(subtask_type, state)

        agent_filter = state.get("hpc_pool_agent_filter")
        if agent_filter:
            required_agents = [a for a in required_agents if a in agent_filter]
        elif state.get("post_hpc_analysis_only"):
            required_agents = [a for a in required_agents if a in ("analysis", "reporter")]
        
        logger.info(f"FIELD_AGENT_ASSIGNMENT: Required agents for {subtask_type}: {required_agents}")
        
        # Get progress - which agent are we on?
        current_agent_idx = state.get("current_agent_idx", 0)
        
        if current_agent_idx >= len(required_agents):
            from agentic.multi_sim_hpc_pool import _sim_setup_ready

            wd = state.get("working_directory") or ""
            if state.get("hpc_pool_prep_only") and wd and not _pool_prep_simsetup_ready(state, wd):
                setup_idx = (
                    required_agents.index("simsetup")
                    if "simsetup" in required_agents
                    else max(len(required_agents) - 1, 0)
                )
                retry_count = state.get("setup_retry_count", 0)
                if retry_count >= 3:
                    sim_label = "unknown"
                    sim_idx = state.get("current_sim_index", 0)
                    sim_prompts = state.get("sim_prompts") or []
                    if isinstance(sim_prompts, list) and 0 <= sim_idx < len(sim_prompts):
                        sim_label = sim_prompts[sim_idx].get("label", sim_label)
                    pool = state.get("hpc_pool") or {}
                    rec = (pool.get("sims") or {}).get(sim_label)
                    if rec:
                        rec["prep_status"] = "failed"
                        rec["error"] = "SimSetup failed after 3 retries"
                    pool["awaiting_hitl"] = True
                    pool["hitl_reason"] = f"SimSetup failed after 3 retries for {sim_label}"
                    state["hpc_pool"] = pool
                    state.pop("hpc_pool_prep_only", None)
                    state["plan_executed"] = False
                    state["execution_plan"] = None
                    state["current_agent_idx"] = 0
                    state.pop("hpc_pool_agent_filter", None)
                    base = state.get("multi_sim_base_dir") or state.get("working_directory")
                    if base:
                        state["working_directory"] = str(Path(base).resolve())
                    _set_base_conversation_log(state)
                    return self._apply_hpc_pool_tick(state)
                else:
                    logger.warning(
                        "FIELD_AGENT_ASSIGNMENT: HPC pool prep incomplete — "
                        "retry simsetup (attempt %s)",
                        retry_count + 1,
                    )
                    state["current_agent_idx"] = setup_idx
                    state["next_node"] = "setup"
                    state["setup_retry_count"] = retry_count + 1
                    log_supervisor_routing(
                        state,
                        "setup",
                        "Simsetup not ready — retry without replanning",
                    )
                    return state

            # All agents complete
            logger.info("FIELD_AGENT_ASSIGNMENT: All required agents completed")
            state["plan_executed"] = True

            # Multi-sim: return to supervisor to advance to next sim or combined phase
            if state.get("is_multi_simulation") and state.get("multi_sim_phase") == "executing_sims":
                logger.info("FIELD_AGENT_ASSIGNMENT: Per-sim cycle done — returning to multi-sim loop")
                state["next_node"] = "supervisor"
                return state

            # Multi-sim combined phases: transition to next phase
            if state.get("multi_sim_phase") == "combined_analysis":
                logger.info("FIELD_AGENT_ASSIGNMENT: Combined analysis done — transitioning to combined reporter")
                state["multi_sim_phase"] = "combined_reporter"
                state["next_node"] = "supervisor"
                return state

            if state.get("multi_sim_phase") == "combined_reporter":
                logger.info("FIELD_AGENT_ASSIGNMENT: Combined reporter done — going to final report")
                state["next_node"] = "final_report"
                log_supervisor_routing(state, "final_report", "Multi-sim workflow complete")
                return state

            if (
                state.get("multi_sim_phase") == "hpc_pool"
                and not state.get("post_hpc_analysis_only")
            ):
                logger.info(
                    "FIELD_AGENT_ASSIGNMENT: HPC pool prep done — returning to supervisor"
                )
                state["plan_executed"] = True
                state["next_node"] = "supervisor"
                return state

            state["next_node"] = "final_report"
            log_supervisor_routing(state, "final_report", "All workflow tasks complete")
            return state
        
        # Get the current agent to execute
        current_agent = required_agents[current_agent_idx]
        logger.info(f"FIELD_AGENT_ASSIGNMENT: Executing agent {current_agent_idx + 1}/{len(required_agents)}: {current_agent}")
        
        # Execute based on agent type with completion checks
        if current_agent == "preprocessing":
            if state.get("cleaned_pdb") and not _artifact_in_sim_dir(
                state.get("cleaned_pdb"), state.get("working_directory")
            ):
                logger.warning(
                    "FIELD_AGENT_ASSIGNMENT: Ignoring cleaned_pdb outside active sim dir"
                )
                state["cleaned_pdb"] = None
            if state.get("cleaned_pdb"):
                logger.info("FIELD_AGENT_ASSIGNMENT: Preprocessing already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("preprocess_retry_count", 0)
            if retry_count >= 3:
                state["errors"].append("Preprocessing failed after 3 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "preprocess"
            state["preprocess_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to preprocessing")
            log_supervisor_routing(state, "preprocess", "Executing preprocessing agent")
            return state
        
        elif current_agent == "simsetup":
            if state.get("coordinates") and not _artifact_in_sim_dir(
                state.get("coordinates"), state.get("working_directory")
            ):
                logger.warning(
                    "FIELD_AGENT_ASSIGNMENT: Ignoring coordinates outside active sim dir"
                )
                state["coordinates"] = None
            if state.get("coordinates"):
                logger.info("FIELD_AGENT_ASSIGNMENT: SimSetup already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("setup_retry_count", 0)
            if retry_count >= 3:
                if state.get("multi_sim_phase") == "hpc_pool" and state.get("hpc_pool_prep_only"):
                    sim_label = "unknown"
                    sim_idx = state.get("current_sim_index", 0)
                    sim_prompts = state.get("sim_prompts") or []
                    if isinstance(sim_prompts, list) and 0 <= sim_idx < len(sim_prompts):
                        sim_label = sim_prompts[sim_idx].get("label", sim_label)
                    pool = state.get("hpc_pool") or {}
                    rec = (pool.get("sims") or {}).get(sim_label)
                    if rec:
                        rec["prep_status"] = "failed"
                        rec["error"] = "SimSetup failed after 3 retries"
                    pool["awaiting_hitl"] = True
                    pool["hitl_reason"] = f"SimSetup failed after 3 retries for {sim_label}"
                    state["hpc_pool"] = pool
                    state.pop("hpc_pool_prep_only", None)
                    state["plan_executed"] = False
                    state["execution_plan"] = None
                    state["current_agent_idx"] = 0
                    state.pop("hpc_pool_agent_filter", None)
                    base = state.get("multi_sim_base_dir") or state.get("working_directory")
                    if base:
                        state["working_directory"] = str(Path(base).resolve())
                    _set_base_conversation_log(state)
                    return self._apply_hpc_pool_tick(state)

                if state.get("is_multi_simulation") and state.get("multi_sim_phase") == "executing_sims":
                    sim_label = "unknown"
                    sim_idx = state.get("current_sim_index", 0)
                    sim_prompts = state.get("sim_prompts") or []
                    if isinstance(sim_prompts, list) and 0 <= sim_idx < len(sim_prompts):
                        sim_label = sim_prompts[sim_idx].get("label", sim_label)

                    state["errors"].append(
                        f"SimSetup failed after 3 retries for {sim_label} — continuing with next simulation"
                    )
                    state["plan_executed"] = True
                    state["next_node"] = "supervisor"
                    logger.warning(
                        "SimSetup exhausted 3 retries for multi-sim case %s — advancing to next simulation",
                        sim_label,
                    )
                    log_supervisor_routing(
                        state,
                        "supervisor",
                        f"SimSetup failed after 3 retries for {sim_label}; advancing multi-sim loop",
                    )
                    return state

                state["errors"].append("SimSetup failed after 3 retries — skipping HPC submission")
                state["next_node"] = "final_report"
                logger.warning("SimSetup exhausted 3 retries — aborting workflow (no HPC submission)")
                log_supervisor_routing(state, "final_report", "SimSetup failed after 3 retries, skipping HPC")
                return state
            
            state["next_node"] = "setup"
            state["setup_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to simsetup")
            log_supervisor_routing(state, "setup", "Executing simsetup agent")
            return state
        
        elif current_agent == "hpc":
            # Check for user exclusion
            user_goal = state.get("user_goal", "").lower()
            rephrased_goal = state.get("rephrased_goal", "").lower()
            combined_goals = f"{user_goal} {rephrased_goal}"
            
            # Only skip HPC if the user EXPLICITLY excludes it.
            # Use user_goal only (not rephrased_goal) to avoid false positives
            # from enricher phrases like "No simulation execution is performed".
            user_excluded_hpc = any(phrase in user_goal for phrase in [
                "no hpc", "skip hpc", "do not submit", "don't submit",
                "without hpc", "local only"
            ])
            
            if user_excluded_hpc:
                logger.info("FIELD_AGENT_ASSIGNMENT: User excluded HPC, skipping")
                state["warnings"].append("HPC execution skipped per user request")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            if state.get("job_id"):
                logger.info("FIELD_AGENT_ASSIGNMENT: HPC already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # HPC gets only 1 attempt (no retries)
            retry_count = state.get("hpc_retry_count", 0)
            if retry_count >= 1:
                state["errors"].append("HPC execution failed (no retries)")
                state["warnings"].append("HPC simulation not submitted due to failure")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "hpc"
            state["hpc_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to HPC (attempt 1/1)")
            log_supervisor_routing(state, "hpc", "Executing HPC agent")
            return state
        
        elif current_agent == "analysis":
            if state.get("analysis_results"):
                logger.info("FIELD_AGENT_ASSIGNMENT: Analysis already complete, moving to next agent")
                self._mark_post_hpc_agent_done(state, "analysis")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("analysis_retry_count", 0)
            if retry_count >= 3:
                state["errors"].append("Analysis failed after 3 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "analysis"
            state["analysis_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to analysis")
            log_supervisor_routing(state, "analysis", "Executing analysis agent")
            return state
        
        elif current_agent == "reporter":
            if state.get("reporter_output"):
                logger.info("FIELD_AGENT_ASSIGNMENT: Reporter already complete, moving to next agent")
                self._mark_post_hpc_agent_done(state, "reporter")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("reporter_retry_count", 0)
            if retry_count >= 2:
                state["errors"].append("Reporter failed after 2 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "reporter"
            state["reporter_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to reporter")
            log_supervisor_routing(state, "reporter", "Executing reporter agent")
            return state
        
        else:
            # Unknown agent (shouldn't happen with get_agent_execution_order)
            error_msg = f"Unknown agent '{current_agent}' in execution order"
            logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
            state["errors"].append(error_msg)
            state["next_node"] = "final_report"
            return state

    def get_agents_summary(self) -> str:
        """Build summary of available agents for LLM context."""
        summary = []
        for agent_id, config in self.agents_registry.items():
            summary.append(
                f"\n{agent_id.upper()}:\n"
                f"  - Name: {config.get('name', 'N/A')}\n"
                f"  - Purpose: {config.get('description', 'N/A')}\n"
                f"  - Capabilities: {', '.join(config.get('capabilities', []))}\n"
                f"  - Requires: {', '.join(config.get('input_requirements', []))}\n"
                f"  - Produces: {', '.join(config.get('output_provides', []))}"
            )
        return "".join(summary)

    def get_workflow_progress(self, state: MDState) -> str:
        """Get human-readable workflow progress summary."""
        completed = []

        if state.get("raw_pdb"):
            completed.append("input_validation")
        if state.get("execution_plan"):
            completed.append("planning")
        if state.get("cleaned_pdb"):
            completed.append("preprocessing")
        if state.get("coordinates"):
            completed.append("setup")
        if state.get("job_id"):
            completed.append("hpc")
        if state.get("analysis_results"):
            completed.append("analysis")
        if state.get("reporter_output"):
            completed.append("reporter")

        total = len(self.workflow_config.get("default_pipeline", []))
        progress = (len(completed) / (total + 2)) * 100
        return f"Progress: {completed} ({progress:.0f}%)"
