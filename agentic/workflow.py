"""
LLM-Powered MD Workflow with Intelligent Routing

This module implements the complete MD workflow that uses LLM reasoning
for dynamic routing and agent coordination.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from langgraph.graph import StateGraph, END
from .state import MDState
from .supervisor import MDSupervisor
from .preprocess import PreprocessingAgent
from .simsetup import SimulationSetupAgent
from .human_checkpoints import HumanCheckpoints
from .llm import LLMClient
from .hpc import MDHPCAgent
from .analysis import MDAnalysisAgent
from .planner import MDPlanner
from .reporter import ReporterAgent
from .utils.state_persistence import compact_state_for_persistence

logger = logging.getLogger(__name__)

_MULTISIM_SKIP_DIRS = frozenset({
    "supervisor", "planner", "programmer", "analysis", "reporter",
})


def _discover_multisim_labels(base_dir: str) -> list:
    """Return subdirectory labels that look like per-simulation workspaces."""
    base = Path(base_dir)
    if not base.is_dir():
        return []
    labels: list = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name in _MULTISIM_SKIP_DIRS:
            continue
        if (d / "supervisor" / "state.jsonl").exists() or (d / "analysis").is_dir():
            labels.append(d.name)
    return labels


def _multisim_per_sim_analysis_complete(base_dir: str) -> bool:
    """True when every discovered sim label has non-empty analysis output."""
    labels = _discover_multisim_labels(base_dir)
    if not labels:
        return False
    for label in labels:
        adir = Path(base_dir) / label / "analysis"
        if not adir.is_dir():
            return False
        if not any(adir.iterdir()):
            return False
    return True


def _multisim_per_sim_workflow_complete(base_dir: str, progress: Optional[Dict[str, Any]] = None) -> bool:
    """True when every sim has finished required agents (progress-aware)."""
    from agentic.multi_sim_progress import multisim_workflow_incomplete

    if progress:
        return not multisim_workflow_incomplete(progress)
    state_path = Path(base_dir) / "supervisor" / "state.jsonl"
    if state_path.is_file():
        try:
            entry = json.loads(state_path.read_text(encoding="utf-8"))
            saved_progress = (entry.get("state") or {}).get("multi_sim_progress")
            if saved_progress:
                return not multisim_workflow_incomplete(saved_progress)
        except Exception:
            pass
    return _multisim_per_sim_analysis_complete(base_dir)


class MDWorkflow:
    """
    Complete MD workflow with LLM-powered supervisor and agent coordination.
    
    HIERARCHY:
    - Supervisor: Orchestrates workflow, routes to agents
    - Planner: Creates detailed execution plans, coordinates programmer
    - Programmer: Generates scripts for planner (internal to planner)
    - Field Agents: Execute supervisor-assigned tasks (preprocess, setup, hpc, analysis)
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        if llm_client is None:
            raise ValueError("llm_client is required. Pass LLMClient from main script.")
        self.llm = llm_client
        
        # Initialize supervisor with LLM capabilities
        self.supervisor = MDSupervisor(llm_client=self.llm)
        
        # Initialize planner (planner will initialize programmer internally)
        self.planner = MDPlanner(llm_client=self.llm)
        
        # Initialize field-specific agents
        self.preprocessor = PreprocessingAgent(self.llm)
        self.setup_agent = SimulationSetupAgent(self.llm)
        self.hpc_agent = MDHPCAgent(self.llm)
        self.analysis_agent = MDAnalysisAgent(self.llm)
        self.reporter_agent = ReporterAgent(self.llm)
        self.checkpoints = HumanCheckpoints()
        
        # Build the graph
        self.graph = self._build_graph()
        
        logger.info("MD workflow initialized with supervisor → planner → programmer hierarchy")
    
    # Nodes that produce meaningful artifacts worth saving incrementally
    _SAVE_AFTER_NODES = frozenset({
        "input_validation", "planner", "preprocess",
        "setup", "hpc", "analysis", "reporter",
    })

    def _wrap_node(self, node_name: str, node_func: Callable) -> Callable:
        """Wrap a node function to track current_node and save progress."""
        def wrapped_node(state: MDState) -> MDState:
            state["current_node"] = node_name
            result = node_func(state)
            if result is None:
                logger.error(f"Node '{node_name}' returned None – returning input state as fallback")
                return state
            # Save incremental state after key stages (used by non-HITL run())
            if node_name in self._SAVE_AFTER_NODES:
                try:
                    self._save_progress(result, node_name)
                except Exception as exc:
                    logger.debug(f"Incremental save after {node_name} failed: {exc}")
            return result
        return wrapped_node
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow with proper agent hierarchy."""
        
        # Create the graph with our state
        workflow = StateGraph(MDState)
        
        # Add all nodes with wrapper to track current_node
        workflow.add_node("supervisor", self._wrap_node("supervisor", self.supervisor.supervisor_node))
        workflow.add_node("input_validation", self._wrap_node("input_validation", self.supervisor.input_validation_node))
        workflow.add_node("planner", self._wrap_node("planner", self.planner.planner_node))
        workflow.add_node("preprocess", self._wrap_node("preprocess", self.preprocessor.preprocess_node))
        workflow.add_node("setup", self._wrap_node("setup", self.setup_agent.setup_node))
        workflow.add_node("hpc", self._wrap_node("hpc", self.hpc_agent.hpc_node))
        workflow.add_node("analysis", self._wrap_node("analysis", self.analysis_agent.analysis_node))
        workflow.add_node("reporter", self._wrap_node("reporter", self.reporter_agent.reporter_node))
        workflow.add_node("human_preprocess_check", self._wrap_node("human_preprocess_check", self.checkpoints.human_preprocess_check))
        workflow.add_node("human_setup_check", self._wrap_node("human_setup_check", self.checkpoints.human_setup_check))
        workflow.add_node("human_hpc_check", self._wrap_node("human_hpc_check", self.checkpoints.human_hpc_check))
        workflow.add_node("human_hpc_pool_check", self._wrap_node("human_hpc_pool_check", self.checkpoints.human_hpc_pool_check))
        workflow.add_node("human_analysis_check", self._wrap_node("human_analysis_check", self.checkpoints.human_analysis_check))
        workflow.add_node("human_reporter_check", self._wrap_node("human_reporter_check", self.checkpoints.human_reporter_check))
        workflow.add_node("final_report", self._wrap_node("final_report", self._final_report_node))
        workflow.add_node("hpc_pool_wait", self._wrap_node("hpc_pool_wait", self._hpc_pool_wait_node))
        
        # Set entry point
        workflow.set_entry_point("supervisor")
        
        # ========== SUPERVISOR ROUTING ==========
        # Supervisor can route to: input_validation, planner, or field agents
        workflow.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                "input_validation": "input_validation",
                "planner": "planner",
                "preprocess": "preprocess", 
                "setup": "setup",
                "hpc": "hpc",
                "analysis": "analysis",
                "reporter": "reporter",
                "human_reporter_check": "human_reporter_check",
                "human_hpc_pool_check": "human_hpc_pool_check",
                "hpc_pool_wait": "hpc_pool_wait",
                "final_report": "final_report",
                END: END
            }
        )
        
        workflow.add_conditional_edges(
            "hpc_pool_wait",
            lambda state: state.get("next_node", "supervisor"),
            {"supervisor": "supervisor"},
        )

        workflow.add_conditional_edges(
            "human_hpc_pool_check",
            lambda state: state.get("next_node", "supervisor"),
            {"supervisor": "supervisor", "human_hpc_pool_check": "human_hpc_pool_check"},
        )
        
        # ========== INPUT VALIDATION ==========
        # Always routes back to supervisor
        workflow.add_conditional_edges(
            "input_validation",
            lambda state: state.get("next_node", "supervisor"),
            {"supervisor": "supervisor"}
        )
        
        # ========== PLANNER (handles programmer internally) ==========
        # Planner only routes back to supervisor
        # Programmer is called internally by planner, never appears in graph
        workflow.add_conditional_edges(
            "planner",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor"
            }
        )
        
        # ========== FIELD AGENTS - PREPROCESSING ==========
        workflow.add_conditional_edges(
            "preprocess",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "human_preprocess_check": "human_preprocess_check"
            }
        )
        
        # Human preprocessing checkpoint
        workflow.add_conditional_edges(
            "human_preprocess_check",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "preprocess": "preprocess"
            }
        )
        
        # ========== FIELD AGENTS - SETUP ==========
        workflow.add_conditional_edges(
            "setup", 
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "human_setup_check": "human_setup_check"
            }
        )
        
        # Human setup checkpoint
        workflow.add_conditional_edges(
            "human_setup_check",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "setup": "setup"
            }
        )
        
        # ========== FIELD AGENTS - HPC ==========
        workflow.add_conditional_edges(
            "hpc",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "human_hpc_check": "human_hpc_check"
            }
        )
        
        # Human HPC checkpoint
        workflow.add_conditional_edges(
            "human_hpc_check",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "hpc": "hpc"
            }
        )
        
        # ========== FIELD AGENTS - ANALYSIS ==========
        # ========== FIELD AGENTS - ANALYSIS ==========
        workflow.add_conditional_edges(
            "analysis",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "human_analysis_check": "human_analysis_check"
            }
        )
        
        # Human analysis checkpoint
        workflow.add_conditional_edges(
            "human_analysis_check",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "analysis": "analysis"
            }
        )
        
        # ========== FIELD AGENTS - REPORTER ==========
        # Reporter routes to human_reporter_check (auto-skipped unless --HITL).
        workflow.add_conditional_edges(
            "reporter",
            lambda state: state.get("next_node", "human_reporter_check"),
            {
                "supervisor": "supervisor",
                "human_reporter_check": "human_reporter_check",
            }
        )

        # ========== REPORTER CHECKPOINT ==========
        # Skipped unless --HITL (routes supervisor → final_report).
        # In HITL mode: supports reporter re-run, analysis re-run, checkpoint switching.
        workflow.add_conditional_edges(
            "human_reporter_check",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor",
                "analysis": "analysis",
                "reporter": "reporter",
                "human_reporter_check": "human_reporter_check",  # waiting for input
                # Earlier HITL checkpoints the user can switch to
                "human_preprocess_check": "human_preprocess_check",
                "human_setup_check": "human_setup_check",
                "human_hpc_check": "human_hpc_check",
                "human_analysis_check": "human_analysis_check",
            }
        )
        
        # ========== FINAL REPORT ==========
        workflow.add_edge("final_report", END)
        
        return workflow.compile()
    
    def _route_from_supervisor(self, state: MDState) -> str:
        """
        Route from supervisor based on next_node field.
        
        Supervisor decides which field agent to invoke or whether to create plan.
        """
        next_node = state.get("next_node")
        
        valid_nodes = [
            "input_validation", "planner", "preprocess", "setup", 
            "hpc", "analysis", "reporter", "human_reporter_check",
            "human_hpc_pool_check", "hpc_pool_wait", "final_report"
        ]
        
        if next_node in valid_nodes:
            logger.info(f"Supervisor routing to: {next_node}")
            return next_node
        
        logger.warning(f"Invalid next_node: {next_node}, defaulting to final_report")
        return "final_report"
    
    def _hpc_pool_wait_node(self, state: MDState) -> MDState:
        """Sleep until the next SLURM poll while cross-sim HPC jobs run."""
        import time
        from agentic.multi_sim_hpc_pool import init_hpc_pool, pool_summary

        pool = init_hpc_pool(state)
        interval = int(pool.get("check_interval_sec") or state.get("hpc_check_interval_sec") or 7200)
        summary = state.get("hpc_pool_status_summary") or pool_summary(state)
        from agentic.multi_sim_hpc_pool import log_pool_to_base

        log_pool_to_base(
            state,
            f"Pool sleep — next SLURM check in {interval}s",
            pool=pool,
            extra={"summary": summary},
        )
        logger.info(
            "HPC pool: sleeping %ss before next SLURM check\n%s",
            interval,
            summary,
        )
        print(
            f"\n--- HPC pool status (next check in {interval // 60} min) ---\n"
            f"{summary}\n",
            flush=True,
        )
        time.sleep(interval)
        state["next_node"] = "supervisor"
        return state
    
    def _final_report_node(self, state: MDState) -> MDState:
        """Generate enhanced final workflow report using LLM when available."""
        
        if self.llm:
            report = self._generate_llm_report(state)
        else:
            report = self._generate_fallback_report(state)
        
        state["final_report"] = report
        if state.get("is_multi_simulation"):
            from agentic.multi_sim_progress import multisim_workflow_incomplete

            if multisim_workflow_incomplete(state.get("multi_sim_progress")):
                state["workflow_status"] = "in_progress:interrupted"
            else:
                state["workflow_status"] = "completed"
        else:
            state["workflow_status"] = "completed"
        
        # Save execution report and state to working_dir/supervisor/
        self._save_execution_report(state, report, stage="final_report")
        self._save_workflow_state(state)
        
        return state
    
    def _generate_llm_report(self, state: MDState) -> str:
        """Generate comprehensive report using LLM analysis."""
        
        summary = self._generate_workflow_summary(state)
        
        prompt = f"""
