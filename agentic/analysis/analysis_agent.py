"""
MD Workflow Analysis Agent

Performs analysis of simulation outputs based on supervisor prompts.
Uses LLM to plan analysis steps and selects appropriate tools; includes
fallbacks when data or dependencies are unavailable.

Refactored to follow SimulationSetupAgent workflow pattern.
"""
import os
import re
import json
import logging
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_supervisor_routing, log_agent_start, log_llm_interaction,
    log_agent_action, log_file_operation, log_agent_completion, log_error
)
from .schemas import (
    AnalysisPlan, AnalysisStep,
    AnalysisResult as AnalysisExecutionResult,
    AnalysisAgentInput, AnalysisAgentOutput
)
from .tools import AnalysisToolExecutor, get_tool_metadata

logger = logging.getLogger(__name__)

# Optional heavy deps (graceful fallback)
try:
    import MDAnalysis as mda  # type: ignore
    HAS_MDA = True
except Exception:
    HAS_MDA = False


class MDAnalysisAgent:
    """LLM-driven analysis agent that plans and executes analysis tasks."""

    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        self.llm = llm_client
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config = self._load_config()
        self.tool_executor = None
        logger.info("MD Analysis Agent initialized")

    def _load_config(self) -> Dict[str, Any]:
        import yaml
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Analysis config {self.config_path} not found; using defaults")
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "metrics": ["rmsd", "rmsf", "energy"],
            "plots": True,
            "output_dir": "./working_dir/analysis",
            "use_mdanalysis": True,
        }

    def analysis_node(self, state: MDState) -> MDState:
        """
        Main analysis node - entry point from workflow.
        Orchestrates the entire analysis pipeline following simsetup pattern.
        """
        # Check if we have planner instructions
        execution_plan = state.get("execution_plan", {})
        has_planner_instructions = execution_plan.get("format") == "natural_language"
        
        input_summary = {
            "hpc_output_dir": state.get("hpc_output_directory"),
            "trajectory_file": state.get("trajectory_path"),
            "topology_file": state.get("topology")
        }
        
        if has_planner_instructions:
            # Prefer pre-extracted instructions from supervisor (avoids duplication)
            analysis_section = state.get("analysis_instructions")
            
            if not analysis_section:
                # Fallback: Extract from full plan if supervisor didn't provide it
                full_plan = execution_plan.get("full_plan", "")
                analysis_section = self._extract_agent_instructions(full_plan, "Analysis Agent")
            
            if analysis_section:
                input_summary["planner_instructions"] = analysis_section
            else:
                input_summary["planner_instructions"] = "[Natural language plan from planner]"
        else:
            # Fallback to user goal if no planner instructions
            input_summary["user_goal"] = state.get("user_goal")
        
        log_agent_start("analysis", "MD Trajectory Analysis with LLM Planning", input_summary)
        
        try:
            # Initialize tool executor with agent-specific subdirectory
            base_working_dir = state.get("working_directory", "working_dir")
            analysis_dir = str(Path(base_working_dir) / "analysis")
            Path(analysis_dir).mkdir(parents=True, exist_ok=True)
            
            # Set analysis_directory in state
            state["analysis_directory"] = analysis_dir
            
            self.tool_executor = AnalysisToolExecutor(config={"working_directory": analysis_dir})
            
            # Copy files from HPC output directory if needed
            self._copy_files_from_hpc(state, analysis_dir)
            
            # Prepare agent input from state
            agent_input = self._prepare_agent_input(state)
            
            # Run LLM-guided analysis workflow
            agent_output = self._run_analysis_workflow(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Determine next workflow node
            if agent_output.success:
                if state.get("human_in_loop") and agent_output.result.issues:
                    state["next_node"] = "human_analysis_check"
                else:
                    state["next_node"] = "supervisor"
            else:
                state["errors"].append(f"Analysis failed: {agent_output.result.report}")
                state["next_node"] = "supervisor"
            
            success = agent_output.success and len(agent_output.result.issues) == 0
            log_agent_completion("analysis", "MD Trajectory Analysis", state, success)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Analysis agent failed: {e}")
            logger.error(f"Traceback: {tb}")
            log_error("analysis_agent.analysis_node", e, {"state": str(state), "traceback": tb})
            state["errors"].append(f"Analysis error: {str(e)}")
            state["next_node"] = "supervisor"
        
        return state

    def _extract_agent_instructions(self, full_plan: str, agent_name: str) -> Optional[str]:
        """
        Extract agent-specific detailed instructions from planner's natural language plan.
        
        Args:
            full_plan: Complete natural language plan from planner
            agent_name: Name of the agent section to extract (e.g., "Analysis Agent")
            
        Returns:
            Extracted instructions for this specific agent, or full plan as fallback
        """
        # Try multiple patterns to find the agent section
        patterns = [
            # Exact match patterns
            rf'###\s*{agent_name}.*?\n(.*?)(?=###|\Z)',  # Markdown ### heading
            rf'##\s*{agent_name}.*?\n(.*?)(?=##|\Z)',    # Markdown ## heading  
            rf'\*\*{agent_name}\*\*.*?\n(.*?)(?=\*\*[A-Z]|\Z)',  # Bold heading
            # Fuzzy match patterns (allow for variations)
            rf'###\s*(?:MD\s*)?Analysis.*?Agent.*?\n(.*?)(?=###|\Z)',  # Flexible analysis agent heading
            rf'##\s*(?:MD\s*)?Analysis.*?Agent.*?\n(.*?)(?=##|\Z)',
            # Section number patterns
            rf'\d+\..*?(?:MD\s*)?Analysis.*?Agent.*?\n(.*?)(?=\d+\.|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                if len(instructions) > 50:  # Ensure we got substantial content
                    logger.info(f"Extracted {len(instructions)} chars of detailed instructions for {agent_name}")
                    return instructions
        
        # Fallback: Use full plan if no specific section found
        logger.info(f"Could not find specific section for {agent_name}, using full plan as context")
        logger.info(f"Full plan length: {len(full_plan)} chars")
        
        # Return full plan so agent still has context
        return full_plan

    def _copy_files_from_hpc(self, state: MDState, analysis_dir: str):
        """Copy trajectory and topology files from HPC output directory to analysis directory"""
        hpc_output_dir = state.get("hpc_output_directory")
        
        if not hpc_output_dir or not os.path.exists(hpc_output_dir):
            logger.warning(f"HPC output directory not found: {hpc_output_dir}")
            return
        
        # Copy files using file_registry (preferred method)
        file_registry = state.get("file_registry", {})
        copied_files = set()
        
        if file_registry:
            # Copy all HPC output files from registry
            for file_path, metadata in list(file_registry.items()):
                if metadata.get("stage") == "hpc" and os.path.exists(file_path):
                    filename = Path(file_path).name
                    new_path = str(Path(analysis_dir) / filename)
                    
                    if file_path != new_path and new_path not in copied_files:
                        shutil.copy2(file_path, new_path)
                        copied_files.add(new_path)
                        
                        # Update registry with new location
                        new_metadata = metadata.copy()
                        new_metadata["stage"] = "analysis"
                        file_registry[new_path] = new_metadata
                        
                        # Update state paths
                        file_type = metadata.get("type")
                        if file_type == "trajectory":
                            state["trajectory_path"] = new_path
                            logger.info(f"Updated trajectory_path to: {new_path}")
                        elif file_type == "topology":
                            state["topology"] = new_path
                            logger.info(f"Updated topology to: {new_path}")
                        
                        description = metadata.get("description", "N/A")
                        logger.info(f"Copied {filename} ({file_type}) from HPC to analysis")
                        log_file_operation("analysis", "copied", new_path, True, f"From HPC: {description}")
            
            # Write back modified file_registry to state
            state["file_registry"] = file_registry

    def _prepare_agent_input(self, state: MDState) -> AnalysisAgentInput:
        """Prepare structured input for analysis from workflow state"""
        defaults = self.config
        
        # Check if planner provided detailed instructions for this agent
        # Prefer pre-extracted instructions from supervisor
        planner_instructions = state.get("analysis_instructions")
        
        if not planner_instructions:
            # Fallback: Extract from execution_plan if supervisor didn't provide it
            execution_plan = state.get("execution_plan", {})
            if execution_plan.get("format") == "natural_language":
                full_plan = execution_plan.get("full_plan", "")
                planner_instructions = self._extract_agent_instructions(full_plan, "Analysis Agent")
        
        return AnalysisAgentInput(
            working_directory=state.get("working_directory", "working_dir"),
            hpc_output_dir=state.get("hpc_output_directory", ""),
            topology_file=state.get("topology"),
            trajectory_file=state.get("trajectory_path"),
            energy_file=state.get("energy_file"),
            analyses=defaults.get("metrics", ["rmsd", "rmsf", "gyration"]),
            user_goal=state.get("user_goal", ""),
            additional_instructions=planner_instructions
        )

    def _run_analysis_workflow(self, agent_input: AnalysisAgentInput, 
                               state: MDState) -> AnalysisAgentOutput:
        """
        Run complete analysis workflow:
        1. LLM creates intelligent plan based on available data
        2. Execute plan step-by-step using tools
        3. Return structured results
        """
        try:
            # Step 1: LLM analyzes available data and creates plan
            plan = self._create_analysis_plan_llm(agent_input, state)
            
            log_agent_action("analysis", "Generated analysis plan", {
                "steps": len(plan.steps),
                "reasoning": plan.reasoning[:200]
            })
            
            # Step 2: Execute plan using tool executor
            result = self._execute_analysis_plan(agent_input, plan, state)
            
            # Step 3: Register created files in file_registry
            file_registry = state.get("file_registry", {})
            
            for file_path, description in result.generated_files.items():
                # Determine file type from extension
                file_type = "analysis_output"
                if ".dat" in file_path or ".xvg" in file_path:
                    file_type = "analysis_data"
                elif ".png" in file_path or ".pdf" in file_path:
                    file_type = "plot"
                
                file_registry[file_path] = {
                    "type": file_type,
                    "description": description,
                    "stage": "analysis"
                }
            
            # Write back modified file_registry to state
            state["file_registry"] = file_registry
            
            # Step 4: Prepare supervisor update
            supervisor_update = {
                "analysis_results": result.results,
                "analysis_directory": result.output_directory,
                "analysis_report": result.report,
                "file_registry": file_registry
            }
            
            return AnalysisAgentOutput(
                success=result.success,
                plan=plan,
                result=result,
                supervisor_update=supervisor_update
            )
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Analysis workflow failed: {e}")
            logger.error(f"Traceback: {tb}")
            return AnalysisAgentOutput(
                success=False,
                plan=AnalysisPlan(
                    reasoning=f"Error in planning: {str(e)}",
                    overview="Failed",
                    steps=[]
                ),
                result=AnalysisExecutionResult(
                    success=False,
                    report=f"Error: {str(e)}\n\nTraceback:\n{tb}",
                    issues=[str(e)],
                    warnings=[],
                    output_directory=state.get("analysis_directory", "./working_dir/analysis")
                ),
                supervisor_update={}
            )

    def _update_state(self, state: MDState, agent_output: AnalysisAgentOutput):
        """Update workflow state with analysis results"""
        if agent_output.supervisor_update:
            state.update(agent_output.supervisor_update)
        
        state["analysis_report"] = agent_output.result.report
        state["analysis_issues"] = agent_output.result.issues
        state["analysis_warnings"] = agent_output.result.warnings
        state["analysis_execution_log"] = agent_output.result.execution_log
        
        # Initialize file registry if not present
        if "file_registry" not in state or state["file_registry"] is None:
            state["file_registry"] = {}
        
        # Register all generated files with metadata
        for file_path, description in agent_output.result.generated_files.items():
            # Determine file type from filename
            file_type = "analysis_output"
            if ".dat" in file_path or ".xvg" in file_path:
                file_type = "analysis_data"
            elif ".png" in file_path or ".pdf" in file_path:
                file_type = "plot"
            
            state["file_registry"][file_path] = {
                "type": file_type,
                "description": description,
                "stage": "analysis"
            }
        
        # Log file operations
        for file_path, description in agent_output.result.generated_files.items():
            log_file_operation("analysis", "create", file_path, True, description)

    def _create_analysis_plan_llm(self, agent_input: AnalysisAgentInput, state: MDState) -> AnalysisPlan:
        """
        Use LLM to analyze available data and create intelligent analysis plan.
        Falls back to template-based plan if LLM fails.
        """
        # Build LLM prompt from config template
        prompt = self._build_analysis_planning_prompt(agent_input, state)
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            log_llm_interaction("analysis.planning", prompt, content,
                              is_mock=hasattr(self.llm, '_is_mock_mode') and self.llm._is_mock_mode)
            
            # Parse LLM response into structured plan
            plan_dict = self._extract_plan_json(content)
            
            return AnalysisPlan(
                reasoning=plan_dict.get("reasoning", content[:500]),
                overview=plan_dict.get("overview", "Analyzing MD trajectory"),
                steps=[
                    AnalysisStep(
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
            return self._create_fallback_analysis_plan(agent_input)

    def _build_analysis_planning_prompt(self, agent_input: AnalysisAgentInput, 
                                        state: MDState) -> str:
        """Build LLM planning prompt - use planner's detailed instructions if available"""
        
        # Check if we have detailed instructions from planner
        if agent_input.additional_instructions:
            logger.info("Using planner's detailed instructions for analysis")
            return self._build_prompt_from_planner_instructions(
                agent_input, agent_input.additional_instructions, state
            )
        
        # Otherwise use standard config-based prompt
        return self._build_standard_analysis_prompt(agent_input)

    def _build_prompt_from_planner_instructions(self, agent_input: AnalysisAgentInput,
                                                planner_instructions: str,
                                                state: MDState) -> str:
        """Build prompt using planner's detailed natural language instructions"""
        
        # Get available tools for reference using tool metadata
        tool_metadata = get_tool_metadata()
        tools_list = []
        
        for tool_info in tool_metadata.values():
            tool_entry = f"• {tool_info['name']}: {tool_info['description']}"
            tools_list.append(tool_entry)
        
        tools_list_str = "\n".join(tools_list)
        
        # Extract file registry information
        file_registry = state.get("file_registry", {})
        if file_registry:
            registry_str = "\n**Files Available from HPC:**\n"
            for file_path, metadata in file_registry.items():
                if metadata.get("stage") == "hpc":
                    filename = Path(file_path).name
                    file_type = metadata.get("type", "unknown")
                    description = metadata.get("description", "")
                    registry_str += f"- {filename} (type: {file_type}) - {description}\n"
        else:
            registry_str = "\n**Files Available from HPC:** None registered\n"
        
        return f"""You are a molecular dynamics analysis expert executing a detailed plan from the workflow planner.

**Available Data:**
- Topology File: {agent_input.topology_file or "Not available"}
- Trajectory File: {agent_input.trajectory_file or "Not available"}
- Energy File: {agent_input.energy_file or "Not available"}
- Working Directory: {agent_input.working_directory}
{registry_str}

**DETAILED INSTRUCTIONS FROM PLANNER:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{planner_instructions}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Available Tools:**
{tools_list_str}

**CRITICAL INSTRUCTIONS:**
- You MUST ONLY use the tools listed above - do NOT invent or suggest non-existent tools
- Every "tool_name" in your plan must match exactly one of the tool names listed above
- FORBIDDEN tool names: "none", "manual", "skip", "custom", "placeholder", or any made-up tool
- If a required capability is missing, either:
  a) Use available tools creatively to achieve the same goal, OR
  b) OMIT that step entirely from your plan (do NOT include it with tool_name="none")
- When you cannot perform a step, simply do NOT include it in the steps array

Your task: Create a detailed, step-by-step execution plan that follows the planner's instructions above.
The plan should specify which tools to call and in what order to achieve the planner's objectives.
ONLY include steps that use valid tools from the list above.

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

    def _build_standard_analysis_prompt(self, agent_input: AnalysisAgentInput) -> str:
        """Build LLM planning prompt from config template using dynamic tool metadata"""
        config_prompt = self.config.get("llm", {}).get("planning_prompt_template", "")
        
        # Get available tools list dynamically from tool metadata
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
        
        # Build analysis context
        analysis_context = "\n".join([
            f"- Trajectory available: {bool(agent_input.trajectory_file)}",
            f"- Topology available: {bool(agent_input.topology_file)}",
            f"- Energy file available: {bool(agent_input.energy_file)}",
            f"- Requested analyses: {', '.join(agent_input.analyses) if agent_input.analyses else 'None specified'}"
        ])
        
        # Use template from config or build basic prompt
        if config_prompt:
            return config_prompt.format(
                trajectory_file=agent_input.trajectory_file or "Not available",
                topology_file=agent_input.topology_file or "Not available",
                energy_file=agent_input.energy_file or "Not available",
                user_goal=agent_input.user_goal,
                hpc_output_dir=agent_input.hpc_output_dir or "Not specified",
                analysis_context=analysis_context,
                tools_list=tools_list_str
            )
        else:
            # Fallback prompt if config template missing
            return f"""You are a molecular dynamics analysis expert. Create an analysis plan for:

**Available Data:**
- Topology: {agent_input.topology_file or "Not available"}
- Trajectory: {agent_input.trajectory_file or "Not available"}
- Energy File: {agent_input.energy_file or "Not available"}
- User Goal: {agent_input.user_goal}

**Available Tools:**
{tools_list_str}

**CRITICAL: You MUST ONLY use the tools listed above. Do NOT invent or suggest non-existent tools.**

Return JSON with: reasoning, overview, steps (name, description, tool_name, tool_params, reason)
"""

    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract and parse JSON plan from LLM response"""
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
            "overview": "MD trajectory analysis plan",
            "steps": []
        }

    def _create_fallback_analysis_plan(self, agent_input: AnalysisAgentInput) -> AnalysisPlan:
        """
        Create template-based fallback plan when LLM fails.
        Uses standard MD analysis workflow.
        """
        steps = []
        
        # Only add steps if we have the required files
        if agent_input.trajectory_file and agent_input.topology_file:
            steps.extend([
                AnalysisStep(
                    name="Calculate RMSD",
                    description="Calculate Root Mean Square Deviation to assess structural stability",
                    tool_name="calculate_rmsd",
                    tool_params={
                        "topology_file": agent_input.topology_file,
                        "trajectory_file": agent_input.trajectory_file,
                        "selection": "protein and name CA"
                    },
                    reason="RMSD indicates structural stability over time"
                ),
                AnalysisStep(
                    name="Calculate RMSF",
                    description="Calculate Root Mean Square Fluctuation to identify flexible regions",
                    tool_name="calculate_rmsf",
                    tool_params={
                        "topology_file": agent_input.topology_file,
                        "trajectory_file": agent_input.trajectory_file,
                        "selection": "protein and name CA"
                    },
                    reason="RMSF identifies flexible and rigid regions"
                ),
                AnalysisStep(
                    name="Calculate Radius of Gyration",
                    description="Calculate radius of gyration to assess protein compactness",
                    tool_name="calculate_radius_of_gyration",
                    tool_params={
                        "topology_file": agent_input.topology_file,
                        "trajectory_file": agent_input.trajectory_file,
                        "selection": "protein"
                    },
                    reason="Radius of gyration indicates protein compactness"
                )
            ])
        
        if agent_input.energy_file:
            steps.append(
                AnalysisStep(
                    name="Analyze Energy",
                    description="Extract and analyze energy terms from simulation",
                    tool_name="analyze_energy",
                    tool_params={
                        "energy_file": agent_input.energy_file
                    },
                    reason="Energy analysis assesses simulation stability"
                )
            )
        
        return AnalysisPlan(
            reasoning="Using standard MD analysis workflow (LLM fallback)",
            overview="Standard trajectory analysis with RMSD, RMSF, and Rg",
            steps=steps,
            potential_issues=["Requires trajectory and topology files"],
            recommendations=["Verify all files exist before execution"]
        )

    def _execute_analysis_plan(self, agent_input: AnalysisAgentInput, 
                               plan: AnalysisPlan,
                               state: MDState) -> AnalysisExecutionResult:
        """
        Execute analysis plan step-by-step using tool executor.
        Tracks outputs and handles errors gracefully.
        """
        execution_log = []
        issues = []
        warnings = []
        generated_files = {}
        results = {}
        
        # Get execution limits from config
        agent_config = self.config
        max_retries = agent_config.get("max_tool_retries", 2)
        max_steps = agent_config.get("max_total_steps", 20)
        fail_fast = agent_config.get("fail_fast", False)
        
        # Get analysis directory
        analysis_dir = state.get("analysis_directory", self.tool_executor.working_dir)
        
        try:
            # Enforce max steps limit
            if len(plan.steps) > max_steps:
                warnings.append(f"Plan has {len(plan.steps)} steps, limiting to {max_steps}")
                plan.steps = plan.steps[:max_steps]
            
            for i, step in enumerate(plan.steps):
                # Validate tool name - skip invalid placeholder names
                invalid_tools = ["none", "manual", "skip", "custom", "placeholder", ""]
                if not step.tool_name or step.tool_name.lower() in invalid_tools:
                    skip_msg = f"Skipping step {i+1} '{step.name}': invalid tool name '{step.tool_name}'"
                    execution_log.append(f"\n⚠ {skip_msg}")
                    warnings.append(skip_msg)
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} skipped", {
                        "step": step.name,
                        "reason": f"Invalid tool name: {step.tool_name}"
                    })
                    continue
                
                # Log step start
                log_agent_action("analysis", f"Executing step {i+1}/{len(plan.steps)}", {
                    "step": step.name,
                    "tool": step.tool_name
                })
                
                execution_log.append(f"\n--- Step {i+1}: {step.name} ---")
                execution_log.append(f"Description: {step.description}")
                execution_log.append(f"Tool: {step.tool_name}")
                execution_log.append(f"Reason: {step.reason}")
                
                # Prepare tool parameters
                tool_params = dict(step.tool_params) if step.tool_params else {}
                
                # Get base working directory for path resolution
                base_working_dir = state.get("working_directory", "working_dir")
                
                # Normalize file paths to avoid double-nesting issues
                # If paths start with working_dir prefix and we're setting working_dir parameter,
                # we need to convert them to absolute paths or remove the prefix
                path_params = ["topology_file", "trajectory_file", "energy_file", "output_file", 
                              "pdb_file", "gro_file", "output_dir"]
                
                for param_name in path_params:
                    if param_name in tool_params and tool_params[param_name]:
                        path_value = str(tool_params[param_name])
                        
                        # If path starts with the working_dir prefix, convert to absolute path
                        if path_value.startswith(base_working_dir + "/") or path_value.startswith(base_working_dir + os.sep):
                            # Convert to absolute path from current directory
                            abs_path = os.path.abspath(path_value)
                            tool_params[param_name] = abs_path
                            logger.debug(f"Normalized {param_name}: {path_value} -> {abs_path}")
                
                # Ensure working_dir is set (as absolute path)
                if "working_dir" not in tool_params:
                    tool_params["working_dir"] = os.path.abspath(analysis_dir)
                elif not os.path.isabs(tool_params["working_dir"]):
                    tool_params["working_dir"] = os.path.abspath(tool_params["working_dir"])
                
                execution_log.append(f"Parameters: {json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in tool_params.items()}, indent=2)}")
                
                # Execute tool with retry logic
                retry_count = 0
                result = None
                
                while retry_count <= max_retries:
                    result = self.tool_executor.execute(step.tool_name, **tool_params)
                    
                    if result.get("success"):
                        break
                    
                    retry_count += 1
                    if retry_count <= max_retries:
                        execution_log.append(f"⚠ Retry {retry_count}/{max_retries}: {result.get('error')}")
                    else:
                        execution_log.append(f"✗ Max retries ({max_retries}) exceeded")
                
                # Process results
                if result and result.get("success"):
                    execution_log.append(f"✓ Success: {result.get('message', 'Step completed')}")
                    
                    # Store analysis results
                    analysis_name = step.name.lower().replace(" ", "_")
                    results[analysis_name] = result
                    
                    # Track generated files
                    if "output_file" in result:
                        output_file = result["output_file"]
                        generated_files[output_file] = step.description
                        log_file_operation("analysis", "create", output_file, True)
                    
                    if "output_files" in result:
                        for out_file in result["output_files"]:
                            generated_files[out_file] = step.description
                            log_file_operation("analysis", "create", out_file, True)
                    
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} completed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "✅ SUCCESS"
                    })
                    
                    if result.get("warning"):
                        warnings.append(f"{step.name}: {result['warning']}")
                else:
                    error_msg = result.get('error', 'Failed to execute') if result else 'Tool execution failed'
                    execution_log.append(f"✗ Failed after {retry_count} attempts: {error_msg}")
                    issues.append(f"{step.name}: {error_msg}")
                    
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} failed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "❌ FAILED",
                        "error": error_msg
                    })
                    
                    if fail_fast:
                        execution_log.append("⚠ Stopping execution (fail_fast enabled)")
                        break
            
            execution_log_str = "\n".join(execution_log)
            
            # Generate execution report
            report = self._generate_execution_report(plan, results, issues, warnings)
            
            return AnalysisExecutionResult(
                success=len(issues) == 0,
                analyses_completed=[step.name for step in plan.steps if step.name.lower().replace(" ", "_") in results],
                results=results,
                output_directory=analysis_dir,
                report=report,
                issues=issues,
                warnings=warnings,
                generated_files=generated_files,
                execution_log=execution_log_str
            )
            
        except Exception as e:
            return AnalysisExecutionResult(
                success=False,
                output_directory=analysis_dir,
                report=f"Analysis failed: {str(e)}",
                issues=[str(e)],
                warnings=warnings,
                generated_files=generated_files,
                execution_log="\n".join(execution_log)
            )

    def _generate_execution_report(self, plan: AnalysisPlan, results: Dict[str, Any],
                                   issues: list, warnings: list) -> str:
        """Generate human-readable execution report"""
        report_lines = [
            "=" * 80,
            "MD TRAJECTORY ANALYSIS REPORT",
            "=" * 80,
            "",
            f"Plan Overview: {plan.overview}",
            f"Total Steps: {len(plan.steps)}",
            f"Completed: {len(results)}",
            f"Issues: {len(issues)}",
            f"Warnings: {len(warnings)}",
            "",
            "=" * 80,
            "RESULTS SUMMARY",
            "=" * 80,
        ]
        
        for analysis_name, result in results.items():
            report_lines.append(f"\n{analysis_name.upper()}:")
            if "message" in result:
                report_lines.append(f"  {result['message']}")
            
            # Add specific metrics based on analysis type
            if "rmsd" in analysis_name.lower() and "mean_rmsd" in result:
                report_lines.append(f"  Mean RMSD: {result['mean_rmsd']:.2f} Å")
            elif "rmsf" in analysis_name.lower() and "mean_rmsf" in result:
                report_lines.append(f"  Mean RMSF: {result['mean_rmsf']:.2f} Å")
            elif "gyration" in analysis_name.lower() and "mean_rg" in result:
                report_lines.append(f"  Mean Rg: {result['mean_rg']:.2f} Å")
        
        if issues:
            report_lines.extend([
                "",
                "=" * 80,
                "ISSUES ENCOUNTERED",
                "=" * 80,
            ])
            for issue in issues:
                report_lines.append(f"  • {issue}")
        
        if warnings:
            report_lines.extend([
                "",
                "=" * 80,
                "WARNINGS",
                "=" * 80,
            ])
            for warning in warnings:
                report_lines.append(f"  • {warning}")
        
        report_lines.append("\n" + "=" * 80)
        
        return "\n".join(report_lines)

    # ========== Legacy methods (kept for backward compatibility) ==========

    def _create_analysis_plan(self, state: MDState) -> Dict[str, Any]:
        """Legacy method for backward compatibility"""
        traj = state.get("trajectory_path")
        coords = state.get("coordinates")
        request = state.get("analysis_request") or "General stability and energy analysis"
        prompt = f"""
You are an expert MD analysis agent. Draft a practical analysis plan.

INPUTS:
- Trajectory: {traj}
- Coordinates: {coords}
- Request: {request}
- Preferred metrics: {self.config.get('metrics')}

RESPONSE FORMAT:
Metrics: [comma separated list]
Steps:
- Step 1: description
- Step 2: description
Outputs: [files/plots]
Notes: [assumptions/fallbacks]
"""
        resp = self.llm.prompt(prompt, system="You plan MD analysis tasks and ensure reproducible outputs.")
        return {"raw": resp}

    def _execute_basic_analysis(self, state: MDState, plan: Dict[str, Any]) -> None:
        """Legacy method for backward compatibility"""
        out_dir = self.config.get("output_dir", "./working_dir/analysis")
        os.makedirs(out_dir, exist_ok=True)
        traj = state.get("trajectory_path")
        coords = state.get("coordinates") or state.get("topology")

        results = state.setdefault("analysis_results", {})
        if not traj or not os.path.exists(traj):
            results["summary"] = "No trajectory available; stored analysis plan only."
            state["warnings"].append("Trajectory missing; analysis not executed")
            return

        # Minimal, dependency-light analysis placeholder
        if not HAS_MDA or not self.config.get("use_mdanalysis", True):
            results["summary"] = "MDAnalysis unavailable; minimal placeholder analysis done."
            results["metrics"] = {"frames": self._count_lines(traj)}
            return

        # Basic RMSD using MDAnalysis
        try:
            import numpy as np
            u = mda.Universe(coords, traj) if coords else mda.Universe(traj)
            ref = u.select_atoms("protein").positions.copy() if u.atoms.n_atoms > 0 else None
            rmsds = []
            for ts in u.trajectory:
                sel = u.select_atoms("protein")
                if sel.n_atoms == 0 or ref is None:
                    continue
                pos = sel.positions
                diff = pos - ref
                rmsd = (np.sqrt((diff * diff).sum(axis=1).mean()))
                rmsds.append(float(rmsd))
            results["metrics"] = {"rmsd_mean": float(np.mean(rmsds)) if rmsds else None,
                                   "rmsd_max": float(np.max(rmsds)) if rmsds else None,
                                   "frames": len(rmsds)}
            results["summary"] = "Computed simple RMSD over protein selection."
        except Exception as e:
            logger.exception("Error during MDAnalysis RMSD")
            state["errors"].append(f"RMSD analysis failed: {e}")

    def _count_lines(self, path: str) -> int:
        """Legacy helper for counting lines in a file"""
        try:
            with open(path, "rb") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
