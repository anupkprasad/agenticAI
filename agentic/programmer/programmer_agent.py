"""
MD Workflow Programmer Agent

Generates execution scripts (MDP files, analysis scripts, etc.) based on
planner specifications. Only called internally by planner, not by supervisor.
"""
import logging
import os
from typing import Dict, Any, List, Optional
from ..state import MDState
from ..llm import LLMClient

logger = logging.getLogger(__name__)


class MDProgrammer:
    """
    Programmer agent that generates MD workflow scripts.
    
    Called internally by Planner when scripts are needed.
    Does not interact directly with Supervisor.
    
    Responsibilities:
    - Generate MDP files for MD simulations
    - Create analysis scripts
    - Write preprocessing scripts
    - Generate SLURM job submission scripts
    """
    
    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        
        self.llm = llm_client
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "config.yaml"
        )
        
        logger.info("MD Programmer initialized")
    
    def generate_scripts(self, state: MDState, scripts_needed: List[str]) -> MDState:
        """
        Internal method called by planner to generate required scripts.
        
        Args:
            state: Current workflow state
            scripts_needed: List of script types to generate
            
        Returns:
            Updated state with generated_scripts populated
        """
        logger.info(f"Programmer: Generating {len(scripts_needed)} script types: {scripts_needed}")
        
        generated_scripts = {}
        script_errors = []
        
        for script_type in scripts_needed:
            try:
                logger.info(f"Programmer: Generating {script_type}")
                script_info = self._generate_script_by_type(script_type, state)
                generated_scripts[script_type] = script_info
                logger.info(f"✅ Programmer: Generated {script_type}")
            except Exception as e:
                error_msg = f"Programmer: Error generating {script_type}: {str(e)}"
                logger.error(error_msg)
                script_errors.append(error_msg)
        
        # Store in state
        state["generated_scripts"] = generated_scripts
        state["script_generation_errors"] = script_errors if script_errors else []
        
        return state
    
    def _generate_script_by_type(self, script_type: str, state: MDState) -> Dict[str, Any]:
        """Generate a specific type of script."""
        
        if "mdp" in script_type.lower():
            return self._generate_mdp_file(script_type, state)
        elif "analysis" in script_type.lower():
            return self._generate_analysis_script(script_type, state)
        elif "slurm" in script_type.lower() or "job" in script_type.lower():
            return self._generate_slurm_script(script_type, state)
        elif "preprocess" in script_type.lower():
            return self._generate_preprocessing_script(script_type, state)
        else:
            return self._generate_generic_script(script_type, state)
    
    def _generate_mdp_file(self, mdp_type: str, state: MDState) -> Dict[str, Any]:
        """Generate GROMACS MDP (molecular dynamics parameter) file."""
        
        logger.info(f"Programmer: Generating {mdp_type} MDP file")
        
        plan = state.get("execution_plan", {})
        
        prompt = f"""
Generate a GROMACS MDP (molecular dynamics parameter) file for {mdp_type}.

Configuration:
- Force Field: {state.get('force_field', 'amber99sb-ildn')}
- Water Model: {state.get('water_model', 'tip3p')}
- Engine: {state.get('md_engine', 'gromacs')}

Plan Context:
{plan.get('summary', 'Standard MD simulation')}

Generate appropriate GROMACS MDP file content for {mdp_type} with proper settings.
Include all necessary parameters and comments explaining choices.
"""
        
        try:
            response = self.llm.prompt(prompt)
            
            # Save to file
            working_dir = state.get("working_directory", "./working_dir")
            os.makedirs(working_dir, exist_ok=True)
            
            filename = f"{mdp_type}.mdp"
            filepath = os.path.join(working_dir, filename)
            
            with open(filepath, 'w') as f:
                f.write(response)
            
            return {
                "file_path": filepath,
                "filename": filename,
                "type": mdp_type,
                "content_preview": response[:200],
                "purpose": f"GROMACS parameter file for {mdp_type}",
                "status": "generated"
            }
        except Exception as e:
            logger.error(f"Programmer: Error generating MDP file: {e}")
            raise
    
    def _generate_analysis_script(self, script_type: str, state: MDState) -> Dict[str, Any]:
        """Generate analysis script."""
        
        logger.info(f"Programmer: Generating {script_type} analysis script")
        
        plan = state.get("execution_plan", {})
        
        prompt = f"""
Generate a Python analysis script for {script_type}.

Context:
- Simulation type: {plan.get('summary', 'MD simulation')}
- Available tools: MDAnalysis, numpy, matplotlib

Create a complete, runnable Python script that performs {script_type}.
Include proper error handling and output generation.
"""
        
        try:
            response = self.llm.prompt(prompt)
            
            working_dir = state.get("working_directory", "./working_dir")
            os.makedirs(working_dir, exist_ok=True)
            
            filename = f"analyze_{script_type}.py"
            filepath = os.path.join(working_dir, filename)
            
            with open(filepath, 'w') as f:
                f.write(response)
            
            return {
                "file_path": filepath,
                "filename": filename,
                "type": script_type,
                "content_preview": response[:200],
                "purpose": f"Analysis script for {script_type}",
                "status": "generated"
            }
        except Exception as e:
            logger.error(f"Programmer: Error generating analysis script: {e}")
            raise
    
    def _generate_slurm_script(self, script_type: str, state: MDState) -> Dict[str, Any]:
        """Generate SLURM job submission script."""
        
        logger.info(f"Programmer: Generating {script_type} SLURM script")
        
        plan = state.get("execution_plan", {})
        resources = plan.get("resource_requirements", {})
        
        prompt = f"""
Generate a SLURM job submission script for {script_type}.

Resources needed:
{resources}

Create a production-ready SLURM script with:
- Proper resource allocation
- Module loading
- Job setup and teardown
- Error handling
- Output logging
"""
        
        try:
            response = self.llm.prompt(prompt)
            
            working_dir = state.get("working_directory", "./working_dir")
            os.makedirs(working_dir, exist_ok=True)
            
            filename = f"submit_{script_type}.sh"
            filepath = os.path.join(working_dir, filename)
            
            with open(filepath, 'w') as f:
                f.write(response)
            
            os.chmod(filepath, 0o755)
            
            return {
                "file_path": filepath,
                "filename": filename,
                "type": script_type,
                "content_preview": response[:200],
                "purpose": f"SLURM job submission script for {script_type}",
                "status": "generated"
            }
        except Exception as e:
            logger.error(f"Programmer: Error generating SLURM script: {e}")
            raise
    
    def _generate_preprocessing_script(self, script_type: str, state: MDState) -> Dict[str, Any]:
        """Generate preprocessing script."""
        
        logger.info(f"Programmer: Generating {script_type} preprocessing script")
        
        prompt = f"""
Generate a preprocessing script for {script_type}.

Input PDB: {state.get('raw_pdb', 'protein.pdb')}

Create a Python script using BioPython/MDAnalysis that:
- Loads the PDB file
- Performs {script_type} operations
- Validates the output
- Saves processed structure
"""
        
        try:
            response = self.llm.prompt(prompt)
            
            working_dir = state.get("working_directory", "./working_dir")
            os.makedirs(working_dir, exist_ok=True)
            
            filename = f"preprocess_{script_type}.py"
            filepath = os.path.join(working_dir, filename)
            
            with open(filepath, 'w') as f:
                f.write(response)
            
            return {
                "file_path": filepath,
                "filename": filename,
                "type": script_type,
                "content_preview": response[:200],
                "purpose": f"Preprocessing script for {script_type}",
                "status": "generated"
            }
        except Exception as e:
            logger.error(f"Programmer: Error generating preprocessing script: {e}")
            raise
    
    def _generate_generic_script(self, script_type: str, state: MDState) -> Dict[str, Any]:
        """Generate generic script for unknown types."""
        
        logger.info(f"Programmer: Generating generic script for {script_type}")
        
        prompt = f"""
Generate a script for: {script_type}

Context from MD workflow:
{state.get('execution_plan', {}).get('summary', 'MD workflow')}

Create a useful, well-documented script for this purpose.
"""
        
        try:
            response = self.llm.prompt(prompt)
            
            working_dir = state.get("working_directory", "./working_dir")
            os.makedirs(working_dir, exist_ok=True)
            
            filename = f"{script_type}.py"
            filepath = os.path.join(working_dir, filename)
            
            with open(filepath, 'w') as f:
                f.write(response)
            
            return {
                "file_path": filepath,
                "filename": filename,
                "type": script_type,
                "content_preview": response[:200],
                "purpose": f"Script for {script_type}",
                "status": "generated"
            }
        except Exception as e:
            logger.error(f"Programmer: Error generating script: {e}")
            raise