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

logger = logging.getLogger(__name__)

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
        workflow.add_node("human_analysis_check", self._wrap_node("human_analysis_check", self.checkpoints.human_analysis_check))
        workflow.add_node("human_reporter_check", self._wrap_node("human_reporter_check", self.checkpoints.human_reporter_check))
        workflow.add_node("final_report", self._wrap_node("final_report", self._final_report_node))
        
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
                "final_report": "final_report",
                END: END
            }
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
        # Reporter routes to human_reporter_check (auto-skipped when --no-human-loop).
        workflow.add_conditional_edges(
            "reporter",
            lambda state: state.get("next_node", "human_reporter_check"),
            {
                "supervisor": "supervisor",
                "human_reporter_check": "human_reporter_check",
            }
        )

        # ========== REPORTER CHECKPOINT ==========
        # Skipped when --no-human-loop (routes supervisor → final_report).
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
            "hpc", "analysis", "reporter", "human_reporter_check", "final_report"
        ]
        
        if next_node in valid_nodes:
            logger.info(f"Supervisor routing to: {next_node}")
            return next_node
        
        logger.warning(f"Invalid next_node: {next_node}, defaulting to final_report")
        return "final_report"
    
    def _final_report_node(self, state: MDState) -> MDState:
        """Generate enhanced final workflow report using LLM when available."""
        
        if self.llm:
            report = self._generate_llm_report(state)
        else:
            report = self._generate_fallback_report(state)
        
        state["final_report"] = report
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
            working_dir = state.get("working_directory", ".")
            supervisor_dir = Path(working_dir) / "supervisor"
            supervisor_dir.mkdir(parents=True, exist_ok=True)
            state_path = supervisor_dir / "state.jsonl"
            
            # Build a serializable snapshot of the state
            serializable_state = {}
            for key, value in state.items():
                try:
                    json.dumps(value, default=str)
                    serializable_state[key] = value
                except (TypeError, ValueError):
                    serializable_state[key] = str(value)
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "workflow_status": state.get("workflow_status", "unknown"),
                "state": serializable_state,
            }
            
            # Overwrite with a single entry so the file is always the latest state
            state_path.write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")
            
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
            "human_in_loop": False,
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
            "combined_analysis_plan": None,
            "current_sim_index": 0,
            "completed_sim_states": None,
            "sim_working_dirs": None,
        }

        if config:
            state.update(config)

        # CRITICAL: Convert working_directory to absolute path to prevent nested directory creation
        # This ensures that even if agents use os.chdir(), paths remain correct
        working_dir = state.get("working_directory", "working_dir")
        if working_dir == ".":
            working_dir = "working_dir"  # Use working_dir instead of current directory
        if not Path(working_dir).is_absolute():
            working_dir = str(Path.cwd() / working_dir)
        state["working_directory"] = working_dir
        
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
            # Single-sim: create standard agent directories at working_dir level
            state["preprocess_dir"] = str(Path(working_dir) / "preprocess")
            state["simsetup_dir"] = str(Path(working_dir) / "simsetup")
            state["hpc_dir"] = str(Path(working_dir) / "hpc")
            state["analysis_dir"] = str(Path(working_dir) / "analysis")
            for agent_dir in [state["preprocess_dir"], state["simsetup_dir"],
                             state["hpc_dir"], state["analysis_dir"],
                             str(Path(working_dir) / "reporter"),
                             str(Path(working_dir) / "supervisor")]:
                Path(agent_dir).mkdir(parents=True, exist_ok=True)
        
        # Check for saved workflow state from a previous run
        saved_state = self._load_workflow_state(working_dir)
        if saved_state:
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
            ]
            for key in restore_keys:
                if key in saved_state and saved_state[key] is not None:
                    state[key] = saved_state[key]
            
            logger.info("Restored previous workflow state — supervisor will skip completed stages")
        
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
                current_node = state.get("next_node", "supervisor")

            elif current_node == "setup":
                state = self.setup_agent.setup_node(state)
                self._save_progress(state, "setup")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "hpc":
                state = self.hpc_agent.hpc_node(state)
                self._save_progress(state, "hpc")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "analysis":
                state = self.analysis_agent.analysis_node(state)
                self._save_progress(state, "analysis")
                current_node = state.get("next_node", "supervisor")

            elif current_node == "reporter":
                state = self.reporter_agent.reporter_node(state)
                self._save_progress(state, "reporter")
                # Route to reporter checkpoint for human review
                current_node = state.get("next_node", "human_reporter_check")

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
