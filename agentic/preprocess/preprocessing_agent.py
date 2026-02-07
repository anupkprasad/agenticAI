"""
Preprocessing Agent - Orchestrates PDB structure preparation for MD simulations
Focuses on high-level workflow coordination, delegates tool execution to tools.py
"""
import logging
import json
import yaml
import os
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
from .tools import PreprocessingToolExecutor, get_tool_metadata

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
        # Check if we have planner instructions
        execution_plan = state.get("execution_plan", {})
        has_planner_instructions = execution_plan.get("format") == "natural_language"
        
        input_summary = {
            "raw_pdb": state.get("raw_pdb"),
            "force_field": state.get("force_field"),
            "water_model": state.get("water_model")
        }
        
        if has_planner_instructions:
            # Extract just the preprocessing agent section from the full plan
            full_plan = execution_plan.get("full_plan", "")
            preprocessing_section = self._extract_agent_instructions(full_plan, "Preprocessing Agent")
            if preprocessing_section:
                input_summary["planner_instructions"] = preprocessing_section
            else:
                input_summary["planner_instructions"] = "[Natural language plan from planner - see above]"
        else:
            # Fallback to user goal if no planner instructions
            input_summary["user_goal"] = state.get("user_goal")
        
        log_agent_start("preprocessing", "PDB Preprocessing with LLM Tool Calling", input_summary)
        
        try:
            # Initialize tool executor with agent-specific subdirectory
            base_working_dir = state.get("working_directory", "working_dir")
            preprocess_dir = str(Path(base_working_dir) / "preprocess")
            Path(preprocess_dir).mkdir(parents=True, exist_ok=True)
            
            # CRITICAL: Set preprocess_directory in state BEFORE creating tool executor
            # This allows tools to access the directory during execution
            state["preprocess_directory"] = preprocess_dir
            
            self.tool_executor = PreprocessingToolExecutor(preprocess_dir, self.config)
            
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
    
    def _extract_agent_instructions(self, full_plan: str, agent_name: str) -> Optional[str]:
        """
        Extract agent-specific detailed instructions from planner's natural language plan.
        
        Args:
            full_plan: Complete natural language plan from planner
            agent_name: Name of the agent section to extract (e.g., "Preprocessing Agent")
            
        Returns:
            Extracted instructions for this specific agent, or None if not found
        """
        import re
        
        # Try to find the agent section (supports various heading formats)
        patterns = [
            rf'###\s*{agent_name}.*?\n(.*?)(?=###|\Z)',  # Markdown ### heading
            rf'##\s*{agent_name}.*?\n(.*?)(?=##|\Z)',    # Markdown ## heading  
            rf'\*\*{agent_name}\*\*.*?\n(.*?)(?=\*\*[A-Z]|\Z)',  # Bold heading
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                logger.info(f"Extracted {len(instructions)} chars of detailed instructions for {agent_name}")
                return instructions
        
        logger.warning(f"Could not find specific instructions for {agent_name} in natural language plan")
        return None
    
    def _prepare_agent_input(self, state: MDState) -> PreprocessingAgentInput:
        """Prepare structured input for preprocessing from workflow state"""
        defaults = self.config.get("defaults", {})
        
        # Check if planner provided detailed instructions for this agent
        execution_plan = state.get("execution_plan", {})
        planner_instructions = None
        
        if execution_plan.get("format") == "natural_language":
            # Extract preprocessing-specific instructions from natural language plan
            full_plan = execution_plan.get("full_plan", "")
            planner_instructions = self._extract_agent_instructions(full_plan, "Preprocessing Agent")
            
        return PreprocessingAgentInput(
            pdb_path=state.get("raw_pdb", ""),
            working_directory=state.get("working_directory", "working_dir"),
            force_field=state.get("force_field", defaults.get("force_field", "amber99sb-ildn")),
            water_model=state.get("water_model", defaults.get("water_model", "tip3p")),
            remove_waters=state.get("remove_waters", defaults.get("remove_waters", True)),
            add_hydrogens=state.get("add_hydrogens", defaults.get("add_hydrogens", True)),
            user_goal=state.get("user_goal", ""),
            additional_instructions=planner_instructions or state.get("preprocessing_instructions", None)
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
        """Build LLM planning prompt - use planner's detailed instructions if available"""
        
        # Check if we have detailed instructions from planner
        if agent_input.additional_instructions:
            logger.info("Using planner's detailed instructions for preprocessing")
            return self._build_prompt_from_planner_instructions(
                agent_input, analysis, agent_input.additional_instructions
            )
        
        # Otherwise use standard config-based prompt
        return self._build_standard_planning_prompt(agent_input, analysis)
    
    def _build_prompt_from_planner_instructions(self, agent_input: PreprocessingAgentInput,
                                                analysis: Dict[str, Any],
                                                planner_instructions: str) -> str:
        """Build prompt using planner's detailed natural language instructions"""
        
        # Get available tools for reference
        tool_metadata = get_tool_metadata()
        tools_list = []
        
        for tool_info in tool_metadata.values():
            tool_entry = f"• {tool_info['name']}\n"
            tool_entry += f"  Description: {tool_info['description']}\n"
            
            if tool_info['args']:
                tool_entry += "  Arguments:\n"
                for arg_name, arg_details in tool_info['args'].items():
                    required = "required" if arg_details['required'] else "optional"
                    arg_type = arg_details['type']
                    tool_entry += f"    - {arg_name} ({arg_type}, {required})\n"
            
            tools_list.append(tool_entry)
        
        tools_list_str = "\n".join(tools_list)
        
        # Format analysis
        analysis_str = "\n".join([
            f"- Atoms: {analysis.get('atom_count', 'unknown')}",
            f"- Chains: {analysis.get('chain_ids', [])}",
            f"- Has Waters: {analysis.get('has_waters', False)}",
            f"- Heteroatoms: {analysis.get('heteroatoms', [])}",
            f"- Alternate Locations: {analysis.get('alternate_locations', False)}"
        ])
        
        return f"""You are a molecular dynamics preprocessing expert executing a detailed plan from the workflow planner.

**PDB Information:**
- File: {agent_input.pdb_path}
- Force Field: {agent_input.force_field}
- Water Model: {agent_input.water_model}

**Structure Analysis:**
{analysis_str}

**DETAILED INSTRUCTIONS FROM PLANNER:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{planner_instructions}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Available Tools:**
{tools_list_str}

**CRITICAL INSTRUCTIONS:**
- You MUST ONLY use the tools listed above - do NOT invent or suggest non-existent tools
- If a required capability is missing, use the available tools creatively or skip that step
- Every "tool_name" in your plan must match exactly one of the tool names listed above
- Do NOT create placeholder tools like "custom_file_filter" or similar

Your task: Create a detailed, step-by-step execution plan that follows the planner's instructions above.
The plan should specify which tools to call and in what order to achieve the planner's objectives.

Output as JSON with this structure:
{{
  "reasoning": "How you'll implement the planner's instructions",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"param": "value"}},
      "reason": "why it's needed per planner's instructions"
    }}
  ],
  "potential_issues": ["issue1"],
  "recommendations": ["rec1"]
}}
"""
    
    def _build_standard_planning_prompt(self, agent_input: PreprocessingAgentInput,
                                        analysis: Dict[str, Any]) -> str:
        """Build LLM planning prompt from config template using dynamic tool metadata"""
        config_prompt = self.config.get("llm", {}).get("planning_prompt_template", "")
        
        # Get available tools list dynamically from tool metadata - properly formatted
        tool_metadata = get_tool_metadata()
        tools_list = []
        
        for tool_info in tool_metadata.values():
            tool_entry = f"• {tool_info['name']}\n"
            tool_entry += f"  Description: {tool_info['description']}\n"
            
            # Format arguments nicely
            if tool_info['args']:
                tool_entry += "  Arguments:\n"
                for arg_name, arg_details in tool_info['args'].items():
                    required = "required" if arg_details['required'] else "optional"
                    arg_type = arg_details['type']
                    tool_entry += f"    - {arg_name} ({arg_type}, {required})\n"
            
            tools_list.append(tool_entry)
        
        tools_list_str = "\n".join(tools_list)
        
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
                tools_list=tools_list_str
            )
        else:
            # Fallback prompt
            return f"""
You are a molecular dynamics preprocessing expert. Create a preprocessing plan for:

PDB: {agent_input.pdb_path}
Goal: {agent_input.user_goal}
Analysis: {analysis_str}

Available tools:
{tools_list_str}

**CRITICAL: You MUST ONLY use the tools listed above. Do NOT invent or suggest non-existent tools.**

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
            "analyze_pdb", "separate_protein_ligand", 
            "add_hydrogens", "validate_structure"
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
        # Most tools are applied universally now
        
        # Build tool params
        tool_params = {"pdb_file": agent_input.pdb_path}
        
        if tool_name == "add_hydrogens":
            defaults = self.config.get("defaults", {})
            tool_params["method"] = defaults.get("hydrogen_method", "auto")
            tool_params["ph"] = defaults.get("ph", 7.4)
        
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
        Includes retry limits to prevent infinite loops
        """
        execution_log = []
        issues = []
        warnings = []
        generated_files = {}
        
        current_pdb = agent_input.pdb_path
        topology_file = None
        processed_coords = None
        
        # Get execution limits from config
        agent_config = self.config.get("agent", {})
        max_retries = agent_config.get("max_tool_retries", 2)
        max_steps = agent_config.get("max_total_steps", 20)
        fail_fast = agent_config.get("fail_fast", False)
        
        # Track retry counts per tool
        tool_retry_counts = {}
        
        try:
            # Enforce max steps limit
            if len(plan.steps) > max_steps:
                warnings.append(f"Plan has {len(plan.steps)} steps, limiting to {max_steps}")
                plan.steps = plan.steps[:max_steps]
            
            for i, step in enumerate(plan.steps):
                # Log step start
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
                    "add_hydrogens", "validate_structure", "separate_protein_ligand"
                ]:
                    tool_params["pdb_file"] = current_pdb
                
                # Update chained input file - handle both explicit and implicit chaining
                if "pdb_file" in tool_params:
                    specified_pdb = tool_params["pdb_file"]
                    # If the specified file doesn't exist, use current_pdb (the actual last output)
                    if not os.path.exists(specified_pdb) and current_pdb != agent_input.pdb_path:
                        tool_params["pdb_file"] = current_pdb
                    # Or if it explicitly matches the original input but we've processed files
                    elif specified_pdb == agent_input.pdb_path and current_pdb != agent_input.pdb_path:
                        tool_params["pdb_file"] = current_pdb
                
                # Override output_file to ensure files are written to preprocess directory
                # This fixes LLM-generated plans that specify working_dir paths
                if step.tool_name in ["add_hydrogens", "separate_protein_ligand"]:
                    input_file = tool_params.get("pdb_file", current_pdb)
                    base_name = Path(input_file).stem
                    # Generate output filename based on tool
                    if step.tool_name == "separate_protein_ligand":
                        # Special handling for separation tool - ALWAYS override to preprocess dir
                        tool_params["protein_output"] = str(Path(self.tool_executor.working_dir) / f"{base_name}_protein.pdb")
                        tool_params["ligand_output"] = str(Path(self.tool_executor.working_dir) / f"{base_name}_ligand.pdb")
                    else:
                        # Regular tools with single output
                        suffix = "_h"  # add_hydrogens
                        output_file = str(Path(self.tool_executor.working_dir) / f"{base_name}{suffix}.pdb")
                        tool_params["output_file"] = output_file
                
                # Execute tool with retry logic
                retry_count = 0
                result = None
                tool_key = f"{step.tool_name}_{i}"
                
                while retry_count <= max_retries:
                    result = self.tool_executor.execute_tool(step.tool_name, tool_params)
                    
                    if result.get("success"):
                        break  # Success, exit retry loop
                    
                    retry_count += 1
                    if retry_count <= max_retries:
                        execution_log.append(f"⚠ Retry {retry_count}/{max_retries}: {result.get('error')}")
                        tool_retry_counts[tool_key] = retry_count
                    else:
                        execution_log.append(f"✗ Max retries ({max_retries}) exceeded")
                
                # Process results
                if result and result.get("success"):
                    execution_log.append(f"✓ Success: {result.get('message', 'Step completed')}")
                    
                    # Collect output files for logging
                    output_files = []
                    if "output_file" in result:
                        output_files.append(result["output_file"])
                        current_pdb = result["output_file"]
                        generated_files[result["output_file"]] = step.description
                    if "protein_file" in result:
                        output_files.append(result["protein_file"])
                        current_pdb = result["protein_file"]  # Use protein for chaining
                        generated_files[result["protein_file"]] = "Protein component"
                    if "ligand_file" in result:
                        output_files.append(result["ligand_file"])
                        generated_files[result["ligand_file"]] = "Ligand component"
                    if "topology_file" in result:
                        topology_file = result["topology_file"]
                        generated_files[topology_file] = "GROMACS topology file"
                    
                    # Log step completion status with output files
                    log_data = {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "✅ SUCCESS"
                    }
                    if output_files:
                        log_data["output_files"] = output_files
                    log_agent_action("preprocessing", f"Step {i+1}/{len(plan.steps)} completed", log_data)
                    
                    if result.get("warning"):
                        warnings.append(f"{step.name}: {result['warning']}")
                else:
                    error_msg = result.get('error', 'Failed to execute') if result else 'Tool execution failed'
                    execution_log.append(f"✗ Failed after {retry_count} attempts: {error_msg}")
                    issues.append(f"{step.name}: {error_msg}")
                    
                    # Log step failure status
                    log_agent_action("preprocessing", f"Step {i+1}/{len(plan.steps)} failed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "❌ FAILED",
                        "error": error_msg
                    })
                    
                    # Fail fast option
                    if fail_fast:
                        execution_log.append("⚠ Stopping execution (fail_fast enabled)")
                        break
            
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
