"""
Preprocessing Agent - Orchestrates PDB structure preparation for MD simulations
Focuses on high-level workflow coordination, delegates tool execution to tools.py
"""
import logging
import json
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action, 
    log_file_operation, log_agent_completion, log_error
)
from .schemas import (
    PreprocessingPlan, PreprocessingStep, 
    PreprocessingResult, PreprocessingAgentInput, PreprocessingAgentOutput
)
from .tools import PreprocessingToolExecutor

logger = logging.getLogger(__name__)


class PreprocessingAgent:
    """
    LLM-powered preprocessing agent - orchestrates PDB preparation workflow
    Delegates tool execution to PreprocessingToolExecutor from tools.py
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        """
        Initialize preprocessing agent
        
        Args:
            llm_client: LLM client for intelligent planning
            config_path: Path to config.yaml (defaults to same directory)
        """
        if llm_client is None:
            self.llm = LLMClient("gpt-oss:20b")
        else:
            self.llm = llm_client
        
        self.tool_executor = None
        self.config = self._load_config(config_path)
        
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load preprocessing configuration from YAML"""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            return {}
    
    def preprocess_node(self, state: MDState) -> MDState:
        """
        Main preprocessing node - entry point from workflow
        Orchestrates the entire preprocessing pipeline
        """
        log_agent_start("preprocessing", "PDB Preprocessing with LLM Tool Calling", state)
        
        try:
            # Initialize tool executor with config
            working_dir = state.get("working_directory", "working_dir")
            self.tool_executor = PreprocessingToolExecutor(working_dir, self.config)
            
            # Prepare agent input from state
            agent_input = self._prepare_agent_input(state)
            
            # Run LLM-guided preprocessing workflow
            agent_output = self._run_preprocessing_workflow(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Determine next workflow node
            if agent_output.success:
                if state.get("human_in_loop") and agent_output.result.issues:
                    state["next_node"] = "human_preprocess_check"
                else:
                    state["next_node"] = "supervisor"
            else:
                state["errors"].append(f"Preprocessing failed: {agent_output.result.report}")
                state["next_node"] = "supervisor"
            
            success = agent_output.success and len(agent_output.result.issues) == 0
            log_agent_completion("preprocessing", "PDB Preprocessing", state, success)
            
        except Exception as e:
            logger.error(f"Preprocessing agent failed: {e}")
            log_error("preprocessing_agent.preprocess_node", e, {"state": state})
            state["errors"].append(f"Preprocessing error: {str(e)}")
            state["next_node"] = "supervisor"
        
        return state
    
    def _prepare_agent_input(self, state: MDState) -> PreprocessingAgentInput:
        """Prepare structured input for preprocessing from workflow state"""
        defaults = self.config.get("defaults", {})
        
        return PreprocessingAgentInput(
            pdb_path=state.get("raw_pdb", ""),
            working_directory=state.get("working_directory", "working_dir"),
            force_field=state.get("force_field", defaults.get("force_field", "amber99sb-ildn")),
            water_model=state.get("water_model", defaults.get("water_model", "tip3p")),
            remove_waters=state.get("remove_waters", defaults.get("remove_waters", True)),
            add_hydrogens=state.get("add_hydrogens", defaults.get("add_hydrogens", True)),
            user_goal=state.get("user_goal", ""),
            additional_instructions=state.get("preprocessing_instructions", None)
        )
    
    def _run_preprocessing_workflow(self, agent_input: PreprocessingAgentInput, 
                                    state: MDState) -> PreprocessingAgentOutput:
        """
        Run complete preprocessing workflow:
        1. LLM creates intelligent plan based on PDB analysis
        2. Execute plan step-by-step using tools
        3. Return structured results
        """
        try:
            # Step 1: LLM analyzes PDB and creates plan
            plan = self._create_preprocessing_plan(agent_input)
            
            log_agent_action("preprocessing", "Generated preprocessing plan", {
                "steps": len(plan.steps),
                "reasoning": plan.reasoning[:200]
            })
            
            # Step 2: Execute plan using tool executor
            result = self._execute_plan(agent_input, plan, state)
            
            # Step 3: Prepare supervisor update
            supervisor_update = {
                "cleaned_pdb": result.cleaned_pdb,
                "topology": result.topology,
                "processed_coordinates": result.processed_coordinates,
                "preprocessing_report": result.report
            }
            
            return PreprocessingAgentOutput(
                success=result.success,
                plan=plan,
                result=result,
                supervisor_update=supervisor_update
            )
            
        except Exception as e:
            logger.error(f"Preprocessing workflow failed: {e}")
            return PreprocessingAgentOutput(
                success=False,
                plan=PreprocessingPlan(
                    reasoning=f"Error in planning: {str(e)}",
                    overview="Failed",
                    steps=[]
                ),
                result=PreprocessingResult(
                    success=False,
                    report=f"Error: {str(e)}",
                    issues=[str(e)],
                    warnings=[]
                ),
                supervisor_update={}
            )
    
    def _create_preprocessing_plan(self, agent_input: PreprocessingAgentInput) -> PreprocessingPlan:
        """
        Use LLM to analyze PDB and create intelligent preprocessing plan
        Falls back to template-based plan if LLM fails
        """
        # First, analyze the PDB structure
        analysis_result = self.tool_executor.execute_tool(
            "analyze_pdb",
            {"pdb_file": agent_input.pdb_path}
        )
        
        analysis = analysis_result.get("analysis", {}) if analysis_result.get("success") else {}
        
        # Build LLM prompt from config template
        prompt = self._build_planning_prompt(agent_input, analysis)
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            log_llm_interaction("preprocessing.planning", prompt, content,
                              is_mock=hasattr(self.llm, '_is_mock_mode') and self.llm._is_mock_mode)
            
            # Parse LLM response into structured plan
            plan_dict = self._extract_plan_json(content)
            
            return PreprocessingPlan(
                reasoning=plan_dict.get("reasoning", content[:500]),
                overview=plan_dict.get("overview", "Processing PDB for MD simulation"),
                steps=[
                    PreprocessingStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", "")
                    )
                    for step in plan_dict.get("steps", [])
                ],
                potential_issues=plan_dict.get("potential_issues", []),
                recommendations=plan_dict.get("recommendations", [])
            )
            
        except Exception as e:
            logger.warning(f"LLM planning failed, using fallback: {e}")
            return self._create_fallback_plan(agent_input, analysis)
    
    def _build_planning_prompt(self, agent_input: PreprocessingAgentInput, 
                               analysis: Dict[str, Any]) -> str:
        """Build LLM planning prompt from config template"""
        config_prompt = self.config.get("llm", {}).get("planning_prompt_template", "")
        
        # Get available tools list from config
        tools_config = self.config.get("tools", {})
        tools_list = "\n".join([
            f"- {name}: {info.get('description', '')}"
            for name, info in tools_config.items()
        ])
        
        # Format analysis for prompt
        analysis_str = "\n".join([
            f"- Atoms: {analysis.get('atom_count', 'unknown')}",
            f"- Chains: {analysis.get('chain_ids', [])}",
            f"- Has Waters: {analysis.get('has_waters', False)}",
            f"- Heteroatoms: {analysis.get('heteroatoms', [])}",
            f"- Alternate Locations: {analysis.get('alternate_locations', False)}"
        ])
        
        # Use template or build basic prompt
        if config_prompt:
            return config_prompt.format(
                pdb_path=agent_input.pdb_path,
                user_goal=agent_input.user_goal,
                force_field=agent_input.force_field,
                water_model=agent_input.water_model,
                analysis=analysis_str,
                tools_list=tools_list
            )
        else:
            # Fallback prompt
            return f"""
You are a molecular dynamics preprocessing expert. Create a preprocessing plan for:

PDB: {agent_input.pdb_path}
Goal: {agent_input.user_goal}
Analysis: {analysis_str}

Available tools: {tools_list}

Return JSON with: reasoning, overview, steps (name, description, tool_name, tool_params, reason)
"""
    
    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract and parse JSON plan from LLM response"""
        import re
        
        # Try to find JSON block in response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: return minimal structure
        return {
            "reasoning": content,
            "overview": "Preprocessing plan",
            "steps": []
        }
    
    def _create_fallback_plan(self, agent_input: PreprocessingAgentInput, 
                             analysis: Dict[str, Any]) -> PreprocessingPlan:
        """
        Create template-based fallback plan when LLM fails
        Uses workflows from config.yaml
        """
        steps = []
        workflows = self.config.get("workflows", {})
        
        # Use "full" workflow as default
        default_workflow = workflows.get("full", {}).get("steps", [
            "analyze_pdb", "remove_waters", "handle_alternate_locations", 
            "add_hydrogens", "prepare_for_gromacs", "validate_structure"
        ])
        
        # Build steps based on workflow and analysis
        for tool_name in default_workflow:
            step = self._create_step_from_tool(tool_name, agent_input, analysis)
            if step:
                steps.append(step)
        
        return PreprocessingPlan(
            reasoning="Using standard preprocessing workflow (LLM fallback)",
            overview="Standard PDB preprocessing for GROMACS MD simulation",
            steps=steps,
            potential_issues=[],
            recommendations=["Review generated topology file before simulation"]
        )
    
    def _create_step_from_tool(self, tool_name: str, agent_input: PreprocessingAgentInput,
                               analysis: Dict[str, Any]) -> Optional[PreprocessingStep]:
        """Create preprocessing step from tool name and analysis"""
        tools_config = self.config.get("tools", {})
        tool_info = tools_config.get(tool_name, {})
        
        # Skip if conditions not met
        if tool_name == "remove_waters" and not analysis.get("has_waters"):
            return None
        if tool_name == "handle_alternate_locations" and not analysis.get("alternate_locations"):
            return None
        
        # Build tool params
        tool_params = {"pdb_file": agent_input.pdb_path}
        
        if tool_name == "add_hydrogens":
            defaults = self.config.get("defaults", {})
            tool_params["method"] = defaults.get("hydrogen_method", "reduce")
        elif tool_name == "prepare_for_gromacs":
            tool_params["force_field"] = agent_input.force_field
        
        return PreprocessingStep(
            name=tool_name.replace("_", " ").title(),
            description=tool_info.get("description", f"Execute {tool_name}"),
            tool_name=tool_name,
            tool_params=tool_params,
            reason=f"Required for {tool_info.get('description', 'preprocessing')}"
        )
    
    def _execute_plan(self, agent_input: PreprocessingAgentInput, plan: PreprocessingPlan,
                     state: MDState) -> PreprocessingResult:
        """
        Execute preprocessing plan step-by-step using tool executor
        Tracks file outputs and chains them between steps
        """
        execution_log = []
        issues = []
        warnings = []
        generated_files = {}
        
        current_pdb = agent_input.pdb_path
        topology_file = None
        processed_coords = None
        
        try:
            for i, step in enumerate(plan.steps):
                log_agent_action("preprocessing", f"Executing step {i+1}/{len(plan.steps)}", {
                    "step": step.name,
                    "tool": step.tool_name
                })
                
                execution_log.append(f"\n--- Step {i+1}: {step.name} ---")
                execution_log.append(f"Description: {step.description}")
                execution_log.append(f"Tool: {step.tool_name}")
                execution_log.append(f"Reason: {step.reason}")
                
                # Prepare tool parameters
                tool_params = dict(step.tool_params) if step.tool_params else {}
                
                # Auto-inject pdb_file for tools that need it
                if "pdb_file" not in tool_params and step.tool_name in [
                    "remove_waters", "handle_alternate_locations", "add_hydrogens",
                    "assign_protonation", "prepare_for_gromacs", "validate_structure"
                ]:
                    tool_params["pdb_file"] = current_pdb
                
                # Update chained input file
                if tool_params.get("pdb_file") == agent_input.pdb_path and current_pdb != agent_input.pdb_path:
                    tool_params["pdb_file"] = current_pdb
                
                # Execute tool via tool executor
                result = self.tool_executor.execute_tool(step.tool_name, tool_params)
                
                # Process results
                if result.get("success"):
                    execution_log.append(f"✓ Success: {result.get('message', 'Step completed')}")
                    
                    # Track output files for chaining
                    if "output_file" in result:
                        current_pdb = result["output_file"]
                        generated_files[result["output_file"]] = step.description
                    
                    if "topology_file" in result:
                        topology_file = result["topology_file"]
                        generated_files[topology_file] = "GROMACS topology file"
                    
                    if result.get("warning"):
                        warnings.append(f"{step.name}: {result['warning']}")
                else:
                    execution_log.append(f"✗ Failed: {result.get('error', 'Unknown error')}")
                    issues.append(f"{step.name}: {result.get('error', 'Failed to execute')}")
            
            # Verify required outputs
            if not topology_file:
                issues.append("No topology file generated - GROMACS preparation may have failed")
            
            execution_log_str = "\n".join(execution_log)
            
            return PreprocessingResult(
                success=len(issues) == 0,
                cleaned_pdb=current_pdb,
                topology=topology_file or str(Path(agent_input.working_directory) / "topol.top"),
                processed_coordinates=processed_coords or str(Path(agent_input.working_directory) / "processed.gro"),
                report=f"Preprocessing completed: {len(plan.steps)} steps executed",
                issues=issues,
                warnings=warnings,
                generated_files=generated_files,
                execution_log=execution_log_str
            )
            
        except Exception as e:
            return PreprocessingResult(
                success=False,
                report=f"Preprocessing failed: {str(e)}",
                issues=[str(e)],
                warnings=warnings,
                generated_files=generated_files,
                execution_log="\n".join(execution_log)
            )
    
    def _update_state(self, state: MDState, agent_output: PreprocessingAgentOutput):
        """Update workflow state with preprocessing results"""
        if agent_output.supervisor_update:
            state.update(agent_output.supervisor_update)
        
        state["preprocessing_report"] = agent_output.result.report
        state["preprocessing_issues"] = agent_output.result.issues
        state["preprocessing_warnings"] = agent_output.result.warnings
        state["preprocessing_execution_log"] = agent_output.result.execution_log
        
        # Log file operations
        for file_path, description in agent_output.result.generated_files.items():
            log_file_operation("preprocessing", "create", file_path, True, description)
