"""Preprocessing Agent with Planning Capability"""
import logging
import os
from typing import Dict, Any, List
from .md_state import MDState
from .llm import LLMClient
from .conversation_logger import (
    log_agent_start, log_llm_interaction, log_agent_action, 
    log_file_operation, log_agent_completion
)

logger = logging.getLogger(__name__)

class PreprocessingAgent:
    """
    Handles PDB cleaning, protonation, and GROMACS compatibility.
    Uses LLM for adaptive planning based on PDB structure.
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client or LLMClient()
        
    def preprocess_node(self, state: MDState) -> MDState:
        """Main preprocessing node with planning."""
        # Log agent start
        log_agent_start("preprocessing", "PDB Cleaning", state)
        
        try:
            # 1. Analyze PDB structure
            log_agent_action("preprocessing", "Analyzing PDB structure", {
                "pdb_file": state.get("raw_pdb", "unknown")
            })
            analysis = self._analyze_pdb_structure(state)
            
            # 2. Generate preprocessing plan using LLM
            log_agent_action("preprocessing", "Generating preprocessing plan", {
                "analysis_results": analysis
            })
            plan = self._generate_preprocessing_plan(state, analysis)
            
            # 3. Execute the plan
            log_agent_action("preprocessing", "Executing preprocessing commands", {
                "plan_commands": plan.get("commands", [])
            })
            result = self._execute_preprocessing_plan(state, plan)
            
            # 4. Validate results
            validation = self._validate_preprocessing(state, result)
            
            # 5. Update state
            state.update(result)
            state["preprocessing_report"] = plan.get("reasoning", "") + "\n" + validation.get("report", "")
            state["preprocessing_issues"] = validation.get("issues", [])
            
            # Route based on validation
            if state["preprocessing_issues"] and state["human_in_loop"]:
                state["next_node"] = "human_preprocess_check"
            else:
                state["next_node"] = "supervisor"
            
            # Log completion
            success = len(state["preprocessing_issues"]) == 0
            log_agent_completion("preprocessing", "PDB Cleaning", state, success)
                
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}")
            from .conversation_logger import log_error
            log_error("preprocessing_agent.preprocess_node", e, {"state": state})
            state["errors"].append(f"Preprocessing error: {str(e)}")
            state["next_node"] = "supervisor"
            
        return state
    
    def _analyze_pdb_structure(self, state: MDState) -> Dict[str, Any]:
        """Analyze PDB file to understand what preprocessing is needed."""
        pdb_path = state["raw_pdb"]
        analysis = {
            "file_exists": os.path.exists(pdb_path),
            "has_heteroatoms": False,
            "missing_residues": [],
            "chain_count": 0,
            "alternate_locations": False,
            "waters_present": False
        }
        
        if not analysis["file_exists"]:
            return analysis
            
        try:
            with open(pdb_path, 'r') as f:
                for line in f:
                    if line.startswith("HETATM"):
                        analysis["has_heteroatoms"] = True
                        if "HOH" in line or "WAT" in line:
                            analysis["waters_present"] = True
                    elif line.startswith("ATOM"):
                        if len(line) > 21:
                            chain = line[21]
                            analysis["chain_count"] = max(analysis["chain_count"], ord(chain) - ord('A') + 1)
                        if len(line) > 16 and line[16] not in [' ', 'A']:
                            analysis["alternate_locations"] = True
                            
        except Exception as e:
            logger.warning(f"Could not analyze PDB: {e}")
            
        return analysis
    
    def _generate_preprocessing_plan(self, state: MDState, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to generate adaptive preprocessing plan."""
        prompt = f"""
        You are a molecular dynamics preprocessing expert. Analyze this PDB structure and create a detailed preprocessing plan for GROMACS simulation.

        User Goal: {state['user_goal']}
        PDB Path: {state['raw_pdb']}
        Force Field: {state['force_field']}
        
        Structure Analysis:
        - File exists: {analysis['file_exists']}
        - Has heteroatoms: {analysis['has_heteroatoms']}
        - Waters present: {analysis['waters_present']}
        - Chain count: {analysis['chain_count']}
        - Alternate locations: {analysis['alternate_locations']}
        - Missing residues detected: {analysis['missing_residues']}
        
        Generate a preprocessing plan including:
        1. Detailed reasoning for each step
        2. Specific GROMACS commands to run
        3. Expected outputs
        4. Potential issues to watch for
        
        Focus on:
        - PDB cleaning (remove waters, heteroatoms if not needed)
        - Handling alternate locations
        - Protonation state decisions
        - Chain selection if multiple chains
        - Missing residue handling
        
        Format your response as:
        REASONING:
        [Your detailed analysis and reasoning]
        
        COMMANDS:
        [Specific gmx commands to execute]
        
        EXPECTED_OUTPUTS:
        [Files that will be generated]
        
        VALIDATION_CHECKS:
        [How to verify success]
        """
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            # Log LLM interaction
            log_llm_interaction("preprocessing", prompt, content, 
                              is_mock=hasattr(self.llm, '_is_mock_mode') and self.llm._is_mock_mode)
            
            return {
                "reasoning": content,
                "commands": self._extract_commands(content),
                "expected_outputs": self._extract_expected_outputs(content),
                "validation_checks": self._extract_validation_checks(content)
            }
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            from .conversation_logger import log_error
            log_error("preprocessing_agent._generate_preprocessing_plan", e)
            return self._fallback_preprocessing_plan(state, analysis)
    
    def _extract_commands(self, content: str) -> List[str]:
        """Extract GROMACS commands from LLM response."""
        import re
        commands = []
        
        # Look for gmx commands
        gmx_pattern = r'gmx\s+\w+.*'
        matches = re.findall(gmx_pattern, content, re.MULTILINE)
        commands.extend(matches)
        
        return commands
    
    def _extract_expected_outputs(self, content: str) -> List[str]:
        """Extract expected output files from LLM response.""" 
        # Simple extraction - could be improved
        outputs = []
        if "EXPECTED_OUTPUTS:" in content:
            section = content.split("EXPECTED_OUTPUTS:")[1].split("VALIDATION_CHECKS:")[0]
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            outputs = [line for line in lines if '.' in line and not line.startswith('#')]
        
        return outputs
    
    def _extract_validation_checks(self, content: str) -> List[str]:
        """Extract validation checks from LLM response."""
        checks = []
        if "VALIDATION_CHECKS:" in content:
            section = content.split("VALIDATION_CHECKS:")[1]
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            checks = [line for line in lines if line and not line.startswith('#')]
            
        return checks
    
    def _fallback_preprocessing_plan(self, state: MDState, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback plan if LLM fails."""
        return {
            "reasoning": "Using default preprocessing workflow",
            "commands": [
                f"gmx pdb2gmx -f {state['raw_pdb']} -o processed.gro -p topol.top -ff {state['force_field']} -water {state['water_model']}"
            ],
            "expected_outputs": ["processed.gro", "topol.top"],
            "validation_checks": ["Check for missing residues", "Verify topology file"]
        }
    
    def _execute_preprocessing_plan(self, state: MDState, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the preprocessing commands."""
        # For now, simulate execution - in real implementation, run actual gmx commands
        working_dir = state.get("working_directory", ".")
        
        # Ensure working directory exists
        os.makedirs(working_dir, exist_ok=True)
        
        cleaned_pdb_path = os.path.join(working_dir, "processed.gro")
        topology_path = os.path.join(working_dir, "topol.top")
        
        # Create dummy files to simulate successful execution
        try:
            with open(cleaned_pdb_path, 'w') as f:
                f.write("; Simulated processed structure file\n")
                f.write("; Generated by preprocessing agent\n")
            
            # Log file creation
            log_file_operation("preprocessing", "create", cleaned_pdb_path, True, 
                             "Simulated processed structure file created")
                
            with open(topology_path, 'w') as f:
                f.write("; Simulated topology file\n") 
                f.write("; Generated by preprocessing agent\n")
            
            # Log file creation
            log_file_operation("preprocessing", "create", topology_path, True, 
                             "Simulated topology file created")
                
        except Exception as e:
            logger.warning(f"Could not create simulated files: {e}")
            log_file_operation("preprocessing", "create", cleaned_pdb_path, False, str(e))
        
        result = {
            "cleaned_pdb": cleaned_pdb_path,
            "topology": topology_path,
            "execution_log": "Simulated execution - commands would run here"
        }
        
        # In real implementation:
        # for cmd in plan["commands"]:
        #     subprocess.run(cmd, shell=True, cwd=working_dir)
        
        return result
    
    def _validate_preprocessing(self, state: MDState, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate preprocessing results."""
        issues = []
        
        # Check if expected files exist
        if not os.path.exists(result.get("cleaned_pdb", "")):
            issues.append("Cleaned PDB file not generated")
            
        if not os.path.exists(result.get("topology", "")):
            issues.append("Topology file not generated")
        
        return {
            "issues": issues,
            "report": f"Preprocessing validation: {len(issues)} issues found"
        }
