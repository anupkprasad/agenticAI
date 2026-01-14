"""Pure Orchestrator Supervisor for MD Workflow"""
import logging
from typing import Any, Dict
from .md_state import MDState
from .conversation_logger import log_supervisor_routing

logger = logging.getLogger(__name__)

class MDSupervisor:
    """
    Pure orchestrator that routes tasks but does not perform scientific reasoning.
    Acts as a finite-state controller for the MD workflow.
    """
    
    def __init__(self):
        self.default_config = {
            "md_engine": "gromacs",
            "force_field": "amber99sb-ildn", 
            "water_model": "tip3p",
            "human_in_loop": True
        }
    
    def supervisor_node(self, state: MDState) -> MDState:
        """
        Pure routing logic - no scientific reasoning.
        Determines next node based on current state.
        """
        # Initialize defaults if not set
        if not state.get("md_engine"):
            state.update(self.default_config)
            
        if not state.get("errors"):
            state["errors"] = []
        if not state.get("warnings"):
            state["warnings"] = []
            
        # Deterministic routing based on completion state
        if not state.get("raw_pdb"):
            state["next_node"] = "input_validation"
        elif not state.get("cleaned_pdb"):
            state["next_node"] = "preprocess"
        elif state.get("preprocessing_issues") and not self._preprocess_validated(state):
            state["next_node"] = "human_preprocess_check"
        elif not state.get("coordinates"):
            state["next_node"] = "setup"
        elif state.get("setup_issues") and not self._setup_validated(state):
            state["next_node"] = "human_setup_check"
        else:
            # For now, route to final report until HPC and analysis agents are implemented
            state["next_node"] = "final_report"
            
        # Generate routing reasoning
        reasoning = self._get_routing_reasoning(state)
        
        # Log supervisor routing decision
        log_supervisor_routing(state, state['next_node'], reasoning)
            
        logger.info(f"Supervisor routing to: {state['next_node']}")
        return state
    
    def _get_routing_reasoning(self, state: MDState) -> str:
        """Generate human-readable reasoning for routing decision."""
        if not state.get("raw_pdb"):
            return "No input PDB file found, need to validate input"
        elif not state.get("cleaned_pdb"):
            return "Raw PDB needs preprocessing (cleaning, fixing)"
        elif state.get("preprocessing_issues") and not self._preprocess_validated(state):
            return "Preprocessing found issues requiring human review"
        elif not state.get("coordinates"):
            return "Need to setup simulation system (solvation, ions)"
        elif state.get("setup_issues") and not self._setup_validated(state):
            return "Setup found issues requiring human review"
        else:
            return "All workflow steps completed, generating final report"
    
    def _preprocess_validated(self, state: MDState) -> bool:
        """Check if preprocessing issues have been addressed."""
        return state.get("human_feedback") and "preprocess_approved" in str(state.get("human_feedback", ""))
    
    def _setup_validated(self, state: MDState) -> bool:
        """Check if setup issues have been addressed.""" 
        return state.get("human_feedback") and "setup_approved" in str(state.get("human_feedback", ""))
    
    def input_validation_node(self, state: MDState) -> MDState:
        """Validate user input and extract PDB path with working directory."""
        user_goal = state.get("user_goal", "")
        
        # Enhanced path extraction with multiple patterns
        pdb_path = self._extract_pdb_path(user_goal)
        
        if pdb_path:
            state["raw_pdb"] = pdb_path
            
            # Set working directory intelligently
            import os
            pdb_dir = os.path.dirname(pdb_path)
            
            if pdb_dir and pdb_dir != ".":
                # Use the directory containing the PDB file
                state["working_directory"] = pdb_dir
                log_supervisor_routing(state, "input_validation", 
                    f"Extracted PDB: {pdb_path}, Working directory set to: {pdb_dir}")
            else:
                # PDB is in current directory or no directory specified
                state["working_directory"] = "."
                log_supervisor_routing(state, "input_validation", 
                    f"Extracted PDB: {pdb_path}, Using current directory as working directory")
                    
            # Ensure the PDB file exists (if it's an absolute or relative path)
            if os.path.isabs(pdb_path) or "/" in pdb_path:
                if not os.path.exists(pdb_path):
                    state["warnings"].append(f"PDB file {pdb_path} does not exist yet (will be created or provided later)")
                else:
                    log_supervisor_routing(state, "input_validation", 
                        f"Confirmed PDB file exists: {pdb_path}")
        else:
            state["errors"].append("Could not extract PDB path from user goal. Please specify a .pdb file path.")
            
        state["next_node"] = "supervisor"
        return state
    
    def _extract_pdb_path(self, user_goal: str) -> str:
        """Extract PDB file path from user goal with multiple extraction strategies."""
        import re
        import os
        
        # Strategy 1: Look for explicit file paths (with directories)
        # Patterns like: /path/to/file.pdb, ./file.pdb, ../file.pdb, working_dir/0.pdb
        path_patterns = [
            r'([^\s]+/[^\s]*\.pdb)',  # Paths with directories
            r'(\./[^\s]*\.pdb)',       # Relative paths starting with ./
            r'(\.\./[^\s]*\.pdb)',     # Relative paths starting with ../
            r'([~/][^\s]*\.pdb)',      # Home directory paths
            r'([A-Za-z]:[\\\\/][^\s]*\.pdb)',  # Windows absolute paths
        ]
        
        for pattern in path_patterns:
            match = re.search(pattern, user_goal)
            if match:
                return match.group(1)
        
        # Strategy 2: Look for any PDB filename (fallback)
        simple_match = re.search(r'(\S+\.pdb)', user_goal)
        if simple_match:
            return simple_match.group(1)
            
        # Strategy 3: Look for common PDB naming patterns
        # Look for protein names that might indicate PDB files
        protein_patterns = [
            r'protein\s+([A-Za-z0-9_-]+)',
            r'PDB\s+([A-Za-z0-9_-]+)',
            r'structure\s+([A-Za-z0-9_-]+)',
        ]
        
        for pattern in protein_patterns:
            match = re.search(pattern, user_goal, re.IGNORECASE)
            if match:
                # Assume .pdb extension
                protein_name = match.group(1)
                if not protein_name.endswith('.pdb'):
                    protein_name += '.pdb'
                return protein_name
        
        return None
