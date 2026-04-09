"""Human-in-the-Loop Checkpoint Nodes"""
import logging
from pathlib import Path
from typing import Dict, Any, List
from .state import MDState
from .utils import log_human_checkpoint

logger = logging.getLogger(__name__)


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
    def _process_feedback(feedback: str, state: MDState, checkpoint_label: str,
                          retry_node: str, clear_keys: List[str] = None) -> MDState:
        """Common feedback processing logic for all checkpoints."""
        log_human_checkpoint(checkpoint_label, {}, feedback.lower(), feedback)
        logger.info(f"Received human feedback for {checkpoint_label}: {feedback}")
        
        lower = feedback.lower()
        if "approved" in lower or "continue" in lower:
            state["human_feedback"] = f"{checkpoint_label}_approved"
            state["next_node"] = "supervisor"
        elif "retry" in lower or "redo" in lower:
            # Clear previous results and retry
            for key in (clear_keys or []):
                if key in state:
                    default = [] if isinstance(state.get(key), list) else ({} if isinstance(state.get(key), dict) else None)
                    state[key] = default
            state["next_node"] = retry_node
        elif "modify" in lower:
            # Store the human's modification instructions for the agent
            issues_key = f"{checkpoint_label}_issues" if f"{checkpoint_label}_issues" in state else None
            if issues_key:
                state[issues_key].append(f"Human modification request: {feedback}")
            else:
                state.setdefault("warnings", []).append(f"Human modify request ({checkpoint_label}): {feedback}")
            state["next_node"] = retry_node
        else:
            # Default: treat any other text as approval with a note
            state["human_feedback"] = f"{checkpoint_label}_approved"
            state.setdefault("warnings", []).append(f"Human note ({checkpoint_label}): {feedback}")
            state["next_node"] = "supervisor"
        
        return state
    
    @staticmethod
    def human_preprocess_check(state: MDState) -> MDState:
        """
        Human checkpoint after preprocessing.
        Allows human to review and provide feedback on PDB cleaning.
        """
        feedback = state.get("human_feedback", "")
        if feedback:
            return HumanCheckpoints._process_feedback(
                feedback, state, "preprocessing", "preprocess",
                clear_keys=["cleaned_pdb", "topology", "preprocessing_report", "preprocessing_issues"]
            )
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
        else:
            state["next_node"] = "human_setup_check"
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
        else:
            state["next_node"] = "human_analysis_check"
            return state
    
    @staticmethod
    def get_checkpoint_summary(state: MDState, checkpoint_type: str) -> Dict[str, Any]:
        """
        Generate summary for human review at checkpoints.
        Includes actual agent output and generated files for informed decisions.
        """
        summary: Dict[str, Any] = {
            "checkpoint_type": checkpoint_type,
            "current_state": {},
            "issues_found": [],
            "recommendations": []
        }
        
        if checkpoint_type == "preprocess":
            # Show actual preprocessing results
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
            # Include preprocessing report (truncated for readability)
            report = state.get("preprocessing_report", "")
            if report:
                summary["current_state"]["preprocessing_report"] = report[:500]
            
            summary["issues_found"] = state.get("preprocessing_issues", [])
            summary["recommendations"] = [
                "Review cleaned PDB and check that correct chains/molecules were kept",
                "Verify ligand and ion residue names were correctly identified",
                "Check protonation states if relevant",
            ]
            
        elif checkpoint_type == "setup":
            # Show actual setup results
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
            
            summary["issues_found"] = state.get("setup_issues", [])
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
            
            summary["current_state"] = {
                "analysis_results": list(state.get("analysis_results", {}).keys()),
                "figures": [Path(f).name for f in figures] if figures else [],
                "generated_files": generated,
            }
            conclusions = state.get("conclusions", "")
            if conclusions:
                summary["current_state"]["conclusions"] = conclusions[:500]
            
            summary["issues_found"] = []
            summary["recommendations"] = [
                "Review generated plots for expected trends",
                "Check that all requested analyses were completed",
                "Verify analysis results make physical sense",
            ]
            
        # Add errors from the workflow so far
        errors = state.get("errors", [])
        if errors:
            summary["issues_found"] = list(summary["issues_found"]) + [f"ERROR: {e}" for e in errors[-5:]]
        
        return summary
