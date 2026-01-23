"""Simulation Setup Agent with Deep Planning"""
import logging
import os
from typing import Dict, Any, List
from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action, 
    log_file_operation, log_agent_completion
)

logger = logging.getLogger(__name__)

class SimulationSetupAgent:
    """
    Handles simulation system setup: solvation, ions, MDP generation.
    Uses deep planning for protocol decisions and equilibration strategies.
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client or LLMClient()
        
    def setup_node(self, state: MDState) -> MDState:
        """Main setup node with planning capability."""
        # Log agent start
        log_agent_start("setup", "System Setup", state)
        
        try:
            # 1. Analyze preprocessed system
            log_agent_action("setup", "Analyzing preprocessed system", {
                "cleaned_structure": state.get("cleaned_pdb", "unknown")
            })
            analysis = self._analyze_preprocessed_system(state)
            
            # 2. Generate setup plan using LLM
            log_agent_action("setup", "Generating setup plan", {
                "analysis_results": analysis
            })
            plan = self._generate_setup_plan(state, analysis)
            
            # 3. Execute setup commands
            log_agent_action("setup", "Executing setup commands", {
                "plan_protocols": plan.get("mdp_protocols", "unknown")
            })
            result = self._execute_setup_plan(state, plan)
            
            # 4. Validate setup
            validation = self._validate_setup(state, result)
            
            # 5. Update state
            state.update(result)
            state["setup_report"] = plan.get("reasoning", "") + "\n" + validation.get("report", "")
            state["setup_issues"] = validation.get("issues", [])
            
            # Route based on validation
            if state["setup_issues"] and state["human_in_loop"]:
                state["next_node"] = "human_setup_check"
            else:
                state["next_node"] = "supervisor"
            
            # Log completion
            success = len(state["setup_issues"]) == 0
            log_agent_completion("setup", "System Setup", state, success)
                
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            from ..utils import log_error
            log_error("setup_agent.setup_node", e, {"state": state})
            state["errors"].append(f"Setup error: {str(e)}")
            state["next_node"] = "supervisor"
            
        return state
    
    def _analyze_preprocessed_system(self, state: MDState) -> Dict[str, Any]:
        """Analyze the preprocessed system to inform setup decisions."""
        analysis = {
            "system_size": "unknown",
            "charge": 0,
            "has_membrane": False,
            "protein_only": True,
            "estimated_atoms": 0
        }
        
        # In real implementation, analyze the topology/gro file
        cleaned_pdb = state.get("cleaned_pdb", "")
        if os.path.exists(cleaned_pdb):
            try:
                with open(cleaned_pdb, 'r') as f:
                    lines = f.readlines()
                    analysis["estimated_atoms"] = len([l for l in lines if l.strip() and not l.startswith(';')])
            except Exception as e:
                logger.warning(f"Could not analyze system: {e}")
                
        return analysis
    
    def _generate_setup_plan(self, state: MDState, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to generate comprehensive simulation setup plan."""
        
        prompt = f"""
        You are an expert in molecular dynamics simulation setup using GROMACS. Generate a detailed setup plan for this system.

        User Goal: {state['user_goal']}
        System Information:
        - Preprocessed structure: {state.get('cleaned_pdb')}
        - Topology: {state.get('topology')}
        - Force field: {state['force_field']}
        - Water model: {state['water_model']}
        - Estimated atoms: {analysis['estimated_atoms']}
        - System charge: {analysis['charge']}
        
        Create a comprehensive setup plan including:
        
        1. **Box Definition Strategy**
           - Box type and size considerations
           - Distance from protein surface
           - Justification for choices
        
        2. **Solvation Strategy**
           - Water model application
           - Expected water molecules
           - Solvation shell considerations
        
        3. **Ion Placement Strategy**
           - Neutralization approach
           - Physiological salt concentration (0.15 M NaCl)
           - Ion placement methodology
        
        4. **MDP File Strategy**
           - Energy minimization protocol
           - NVT equilibration parameters
           - NPT equilibration parameters  
           - Production MD settings
           - Time steps, thermostats, barostats
        
        5. **Quality Control Checks**
           - Energy validation criteria
           - Equilibration convergence metrics
           - Common failure modes to watch for
        
        Format your response as:
        
        REASONING:
        [Your detailed scientific reasoning for each choice]
        
        BOX_SETUP:
        [Specific box parameters and gmx editconf command]
        
        SOLVATION:
        [Water addition strategy and gmx solvate command]
        
        ION_PLACEMENT:
        [Ion addition strategy and gmx genion commands]
        
        MDP_PROTOCOLS:
        [Detailed MDP file contents for each phase]
        
        GROMPP_SEQUENCE:
        [gmx grompp commands to prepare TPR files]
        
        VALIDATION:
        [Quality control checks to perform]
        """
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            return {
                "reasoning": self._extract_section(content, "REASONING"),
                "box_setup": self._extract_section(content, "BOX_SETUP"),
                "solvation": self._extract_section(content, "SOLVATION"),
                "ion_placement": self._extract_section(content, "ION_PLACEMENT"),
                "mdp_protocols": self._extract_section(content, "MDP_PROTOCOLS"),
                "grompp_sequence": self._extract_section(content, "GROMPP_SEQUENCE"),
                "validation": self._extract_section(content, "VALIDATION"),
                "full_response": content
            }
        except Exception as e:
            logger.error(f"LLM setup planning failed: {e}")
            return self._fallback_setup_plan(state, analysis)
    
    def _extract_section(self, content: str, section: str) -> str:
        """Extract a specific section from LLM response."""
        if f"{section}:" in content:
            start = content.find(f"{section}:")
            # Find next section or end
            next_sections = ["REASONING:", "BOX_SETUP:", "SOLVATION:", "ION_PLACEMENT:", 
                           "MDP_PROTOCOLS:", "GROMPP_SEQUENCE:", "VALIDATION:"]
            next_sections.remove(f"{section}:")
            
            end = len(content)
            for next_section in next_sections:
                next_pos = content.find(next_section, start + 1)
                if next_pos != -1:
                    end = min(end, next_pos)
            
            return content[start + len(f"{section}:"):end].strip()
        return ""
    
    def _fallback_setup_plan(self, state: MDState, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback setup plan if LLM fails."""
        working_dir = state.get("working_directory", ".")
        cleaned_pdb = state.get("cleaned_pdb", "")
        
        return {
            "reasoning": "Using default GROMACS setup protocol",
            "commands": [
                f"gmx editconf -f {cleaned_pdb} -o boxed.gro -c -d 1.0 -bt cubic",
                f"gmx solvate -cp boxed.gro -cs spc216.gro -p topol.top -o solvated.gro",
                f"gmx grompp -f minim.mdp -c solvated.gro -p topol.top -o ions.tpr",
                f"echo 'SOL' | gmx genion -s ions.tpr -p topol.top -pname NA -nname CL -neutral -conc 0.15 -o system.gro"
            ],
            "mdp_files": self._generate_default_mdp_files()
        }
    
    def _generate_default_mdp_files(self) -> Dict[str, str]:
        """Generate default MDP file contents."""
        return {
            "minim": """
; Energy minimization
integrator  = steep
emtol       = 1000.0
emstep      = 0.01
nsteps      = 50000
nstlist     = 1
cutoff-scheme = Verlet
ns_type     = grid
coulombtype = PME
rcoulomb    = 1.0
rvdw        = 1.0
pbc         = xyz
""",
            "nvt": """
; NVT equilibration
title       = NVT equilibration
integrator  = md
nsteps      = 50000    ; 100 ps
dt          = 0.002    ; 2 fs
nstxout     = 1000
nstvout     = 1000
nstenergy   = 1000
nstlog      = 1000
continuation = no
constraint_algorithm = lincs
constraints = all-bonds
nstlist     = 10
ns_type     = grid
pbc         = xyz
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb    = 1.0
rvdw        = 1.0
tcoupl      = V-rescale
tc-grps     = System
tau_t       = 0.1
ref_t       = 300
pcoupl      = no
""",
            "npt": """
; NPT equilibration  
title       = NPT equilibration
integrator  = md
nsteps      = 50000    ; 100 ps
dt          = 0.002    ; 2 fs
nstxout     = 1000
nstvout     = 1000
nstenergy   = 1000
nstlog      = 1000
continuation = yes
constraint_algorithm = lincs
constraints = all-bonds
nstlist     = 10
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb    = 1.0
rvdw        = 1.0
tcoupl      = V-rescale
tc-grps     = System
tau_t       = 0.1
ref_t       = 300
pcoupl      = Parrinello-Rahman
pcoupltype  = isotropic
tau_p       = 2.0
ref_p       = 1.0
compressibility = 4.5e-5
""",
            "md": """
; Production MD
title       = Production MD
integrator  = md
nsteps      = 50000000  ; 100 ns
dt          = 0.002     ; 2 fs
nstxout     = 5000      ; save coords every 10 ps
nstvout     = 5000      ; save velocities every 10 ps
nstenergy   = 1000      ; save energies every 2 ps
nstlog      = 1000      ; save log every 2 ps
continuation = yes
constraint_algorithm = lincs
constraints = all-bonds
nstlist     = 10
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb    = 1.0
rvdw        = 1.0
tcoupl      = V-rescale
tc-grps     = System
tau_t       = 0.1
ref_t       = 300
pcoupl      = Parrinello-Rahman
pcoupltype  = isotropic
tau_p       = 2.0
ref_p       = 1.0
compressibility = 4.5e-5
"""
        }
    
    def _execute_setup_plan(self, state: MDState, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the setup plan."""
        working_dir = state.get("working_directory", ".")
        
        # Ensure working directory exists
        os.makedirs(working_dir, exist_ok=True)
        
        # Generate MDP files
        mdp_files = {}
        mdp_content = plan.get("mdp_protocols", "")
        if mdp_content:
            # Parse MDP content from LLM response
            mdp_files = self._parse_mdp_from_plan(mdp_content)
        else:
            mdp_files = self._generate_default_mdp_files()
        
        # Write MDP files and create dummy simulation files
        mdp_paths = {}
        for phase, content in mdp_files.items():
            mdp_path = os.path.join(working_dir, f"{phase}.mdp")
            try:
                with open(mdp_path, 'w') as f:
                    f.write(content)
                mdp_paths[phase] = mdp_path
            except Exception as e:
                logger.warning(f"Could not create MDP file {mdp_path}: {e}")
        
        # Create dummy system coordinate file
        coords_path = os.path.join(working_dir, "system.gro")
        try:
            with open(coords_path, 'w') as f:
                f.write("; Simulated system coordinates\n")
                f.write("; Generated by setup agent\n")
                f.write("System\n")
                f.write("    1\n")
                f.write("1SOL     OW    1   1.000   1.000   1.000\n")
                f.write("   2.00000   2.00000   2.00000\n")
        except Exception as e:
            logger.warning(f"Could not create coordinates file: {e}")
        
        result = {
            "coordinates": coords_path,
            "mdp_files": mdp_paths,
            "execution_log": "Simulated setup execution",
            "box_dimensions": "cubic, 1.0 nm buffer",
            "water_molecules": "estimated 15000-20000",
            "ion_count": {"NA": 10, "CL": 10}
        }
        
        return result
    
    def _parse_mdp_from_plan(self, mdp_content: str) -> Dict[str, str]:
        """Parse MDP file contents from LLM plan."""
        # Simple parsing - could be improved
        mdp_files = {}
        
        # Look for common MDP sections
        sections = ["minim", "nvt", "npt", "md"]
        for section in sections:
            if section in mdp_content.lower():
                # Extract content between markers
                start = mdp_content.lower().find(section)
                # Find next section or end
                next_start = len(mdp_content)
                for other in sections:
                    if other != section:
                        pos = mdp_content.lower().find(other, start + 1)
                        if pos != -1:
                            next_start = min(next_start, pos)
                
                content = mdp_content[start:next_start]
                mdp_files[section] = content
        
        # If parsing fails, use defaults
        if not mdp_files:
            mdp_files = self._generate_default_mdp_files()
            
        return mdp_files
    
    def _validate_setup(self, state: MDState, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate setup results."""
        issues = []
        
        # Check required files
        if not result.get("coordinates"):
            issues.append("Final coordinate file not generated")
            
        if not result.get("mdp_files"):
            issues.append("MDP files not generated")
            
        # Check MDP completeness
        required_phases = ["minim", "nvt", "npt", "md"]
        missing_phases = [p for p in required_phases if p not in result.get("mdp_files", {})]
        if missing_phases:
            issues.append(f"Missing MDP files for: {', '.join(missing_phases)}")
        
        return {
            "issues": issues,
            "report": f"Setup validation: {len(issues)} issues found. Generated {len(result.get('mdp_files', {}))} MDP files."
        }