Generate a comprehensive MD workflow completion report.

WORKFLOW SUMMARY:
{summary}

ERRORS: {len(state.get('errors', []))} total
{chr(10).join(state.get('errors', [])[:5])}

WARNINGS: {len(state.get('warnings', []))} total

Create a professional summary including:
1. Workflow status (success/partial/failed)
2. Agents executed and results
3. Files generated
4. Any issues encountered
5. Next steps recommendations
"""
        
        try:
            report = self.llm.prompt(prompt)
            return report
        except Exception as e:
            logger.error(f"Error generating LLM report: {e}")
            return self._generate_fallback_report(state)
    
    def _generate_fallback_report(self, state: MDState) -> str:
        """Generate standard report when LLM is not available."""
        
        summary = self._generate_workflow_summary(state)
        
        report = f"""
=== MD WORKFLOW COMPLETION REPORT ===

Status: {'✅ SUCCESS' if not state.get('errors') else '❌ FAILED'}

WORKFLOW SUMMARY:
{summary}

Files Generated: {len(state.get('figures', []))} figures, {len(state.get('mdp_files', {}))} MDP files

Total Errors: {len(state.get('errors', []))}
Total Warnings: {len(state.get('warnings', []))}

Execution Path: {' → '.join(state.get('execution_path', []))}
"""
        return report
    
    def _generate_workflow_summary(self, state: MDState) -> Dict[str, Any]:
        """Generate a summary of the entire workflow execution."""
        
        summary = {
            "user_goal": state.get("user_goal", "Not specified"),
            "agents_used": [],
            "total_errors": len(state.get("errors", [])),
            "total_warnings": len(state.get("warnings", [])),
            "supervisor_decisions": [],
            "final_outputs": {},
            "execution_path": state.get("execution_path", [])
        }
        
        # Collect agent usage
        for agent in ["preprocessing", "setup", "hpc", "analysis", "planner"]:
            if state.get(f"{agent}_completed"):
                summary["agents_used"].append(agent)
        
        # Collect supervisor decisions
        if "supervisor_reasoning" in state:
            summary["supervisor_decisions"] = state.get("all_supervisor_decisions", [])
        
        # Collect final outputs
        output_keys = [
            "cleaned_pdb", "topology", "coordinates", 
            "mdp_files", "figures", "analysis_results"
        ]
        for key in output_keys:
            if state.get(key):
                summary["final_outputs"][key] = str(state[key])[:100]
        
        return summary
    
    def _save_execution_report(self, state: MDState, report: str, stage: str = None):
        """Save execution_report.md to working_dir/supervisor/.
        
        Args:
            state: Current workflow state.
            report: Optional LLM-generated summary or progress note.
            stage: Optional current stage label (e.g. 'planner', 'preprocess').
        """
        try:
            working_dir = state.get("working_directory", ".")
            supervisor_dir = Path(working_dir) / "supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            report_path = supervisor_dir / "execution_report.md"
            
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Build a concise markdown report
            wf_status = state.get("workflow_status", "")
            if wf_status and wf_status.startswith("in_progress"):
                status = f"IN PROGRESS ({stage or wf_status})" 
            elif not state.get('errors'):
                status = 'SUCCESS'
            else:
                status = 'COMPLETED WITH ERRORS'

            lines = [
                f"# MD Workflow Execution Report",
                f"",
                f"**Generated:** {ts}  ",
                f"**Status:** {status}",
                f"",
                f"---",
                f"",
                f"## User Prompt",
                f"",
                f"> {state.get('user_goal', 'N/A')}",
                f"",
            ]
            
            # Enriched prompt
            rephrased = state.get("rephrased_goal") or state.get("enriched_prompt")
            if rephrased:
                lines += [
                    f"## Enriched Prompt",
                    f"",
                    f"{rephrased}",
                    f"",
                ]
            
            # Execution Plan (from planner)
            plan = state.get("execution_plan")
            if plan and isinstance(plan, dict):
                lines += [f"## Execution Plan", f""]
                if plan.get("title"):
                    lines.append(f"**{plan['title']}**")
                    lines.append("")
                agent_seq = plan.get("agent_sequence", [])
                if agent_seq:
                    lines.append(f"Agent sequence: {' → '.join(agent_seq)}")
                    lines.append("")
                full_plan = plan.get("full_plan", "")
                if full_plan:
                    # Truncate very long plans
                    lines.append(full_plan[:3000] + ("..." if len(full_plan) > 3000 else ""))
                    lines.append("")

            # Agents executed
            exec_path = state.get("execution_path", [])
            if exec_path:
                seen = set()
                agents = []
                for node in exec_path:
                    if node not in seen and node not in ("supervisor", "input_validation", "final_report"):
                        seen.add(node)
                        agents.append(node)
                if agents:
                    lines += [
                        f"## Agents Executed",
                        f"",
                        f"{' → '.join(agents)}",
                        f"",
                    ]

            # Key Artifacts produced so far
            artifacts = []
            if state.get("cleaned_pdb"):
                artifacts.append(f"- Cleaned PDB: `{state['cleaned_pdb']}`")
            if state.get("topology"):
                artifacts.append(f"- Topology: `{state['topology']}`")
            if state.get("coordinates"):
                artifacts.append(f"- Coordinates: `{state['coordinates']}`")
            mdp = state.get("mdp_files", {})
            if mdp:
                artifacts.append(f"- MDP files: {', '.join(f'`{k}`' for k in mdp)}")
            if state.get("job_script"):
                artifacts.append(f"- Job script: `{state['job_script']}`")
            figs = state.get("figures", [])
            if figs:
                artifacts.append(f"- Figures: {len(figs)} generated")
            if artifacts:
                lines += [f"## Key Artifacts", f""] + artifacts + [f""]

            # Errors & Warnings (only if present)
            errors = state.get("errors", [])
            warnings = state.get("warnings", [])
            
            # Human Recommendations (if any were given during HITL)
            human_rec = state.get("human_recommendation")
            # Also gather recommendation entries from warnings
            rec_entries = [w for w in warnings if "Human recommendation" in w or "Human modification" in w or "Human modify" in w]
            if human_rec or rec_entries:
                lines += [f"## Human Recommendations", f""]
                if human_rec:
                    lines.append(f"**Active recommendation:** {human_rec}")
                    lines.append("")
                if rec_entries:
                    for r in rec_entries:
                        lines.append(f"- {r}")
                    lines.append("")
                # Show parameter overrides
                param_overrides = []
                if state.get("force_field"):
                    param_overrides.append(f"Force field: {state['force_field']}")
                if state.get("water_model"):
                    param_overrides.append(f"Water model: {state['water_model']}")
                if state.get("temperature"):
                    param_overrides.append(f"Temperature: {state['temperature']} K")
                if state.get("pressure"):
                    param_overrides.append(f"Pressure: {state['pressure']} bar")
                if param_overrides:
                    lines.append("**Current parameters:** " + " | ".join(param_overrides))
                    lines.append("")
            
            if errors:
                lines += [f"## Errors ({len(errors)})", f""]
                for e in errors:
                    lines.append(f"- {e}")
                lines.append("")
            if warnings:
                lines += [f"## Warnings ({len(warnings)})", f""]
                for w in warnings:
                    lines.append(f"- {w}")
                lines.append("")
            
            # LLM-generated summary
            if report:
                lines += [f"## Summary", f"", report, f""]
            
            report_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"Execution report saved to {report_path}")
            
        except Exception as e:
            logger.error(f"Failed to save execution report: {e}")
    
    def _save_progress(self, state: MDState, stage: str):
        """Save incremental state and execution report after a workflow stage.
        
        Called after each major stage so that HITL checkpoints and the
        interactive Q&A handler always have up-to-date context files.
        """
        state["workflow_status"] = f"in_progress:{stage}"
        self._save_workflow_state(state)
        progress = f"Workflow in progress — last completed stage: **{stage}**"
        self._save_execution_report(state, progress, stage=stage)

    def _save_workflow_state(self, state: MDState):
        """Save serializable workflow state to working_dir/supervisor/state.jsonl."""
        try:
            if state.get("is_multi_simulation") and state.get("sim_prompts"):
                from agentic.multi_sim_progress import ensure_multi_sim_progress

                ensure_multi_sim_progress(state)

            working_dir = state.get("working_directory", ".")
            supervisor_dir = Path(working_dir) / "supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            state_path = supervisor_dir / "state.jsonl"
            
            # Build a serializable snapshot of the state
            snapshot = compact_state_for_persistence(dict(state))
            serializable_state = {}
            for key, value in snapshot.items():
                try:
                    json.dumps(value, default=str)
                    serializable_state[key] = value
                except (TypeError, ValueError):
                    serializable_state[key] = str(value)

            # Never mark completed in state file while multisim loop is incomplete
            persist_status = state.get("workflow_status", "unknown")
            if (
                state.get("is_multi_simulation")
                and persist_status == "completed"
            ):
                from agentic.multi_sim_progress import multisim_workflow_incomplete

                if multisim_workflow_incomplete(state.get("multi_sim_progress")):
                    persist_status = state.get("workflow_status") or "in_progress:checkpoint"
                    if not str(persist_status).startswith("in_progress"):
                        persist_status = "in_progress:checkpoint"

            # HITL: keep multi-sim base working_directory stable when view is per-sim
            if (
                state.get("is_multi_simulation")
                and state.get("multi_sim_base_dir")
                and state.get("hitl_target_sim_label")
            ):
                serializable_state["working_directory"] = str(
                    Path(state["multi_sim_base_dir"]).resolve()
                )
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "workflow_status": persist_status,
                "state": serializable_state,
            }
            
            # Overwrite with a single entry so the file is always the latest state
            state_path.write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")

            # In multi-simulation mode, mirror the latest state at the base
            # working directory as a resume checkpoint for subsequent reruns.
            multi_base_dir = state.get("multi_sim_base_dir")
            if state.get("is_multi_simulation") and multi_base_dir:
                base_dir = Path(str(multi_base_dir)).resolve()
                current_dir = Path(str(working_dir)).resolve()
                if base_dir != current_dir:
                    base_supervisor_dir = base_dir / "supervisor"
                    base_supervisor_dir.mkdir(parents=True, exist_ok=True)
                    base_state_path = base_supervisor_dir / "state.jsonl"
                    base_state_path.write_text(
                        json.dumps(entry, indent=2, default=str) + "\n",
                        encoding="utf-8"
                    )
            
            logger.info(f"Workflow state saved to {state_path}")
            
        except Exception as e:
            logger.error(f"Failed to save workflow state: {e}")
    
    def _load_workflow_state(self, working_dir: str) -> Optional[Dict[str, Any]]:
        """Load the most recent workflow state from working_dir/supervisor/state.jsonl.
        
        Returns the last saved state dict, or None if no saved state exists.
        """
        state_path = Path(working_dir) / "supervisor" / "state.jsonl"
        if not state_path.exists():
            return None
        
        try:
            content = state_path.read_text(encoding="utf-8").strip()
            if not content:
                return None
            entry = json.loads(content)
            saved_state = entry.get("state")
            if saved_state:
                # Expose save metadata to restore policy in _initialize_state.
                saved_state["_saved_workflow_status"] = entry.get("workflow_status")
                saved_state["_saved_timestamp"] = entry.get("timestamp")
                logger.info(
                    f"Loaded previous workflow state from {state_path} "
                    f"(status={entry.get('workflow_status')}, ts={entry.get('timestamp')})"
                )
            return saved_state
        except Exception as e:
            logger.warning(f"Failed to load workflow state from {state_path}: {e}")
            return None
    
    def _initialize_state(self, user_goal: str, config: Optional[Dict[str, Any]]) -> MDState:
        """Create initial workflow state with config overrides applied."""
        # Note: TypedDict is a type hint only, cannot be instantiated as a class.
        # Use a plain dict instead and let Python's type system handle validation.
        state: MDState = {
            "user_goal": user_goal,
            "md_engine": "gromacs",
            "force_field": "amber99sb-ildn",
            "water_model": "tip3p",
            "production_ns": None,
            "extended_minimization": config.get("extended_minimization", False),
            "human_in_loop": False,
            "hitl_mode": None,
            "preprocessing_issues": [],
            "setup_issues": [],
            "mdp_files": {},
            "analysis_results": {},
            "figures": [],
            "errors": [],
            "warnings": [],
            "next_node": None,
            "human_feedback": None,
            "working_directory": None,
            "execution_path": [],
            "execution_plan": None,
            "plan_executed": False,
            "rephrased_goal": None,
            "enriched_prompt": None,
            "master_enriched_prompt": None,
            "user_goal_original": None,
            "current_node": None,
            "file_registry": {},
            "generated_files": {},
            "subtask_type": None,
            "subtask_type_initialized": None,
            "agent_list": None,
            "required_inputs": None,
            "input_validated": None,
            "analysis_directory": None,
            "trajectory_paths": None,
            "system_info": None,
            "pdb_analysis": None,
            "component_selection": {},
            "structured_prompt": None,
            "raw_pdb": None,
            "cleaned_pdb": None,
            "preprocessing_report": None,
            "topology": None,
            "coordinates": None,
            "setup_report": None,
            "hpc_action": None,
            "job_script": None,
            "job_id": None,
            "job_status": None,
            "trajectory_path": None,
            "energy_file": None,
            "hpc_report": None,
            "analysis_action": "full_analysis",
            "analysis_request": None,
            "conclusions": None,
            # Agent-specific instruction sections (extracted from the full execution
            # plan by supervisor._extract_agent_specific_plans after planner returns)
            "preprocessing_instructions": None,
            "setup_instructions": None,
            "hpc_instructions": None,
            "analysis_instructions": None,
            # Agent execution tracking
            "current_agent_idx": 0,
            "preprocess_retry_count": 0,
            "setup_retry_count": 0,
            "hpc_retry_count": 0,
            "analysis_retry_count": 0,
            "reporter_retry_count": 0,
            # Intermediate validation artifacts
            "pdb_summary": None,
            "file_info": None,
            "reporter_file_info": None,
            # Reporter stage
            "reporter_output": None,
            "report_type": "comprehensive",
            "include_literature": True,
            "literature_keywords": None,
            "reporter_plan": None,
            "reporter_instructions": None,
            # Final report
            "final_report": None,
            "workflow_status": None,
            "human_final_decision": None,
            # Human-in-the-loop
            "human_recommendation": None,
            "error_triggered_hitl": False,
            # Multi-simulation mode
            "is_multi_simulation": False,
            "multi_sim_phase": None,
            "pdb_list": None,
            "sim_prompts": None,
            "run_combined_analysis": None,
            "combined_analysis_plan": None,
            "current_sim_index": 0,
            "completed_sim_states": None,
            "sim_working_dirs": None,
            "multi_sim_base_dir": None,
            "combined_only": False,
            "resume_failed_only": None,
            "retry_labels": None,
            "_resume_succeeded_labels": None,
            "hpc_pool": None,
            "allowed_hpc_jobs": None,
            "hpc_check_interval_sec": None,
            "hpc_check_interval": None,
            "post_hpc_analysis_only": False,
            "hpc_pool_phase_complete": False,
        }

        if config:
            state.update(config)

        if state.get("pdb_list") is None:
            state["pdb_list"] = []

        # CRITICAL: Convert working_directory to absolute path to prevent nested directory creation
        # This ensures that even if agents use os.chdir(), paths remain correct
        working_dir = state.get("working_directory", "working_dir")
        if working_dir == ".":
            working_dir = "working_dir"  # Use working_dir instead of current directory
        if not Path(working_dir).is_absolute():
            working_dir = str(Path.cwd() / working_dir)
        state["working_directory"] = working_dir

        if state.get("is_multi_simulation"):
            state["multi_sim_base_dir"] = working_dir
        
        # In multi-sim mode, agent sub-directories live inside each per-simulation
        # directory (e.g. {basepath}/1A/analysis/).  Only shared dirs are created at
        # basepath level: planner/, programmer/, supervisor/.
        # Combined analysis/reporter dirs are created by supervisor when needed.
        if state.get("is_multi_simulation"):
            Path(working_dir).mkdir(parents=True, exist_ok=True)
            for shared_dir in ("planner", "programmer", "supervisor"):
                Path(working_dir, shared_dir).mkdir(parents=True, exist_ok=True)
            # Placeholder dir state — per-sim supervisor will overwrite these
            state["preprocess_dir"] = str(Path(working_dir) / "preprocess")
            state["simsetup_dir"] = str(Path(working_dir) / "simsetup")
            state["hpc_dir"] = str(Path(working_dir) / "hpc")
            state["analysis_dir"] = str(Path(working_dir) / "analysis")
        else:
            # Single-sim: set all dir state fields unconditionally (agents may read them)
            state["preprocess_dir"] = str(Path(working_dir) / "preprocess")
            state["simsetup_dir"] = str(Path(working_dir) / "simsetup")
            state["hpc_dir"] = str(Path(working_dir) / "hpc")
            state["analysis_dir"] = str(Path(working_dir) / "analysis")

            # Determine which agent directories to actually create on disk.
            # Only create directories for agents that will run in this subtask so
            # the working directory stays clean and unambiguous.
            _AGENT_DIR_MAP = {
                "preprocess": state["preprocess_dir"],
                "simsetup":   state["simsetup_dir"],
                "hpc":        state["hpc_dir"],
                "analysis":   state["analysis_dir"],
                "reporter":   str(Path(working_dir) / "reporter"),
            }
            _SUBTASK_AGENTS = {
                "preprocess_only": ["preprocess"],
                "setup_only":      ["simsetup"],
                "hpc_only":        ["hpc"],
                "analysis_only":   ["analysis"],
                "reporter_only":   ["reporter"],
                "full_task":       list(_AGENT_DIR_MAP.keys()),
            }
            # CLI agent name → directory key mapping for multi_agent mode
            _CLI_TO_DIR_KEY = {
                "preprocess": "preprocess",
                "simsetup":   "simsetup",
                "hpcjob":     "hpc",
                "analysis":   "analysis",
                "reporter":   "reporter",
            }

            subtask_type = state.get("subtask_type") or "full_task"
            if subtask_type == "multi_agent":
                agent_list = state.get("agent_list") or []
                agents_needed = [_CLI_TO_DIR_KEY[a] for a in agent_list if a in _CLI_TO_DIR_KEY]
            else:
                agents_needed = _SUBTASK_AGENTS.get(subtask_type, list(_AGENT_DIR_MAP.keys()))

            # supervisor/planner/programmer always needed (state, plans, generated tools)
            dirs_to_create = [_AGENT_DIR_MAP[a] for a in agents_needed] + \
                             [str(Path(working_dir) / d) for d in ("supervisor", "planner", "programmer")]
            for agent_dir in dirs_to_create:
                Path(agent_dir).mkdir(parents=True, exist_ok=True)
        
        # Check for saved workflow state from a previous run
        saved_state = self._load_workflow_state(working_dir)
        if saved_state:
            saved_subtask = saved_state.get("subtask_type")
            current_subtask = state.get("subtask_type")
            saved_agents = saved_state.get("agent_list")
            current_agents = state.get("agent_list")
            saved_status = saved_state.get("_saved_workflow_status")

            same_subtask_signature = (
                saved_subtask == current_subtask
                and list(saved_agents or []) == list(current_agents or [])
            )
            is_completed_snapshot = str(saved_status).startswith("completed")

            # Auto-resume interrupted multi-sim runs from base/per-sim state files.
            if (
                state.get("is_multi_simulation")
                and not state.get("combined_only")
                and not state.get("resume_failed_only")
            ):
                from agentic.multi_sim_progress import multisim_workflow_incomplete

                saved_progress = saved_state.get("multi_sim_progress")
                if multisim_workflow_incomplete(saved_progress):
                    state["resume_failed_only"] = True
                    is_completed_snapshot = False
                    logger.info(
                        "[multi-sim] Incomplete progress in saved state — "
                        "auto-resuming (q7rtn6/q96c45 etc. need not use --resume)"
                    )
                elif str(saved_status).startswith("in_progress") and saved_state.get("sim_prompts"):
                    state["resume_failed_only"] = True
                    is_completed_snapshot = False
                    logger.info(
                        "[multi-sim] in_progress snapshot with sim_prompts — auto-resuming"
                    )

            # Multi-simulation loop bookkeeping: restore when resuming (explicit or auto).
            multisim_loop_restore = (
                state.get("is_multi_simulation")
                and not state.get("combined_only")
                and state.get("resume_failed_only")
            )

            # Restore artifact paths and completed-stage outputs so agents
            # can skip already-finished work.  Control-flow and retry counters
            # are intentionally NOT restored — the workflow re-evaluates routing
            # fresh each time.
            restore_keys = [
                # Preprocessing outputs
                "raw_pdb", "cleaned_pdb", "preprocessing_report",
                "pdb_analysis", "component_selection", "file_registry", "generated_files",
                "ligand_files", "ligand_resnames", "ion_files", "ion_resnames",
                # Setup outputs
                "topology", "coordinates", "mdp_files", "setup_report",
                # HPC outputs
                "job_script", "job_id", "job_status", "trajectory_path", "energy_file",
                "hpc_report", "hpc_output_directory",
                # Analysis outputs
                "analysis_results", "figures", "conclusions",
                # Reporter outputs
                "reporter_output",
                # Enriched prompt / plan (avoid re-doing expensive LLM calls)
                "rephrased_goal", "enriched_prompt", "master_enriched_prompt",
                "user_goal_original",
                "execution_plan",
                "structured_prompt", "pdb_summary",
                # Agent instructions
                "preprocessing_instructions", "setup_instructions",
                "hpc_instructions", "analysis_instructions", "reporter_instructions",
                # HITL session (agent switch / sim binding across checkpoints)
                "hitl_active_agent", "hitl_target_sim_label", "hitl_sim_dirs",
                "hitl_agent_working_directory",                 "hitl_agent_output_directory",
                "multi_sim_progress",
                "hpc_pool",
                "allowed_hpc_jobs",
                "hpc_check_interval_sec",
                "post_hpc_analysis_only",
                "hpc_pool_phase_complete",
            ]

            # Multi-simulation progress bookkeeping is restored when resuming.
            if multisim_loop_restore:
                restore_keys.extend([
                    "multi_sim_phase",
                    "sim_prompts",
                    "run_combined_analysis",
                    "combined_analysis_plan",
                    "current_sim_index",
                    "completed_sim_states",
                    "sim_working_dirs",
                    "multi_sim_base_dir",
                    "master_enriched_prompt",
                    "all_pdb_analyses",
                    "user_goal_original",
                    "enriched_prompt",
                    "rephrased_goal",
                    "structured_prompt",
                ])

            # For a completed snapshot or a different subtask signature,
            # avoid restoring stale planning/results that can short-circuit
            # routing in subsequent stage runs (for example stage-2 analysis).
            if is_completed_snapshot or not same_subtask_signature:
                skip_stale_keys = {
                    "execution_plan",
                    "analysis_results",
                    "reporter_output",
                    "rephrased_goal",
                    "enriched_prompt",
                    "master_enriched_prompt",
                    "user_goal_original",
                    "structured_prompt",
                    "preprocessing_instructions",
                    "setup_instructions",
                    "hpc_instructions",
                    "analysis_instructions",
                    "reporter_instructions",
                    "sim_prompts",
                    "run_combined_analysis",
                    "combined_analysis_plan",
                    "multi_sim_phase",
                    "current_sim_index",
                    "completed_sim_states",
                    "all_pdb_analyses",
                }
                # In resume mode, keep multi-sim bookkeeping so the supervisor can
                # identify which sims have already succeeded and skip them.
                if state.get("resume_failed_only") and state.get("is_multi_simulation"):
                    skip_stale_keys -= {
                        "sim_prompts",
                        "run_combined_analysis",
                        "combined_analysis_plan",
                        "completed_sim_states",
                        "master_enriched_prompt",
                        "all_pdb_analyses",
                        "enriched_prompt",
                        "rephrased_goal",
                        "structured_prompt",
                        "user_goal_original",
                        "multi_sim_phase",
                        "current_sim_index",
                    }
                restore_keys = [k for k in restore_keys if k not in skip_stale_keys]
                logger.info(
                    "Restore policy: skipping stale planning/results keys "
                    f"(completed={is_completed_snapshot}, same_signature={same_subtask_signature}, "
                    f"resume={state.get('resume_failed_only', False)})"
                )

            for key in restore_keys:
                if key in saved_state and saved_state[key] is not None:
                    state[key] = saved_state[key]

            if state.get("is_multi_simulation"):
                from agentic.multi_sim_progress import (
                    rebuild_progress_from_disk,
                    sync_state_from_progress,
                )

                if state.get("multi_sim_progress"):
                    sync_state_from_progress(state)
                    from agentic.multi_sim_progress import ensure_per_sim_working_directory

                    ensure_per_sim_working_directory(state)
                elif state.get("sim_prompts"):
                    rebuild_progress_from_disk(state, working_dir)

            if state.get("is_multi_simulation") and (is_completed_snapshot or not same_subtask_signature):
                if state.get("resume_failed_only"):
                    # Resume: keep sim_prompts + progress; re-enter per-sim loop.
                    state["multi_sim_phase"] = None
                    state["execution_plan"] = None
                    state["plan_executed"] = False
                    logger.info(
                        "[resume] Multi-sim state preserved — supervisor will continue "
                        "from multi_sim_progress"
                    )
                else:
                    state["multi_sim_phase"] = None
                    state["current_sim_index"] = 0
                    state["completed_sim_states"] = None
                    state["sim_prompts"] = None
                    state["run_combined_analysis"] = None
                    state["combined_analysis_plan"] = None
                    state["master_enriched_prompt"] = None
                    state["user_goal_original"] = None
                    state["all_pdb_analyses"] = []

            # Fresh multi-sim run (no --resume): never inherit a mid-loop checkpoint.
            if (
                state.get("is_multi_simulation")
                and not state.get("combined_only")
                and not state.get("resume_failed_only")
                and saved_state
            ):
                state["multi_sim_base_dir"] = working_dir
                state["multi_sim_phase"] = None
                state["current_sim_index"] = 0
                state["completed_sim_states"] = None
                state["sim_prompts"] = None
                state["run_combined_analysis"] = None
                state["combined_analysis_plan"] = None
                state["execution_plan"] = None
                state["plan_executed"] = False
                state["current_agent_idx"] = 0
                state["enriched_prompt"] = None
                state["rephrased_goal"] = None
                state["master_enriched_prompt"] = None
                state["analysis_results"] = {}
                state["reporter_output"] = None
                state["figures"] = []
                state["input_validated"] = False
                logger.info(
                    "[multi-sim] Fresh run — cleared stale loop/checkpoint state; "
                    "supervisor will enrich, build master plan, then enter per-sim loop"
                )
            
            logger.info("Restored previous workflow state — supervisor will skip completed stages")

            from agentic.multi_sim_hpc_pool import resume_hpc_pool_if_needed, reconcile_post_hpc_with_pool

            if reconcile_post_hpc_with_pool(state):
                logger.info(
                    "[resume] Cleared premature post-HPC state — HPC pool still active"
                )
            elif state.get("hpc_pool") or state.get("multi_sim_phase") == "hpc_pool":
                if resume_hpc_pool_if_needed(state):
                    logger.info("[resume] Re-entered cross-sim HPC pool from saved state")

        # HITL re-run after per-sim work already exists: skip the full per-sim loop
        # and enter combined analysis + reporter (with human checkpoints).
        if (
            state.get("human_in_loop")
            and state.get("hitl_mode") == "all"
            and state.get("is_multi_simulation")
            and not state.get("combined_only")
            and not state.get("resume_failed_only")
            and _multisim_per_sim_workflow_complete(
                working_dir, state.get("multi_sim_progress")
            )
        ):
            state["combined_only"] = True
            logger.info(
                "[hitl] Per-simulation analysis outputs found on disk — "
                "auto-enabling combined-only mode for interactive review"
            )

        # --combined-only reruns must not inherit per-sim routing from a saved state.
        if state.get("combined_only"):
            base_dir = state.get("working_directory")
            for _k, _default in (
                ("multi_sim_phase", None),
                ("execution_plan", None),
                ("plan_executed", False),
                ("current_agent_idx", 0),
                ("current_sim_index", 0),
                ("enriched_prompt", None),
                ("rephrased_goal", None),
                ("analysis_results", {}),
                ("reporter_output", None),
                ("raw_pdb", None),
                ("trajectory_path", None),
                ("topology", None),
                ("coordinates", None),
                ("job_id", None),
                ("analysis_instructions", None),
                ("reporter_instructions", None),
                ("sim_prompts", None),
                ("completed_sim_states", None),
                ("run_combined_analysis", None),
                ("combined_analysis_plan", None),
                ("input_validated", True),
                ("subtask_type_initialized", False),
            ):
                state[_k] = _default
            state["figures"] = []
            if base_dir:
                state["multi_sim_base_dir"] = base_dir
                state["working_directory"] = base_dir
            logger.info(
                "[combined_only] Cleared restored routing state — "
                "supervisor will run combined analysis + report only"
            )
        
        # Ensure execution_path is always a list we control
        state["execution_path"] = list(state.get("execution_path", []))
        # Always stamp the original user goal so the combined reporter can show it
        # verbatim, regardless of later state mutations (enrichment, combined goals).
        if not state.get("user_goal_original"):
            state["user_goal_original"] = user_goal
        return state

    def run(self, user_goal: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run the MD workflow without human checkpoints.
        
        Args:
            user_goal: Natural language description of what user wants
            config: Optional configuration overrides
            
        Returns:
            Final state dictionary
        """
        initial_state = self._initialize_state(user_goal, config)
        # Respect explicit config for human loop but default to automatic mode here
        initial_state["human_in_loop"] = bool(initial_state.get("human_in_loop", False))
        
        try:
            # Multi-sim needs many iterations (each sim ≈ 15 graph steps)
            recursion_limit = 500 if initial_state.get("is_multi_simulation") else 50
            final_state = self.graph.invoke(
                initial_state, {"recursion_limit": recursion_limit}
            )
            return final_state
            
        except Exception as e:
            import traceback
            import sys
            error_traceback = traceback.format_exc()
            logger.error(f"Workflow execution error: {e}\n{error_traceback}")
            # Also print to stdout for immediate visibility
            print(f"\n{'='*60}")
            print(f"WORKFLOW ERROR: {e}")
            print(f"{'='*60}")
            print("Full traceback:")
            print(error_traceback)
            print(f"{'='*60}\n")
            initial_state["errors"].append(f"Workflow error: {str(e)}")
            return initial_state

    def _next_after_field_agent(self, state: MDState, default: str = "supervisor") -> str:
        """After a field agent runs, return to HITL checkpoint if this was a delegated task."""
        return_checkpoint = state.pop("hitl_return_checkpoint", None)
        if return_checkpoint:
            state.pop("hitl_delegate_agent", None)
            state.pop("hitl_delegate_task", None)
            logger.info("HITL delegated run complete — returning to %s", return_checkpoint)
            return return_checkpoint
        return state.get("next_node", default)

    def run_with_human_feedback(
        self,
        user_goal: str,
        feedback_handler: Callable[[Dict[str, Any]], str],
        config: Optional[Dict[str, Any]] = None,
        max_steps: int = 200
    ) -> Dict[str, Any]:
        """Run workflow with interactive human checkpoints."""
        if feedback_handler is None:
            raise ValueError("feedback_handler is required for human-in-the-loop execution")

        state = self._initialize_state(user_goal, config)
        state["human_in_loop"] = True
        if not state.get("hitl_mode"):
            state["hitl_mode"] = "all"
        current_node = "supervisor"
        steps = 0

        while steps < max_steps:
            steps += 1
            state["execution_path"].append(current_node)

            if current_node == "supervisor":
                state = self.supervisor.supervisor_node(state)
                current_node = self._route_from_supervisor(state)

            elif current_node == "input_validation":
                state = self.supervisor.input_validation_node(state)
                self._save_progress(state, "input_validation")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "planner":
                state = self.planner.planner_node(state)
                self._save_progress(state, "planner")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "preprocess":
                state = self.preprocessor.preprocess_node(state)
                self._save_progress(state, "preprocess")
                current_node = self._next_after_field_agent(state)

            elif current_node == "setup":
                state = self.setup_agent.setup_node(state)
                self._save_progress(state, "setup")
                current_node = self._next_after_field_agent(state)

            elif current_node == "hpc":
                state = self.hpc_agent.hpc_node(state)
                self._save_progress(state, "hpc")
                current_node = self._next_after_field_agent(state)

            elif current_node == "analysis":
                state = self.analysis_agent.analysis_node(state)
                if (
                    state.get("is_multi_simulation")
                    and state.get("sim_prompts")
                    and state.get("next_node") == "human_analysis_check"
                ):
                    from agentic.multi_sim_progress import record_agent_finished

                    record_agent_finished(state, "analysis")
                self._save_progress(state, "analysis")
                current_node = self._next_after_field_agent(state)

            elif current_node == "reporter":
                state = self.reporter_agent.reporter_node(state)
                if (
                    state.get("is_multi_simulation")
                    and state.get("sim_prompts")
                    and state.get("next_node") == "human_reporter_check"
                ):
                    from agentic.multi_sim_progress import record_agent_finished

                    record_agent_finished(state, "reporter")
                self._save_progress(state, "reporter")
                current_node = self._next_after_field_agent(
                    state, state.get("next_node", "human_reporter_check")
                )

            elif current_node == "human_preprocess_check":
                feedback = self._collect_human_feedback(state, "preprocess", feedback_handler)
                if self._should_stop(feedback, state, "preprocessing"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_preprocess_check(state)
                self._save_progress(state, "human_preprocess_check")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_setup_check":
                feedback = self._collect_human_feedback(state, "setup", feedback_handler)
                if self._should_stop(feedback, state, "setup"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_setup_check(state)
                self._save_progress(state, "human_setup_check")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_hpc_check":
                feedback = self._collect_human_feedback(state, "hpc", feedback_handler)
                if self._should_stop(feedback, state, "hpc"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_hpc_check(state)
                self._save_progress(state, "human_hpc_check")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_hpc_pool_check":
                feedback = self._collect_human_feedback(state, "hpc_pool", feedback_handler)
                if self._should_stop(feedback, state, "hpc_pool"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_hpc_pool_check(state)
                self._save_progress(state, "human_hpc_pool_check")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "hpc_pool_wait":
                state = self._hpc_pool_wait_node(state)
                self._save_progress(state, "hpc_pool_wait")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_analysis_check":
                feedback = self._collect_human_feedback(state, "analysis", feedback_handler)
                if self._should_stop(feedback, state, "analysis"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_analysis_check(state)
                self._save_progress(state, "human_analysis_check")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_reporter_check":
                feedback = self._collect_human_feedback(state, "reporter", feedback_handler)
                if self._should_stop(feedback, state, "reporter"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_reporter_check(state)
                self._save_progress(state, "human_reporter_check")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "final_report":
                return self._final_report_node(state)

            else:
                logger.error(f"Unknown workflow node encountered: {current_node}")
                state["errors"].append(f"Unknown workflow node: {current_node}")
                return self._final_report_node(state)

        state["errors"].append("Human-in-the-loop workflow exceeded maximum iterations")
        return self._final_report_node(state)

    def _collect_human_feedback(
        self,
        state: MDState,
        checkpoint_type: str,
        feedback_handler: Callable[[Dict[str, Any]], str]
    ) -> str:
        """Prompt human for feedback using provided handler.
        
        Injects '_llm' and '_state' into the summary so interactive handlers
        can answer user questions conversationally.
        """
        summary = self.checkpoints.get_checkpoint_summary(state, checkpoint_type)
        # Provide LLM and full state to handler for interactive Q&A
        summary["_llm"] = self.llm
        summary["_state"] = state
        try:
            response = feedback_handler(summary)
        except Exception as exc:
            logger.error(f"Feedback handler failed: {exc}")
            state["errors"].append(f"Feedback handler error at {checkpoint_type}: {exc}")
            return "exit"
        return (response or "").strip()

    def _should_stop(self, feedback: str, state: MDState, checkpoint_label: str) -> bool:
        """Detect stop keywords from human feedback."""
        if feedback.lower() in {"exit", "quit", "stop"}:
            state["errors"].append(
                f"Workflow stopped by human during {checkpoint_label} checkpoint"
            )
            state["next_node"] = "final_report"
            return True
        return False
    
    def visualize_workflow(self, output_file: str = "current_workflow.png") -> bool:
        """
        Create a visualization of this workflow instance.
        
        Args:
            output_file: Path where to save the PNG diagram
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from .utils import WorkflowVisualizer
            visualizer = WorkflowVisualizer()
            return visualizer.visualize_workflow(output_file, use_actual_graph=True)
        except Exception as e:
            logger.error(f"Failed to visualize workflow: {e}")
            return False
