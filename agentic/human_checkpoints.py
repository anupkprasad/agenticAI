"""Human-in-the-Loop Checkpoint Nodes"""
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from .state import MDState
from .utils import log_human_checkpoint
from .hitl_router import (
    parse_hitl_command,
    parse_execute_feedback,
    prepare_hitl_execution,
    bind_agent_context,
    restore_multi_sim_executing_working_directory,
    sync_hitl_active_agent_for_checkpoint,
    merge_hitl_context_into_state_jsonl,
    CHECKPOINT_FOR_AGENT,
    agents_in_workflow,
    artifact_summary,
    AGENT_DISPLAY,
    HITL_EXECUTE_PREFIX,
)
from .multi_sim_progress import apply_hitl_continue
from .hitl_config import hitl_should_interact

logger = logging.getLogger(__name__)

_CHECKPOINT_RETURN_NODE = {
    "preprocess": "human_preprocess_check",
    "setup": "human_setup_check",
    "hpc": "human_hpc_check",
    "analysis": "human_analysis_check",
    "reporter": "human_reporter_check",
}


def _looks_like_combined_report_regen(text: str) -> bool:
    """Natural-language requests to redo the combined HTML report."""
    lower = text.lower().strip()
    if not lower or lower.startswith(("run ", "execute ", "switch ", "continue", "approved")):
        return False
    wants_report = any(
        kw in lower
        for kw in ("report", "combined_report", "combined report", "html")
    )
    wants_change = any(
        kw in lower
        for kw in (
            "recreate", "regenerate", "redo", "improve", "fix", "update",
            "missing", "include", "add", "no rmsf", "no plot", "not good",
        )
    )
    plot_terms = any(kw in lower for kw in ("rmsf", "plot", "overlay", "dccm", "comparison"))
    return wants_report and (wants_change or plot_terms)


def _list_files_in_dir(directory: str, extensions: list = None) -> List[str]:
    """List files in a directory, optionally filtered by extension."""
    if not directory:
        return []
    d = Path(directory)
    if not d.is_dir():
        return []
    files = []
    for f in sorted(d.iterdir()):
        if f.is_file():
            if extensions is None or f.suffix.lower() in extensions:
                files.append(f.name)
    return files


