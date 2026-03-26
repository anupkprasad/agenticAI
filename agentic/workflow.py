"""
LLM-Powered MD Workflow with Intelligent Routing

This module implements the complete MD workflow that uses LLM reasoning
for dynamic routing and agent coordination.
"""
import logging
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
    
    def _wrap_node(self, node_name: str, node_func: Callable) -> Callable:
        """Wrap a node function to automatically set current_node in state."""
        def wrapped_node(state: MDState) -> MDState:
            state["current_node"] = node_name
            return node_func(state)
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
        workflow.add_conditional_edges(
            "analysis",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor"
            }
        )
        
        # ========== FIELD AGENTS - REPORTER ==========
        workflow.add_conditional_edges(
            "reporter",
            lambda state: state.get("next_node", "supervisor"),
            {
                "supervisor": "supervisor"
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
            "hpc", "analysis", "reporter", "final_report"
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
            "current_node": None,
            "file_registry": {},
            "generated_files": {},
            "subtask_type": None,
            "subtask_type_initialized": None,
            "agent_list": None,
            "required_inputs": None,
            "analysis_validated": None,
            "reporter_validated": None,
            "multi_agent_validated": None,
            "analysis_directory": None,
            "trajectory_paths": None,
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
        }

        if config:
            state.update(config)

        # CRITICAL: Convert working_directory to absolute path to prevent nested directory creation
        # This ensures that even if agents use os.chdir(), paths remain correct
        from pathlib import Path
        working_dir = state.get("working_directory", "working_dir")
        if working_dir == ".":
            working_dir = "working_dir"  # Use working_dir instead of current directory
        if not Path(working_dir).is_absolute():
            working_dir = str(Path.cwd() / working_dir)
        state["working_directory"] = working_dir
        
        # Initialize agent-specific directories (hardcoded structure)
        state["preprocess_dir"] = str(Path(working_dir) / "preprocess")
        state["simsetup_dir"] = str(Path(working_dir) / "simsetup")
        state["hpc_dir"] = str(Path(working_dir) / "hpc")
        state["analysis_dir"] = str(Path(working_dir) / "analysis")
        
        # Create all agent directories
        for agent_dir in [state["preprocess_dir"], state["simsetup_dir"], 
                         state["hpc_dir"], state["analysis_dir"],
                         str(Path(working_dir) / "reporter")]:
            Path(agent_dir).mkdir(parents=True, exist_ok=True)
        
        # Ensure execution_path is always a list we control
        state["execution_path"] = list(state.get("execution_path", []))
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
            final_state = self.graph.invoke(initial_state)
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
                current_node = state.get("next_node", "supervisor")

            elif current_node == "planner":
                state = self.planner.planner_node(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "preprocess":
                state = self.preprocessor.preprocess_node(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "setup":
                state = self.setup_agent.setup_node(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "hpc":
                state = self.hpc_agent.hpc_node(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "analysis":
                state = self.analysis_agent.analysis_node(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_preprocess_check":
                feedback = self._collect_human_feedback(state, "preprocess", feedback_handler)
                if self._should_stop(feedback, state, "preprocessing"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_preprocess_check(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_setup_check":
                feedback = self._collect_human_feedback(state, "setup", feedback_handler)
                if self._should_stop(feedback, state, "setup"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_setup_check(state)
                current_node = state.get("next_node", "supervisor")

            elif current_node == "human_hpc_check":
                feedback = self._collect_human_feedback(state, "hpc", feedback_handler)
                if self._should_stop(feedback, state, "hpc"):
                    current_node = "final_report"
                    continue
                state["human_feedback"] = feedback
                state = self.checkpoints.human_hpc_check(state)
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
        """Prompt human for feedback using provided handler."""
        summary = self.checkpoints.get_checkpoint_summary(state, checkpoint_type)
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
