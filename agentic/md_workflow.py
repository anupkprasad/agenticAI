"""Main LangGraph MD Workflow"""
import logging
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END
from .md_state import MDState
from .md_supervisor import MDSupervisor
from .preprocessing_agent import PreprocessingAgent
from .setup_agent import SimulationSetupAgent
from .human_checkpoints import HumanCheckpoints
from .llm import LLMClient

logger = logging.getLogger(__name__)

class MDWorkflow:
    """
    LangGraph-based MD simulation workflow with human-in-the-loop capabilities.
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient(model="llama3.1")
        
        # Initialize agents
        self.supervisor = MDSupervisor()
        self.preprocessor = PreprocessingAgent(self.llm)
        self.setup_agent = SimulationSetupAgent(self.llm)
        self.checkpoints = HumanCheckpoints()
        
        # Build the graph
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        
        # Create the graph with our state
        workflow = StateGraph(MDState)
        
        # Add all nodes
        workflow.add_node("supervisor", self.supervisor.supervisor_node)
        workflow.add_node("input_validation", self.supervisor.input_validation_node)
        workflow.add_node("preprocess", self.preprocessor.preprocess_node)
        workflow.add_node("setup", self.setup_agent.setup_node)
        workflow.add_node("human_preprocess_check", self.checkpoints.human_preprocess_check)
        workflow.add_node("human_setup_check", self.checkpoints.human_setup_check)
        workflow.add_node("final_report", self._final_report_node)
        
        # Set entry point
        workflow.set_entry_point("supervisor")
        
        # Add conditional routing
        workflow.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                "input_validation": "input_validation",
                "preprocess": "preprocess", 
                "setup": "setup",
                "final_report": "final_report",
                END: END
            }
        )
        
        # Simple routing for other nodes
        workflow.add_conditional_edges(
            "input_validation",
            lambda state: state["next_node"],
            {"supervisor": "supervisor"}
        )
        
        workflow.add_conditional_edges(
            "preprocess",
            lambda state: state["next_node"],
            {
                "supervisor": "supervisor",
                "human_preprocess_check": "human_preprocess_check"
            }
        )
        
        workflow.add_conditional_edges(
            "setup", 
            lambda state: state["next_node"],
            {
                "supervisor": "supervisor",
                "human_setup_check": "human_setup_check"
            }
        )
        
        workflow.add_conditional_edges(
            "human_preprocess_check",
            lambda state: state["next_node"],
            {
                "supervisor": "supervisor",
                "preprocess": "preprocess",
                "human_preprocess_check": "human_preprocess_check"
            }
        )
        
        workflow.add_conditional_edges(
            "human_setup_check",
            lambda state: state["next_node"], 
            {
                "supervisor": "supervisor",
                "setup": "setup",
                "human_setup_check": "human_setup_check"
            }
        )
        
        workflow.add_edge("final_report", END)
        
        return workflow.compile()
    
    def _route_from_supervisor(self, state: MDState) -> str:
        """Route from supervisor based on next_node."""
        next_node = state.get("next_node")
        
        # Handle special cases
        if next_node == "hpc":
            # HPC not implemented yet - go to final report
            return "final_report"
        elif next_node == "analysis":
            # Analysis not implemented yet - go to final report  
            return "final_report"
        elif next_node is None:
            return END
        else:
            return next_node
    
    def _final_report_node(self, state: MDState) -> MDState:
        """Generate final workflow report."""
        
        report = f"""
        MD Workflow Completion Report
        ============================

        User Goal: {state.get('user_goal')}
        Status: {'Completed' if not state.get('errors') else 'Completed with errors'}

        Input Files:
        - Original PDB: {state.get('raw_pdb')}

        Preprocessing:
        - Cleaned structure: {state.get('cleaned_pdb')}
        - Force field: {state.get('force_field')}
        - Water model: {state.get('water_model')}

        Setup:
        - Final coordinates: {state.get('coordinates')}
        - Topology: {state.get('topology')}
        - MDP files generated: {len(state.get('mdp_files', {}))}

        Errors: {len(state.get('errors', []))}
        Warnings: {len(state.get('warnings', []))}

        Next Steps:
        - Review generated files in {state.get('working_directory')}
        - Submit job to HPC system (not yet implemented)
        - Run analysis pipeline (not yet implemented)
        """
        
        state["final_report"] = report
        state["next_node"] = None  # End workflow
        
        logger.info("MD Workflow completed")
        logger.info(report)
        
        return state
    
    def visualize_workflow(self, output_file: str = "current_workflow.png") -> bool:
        """
        Create a visualization of this workflow instance.
        
        Args:
            output_file: Path where to save the PNG diagram
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from .workflow_visualizer import WorkflowVisualizer
            visualizer = WorkflowVisualizer()
            return visualizer.visualize_workflow(output_file, use_actual_graph=True)
        except Exception as e:
            logger.error(f"Failed to visualize workflow: {e}")
            return False
    
    def get_workflow_structure(self) -> Dict[str, Any]:
        """
        Get information about the current workflow structure.
        
        Returns:
            Dict with nodes, edges, and other workflow metadata
        """
        try:
            from .workflow_visualizer import WorkflowVisualizer
            visualizer = WorkflowVisualizer()
            G = visualizer.extract_actual_workflow_graph()
            
            if G:
                return {
                    "nodes": list(G.nodes()),
                    "edges": [(u, v, d.get('label', '')) for u, v, d in G.edges(data=True)],
                    "node_count": len(G.nodes()),
                    "edge_count": len(G.edges())
                }
        except Exception as e:
            logger.error(f"Failed to get workflow structure: {e}")
            
        return {"error": "Could not extract workflow structure"}

    def run(self, user_goal: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run the MD workflow.
        
        Args:
            user_goal: Natural language description of what user wants
            config: Optional configuration overrides
            
        Returns:
            Final state dictionary
        """
        # Initialize state
        initial_state = MDState(
            user_goal=user_goal,
            md_engine="gromacs",
            force_field="amber99sb-ildn", 
            water_model="tip3p",
            human_in_loop=True,
            preprocessing_issues=[],
            setup_issues=[],
            mdp_files={},
            analysis_results={},
            figures=[],
            errors=[],
            warnings=[],
            next_node=None,
            human_feedback=None,
            working_directory=None
        )
        
        # Apply config overrides
        if config:
            initial_state.update(config)
        
        try:
            # Run the graph
            final_state = self.graph.invoke(initial_state)
            return final_state
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            initial_state["errors"].append(f"Workflow error: {str(e)}")
            return initial_state
    
    def run_with_human_feedback(self, user_goal: str, feedback_handler=None) -> Dict[str, Any]:
        """
        Run workflow with interactive human feedback capability.
        
        Args:
            user_goal: Natural language description
            feedback_handler: Function to get human input when needed
            
        Returns:
            Final state
        """
        state = MDState(
            user_goal=user_goal,
            md_engine="gromacs", 
            force_field="amber99sb-ildn",
            water_model="tip3p",
            human_in_loop=True,
            preprocessing_issues=[],
            setup_issues=[],
            mdp_files={},
            analysis_results={},
            figures=[],
            errors=[],
            warnings=[],
            next_node=None,
            human_feedback=None,
            working_directory=None
        )
        
        max_iterations = 50
        iteration = 0
        
        while iteration < max_iterations:
            try:
                # Run one step
                result = self.graph.invoke(state)
                state.update(result)
                
                # Check if we need human input
                if (state.get("next_node") in ["human_preprocess_check", "human_setup_check", "human_hpc_check"] 
                    and not state.get("human_feedback")):
                    
                    if feedback_handler:
                        checkpoint_type = state["next_node"].replace("human_", "").replace("_check", "")
                        summary = self.checkpoints.get_checkpoint_summary(state, checkpoint_type)
                        
                        feedback = feedback_handler(summary)
                        state["human_feedback"] = feedback
                    else:
                        # Auto-approve if no handler
                        state["human_feedback"] = "approved"
                
                # Check for completion
                if state.get("next_node") is None or state.get("final_report"):
                    break
                    
                iteration += 1
                
            except Exception as e:
                logger.error(f"Workflow iteration failed: {e}")
                state["errors"].append(f"Iteration error: {str(e)}")
                break
        
        return state

    def create_visualization(self, output_file: str = "md_workflow_diagram.png") -> bool:
        """
        Create a visual diagram of the current workflow structure.
        
        Args:
            output_file: Output PNG file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from .workflow_visualizer import WorkflowVisualizer
            visualizer = WorkflowVisualizer()
            return visualizer.visualize_workflow(self.graph, output_file)
        except ImportError:
            logger.warning("Visualization dependencies not available. Install with: pip install matplotlib networkx")
            return False
        except Exception as e:
            logger.error(f"Failed to create workflow visualization: {e}")
            return False
