"""Human-in-the-Loop Checkpoint Nodes"""
import logging
from pathlib import Path
from typing import Dict, Any, List
from .state import MDState
from .utils import log_human_checkpoint
from .utils.agent_metadata import load_agent_metadata

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
        
        # Clear error-triggered flag on any human response
        state.pop("error_triggered_hitl", None)
        
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
        elif lower.startswith("recommend"):
            # Human provides guidance — store it and retry with recommendation
            recommendation = feedback.split(":", 1)[1].strip() if ":" in feedback else feedback
            state["human_recommendation"] = recommendation
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
            issues_key = f"{checkpoint_label}_issues"
            if issues_key in state and isinstance(state[issues_key], list):
                state[issues_key].append(f"Human modification request: {modification}")
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
        Auto-approves if not in interactive HITL mode (graph-only execution).
        """
        feedback = state.get("human_feedback", "")
        if feedback:
            return HumanCheckpoints._process_feedback(
                feedback, state, "preprocessing", "preprocess",
                clear_keys=["cleaned_pdb", "topology", "preprocessing_report", "preprocessing_issues"]
            )
        elif not state.get("human_in_loop"):
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
        elif not state.get("human_in_loop"):
            state["next_node"] = "supervisor"
            return state
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
        elif not state.get("human_in_loop"):
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
        elif not state.get("human_in_loop"):
            state["next_node"] = "supervisor"
            return state
        else:
            state["next_node"] = "human_analysis_check"
            return state
    
    @staticmethod
    def get_checkpoint_summary(state: MDState, checkpoint_type: str) -> Dict[str, Any]:
        """
        Generate summary for human review at checkpoints.
        Includes actual agent output, generated files, and agent metadata
        for informed decisions.
        """
        error_triggered = bool(state.get("error_triggered_hitl"))
        
        summary: Dict[str, Any] = {
            "checkpoint_type": checkpoint_type,
            "error_triggered": error_triggered,
            "current_state": {},
            "issues_found": [],
            "recommendations": []
        }
        
        # Load agent metadata if available
        agent_dir_map = {
            "preprocess": state.get("preprocess_dir", ""),
            "setup": state.get("simsetup_dir", ""),
            "hpc": state.get("hpc_dir", ""),
            "analysis": state.get("analysis_dir", ""),
        }
        agent_dir = agent_dir_map.get(checkpoint_type, "")
        agent_meta = load_agent_metadata(agent_dir) if agent_dir else None
        
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
        
        # Merge agent metadata into summary if available
        if agent_meta:
            # Add step counts to current_state
            summary["current_state"]["steps_executed"] = agent_meta.get("steps_executed", 0)
            summary["current_state"]["steps_succeeded"] = agent_meta.get("steps_succeeded", 0)
            summary["current_state"]["steps_failed"] = agent_meta.get("steps_failed", 0)
            # Add execution log tail for error context
            log_tail = agent_meta.get("execution_log_tail", "")
            if log_tail:
                summary["current_state"]["execution_log_tail"] = log_tail[-1000:]
            # Merge issues from metadata
            meta_issues = agent_meta.get("issues", [])
            if meta_issues:
                summary["issues_found"] = list(summary["issues_found"]) + meta_issues
        
        # Add errors from the workflow so far
        errors = state.get("errors", [])
        if errors:
            summary["issues_found"] = list(summary["issues_found"]) + [f"ERROR: {e}" for e in errors[-5:]]
        
        # Adjust recommendations for error-triggered checkpoints
        if error_triggered:
            summary["recommendations"] = [
                "Use 'recommend: <your advice>' to guide the agent on how to fix the issue",
                "Use 'retry' to let the agent try again from scratch",
                "Use 'modify: <instructions>' to specify exact changes",
                "Use 'show <filename>' to inspect generated files",
                "Use 'continue' to skip this agent and proceed",
            ] + summary["recommendations"]
        
        return summary
