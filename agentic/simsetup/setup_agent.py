"""Simulation Setup Agent with Deep Planning and Modular Tools"""
import logging
import os
import yaml
from typing import Dict, Any, List
from pathlib import Path
from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action, 
    log_file_operation, log_agent_completion
)
from .tools import SimulationSetupToolExecutor

logger = logging.getLogger(__name__)

class SimulationSetupAgent:
    """
    Handles simulation system setup: topology, solvation, ions, MDP generation.
    Uses modular @tool functions from src/simsetup/ for all operations.
    """
    
    def __init__(self, llm_client=None, config_path: str = None):
        self.llm = llm_client or LLMClient()
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Tool executor will be initialized per-node with agent-specific directory
        self.tools = None
        
    def setup_node(self, state: MDState) -> MDState:
        """Main setup node with planning capability."""
        # Log agent start
        log_agent_start("setup", "System Setup", state)
        
        try:
            # Initialize tool executor with agent-specific subdirectory
            base_working_dir = state.get("working_directory", "working_dir")
            simsetup_dir = str(Path(base_working_dir) / "simsetup")
            Path(simsetup_dir).mkdir(parents=True, exist_ok=True)
            
            self.tools = SimulationSetupToolExecutor(
                working_dir=simsetup_dir,
                config=self.config
            )
            
            # Copy preprocessed file from preprocess directory if needed
            self._copy_preprocessed_files(state, simsetup_dir)
            
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
    
        
    def _copy_preprocessed_files(self, state: MDState, simsetup_dir: str):
        """Copy necessary files from preprocess directory to simsetup directory"""
        import shutil
        
        preprocess_dir = state.get("preprocess_directory")
        if not preprocess_dir:
            logger.warning("No preprocess_directory in state, files may not be copied")
            return
        
        # Copy cleaned PDB file
        cleaned_pdb = state.get("cleaned_pdb")
        if cleaned_pdb and os.path.exists(cleaned_pdb):
            # Update path to simsetup directory
            filename = Path(cleaned_pdb).name
            new_path = str(Path(simsetup_dir) / filename)
            
            if cleaned_pdb != new_path:  # Only copy if different location
                shutil.copy2(cleaned_pdb, new_path)
                state["cleaned_pdb"] = new_path
                logger.info(f"Copied {filename} from preprocess to simsetup directory")
        
        # Copy topology file if it exists
        topology = state.get("topology")
        if topology and os.path.exists(topology):
            filename = Path(topology).name
            new_path = str(Path(simsetup_dir) / filename)
            
            if topology != new_path:
                shutil.copy2(topology, new_path)
                state["topology"] = new_path
                logger.info(f"Copied {filename} from preprocess to simsetup directory")
    
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
        """Fallback setup plan if LLM fails - uses modular tools."""
        working_dir = state.get("working_directory", ".")
        cleaned_pdb = state.get("cleaned_pdb", "")
        
        return {
            "reasoning": "Using default GROMACS setup protocol with modular tools",
            "box_setup": f"Building cubic box with 1.0 nm buffer around {cleaned_pdb}",
            "solvation": "Adding spc216 water model",
            "ion_placement": "Neutralizing and adding 0.15 M NaCl",
            "mdp_protocols": "Using standard GROMACS MDP templates from modular tools",
            "grompp_sequence": "Standard grompp workflow for each simulation phase",
            "validation": "Checking file generation and parameter correctness"
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
        """Execute the setup plan using modular @tool functions."""
        # Use simsetup subdirectory (already created in setup_node)
        base_working_dir = state.get("working_directory", ".")
        simsetup_dir = str(Path(base_working_dir) / "simsetup")
        
        results = {
            "mdp_files": {},
            "execution_log": []
        }
        
        try:
            # Step 1: Build topology using cleaned PDB
            cleaned_pdb = state.get("cleaned_pdb", "")
            if cleaned_pdb and os.path.exists(cleaned_pdb):
                log_agent_action("setup", "Building topology", {"input": cleaned_pdb})
                topology_result = self.tools.build_topology(
                    pdb_file=cleaned_pdb,
                    force_field=state.get("force_field", "amber99sb-ildn"),
                    water_model=state.get("water_model", "tip3p"),
                    output_file=os.path.join(simsetup_dir, "processed.gro")
                )
                
                if topology_result.get("success"):
                    results["coordinates"] = topology_result.get("output_file")
                    results["topology_file"] = topology_result.get("topology_file")
                    results["execution_log"].append("Topology built successfully")
                    log_file_operation("setup", "created", topology_result.get("output_file"))
                else:
                    results["execution_log"].append(f"Topology build failed: {topology_result.get('error')}")
                    
            # Step 2: Build simulation box
            if results.get("coordinates"):
                log_agent_action("setup", "Building simulation box", {"box_type": "cubic"})
                box_result = self.tools.build_simulation_box(
                    coordinate_file=results["coordinates"],
                    box_type="cubic",
                    box_distance=1.0,
                    output_file=os.path.join(simsetup_dir, "boxed.gro")
                )
                
                if box_result.get("success"):
                    results["coordinates"] = box_result.get("output_file")
                    results["box_dimensions"] = "cubic, 1.0 nm buffer"
                    results["execution_log"].append("Simulation box created")
                    log_file_operation("setup", "created", box_result.get("output_file"))
                else:
                    results["execution_log"].append(f"Box creation failed: {box_result.get('error')}")
                    
            # Step 3: Solvate system
            if results.get("coordinates") and results.get("topology_file"):
                log_agent_action("setup", "Solvating system", {"water_model": "spc216"})
                solvate_result = self.tools.solvate_system(
                    coordinate_file=results["coordinates"],
                    topology_file=results["topology_file"],
                    water_model="spc216",
                    output_file=os.path.join(simsetup_dir, "solvated.gro")
                )
                
                if solvate_result.get("success"):
                    results["coordinates"] = solvate_result.get("output_file")
                    results["water_molecules"] = solvate_result.get("water_molecules", "unknown")
                    results["execution_log"].append("System solvated")
                    log_file_operation("setup", "created", solvate_result.get("output_file"))
                else:
                    results["execution_log"].append(f"Solvation failed: {solvate_result.get('error')}")
                    
            # Step 4: Generate MDP files
            log_agent_action("setup", "Generating MDP files", {"phases": ["minim", "nvt", "npt", "md", "ions"]})
            mdp_phases = ["minim", "nvt", "npt", "md", "ions"]
            for phase in mdp_phases:
                mdp_result = self.tools.generate_mdp_file(
                    mdp_type=phase,
                    temperature=state.get("temperature", 300.0),
                    pressure=1.0,
                    output_file=os.path.join(simsetup_dir, f"{phase}.mdp")
                )
                
                if mdp_result.get("success"):
                    results["mdp_files"][phase] = mdp_result.get("output_file")
                    log_file_operation("setup", "created", mdp_result.get("output_file"))
                else:
                    results["execution_log"].append(f"MDP {phase} generation failed: {mdp_result.get('error')}")
            
            # Step 5: Add ions (after MDP files are ready)
            if results.get("coordinates") and results.get("topology_file") and "ions" in results["mdp_files"]:
                log_agent_action("setup", "Adding ions", {"neutral": True, "concentration": 0.15})
                ions_result = self.tools.add_ions(
                    coordinate_file=results["coordinates"],
                    topology_file=results["topology_file"],
                    mdp_file=results["mdp_files"]["ions"],
                    neutral=True,
                    concentration=0.15,
                    output_file=os.path.join(simsetup_dir, "system.gro")
                )
                
                if ions_result.get("success"):
                    results["coordinates"] = ions_result.get("output_file")
                    results["ion_count"] = ions_result.get("ions_added", {})
                    results["execution_log"].append("Ions added successfully")
                    log_file_operation("setup", "created", ions_result.get("output_file"))
                else:
                    results["execution_log"].append(f"Ion addition failed: {ions_result.get('error')}")
            
            results["execution_log"].append("Setup plan execution complete")
            
        except Exception as e:
            logger.error(f"Setup execution failed: {e}")
            results["execution_log"].append(f"Error during setup: {str(e)}")
        
        return results
    
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
