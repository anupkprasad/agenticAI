"""Human-in-the-Loop Checkpoint Nodes"""
import logging
from typing import Dict, Any
from .md_state import MDState
from .conversation_logger import log_human_checkpoint

logger = logging.getLogger(__name__)

class HumanCheckpoints:
    """Handles human intervention points in the MD workflow."""
    
    @staticmethod
    def human_preprocess_check(state: MDState) -> MDState:
        """
        Human checkpoint after preprocessing.
        Allows human to review and provide feedback on PDB cleaning.
        """
        feedback = state.get("human_feedback", "")
        
        # Log checkpoint interaction
        context = {
            "preprocessing_issues": state.get("preprocessing_issues", []),
            "cleaned_pdb": state.get("cleaned_pdb", ""),
            "preprocessing_report": state.get("preprocessing_report", "")
        }
        
        if feedback:
            log_human_checkpoint("preprocessing", context, feedback)
            logger.info(f"Received human feedback for preprocessing: {feedback}")
            
            # Process feedback
            if "approved" in feedback.lower() or "continue" in feedback.lower():
                state["human_feedback"] = "preprocess_approved"
                state["next_node"] = "supervisor"
                
            elif "retry" in feedback.lower() or "redo" in feedback.lower():
                # Clear previous results and retry
                state["cleaned_pdb"] = None
                state["topology"] = None
                state["preprocessing_report"] = None
                state["preprocessing_issues"] = []
                state["next_node"] = "preprocess"
                
            elif "modify" in feedback.lower():
                # Human wants to modify approach
                state["preprocessing_issues"].append(f"Human modification request: {feedback}")
                state["next_node"] = "preprocess"
                
            else:
                # Default to continuing
                state["human_feedback"] = "preprocess_approved"
                state["next_node"] = "supervisor"
                
        else:
            # No feedback yet - stay in checkpoint
            log_human_checkpoint("preprocessing", context, "awaiting_feedback")
            state["next_node"] = "human_preprocess_check"
            
        return state
    
    @staticmethod
    def human_setup_check(state: MDState) -> MDState:
        """
        Human checkpoint after simulation setup.
        Allows human to review solvation, ions, and protocol parameters.
        """
        feedback = state.get("human_feedback", "")
        
        if feedback:
            logger.info(f"Received human feedback for setup: {feedback}")
            
            if "approved" in feedback.lower() or "continue" in feedback.lower():
                state["human_feedback"] = "setup_approved"
                state["next_node"] = "supervisor"
                
            elif "retry" in feedback.lower():
                # Clear setup results and retry
                state["coordinates"] = None
                state["mdp_files"] = {}
                state["setup_report"] = None
                state["setup_issues"] = []
                state["next_node"] = "setup"
                
            elif "modify" in feedback.lower():
                # Human wants to modify setup
                state["setup_issues"].append(f"Human modification request: {feedback}")
                state["next_node"] = "setup"
                
            else:
                state["human_feedback"] = "setup_approved"
                state["next_node"] = "supervisor"
                
        else:
            # No feedback yet
            state["next_node"] = "human_setup_check"
            
        return state
    
    @staticmethod
    def human_hpc_check(state: MDState) -> MDState:
        """
        Optional human checkpoint before job submission.
        Allows review of job parameters and submission decisions.
        """
        feedback = state.get("human_feedback", "")
        
        if feedback:
            if "submit" in feedback.lower() or "approved" in feedback.lower():
                state["human_feedback"] = "hpc_approved"
                state["next_node"] = "supervisor"
                
            elif "modify" in feedback.lower():
                state["next_node"] = "hpc"
                
            else:
                state["next_node"] = "supervisor"
        else:
            state["next_node"] = "human_hpc_check"
            
        return state
    
    @staticmethod
    def get_checkpoint_summary(state: MDState, checkpoint_type: str) -> Dict[str, Any]:
        """
        Generate summary for human review at checkpoints.
        """
        summary = {
            "checkpoint_type": checkpoint_type,
            "current_state": {},
            "issues_found": [],
            "recommendations": []
        }
        
        if checkpoint_type == "preprocess":
            summary["current_state"] = {
                "raw_pdb": state.get("raw_pdb"),
                "cleaned_pdb": state.get("cleaned_pdb"),
                "force_field": state.get("force_field"),
                "preprocessing_report": state.get("preprocessing_report")
            }
            summary["issues_found"] = state.get("preprocessing_issues", [])
            summary["recommendations"] = [
                "Review preprocessing report for any warnings",
                "Verify protonation states are appropriate", 
                "Check that unwanted molecules were removed"
            ]
            
        elif checkpoint_type == "setup":
            summary["current_state"] = {
                "topology": state.get("topology"),
                "coordinates": state.get("coordinates"),
                "mdp_files": state.get("mdp_files", {}),
                "force_field": state.get("force_field"),
                "water_model": state.get("water_model"),
                "setup_report": state.get("setup_report")
            }
            summary["issues_found"] = state.get("setup_issues", [])
            summary["recommendations"] = [
                "Verify box size is appropriate",
                "Check ion concentration and neutralization",
                "Review equilibration protocol parameters"
            ]
            
        elif checkpoint_type == "hpc":
            summary["current_state"] = {
                "job_script": state.get("job_script"),
                "estimated_runtime": "TBD",
                "resources_requested": "TBD"
            }
            summary["recommendations"] = [
                "Review computational resource allocation",
                "Verify job script parameters",
                "Confirm simulation length is appropriate"
            ]
            
        return summary