class HumanCheckpoints:
    """Handles human intervention points in the MD workflow."""

    @staticmethod
    def _route_hitl_command(
        feedback: str,
        state: MDState,
        checkpoint_label: str,
    ) -> Optional[MDState]:
        """
        Handle cross-agent switch and delegated execute commands.

        Returns updated state if routed, else None to continue normal feedback handling.
        """
        return_node = _CHECKPOINT_RETURN_NODE.get(checkpoint_label, "human_reporter_check")

        combined = False
        parsed = parse_execute_feedback(feedback)
        if not parsed:
            parsed_cmd = parse_hitl_command(
                feedback, state, default_agent=checkpoint_label
            )
            if parsed_cmd and parsed_cmd.get("type") == "execute":
                combined = bool(parsed_cmd.get("combined"))
                parsed = (
                    parsed_cmd["agent"],
                    parsed_cmd["task"],
                    parsed_cmd.get("sim_label"),
                )

        if parsed:
            agent, task, sim_label = parsed
            logger.info(
                "HITL execute: %s (sim=%s, combined=%s) — %s",
                agent, sim_label or "default", combined, task[:80],
            )
            return prepare_hitl_execution(
                state, agent, task, return_node, sim_label=sim_label, combined=combined
            )

        cmd = parse_hitl_command(feedback, state, default_agent=checkpoint_label)
        if cmd and cmd.get("type") in ("switch", "switch_chat"):
            agent = cmd["agent"]
            if cmd.get("combined"):
                state["hitl_view_combined"] = True
                state.pop("hitl_target_sim_label", None)
            bind_agent_context(
                state,
                agent,
                sim_label=cmd.get("sim_label"),
                for_execution=False,
            )
            if cmd["type"] == "switch":
                state["next_node"] = CHECKPOINT_FOR_AGENT[agent]
                state.setdefault("warnings", []).append(
                    f"HITL switched to {AGENT_DISPLAY.get(agent, agent)} checkpoint"
                )
            else:
                state["hitl_active_agent"] = agent
                state["next_node"] = return_node
                state.pop("human_feedback", None)
                state.setdefault("warnings", []).append(
                    f"HITL in-chat switch to {AGENT_DISPLAY.get(agent, agent)}"
                )
            merge_hitl_context_into_state_jsonl(state)
            return state

        if (
            checkpoint_label == "reporter"
            and _looks_like_combined_report_regen(feedback)
            and (
                state.get("multi_sim_phase") in ("combined_reporter", "combined_analysis", "complete")
                or state.get("hitl_view_combined")
                or state.get("run_combined_analysis")
            )
        ):
            from agentic.hitl_router import is_combined_workflow_phase

            combined = bool(
                state.get("hitl_view_combined")
                or is_combined_workflow_phase(state)
                or state.get("run_combined_analysis")
            )
            logger.info("HITL: routing natural-language report request to combined reporter")
            return prepare_hitl_execution(
                state,
                "reporter",
                feedback,
                return_node,
                combined=combined,
            )

        return None
    
    @staticmethod
    def _process_feedback(feedback: str, state: MDState, checkpoint_label: str,
                          retry_node: str, clear_keys: List[str] = None) -> MDState:
        """Common feedback processing logic for all checkpoints."""
        routed = HumanCheckpoints._route_hitl_command(feedback, state, checkpoint_label)
        if routed is not None:
            log_human_checkpoint(checkpoint_label, {}, "hitl_route", feedback)
            return routed

        log_human_checkpoint(checkpoint_label, {}, feedback.lower(), feedback)
        logger.info(f"Received human feedback for {checkpoint_label}: {feedback}")
        
        # Clear error-triggered flag on any human response
        state.pop("error_triggered_hitl", None)
        
        lower = feedback.lower()
        if "approved" in lower or "continue" in lower:
            if state.get("is_multi_simulation") and state.get("sim_prompts"):
                apply_hitl_continue(state, checkpoint_label)
            else:
                restore_multi_sim_executing_working_directory(state)
                state["next_node"] = "supervisor"
            state.pop("human_feedback", None)
        elif "retry" in lower or "redo" in lower:
            # Clear previous results and retry
            for key in (clear_keys or []):
                if key in state:
                    default = [] if isinstance(state.get(key), list) else ({} if isinstance(state.get(key), dict) else None)
                    state[key] = default
            state["next_node"] = retry_node
        elif lower.startswith("recommend"):
            # Human provides guidance — store it and retry with recommendation
            recommendation = feedback.split(":", 1)[1].strip() if ":" in feedback else feedback
            state["human_recommendation"] = recommendation
            # Extract parameter overrides from recommendation text
            HumanCheckpoints._apply_parameter_overrides(recommendation, state)
            # Clear previous results so the agent re-runs cleanly
            for key in (clear_keys or []):
                if key in state:
                    default = [] if isinstance(state.get(key), list) else ({} if isinstance(state.get(key), dict) else None)
                    state[key] = default
            # Append to agent-specific issues so the LLM planner sees it
            issues_key = f"{checkpoint_label}_issues"
            if issues_key in state and isinstance(state[issues_key], list):
                state[issues_key].append(f"Human recommendation: {recommendation}")
            state.setdefault("warnings", []).append(f"Human recommendation ({checkpoint_label}): {recommendation}")
            state["next_node"] = retry_node
        elif "modify" in lower:
            # Store the human's modification instructions for the agent
            modification = feedback.split(":", 1)[1].strip() if ":" in feedback else feedback
            state["human_recommendation"] = modification
            # Extract parameter overrides from modification text
            HumanCheckpoints._apply_parameter_overrides(modification, state)
            # Clear previous results so the agent re-runs cleanly
            for key in (clear_keys or []):
                if key in state:
                    default = [] if isinstance(state.get(key), list) else ({} if isinstance(state.get(key), dict) else None)
                    state[key] = default
            issues_key = f"{checkpoint_label}_issues"
            if issues_key in state and isinstance(state[issues_key], list):
                state[issues_key].append(f"Human modification request: {modification}")
            else:
                state.setdefault("warnings", []).append(f"Human modify request ({checkpoint_label}): {feedback}")
            state["next_node"] = retry_node
        else:
            # Default: treat any other text as approval with a note
            state.setdefault("warnings", []).append(f"Human note ({checkpoint_label}): {feedback}")
            if state.get("is_multi_simulation") and state.get("sim_prompts"):
                apply_hitl_continue(state, checkpoint_label)
            else:
                restore_multi_sim_executing_working_directory(state)
                state["next_node"] = "supervisor"
            state.pop("human_feedback", None)
        
        return state
    
    @staticmethod
    def _apply_parameter_overrides(text: str, state: MDState):
        """Extract and apply parameter overrides from human recommendation text.
        
        Detects force field, water model, temperature, pressure, and simulation
        length keywords and updates state directly so agents pick them up.
        """
        lower = text.lower()
        
        # Force field detection
        ff_patterns = {
            "charmm36": "charmm27",  # GROMACS uses charmm27 for CHARMM36
            "charmm27": "charmm27",
            "charmm": "charmm27",
            "opls": "oplsaa",
            "opls-aa": "oplsaa",
            "oplsaa": "oplsaa",
            "amber99sb-ildn": "amber99sb-ildn",
            "amber99sb": "amber99sb-ildn",
            "amber03": "amber03",
            "amber94": "amber94",
            "gromos": "gromos54a7",
        }
        for pattern, ff_value in ff_patterns.items():
            if pattern in lower:
                old_ff = state.get("force_field", "")
                state["force_field"] = ff_value
                logger.info(f"Parameter override: force_field {old_ff!r} -> {ff_value!r} (from human recommendation)")
                break
        
        # Water model detection
        wm_patterns = {
            "spc/e": "spce", "spce": "spce", "spc": "spc216",
            "tip3p": "tip3p", "tip4p": "tip4p", "tip5p": "tip5p",
        }
        for pattern, wm_value in wm_patterns.items():
            if pattern in lower:
                old_wm = state.get("water_model", "")
                state["water_model"] = wm_value
                logger.info(f"Parameter override: water_model {old_wm!r} -> {wm_value!r} (from human recommendation)")
                break
        
        # Temperature detection (e.g. "310 K", "temperature 350")
        temp_match = re.search(r'(?:temperature|temp)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*k?\b', lower)
        if not temp_match:
            temp_match = re.search(r'(\d+(?:\.\d+)?)\s*k\b', lower)
        if temp_match:
            state["temperature"] = float(temp_match.group(1))
            logger.info(f"Parameter override: temperature -> {state['temperature']} K")
        
        # Pressure detection (e.g. "1.5 bar")
        pres_match = re.search(r'(?:pressure|pres)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*bar\b', lower)
        if not pres_match:
            pres_match = re.search(r'(\d+(?:\.\d+)?)\s*bar\b', lower)
        if pres_match:
            state["pressure"] = float(pres_match.group(1))
            logger.info(f"Parameter override: pressure -> {state['pressure']} bar")
    
    @staticmethod
    def human_preprocess_check(state: MDState) -> MDState:
        """
        Human checkpoint after preprocessing.
        Allows human to review and provide feedback on PDB cleaning.
        Auto-approves if not in interactive HITL mode (graph-only execution).
        """
        feedback = state.get("human_feedback", "")
        if feedback:
            return HumanCheckpoints._process_feedback(
                feedback, state, "preprocessing", "preprocess",
                clear_keys=["cleaned_pdb", "topology", "preprocessing_report", "preprocessing_issues"]
            )
        elif not hitl_should_interact(state):
            # Non-interactive: auto-approve and continue
            state["next_node"] = "supervisor"
            return state
        else:
            state["next_node"] = "human_preprocess_check"
            return state
    
    @staticmethod
    def human_setup_check(state: MDState) -> MDState:
        """
        Human checkpoint after simulation setup.
        Allows human to review topology, solvation, ions, and MDP parameters.
        """
        feedback = state.get("human_feedback", "")
        if feedback:
            return HumanCheckpoints._process_feedback(
                feedback, state, "setup", "setup",
                clear_keys=["coordinates", "mdp_files", "setup_report", "setup_issues"]
            )
        elif not hitl_should_interact(state):
            state["next_node"] = "supervisor"
            return state
        else:
            state["next_node"] = "human_setup_check"
            return state
    
    @staticmethod
    def human_hpc_pool_check(state: MDState) -> MDState:
        """
        HITL checkpoint while cross-sim HPC jobs run or after submit/SLURM failures.

        Supports: continue / retry / resubmit / status
        """
        from agentic.multi_sim_hpc_pool import (
            clear_hitl_pause,
            init_hpc_pool,
            pool_summary,
            _sync_jobs_from_slurm,
        )

        feedback = state.get("human_feedback", "")
        if feedback:
            lower = feedback.lower().strip()
            if any(w in lower for w in ("status", "summary", "pool")):
                state["hpc_pool_status_summary"] = pool_summary(state)
                state.pop("human_feedback", None)
                state["next_node"] = "human_hpc_pool_check"
                return state
            if any(
                w in lower
                for w in (
                    "continue", "proceed", "retry", "resubmit", "ok", "approved",
                    "go", "resume",
                )
            ):
                clear_hitl_pause(state)
                pool = init_hpc_pool(state)
                _sync_jobs_from_slurm(state, pool, force=True)
                state.pop("human_feedback", None)
                state["next_node"] = "supervisor"
                log_human_checkpoint("hpc_pool", {}, lower, feedback)
                return state
            state.setdefault("warnings", []).append(
                f"HPC pool checkpoint note: {feedback}"
            )
            state.pop("human_feedback", None)
            state["next_node"] = "supervisor"
            return state

        if not hitl_should_interact(state):
            state["next_node"] = "supervisor"
            return state

        state["hpc_pool_status_summary"] = pool_summary(state)
        state["next_node"] = "human_hpc_pool_check"
        return state

    @staticmethod
    def human_hpc_check(state: MDState) -> MDState:
        """
        Human checkpoint after HPC job submission/completion.
        Allows review of job results and decision on next steps.
        """
        feedback = state.get("human_feedback", "")
        if feedback:
            return HumanCheckpoints._process_feedback(
                feedback, state, "hpc", "hpc",
                clear_keys=[]
            )
        elif not hitl_should_interact(state):
            state["next_node"] = "supervisor"
            return state
        else:
            state["next_node"] = "human_hpc_check"
            return state
    
    @staticmethod
    def human_analysis_check(state: MDState) -> MDState:
        """
        Human checkpoint after analysis.
        Allows review of analysis results before reporting.
        """
        feedback = state.get("human_feedback", "")
        if feedback:
            return HumanCheckpoints._process_feedback(
                feedback, state, "analysis", "analysis",
                clear_keys=["analysis_results", "figures", "conclusions"]
            )
        elif not hitl_should_interact(state):
            state["next_node"] = "supervisor"
            return state
        else:
            state["next_node"] = "human_analysis_check"
            return state

    @staticmethod
    def human_reporter_check(state: MDState) -> MDState:
        """Human checkpoint after the reporter agent.

        Behaves like all other checkpoints:
        - Skipped automatically when HITL is off (default).
        - Pauses for interactive review when ``--HITL all`` is set, or on errors
          when ``--HITL error`` is set.

        In HITL mode supports:
            'done' / 'approved'               → proceed to final_report
            'reporter [: instructions]'       → re-run reporter then review again
            'analysis [: instructions]'       → re-run analysis + reporter then review again
            'preprocess' / 'setup' / 'hpc'   → switch to that earlier HITL checkpoint
        """
        feedback = state.get("human_feedback", "")

        # ── Non-interactive: auto-approve and continue to supervisor ──
        if not hitl_should_interact(state) and not feedback:
            state["next_node"] = "supervisor"
            return state

        # ── Interactive mode, waiting for input ───────────────────────
        if not feedback:
            state["next_node"] = "human_reporter_check"
            return state

        routed = HumanCheckpoints._route_hitl_command(feedback, state, "reporter")
        if routed is not None:
            return routed

        log_human_checkpoint("reporter", {}, feedback.lower(), feedback)
        logger.info(f"Reporter checkpoint — human decision: {feedback}")
        state.pop("human_feedback", None)

        lower = feedback.lower().strip()

        # ── done / exit ───────────────────────────────────────────────
        if any(w in lower for w in ("done", "exit", "quit", "finish", "ok", "approved",
                                     "good", "satisfied", "continue", "proceed")):
            state["human_final_decision"] = "done"
            if state.get("is_multi_simulation") and state.get("sim_prompts"):
                apply_hitl_continue(state, "reporter")
            else:
                state["next_node"] = "supervisor"
            return state

        # ── re-run reporter ────────────────────────────────────────────
        if any(w in lower for w in ("reporter", "report", "regenerate report", "redo report")):
            state["reporter_output"] = None
            if ":" in feedback:
                instructions = feedback.split(":", 1)[1].strip()
                existing = state.get("reporter_instructions") or ""
                state["reporter_instructions"] = (existing + "\n" + instructions).strip()
            state.setdefault("warnings", []).append(
                f"Human requested reporter re-run at reporter checkpoint: {feedback}"
            )
            state["human_final_decision"] = "rerun_reporter"
            state["next_node"] = "reporter"
            return state

        # ── re-run analysis ────────────────────────────────────────────
        if any(w in lower for w in ("analysis", "analyse", "analyze",
                                     "rerun analysis", "redo analysis")):
            state["analysis_results"] = {}
            state["figures"] = []
            state["conclusions"] = None
            state["reporter_output"] = None
            if ":" in feedback:
                instructions = feedback.split(":", 1)[1].strip()
                existing = state.get("analysis_instructions") or ""
                state["analysis_instructions"] = (existing + "\n" + instructions).strip()
            state.setdefault("warnings", []).append(
                f"Human requested analysis re-run at reporter checkpoint: {feedback}"
            )
            state["human_final_decision"] = "rerun_analysis"
            state["next_node"] = "analysis"
            return state

        # ── switch to earlier HITL checkpoint ─────────────────────────
        _checkpoint_map = {
            "preprocess": "human_preprocess_check",
            "preprocessing": "human_preprocess_check",
            "setup": "human_setup_check",
            "simsetup": "human_setup_check",
            "simulation setup": "human_setup_check",
            "hpc": "human_hpc_check",
            "job": "human_hpc_check",
        }
        for _kw, _target in _checkpoint_map.items():
            if _kw in lower:
                state.setdefault("warnings", []).append(
                    f"Human switched to {_target} from reporter checkpoint: {feedback}"
                )
                state["human_final_decision"] = f"switch_{_target}"
                state["next_node"] = _target
                return state

        # ── default: treat as approval + note ─────────────────────────
        state["human_final_decision"] = "done"
        state.setdefault("warnings", []).append(
            f"Human note at reporter checkpoint: {feedback}"
        )
        state["next_node"] = "supervisor"
        return state
    
    @staticmethod
    def get_checkpoint_summary(state: MDState, checkpoint_type: str) -> Dict[str, Any]:
        """
        Generate summary for human review at checkpoints.
        Includes actual agent output, generated files, and agent metadata
        for informed decisions.
        """
        error_triggered = bool(state.get("error_triggered_hitl"))

        active_agent = sync_hitl_active_agent_for_checkpoint(state, checkpoint_type)
        bind_agent_context(
            state,
            active_agent,
            sim_label=state.get("hitl_target_sim_label"),
            for_execution=False,
        )

        summary: Dict[str, Any] = {
            "checkpoint_type": checkpoint_type,
            "error_triggered": error_triggered,
            "current_state": {},
            "issues_found": [],
            "recommendations": [],
            "available_agents": agents_in_workflow(state),
            "active_agent": active_agent,
        }
        summary["artifacts"] = artifact_summary(state, active_agent)
        
        if checkpoint_type == "preprocess":
            preprocess_dir = state.get("preprocess_dir", "")
            generated = _list_files_in_dir(preprocess_dir, [".pdb", ".log", ".txt"])
            
            summary["current_state"] = {
                "raw_pdb": state.get("raw_pdb"),
                "cleaned_pdb": state.get("cleaned_pdb"),
                "force_field": state.get("force_field"),
                "ligand_resnames": state.get("ligand_resnames", []),
                "ion_resnames": state.get("ion_resnames", []),
                "generated_files": generated,
            }
            report = state.get("preprocessing_report", "")
            if report:
                summary["current_state"]["preprocessing_report"] = report[:500]
            
            summary["issues_found"] = list(state.get("preprocessing_issues", []))
            summary["recommendations"] = [
                "Review cleaned PDB and check that correct chains/molecules were kept",
                "Verify ligand and ion residue names were correctly identified",
                "Check protonation states if relevant",
            ]
            
        elif checkpoint_type == "setup":
            simsetup_dir = state.get("simsetup_dir", "")
            generated = _list_files_in_dir(simsetup_dir, [".top", ".gro", ".mdp", ".itp"])
            
            summary["current_state"] = {
                "topology": state.get("topology"),
                "coordinates": state.get("coordinates"),
                "mdp_files": list(state.get("mdp_files", {}).keys()),
                "force_field": state.get("force_field"),
                "water_model": state.get("water_model"),
                "generated_files": generated,
            }
            report = state.get("setup_report", "")
            if report:
                summary["current_state"]["setup_report"] = report[:500]
            
            summary["issues_found"] = list(state.get("setup_issues", []))
            summary["recommendations"] = [
                "Verify topology includes all components (protein, ligands, ions, solvent)",
                "Check box size and ion concentration",
                "Review MDP parameters (simulation length, timestep, temperature)",
            ]
            
        elif checkpoint_type == "hpc":
            hpc_dir = state.get("hpc_dir", "")
            generated = _list_files_in_dir(hpc_dir)
            
            summary["current_state"] = {
                "job_script": state.get("job_script"),
                "job_id": state.get("job_id"),
                "job_status": state.get("job_status"),
                "hpc_report": state.get("hpc_report", "")[:300] if state.get("hpc_report") else None,
                "generated_files": generated,
            }
            summary["recommendations"] = [
                "Review job script and resource allocation",
                "Check that all simulation files were transferred correctly",
                "Verify simulation completed without GROMACS errors",
            ]
            
        elif checkpoint_type == "analysis":
            analysis_dir = state.get("analysis_dir", "")
            generated = _list_files_in_dir(analysis_dir)
            figures = state.get("figures", [])
            combined_info = (state.get("analysis_results") or {}).get("combined", {})

            summary["current_state"] = {
                "analysis_results": list(state.get("analysis_results", {}).keys()),
                "figures": [Path(f).name for f in figures] if figures else [],
                "generated_files": generated,
            }
            if combined_info:
                summary["current_state"]["combined"] = {
                    "overlay_plots": len(combined_info.get("overlay_plots") or []),
                    "labels": combined_info.get("labels") or [],
                    "analysis_dir": combined_info.get("analysis_dir"),
                }
                summary["scope"] = "combined"
            conclusions = state.get("conclusions", "")
            if conclusions:
                summary["current_state"]["conclusions"] = conclusions[:500]
            
            summary["issues_found"] = []
            summary["recommendations"] = [
                "Review generated plots for expected trends",
                "Check that all requested analyses were completed",
                "Verify analysis results make physical sense",
            ]

        elif checkpoint_type == "reporter":
            rep = HumanCheckpoints.get_reporter_check_summary(state)
            summary["current_state"] = rep.get("current_state", {})
            summary["issues_found"] = rep.get("issues_found", [])
            summary["recommendations"] = rep.get("recommendations", [])
        
        # Add errors from the workflow so far
        errors = state.get("errors", [])
        if errors:
            summary["issues_found"] = list(summary["issues_found"]) + [f"ERROR: {e}" for e in errors[-5:]]
        
        # Adjust recommendations for error-triggered checkpoints
        if error_triggered:
            summary["recommendations"] = [
                "Chat: ask questions or answer agent clarifications before deciding",
                "Switch agent: 'switch analysis' or 'switch reporter'",
                "Delegate task: 'run analysis: calculate RMSF' or 'run: <task>'",
                "Multi-sim: 'run p23458 analysis: calculate Rg'",
                "Use 'recommend: <your advice>' to guide the agent on how to fix the issue",
                "Use 'retry' to let the agent try again from scratch",
                "Use 'modify: <instructions>' to specify exact changes",
                "Use 'show <filename>' to inspect generated files",
                "Use 'approved' / 'continue' to accept and proceed",
            ] + summary["recommendations"]
        else:
            summary["recommendations"] = [
                "Switch to another field agent: switch analysis | switch reporter | switch setup …",
                "Multi-sim sim binding: switch p23458 analysis | switch analysis p23458",
                "Combined (base level): switch combined analysis | switch combined reporter",
                "Ask the active agent to run a task: run analysis: <instructions> | run: <task>",
                "Multi-sim per-label run: run p23458 analysis: <instructions>",
                "Combined run: run combined analysis: <instructions> | run combined reporter: <task>",
            ] + summary["recommendations"]
            if summary.get("scope") == "combined" or state.get("multi_sim_phase", "").startswith("combined"):
                summary["recommendations"] = [
                    "You are at the COMBINED (cross-simulation) phase — outputs go to {base}/analysis and {base}/reporter",
                    "switch combined analysis — review/edit cross-sim overlays at project base",
                    "switch combined reporter — review combined HTML report",
                    "run combined analysis: <task> — e.g. overlay RMSF across all sims",
                ] + summary["recommendations"]

        return summary

    @classmethod
    def get_reporter_check_summary(cls, state: MDState) -> Dict[str, Any]:
        """Build a summary dict for the reporter checkpoint."""
        working_dir = state.get("working_directory", ".")
        reporter_dir = Path(working_dir) / "reporter"

        # Collect reporter output path(s)
        reporter_output = state.get("reporter_output")
        report_paths: List[str] = []
        if isinstance(reporter_output, str):
            report_paths = [reporter_output]
        elif isinstance(reporter_output, dict):
            report_paths = [v for v in reporter_output.values() if isinstance(v, str)]
        # Scan reporter dir for any HTML files not already listed
        if reporter_dir.is_dir():
            for html in sorted(reporter_dir.glob("*.html")):
                if str(html) not in report_paths:
                    report_paths.append(str(html))

        analysis_types = list((state.get("analysis_results") or {}).keys())
        figures = [Path(f).name for f in (state.get("figures") or [])]

        errors = state.get("errors", [])
        warnings = [w for w in state.get("warnings", []) if "Human" not in w]

        return {
            "checkpoint_type": "reporter",
            "error_triggered": False,
            "current_state": {
                "report_files": report_paths,
                "analysis_types_completed": analysis_types,
                "figures_generated": figures,
                "errors": errors[-5:] if errors else [],
                "warnings": warnings[-5:] if warnings else [],
            },
            "issues_found": [f"ERROR: {e}" for e in errors[-3:]] if errors else [],
            "recommendations": [
                "'done' / 'approved' — accept results and proceed",
                "'reporter' — regenerate the HTML report (optionally: 'reporter: <instructions>')",
                "'analysis: <instructions>' — re-run analysis with new instructions then re-report",
                "'switch analysis' — chat as Analysis agent (reload tools/artifacts)",
                "'run analysis: <task>' — delegate task to Analysis agent, return here after",
                "'run p23458 analysis: <task>' — run on one simulation (multi-sim)",
                "'preprocess' / 'setup' / 'hpc' — switch to that agent's HITL checkpoint",
                "'agents' — list field agents and artifact directories",
                "'show <filename>' — inspect a file",
                "'files' — list all generated files",
            ],
        }
