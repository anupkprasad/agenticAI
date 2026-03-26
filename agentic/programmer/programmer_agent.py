"""
MD Workflow Programmer Agent

Generates custom tools and scripts based on planner specifications.
Called by planner when existing tools are insufficient for workflow execution.

Follows the same architectural pattern as analysis, preprocess, simsetup, and hpc agents.
"""
import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_supervisor_routing, log_agent_start, log_llm_interaction,
    log_agent_action, log_file_operation, log_agent_completion, log_error,
    SecureFileManager
)
from .schemas import (
    ProgrammerPlan, ProgrammerStep, ProgrammerResult,
    ProgrammerExecutionResult, ProgrammerAgentInput, ProgrammerAgentOutput,
    ToolSpecification, GeneratedTool, ToolValidationResult
)
from .tools import ProgrammerToolExecutor, get_tool_metadata

logger = logging.getLogger(__name__)


class MDProgrammer:
    """
    LLM-driven programmer agent that creates custom tools and scripts.
    
    Invoked by planner when new functionality is needed for workflow execution.
    Creates Python tools (with @tool decorator) and TCL scripts for field agents to use.
    
    Responsibilities:
    - Generate Python tools for custom analysis or processing
    - Create TCL scripts for VMD/NAMD operations
    - Generate GROMACS MDP parameter files
    - Create SLURM job submission scripts
    - Validate generated code for syntax and imports
    """
    
    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        
        self.llm = llm_client
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "config.yaml"
        )
        self.config = self._load_config()
        self.available_software = self._load_available_software()
        self.tool_executor = None
        self.file_manager = None  # Initialized per execution for state-specific file registry
        logger.info("MD Programmer Agent initialized")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        import yaml
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Programmer config {self.config_path} not found; using defaults")
        return self._default_config()
    
    def _load_available_software(self) -> str:
        """
        Load available software documentation for programmer reference.
        
        Returns:
            String containing available software list or empty string if not found
        """
        # Look for AVAILABLE_SOFTWARE.md in workspace root
        software_doc_paths = [
            "AVAILABLE_SOFTWARE.md",
            "../AVAILABLE_SOFTWARE.md", 
            "../../AVAILABLE_SOFTWARE.md",
            os.path.join(os.path.dirname(__file__), "..", "..", "AVAILABLE_SOFTWARE.md")
        ]
        
        for path in software_doc_paths:
            try:
                abs_path = os.path.abspath(path)
                if os.path.exists(abs_path):
                    with open(abs_path, 'r') as f:
                        content = f.read()
                    logger.info(f"Loaded available software documentation from {abs_path}")
                    return content
            except Exception as e:
                logger.debug(f"Could not load software doc from {path}: {e}")
        
        logger.warning("AVAILABLE_SOFTWARE.md not found - programmer will have limited context")
        return ""
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            "agent": {
                "name": "Programmer Agent",
                "max_tools_per_request": 10,
                "validate_before_save": True,
                "fail_fast": False
            },
            "output": {
                "base_directory": "working_dir/programmer",
                "python_tools": "working_dir/programmer/python",
                "tcl_scripts": "working_dir/programmer/tcl",
                "mdp_files": "working_dir/programmer/mdp",
                "analysis_scripts": "working_dir/programmer/analysis"
            },
            "defaults": {
                "language": "python",
                "add_langchain_decorator": True,
                "include_docstrings": True,
                "include_error_handling": True
            }
        }
    
    def programmer_node(self, state: MDState) -> MDState:
        """
        Main programmer node - entry point from planner workflow.
        
        Executes when planner determines new tools are needed.
        Creates tools and makes them available for field agents to use.
        
        Args:
            state: Current workflow state with planner instructions
            
        Returns:
            Updated state with generated tools
        """
        import sys  # Import at top to avoid UnboundLocalError with debug prints
        import traceback
        
        # Extract programmer instructions from planner
        execution_plan = state.get("execution_plan", {})
        programmer_instructions = state.get("programmer_instructions")
        
        if not programmer_instructions:
            # Fallback: extract from plan if available
            full_plan = execution_plan.get("full_plan", "")
            programmer_instructions = self._extract_programmer_instructions(full_plan)
        
        input_summary = {
            "planner_instructions": programmer_instructions or "[No specific instructions]",
            "working_directory": state.get("working_directory", "working_dir")
        }
        
        log_agent_start("programmer", "Custom Tool Generation", input_summary)
        
        try:
            print(f"\n{'='*70}", file=sys.stderr)
            print(f"DEBUG: programmer_node - Initializing SecureFileManager", file=sys.stderr)
            
            # Initialize secure file manager
            base_working_dir = state.get("working_directory", "working_dir")
            file_registry = state.get("file_registry", {})
            
            self.file_manager = SecureFileManager(
                working_dir=base_working_dir,
                agent_name="programmer",
                file_registry=file_registry
            )
            
            logger.info(f"Programmer agent directory: {self.file_manager.agent_dir}")
            print(f"DEBUG: SecureFileManager initialized: {self.file_manager.agent_dir}", file=sys.stderr)
            
            # Get programmer directory from file manager
            programmer_dir = self.file_manager.agent_dir
            
            print(f"DEBUG: Creating ProgrammerToolExecutor", file=sys.stderr)
            
            self.tool_executor = ProgrammerToolExecutor(
                config={"working_directory": programmer_dir}
            )
            
            print(f"DEBUG: Calling _prepare_agent_input", file=sys.stderr)
            
            # Prepare agent input
            try:
                agent_input = self._prepare_agent_input(state, programmer_instructions)
                print(f"DEBUG: agent_input created successfully", file=sys.stderr)
                print(f"DEBUG: agent_input.tool_specifications: {len(agent_input.tool_specifications) if agent_input.tool_specifications else 0} specs", file=sys.stderr)
            except Exception as prep_error:
                print(f"!!! DEBUG: _prepare_agent_input FAILED !!!", file=sys.stderr)
                print(f"Error type: {type(prep_error).__name__}", file=sys.stderr)
                print(f"Error message: {prep_error}", file=sys.stderr)
                import traceback
                print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
                raise
            
            print(f"DEBUG: Calling _run_programmer_workflow", file=sys.stderr)
            
            # Run LLM-guided programming workflow
            agent_output = self._run_programmer_workflow(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Set next node
            state["next_node"] = "planner"  # Return to planner
            
            success = agent_output.success and len(agent_output.errors) == 0
            log_agent_completion("programmer", "Custom Tool Generation", state, success)
            
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Programmer agent failed: {type(e).__name__}: {e}"
            logger.error(error_msg)
            logger.error(f"Traceback: {tb}")
            
            # Log to file for debugging
            print(f"!!! PROGRAMMER EXCEPTION !!!", file=sys.stderr)
            print(f"Type: {type(e).__name__}", file=sys.stderr)
            print(f"Message: {e}", file=sys.stderr)
            print(f"Traceback:\n{tb}", file=sys.stderr)
            
            log_error("programmer_agent.programmer_node", e, {
                "state": str(state), 
                "traceback": tb
            })
            state["errors"].append(f"Programmer error: {str(e)}")
            state["next_node"] = "planner"
        
        return state
    
    def _reload_field_agent_tools(self):
        """Notify field agents to reload tools after new tools are generated."""
        try:
            from ..utils import get_dynamic_tool_loader
            
            # Refresh the global tool loader
            tool_loader = get_dynamic_tool_loader(refresh=True)
            tools_count = len(tool_loader.loaded_tools)
            
            logger.info(f"PROGRAMMER: Reloaded {tools_count} programmer-generated tools for field agents")
            
            # Log which tools are now available
            if tool_loader.loaded_tools:
                logger.info("PROGRAMMER: Available tools:")
                for tool_name in tool_loader.loaded_tools.keys():
                    logger.info(f"  - {tool_name}")
            
        except Exception as e:
            logger.warning(f"PROGRAMMER: Could not reload field agent tools: {e}")
    
    def _reload_planner_tools_registry(self):
        """Refresh planner's tools registry to include newly created tools."""
        try:
            # Import here to avoid circular dependency
            from ..planner import get_tools_registry
            
            # Refresh the global tools registry
            logger.info("PROGRAMMER: Refreshing planner's tools registry...")
            registry = get_tools_registry(refresh=True)
            
            # Count programmer tools in registry
            programmer_tools = [k for k in registry.tools.keys() if 'programmer' in k.lower()]
            logger.info(f"PROGRAMMER: Planner tools registry refreshed ({len(programmer_tools)} programmer tools)")
            
            if programmer_tools:
                logger.info("PROGRAMMER: Programmer tools in registry:")
                for tool_key in programmer_tools:
                    logger.info(f"  - {tool_key}")
                
        except Exception as e:
            logger.warning(f"PROGRAMMER: Could not reload planner tools registry: {e}")
    
    def _extract_programmer_instructions(self, full_plan: str) -> Optional[str]:
        """Extract programmer-specific instructions from plan"""
        if not full_plan:
            return None
        
        # Look for programmer agent section
        patterns = [
            r"Programmer Agent[:\s]+(.+?)(?=\n\n|\Z)",
            r"Code Generation[:\s]+(.+?)(?=\n\n|\Z)",
            r"Tool Creation[:\s]+(.+?)(?=\n\n|\Z)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _prepare_agent_input(
        self, 
        state: MDState, 
        instructions: Optional[str]
    ) -> ProgrammerAgentInput:
        """Prepare programmer agent input from state"""
        
        tool_specs_from_state = state.get("tool_specifications", None)
        
        # Debug logging
        if tool_specs_from_state:
            logger.info(f"PROGRAMMER: Received {len(tool_specs_from_state)} tool specifications from planner")
            for i, spec in enumerate(tool_specs_from_state, 1):
                spec_name = spec.get("name", "unknown") if isinstance(spec, dict) else getattr(spec, "name", "unknown")
                logger.info(f"  {i}. {spec_name}")
        else:
            logger.warning("PROGRAMMER: No tool specifications received from planner")
        
        return ProgrammerAgentInput(
            working_directory=state.get("working_directory", "working_dir"),
            planner_instructions=instructions or "Generate required tools",
            tool_specifications=tool_specs_from_state,
            user_goal=None,  # Intentionally omitted to prevent LLM hallucination
            context={
                "force_field": state.get("force_field", "amber99sb-ildn"),
                "water_model": state.get("water_model", "tip3p"),
                "md_engine": state.get("md_engine", "gromacs"),
            },
            force_field=state.get("force_field", "amber99sb-ildn"),
            md_engine=state.get("md_engine", "gromacs")
        )
    
    def _run_programmer_workflow(
        self, 
        agent_input: ProgrammerAgentInput,
        state: MDState
    ) -> ProgrammerAgentOutput:
        """
        Execute programmer workflow: plan → generate → validate
        
        Args:
            agent_input: Prepared input for programmer
            state: Current workflow state
            
        Returns:
            Agent output with results
        """
        import sys  # Import at top to avoid UnboundLocalError
        import traceback
        
        try:
            # DEBUG: Log entry point
            print(f"\n{'='*70}", file=sys.stderr)
            print(f"DEBUG: _run_programmer_workflow STARTED", file=sys.stderr)
            print(f"DEBUG: LLM available: {self.llm.available}", file=sys.stderr)
            print(f"DEBUG: LLM client type: {type(self.llm)}", file=sys.stderr)
            print(f"{'='*70}\n", file=sys.stderr)
            
            # Step 1: Create execution plan using LLM
            plan = None
            if self.llm.available:
                logger.info("Creating programmer execution plan with LLM")
                print(f"DEBUG: Calling _create_llm_plan...", file=sys.stderr)
                plan = self._create_llm_plan(agent_input, state)
                print(f"DEBUG: _create_llm_plan returned: {plan is not None}", file=sys.stderr)
            
            if not plan:
                logger.info("Using fallback plan generation")
                print(f"DEBUG: Calling _create_fallback_plan...", file=sys.stderr)
                plan = self._create_fallback_plan(agent_input)
                print(f"DEBUG: _create_fallback_plan returned: {plan is not None}", file=sys.stderr)
            
            print(f"DEBUG: Plan object: {plan}", file=sys.stderr)
            print(f"DEBUG: Plan steps count: {len(plan.steps) if plan else 0}", file=sys.stderr)
            
            log_agent_action(
                agent_name="programmer",
                action="Generated programmer plan",
                details={
                    "steps": len(plan.steps),
                    "reasoning": plan.reasoning[:100] if plan.reasoning else "N/A"
                }
            )
            
            print(f"DEBUG: Calling _execute_programmer_plan...", file=sys.stderr)
            
            # Step 2: Execute the plan
            result = self._execute_programmer_plan(agent_input, plan, state)
            
            print(f"DEBUG: _execute_programmer_plan returned", file=sys.stderr)
            print(f"DEBUG: Result success: {result.success}", file=sys.stderr)
            print(f"DEBUG: Result issues: {result.issues}", file=sys.stderr)
            
            # Step 3: Create final output
            output = ProgrammerAgentOutput(
                success=result.success and len(result.issues) == 0,
                result=ProgrammerResult(
                    success=result.success,
                    generated_tools=[
                        GeneratedTool(
                            name=tool.get("tool_name", "unknown"),
                            file_path=tool.get("file_path", ""),
                            language=tool.get("language", "python"),
                            status="generated" if tool.get("success") else "failed",
                            errors=[tool.get("error")] if tool.get("error") else []
                        )
                        for tool in result.step_results
                        if tool.get("tool_name")
                    ],
                    failed_tools=[
                        tool.get("tool_name", "unknown")
                        for tool in result.step_results
                        if not tool.get("success", False)
                    ],
                    output_directory=agent_input.working_directory,
                    report=result.report,
                    tools_available={
                        tool.get("tool_name", ""): tool.get("file_path", "")
                        for tool in result.step_results
                        if tool.get("success") and tool.get("file_path")
                    }
                ),
                errors=result.issues,
                next_actions=["Return tools to planner for field agent use"]
            )
            
            return output
            
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Programmer workflow failed: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {tb_str}")
            
            # Debug output
            print(f"\n{'='*70}", file=sys.stderr)
            print(f"!!! PROGRAMMER WORKFLOW EXCEPTION !!!", file=sys.stderr)
            print(f"Exception Type: {type(e).__name__}", file=sys.stderr)
            print(f"Exception Message: {e}", file=sys.stderr)
            print(f"Full Traceback:\n{tb_str}", file=sys.stderr)
            print(f"{'='*70}\n", file=sys.stderr)
            
            return ProgrammerAgentOutput(
                success=False,
                result=ProgrammerResult(
                    success=False,
                    output_directory=agent_input.working_directory,
                    report=f"Programmer workflow failed: {str(e)}"
                ),
                errors=[str(e)]
            )
    
    def _create_llm_plan(
        self, 
        agent_input: ProgrammerAgentInput,
        state: MDState
    ) -> Optional[ProgrammerPlan]:
        """Create execution plan using LLM"""
        
        # Get available tools
        tool_metadata = get_tool_metadata()
        tools_list = []
        for tool_name, tool_info in tool_metadata.items():
            tools_list.append(f"→ {tool_name}: {tool_info['description']}")
        tools_str = "\n".join(tools_list)
        
        prompt = self._build_planning_prompt(agent_input, tools_str)
        
        try:
            response = self.llm.prompt(prompt)
            
            log_llm_interaction(
                agent_name="programmer.planning",
                prompt=prompt,
                response=response,
                is_mock=not self.llm.available
            )
            
            # Parse JSON response
            plan_dict = self._extract_plan_json(response)
            
            # Build allowed tool names set from planner specifications
            allowed_tool_names = set()
            if agent_input.tool_specifications:
                for spec in agent_input.tool_specifications:
                    name = spec.get("name", "") if isinstance(spec, dict) else getattr(spec, "name", "")
                    if name:
                        allowed_tool_names.add(name.lower())
            
            # Filter steps to only those creating specified tools
            raw_steps = plan_dict.get("steps", [])
            if allowed_tool_names:
                filtered_steps = []
                for step in raw_steps:
                    created_name = step.get("tool_params", {}).get("tool_name", "").lower()
                    if created_name in allowed_tool_names:
                        filtered_steps.append(step)
                    else:
                        logger.warning(
                            f"PROGRAMMER: Filtered out LLM-proposed tool '{created_name}' "
                            f"- not in planner specs: {allowed_tool_names}"
                        )
                if len(filtered_steps) < len(raw_steps):
                    logger.info(
                        f"PROGRAMMER: Filtered {len(raw_steps) - len(filtered_steps)} "
                        f"extra steps, keeping {len(filtered_steps)} specified tools"
                    )
                raw_steps = filtered_steps
            
            # Build ProgrammerPlan from response
            return ProgrammerPlan(
                reasoning=plan_dict.get("reasoning", "LLM-generated plan"),
                overview=plan_dict.get("overview", "Tool generation"),
                steps=[
                    ProgrammerStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", "")
                    )
                    for step in raw_steps
                ],
                estimated_complexity=plan_dict.get("estimated_complexity", "medium")
            )
            
        except Exception as e:
            logger.warning(f"LLM planning failed: {e}, using fallback")
            return None
    
    def _build_planning_prompt(
        self, 
        agent_input: ProgrammerAgentInput, 
        tools_str: str
    ) -> str:
        """Build LLM planning prompt"""
        
        # Include detailed tool specifications if available from planner
        tool_specs_section = ""
        if agent_input.tool_specifications:
            logger.info(f"PROGRAMMER: Including {len(agent_input.tool_specifications)} tool specifications in prompt")
            import json
            # Convert Pydantic models to dictionaries if needed
            specs_list = []
            for spec in agent_input.tool_specifications:
                if hasattr(spec, 'model_dump'):
                    # Pydantic v2
                    specs_list.append(spec.model_dump())
                elif hasattr(spec, 'dict'):
                    # Pydantic v1
                    specs_list.append(spec.dict())
                else:
                    # Already a dict
                    specs_list.append(spec)
            
            tool_specs_section = f"""
**Detailed Tool Specifications from Planner:**
```json
{json.dumps(specs_list, indent=2)}
```

Use these specifications to generate implementations with correct:
- Parameter types and defaults
- Return types
- Dependencies (imports)
- Function signatures matching the spec

"""
        else:
            logger.warning("PROGRAMMER: No tool specifications available - prompt will not include detailed specs")
        
        # Use loaded available software documentation
        software_section = ""
        if self.available_software:
            # Extract key packages summary for concise prompt
            software_section = """
**Available Software and Command-Line Tools:**
The following software is installed and available for use in generated tools:

"""
            # Try to extract the "Key Package Summary" section for brevity
            import re
            summary_match = re.search(
                r'## Key Package Summary for Programmer Agent.*?(?=\n## |\Z)',
                self.available_software,
                re.DOTALL
            )
            if summary_match:
                software_section += summary_match.group(0) + "\n"
            else:
                # Fallback: extract first 3000 chars of software doc
                software_section += self.available_software[:3000] + "\n...\n(See AVAILABLE_SOFTWARE.md for complete list)\n"
        else:
            software_section = """
**Available Software:**
- GROMACS (gmx command) - MD simulation suite
- AmberTools (sander, cpptraj, antechamber, tleap, pdb4amber)
- Python libraries: MDAnalysis, NumPy, Pandas, Matplotlib
- Chemistry tools: OpenBabel (obabel), RDKit
(Note: AVAILABLE_SOFTWARE.md not found - using minimal list)
"""
        
        # Build prompt using format() to avoid f-string issues with {} in tool specs
        prompt_template = """You are a code generation specialist creating custom tools for an MD workflow.

**Planner Instructions:**
{planner_instructions}
{tool_specs_section}
{software_section}
**Context:**
- Force Field: {force_field}
- MD Engine: {md_engine}
- Working Directory: {working_directory}

**Available Code Generation Tools:**
{tools_str}

**Your Task:**
Create EXACTLY ONE generation step per tool specification above. Do NOT add extra tools.
Use ONLY the code generation tools listed above.
For each tool specification above, create a corresponding generation step with tool_params that include:
- tool_name: Name from specification
- description: From specification
- parameters: Full parameter specs with types and defaults from specification
- implementation: Python/TCL code BODY ONLY (NOT the function definition, just the logic inside)
- add_langchain_decorator: Set to true to add @tool decorator for LangChain integration
- dependencies: List from specification

**CRITICAL for implementation:**
- Provide ONLY the function body code (what goes inside the function)
- DO NOT include 'def function_name(...):' - this will be auto-generated
- DO include imports and logic
- DO NOT include return statements - the template automatically generates proper return with success flag
- Just perform the work and the template will handle returning results  
- The code will be automatically wrapped in proper function structure with error handling

**COMPLETE EXAMPLE of implementation code:**
```python
# ✅ CORRECT: No function definition, no return statement
import MDAnalysis as mda
import pandas as pd

# Resolve input paths
traj_path = _resolve_input_path(trajectory, "trajectory")
topo_path = _resolve_input_path(topology, "topology")

# Load universe and perform analysis
u = mda.Universe(str(topo_path), str(traj_path))
selection = u.select_atoms("protein")

# Calculate values
com_data = []
for ts in u.trajectory:
    com = selection.center_of_mass()
    com_data.append({{
        "frame": ts.frame,
        "time": ts.time,
        "x": com[0],
        "y": com[1],
        "z": com[2]
    }})

# Save results
df = pd.DataFrame(com_data)
df.to_csv(output_file, index=False)

# Log statistics (no return after this!)
try:
    append_analysis_summary(
        working_dir=os.getcwd(),
        analysis_type="COM_Analysis",
        statistics={{
            "n_frames": len(df),
            "mean_x": float(df["x"].mean()),
            "std_x": float(df["x"].std()),
            "min_x": float(df["x"].min()),
            "max_x": float(df["x"].max())
        }},
        files={{"output": output_file}},
        metadata={{"selection": "protein"}}
    )
except Exception as e:
    logger.warning(f"Summary logging failed: {{e}}")

# NO return statement here - template adds it automatically!
```

⚠️ **CRITICAL: DO NOT CREATE ORCHESTRATOR TOOLS**
Tools must be SELF-CONTAINED and implement their own logic. NEVER create tools that:
- Call other programmer-generated tools (they're in separate files and not importable)
- Try to invoke functions like `calculate_something()` or `plot_something()` from other tools
- Attempt to orchestrate multiple operations (that's the WORKFLOW's job)

**BAD EXAMPLE** (orchestrator tool - DON'T DO THIS):
```python
# ❌ WRONG: Trying to call other tools
result = calculate_com_trajectory(trajectory, topology)  # This function doesn't exist!
plot_com_3d(result)  # This function doesn't exist either!
```

**GOOD EXAMPLE** (self-contained tool):
```python
# ✅ CORRECT: Implement the full logic yourself
import MDAnalysis as mda
u = mda.Universe(topology, trajectory)
com_values = [u.select_atoms("protein").center_of_mass() for ts in u.trajectory]
# ... rest of implementation
```

If the planner asks for a "wrapper" or "convenience" tool, implement the FULL logic inline,
don't try to call other tools. The workflow layer handles tool orchestration.

**Path Resolution for File Parameters:**
⚠️ CRITICAL DISTINCTION between INPUT and OUTPUT files:

**INPUT FILES** (trajectory, topology, etc.) - Use `_resolve_input_path()`:
A helper function `_resolve_input_path(file_ref, param_name)` is automatically available
to resolve INPUT file paths that may come from other agent directories.

```python
# ✅ CORRECT: Resolve INPUT file paths (may be from HPC agent directory)
traj_path = _resolve_input_path(trajectory, "trajectory")
topo_path = _resolve_input_path(topology, "topology")

# Use resolved paths in commands
u = mda.Universe(str(topo_path), str(traj_path))
# or
cmd = ["gmx", "dssp", "-s", str(topo_path), "-f", str(traj_path), ...]
```

**OUTPUT FILES** - Use filename directly (NO path resolution):
The tool executor already changes to working_dir, so just write files using the filename.

```python
# ✅ CORRECT: Use output filename directly (already in working_dir)
df.to_csv(output_csv, index=False)
plt.savefig(output_png)

# ❌ WRONG: Do NOT use _resolve_input_path for OUTPUT files
# output_path = _resolve_input_path(output_file, "output_file")  # NEVER DO THIS!
```

This ensures:
- INPUT files are found across agent directories
- OUTPUT files are created in the correct working_dir

**Analysis Summary Logging (CRITICAL for Analysis Tools):**
⚠️ MANDATORY: If generating an ANALYSIS tool, you MUST include logging to analysis_summary.jsonl.
This enables LLMs to extract insights from analysis results and answer user questions.

Required imports (add these to implementation):
```python
from src.analysis.summary_logger import append_analysis_summary
```

Required logging pattern (add at end of implementation - DO NOT add return after this):
```python
# Log important metrics to analysis summary file (REQUIRED for analysis tools)
# NOTE: Do NOT add return statement - template handles that automatically
try:
    append_analysis_summary(
            working_dir=working_dir or os.getcwd(),  # Use provided working_dir
            analysis_type="YourAnalysisType",  # e.g., "Contact_Analysis", "Distance_Matrix"
            statistics={{{{
                "n_frames": num_frames,
                "mean_value": mean_val,      # REQUIRED: Calculate mean
                "std_value": std_val,        # REQUIRED: Calculate std deviation
                "min_value": min_val,        # REQUIRED: Calculate minimum
                "max_value": max_val,        # REQUIRED: Calculate maximum
                # Add other important statistics specific to your analysis
            }}}},
            files={{{{
                "topology": topology_file,
                "trajectory": trajectory_file,
                "output": output_filename    # Use filename only, not full path
            }}}},
            metadata={{{{
                "selection": selection_string,
                # Add important metadata like:
                # "most_important_region": {{{{"residue_id": X, "value": Y}}}},
                # "top_5_highest": [{{{{"id": 1, "value": 5.0}}}}, ...],
                # "threshold": cutoff_value,
                # "interpretation": "Description of what the values mean"
            }}}}
        )
        logger.info(f"Analysis summary logged for {{{{analysis_type}}}}")
    except Exception as e:
        logger.warning(f"Failed to write to summary file: {{{{e}}}}")
```

**What to Log:**
- Statistics: min, max, mean, std of your primary metric
- Important regions/residues (e.g., most active sites, flexible regions)
- Thresholds or cutoff values used
- Top N results (e.g., top 5 contacts, most variable residues)

**Example for Contact Analysis:**
```python
statistics={{{{
    "n_frames": len(contact_counts),
    "mean_contacts": np.mean(contact_counts),
    "std_contacts": np.std(contact_counts),
    "min_contacts": np.min(contact_counts),
    "max_contacts": np.max(contact_counts)
}}}},
metadata={{{{
    "cutoff_distance": cutoff,
    "most_frequent_contacts": top_5_contacts  # List of dicts
}}}}
```

**Output Format (JSON):**
{{{{
  "reasoning": "Why these tools are needed",
  "overview": "High-level summary",
  "steps": [
    {{{{
      "name": "Generate [tool being created]",
      "description": "Create the [tool_name] tool using generate_python_tool",
      "tool_name": "generate_python_tool",  
      "tool_params": {{{{
        "tool_name": "name_of_tool_to_create",
        "description": "what the new tool does",
        "parameters": {{}},
        "implementation": "Python code body"
      }}}},
      "reason": "why this tool is needed"
    }}}}
  ],
  "estimated_complexity": "low|medium|high"
}}}}

**CRITICAL - Example of CORRECT vs WRONG:**

❌ **WRONG** (trying to execute the tool being created):
{{{{
  "steps": [
    {{{{
      "tool_name": "compute_center_of_mass",  // DON'T DO THIS!
      "tool_params": {{{{"trajectory": "..."}}}}
    }}}}
  ]
}}}}

✅ **CORRECT** (using generation tool to CREATE the tool):
{{{{
  "steps": [
    {{{{
      "tool_name": "generate_python_tool",  // Use THIS!
      "tool_params": {{{{
        "tool_name": "compute_center_of_mass",  // Tool to create
        "description": "Calculate COM from trajectory",
        "parameters": {{{{
          "trajectory": {{{{"type": "str", "description": "..."}}}},
          "topology": {{{{"type": "str", "description": "..."}}}}
        }}}},
        "implementation": "import MDAnalysis\\nu = mda.Universe(...)\\n..."
      }}}}
    }}}}
  ]
}}}}

**Remember:**
- tool_name in steps MUST be a CODE GENERATION tool (generate_python_tool, generate_tcl_script, etc.)
- The name of the tool you're CREATING goes in tool_params["tool_name"]
- DO NOT use tool specifications as step tool_names
- Each step creates ONE new tool using a generation tool
"""
        
        return prompt_template.format(
            planner_instructions=agent_input.planner_instructions,
            tool_specs_section=tool_specs_section,
            software_section=software_section,
            force_field=agent_input.force_field,
            md_engine=agent_input.md_engine,
            working_directory=agent_input.working_directory,
            tools_str=tools_str
        )
    
    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract and parse JSON plan from LLM response"""
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        return {
            "reasoning": content,
            "overview": "Fallback plan",
            "steps": [],
            "estimated_complexity": "medium"
        }
    
    def _create_fallback_plan(
        self, 
        agent_input: ProgrammerAgentInput
    ) -> ProgrammerPlan:
        """Create fallback plan when LLM is unavailable"""
        
        steps = []
        
        # PRIORITY: Use tool_specifications from planner if available
        if agent_input.tool_specifications:
            logger.info(f"FALLBACK PLAN: Using {len(agent_input.tool_specifications)} tool specifications from planner")
            for spec in agent_input.tool_specifications:
                # Extract spec fields (handle both dict and Pydantic models)
                if isinstance(spec, dict):
                    tool_name = spec.get("name", "custom_tool")
                    description = spec.get("description", "Custom tool")
                    language = spec.get("language", "python")
                    parameters = spec.get("parameters", {})
                    dependencies = spec.get("dependencies", [])
                    purpose = spec.get("purpose", "")
                else:
                    # Pydantic model
                    tool_name = spec.name
                    description = spec.description
                    language = spec.language
                    parameters = spec.parameters
                    dependencies = getattr(spec, 'dependencies', [])
                    purpose = getattr(spec, 'purpose', '')
                
                # Create step based on tool type
                if language == "python":
                    steps.append(ProgrammerStep(
                        name=f"Generate {tool_name}",
                        description=description,
                        tool_name="generate_python_tool",
                        tool_params={
                            "tool_name": tool_name,
                            "description": description,
                            "parameters": parameters,
                            "dependencies": dependencies,
                            "implementation": f"# {purpose}\npass  # Fallback implementation",
                            "working_directory": agent_input.working_directory
                        },
                        reason=f"Generate {tool_name} as specified by planner"
                    ))
                elif language == "tcl":
                    steps.append(ProgrammerStep(
                        name=f"Generate {tool_name}",
                        description=description,
                        tool_name="generate_tcl_script",
                        tool_params={
                            "script_name": tool_name,
                            "description": description,
                            "parameters": parameters,
                            "implementation": f"# {purpose}\nputs \"TCL script generated\"",
                            "working_directory": agent_input.working_directory
                        },
                        reason=f"Generate TCL script {tool_name}"
                    ))
            
            return ProgrammerPlan(
                reasoning="Fallback plan using tool specifications from planner",
                overview=f"Generate {len(steps)} tools from planner specifications",
                steps=steps,
                estimated_complexity="medium"
            )
        
        # FALLBACK: If no tool specs, use keyword detection from instructions
        instructions_lower = agent_input.planner_instructions.lower()
        
        if "mdp" in instructions_lower or "parameter" in instructions_lower:
            steps.append(ProgrammerStep(
                name="Generate MDP file",
                description="Create GROMACS parameter file",
                tool_name="generate_mdp_file",
                tool_params={
                    "mdp_type": "production",
                    "parameters": {},
                    "force_field": agent_input.force_field
                },
                reason="MDP file needed for simulation"
            ))
        
        if "python" in instructions_lower or "tool" in instructions_lower:
            steps.append(ProgrammerStep(
                name="Generate Python tool",
                description="Create custom Python analysis tool",
                tool_name="generate_python_tool",
                tool_params={
                    "tool_name": "custom_analysis",
                    "description": "Custom analysis tool",
                    "parameters": {},
                    "implementation": "# Implementation goes here\\npass"
                },
                reason="Custom tool needed for workflow"
            ))
        
        if "tcl" in instructions_lower or "vmd" in instructions_lower:
            steps.append(ProgrammerStep(
                name="Generate TCL script",
                description="Create VMD visualization script",
                tool_name="generate_tcl_script",
                tool_params={
                    "script_name": "visualization",
                    "description": "VMD visualization",
                    "parameters": {},
                    "implementation": "# TCL implementation"
                },
                reason="TCL script needed for visualization"
            ))
        
        # If no specific type detected, create a minimal Python tool
        if not steps:
            steps.append(ProgrammerStep(
                name="Generate default tool",
                description="Create default Python tool",
                tool_name="generate_python_tool",
                tool_params={
                    "tool_name": "workflow_tool",
                    "description": "Generated workflow tool",
                    "parameters": {},
                    "implementation": "# Minimal tool implementation\nlogger.info('Tool executed')"
                },
                reason="Default tool for workflow"
            ))
        
        return ProgrammerPlan(
            reasoning="Fallback plan based on keyword detection",
            overview=f"Generate {len(steps)} tool(s) based on instructions",
            steps=steps,
            estimated_complexity="low"
        )
    
    def _execute_programmer_plan(
        self,
        agent_input: ProgrammerAgentInput,
        plan: ProgrammerPlan,
        state: MDState
    ) -> ProgrammerExecutionResult:
        """Execute the programmer plan step by step"""
        
        step_results = []
        issues = []
        warnings = []
        completed = 0
        
        log_agent_action(
            agent_name="programmer",
            action="Executing programmer plan",
            details={
                "total_steps": len(plan.steps),
                "working_dir": agent_input.working_directory
            }
        )
        
        for idx, step in enumerate(plan.steps, 1):
            log_agent_action(
                agent_name="programmer",
                action=f"Executing step {idx}/{len(plan.steps)}",
                details={
                    "step": step.name,
                    "tool": step.tool_name
                }
            )
            
            try:
                # Preprocess tool params - handle LLM generating implementation as list
                tool_params = dict(step.tool_params)
                if "implementation" in tool_params and isinstance(tool_params["implementation"], list):
                    tool_params["implementation"] = "\n".join(tool_params["implementation"])
                
                # Execute tool
                result = self.tool_executor.execute(
                    step.tool_name,
                    **tool_params
                )
                
                step_results.append(result)
                
                if result.get("success"):
                    completed += 1
                    log_agent_action(
                        agent_name="programmer",
                        action=f"Step {idx}/{len(plan.steps)} completed",
                        details={"step": step.name, "status": "✅ SUCCESS"}
                    )
                    
                    # Log file creation
                    if result.get("file_path"):
                        log_file_operation(
                            agent_name="programmer",
                            operation="create",
                            file_path=result["file_path"],
                            success=True,
                            details=result.get("message", "")
                        )
                else:
                    issues.append(f"{step.name}: {result.get('error', 'Unknown error')}")
                    log_agent_action(
                        agent_name="programmer",
                        action=f"Step {idx}/{len(plan.steps)} failed",
                        details={
                            "step": step.name,
                            "status": "❌ FAILED",
                            "error": result.get("error")
                        }
                    )
                    
            except Exception as e:
                error_msg = f"{step.name} failed: {str(e)}"
                issues.append(error_msg)
                logger.error(error_msg)
                step_results.append({
                    "success": False,
                    "step": step.name,
                    "error": str(e)
                })
        
        # Reload tools in planner and field agents after successful generation
        if completed > 0:
            logger.info(f"PROGRAMMER: Reloading tools after generating {completed} tool(s)...")
            self._reload_field_agent_tools()
            self._reload_planner_tools_registry()
        
        # Generate report
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("PROGRAMMER AGENT EXECUTION REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Plan: {plan.overview}")
        report_lines.append(f"Total Steps: {len(plan.steps)}")
        report_lines.append(f"Completed: {completed}")
        report_lines.append(f"Failed: {len(plan.steps) - completed}")
        report_lines.append("")
        
        if step_results:
            report_lines.append("GENERATED TOOLS:")
            for result in step_results:
                if result.get("success"):
                    tool_name = result.get("tool_name") or result.get("script_name") or result.get("mdp_type", "unknown")
                    file_path = result.get("file_path", "N/A")
                    report_lines.append(f"  ✅ {tool_name}: {file_path}")
        
        if issues:
            report_lines.append("")
            report_lines.append("ISSUES:")
            for issue in issues:
                report_lines.append(f"  ❌ {issue}")
        
        report_lines.append("=" * 80)
        report = "\n".join(report_lines)
        
        logger.info(report)
        
        return ProgrammerExecutionResult(
            success=len(issues) == 0,
            completed_steps=completed,
            total_steps=len(plan.steps),
            issues=issues,
            warnings=warnings,
            report=report,
            step_results=step_results,
            generated_files={
                result.get("tool_name", result.get("script_name", f"file_{idx}")): result.get("file_path", "")
                for idx, result in enumerate(step_results)
                if result.get("success") and result.get("file_path")
            }
        )
    
    def _update_state(self, state: MDState, output: ProgrammerAgentOutput) -> None:
        """Update workflow state with programmer results"""
        
        state["programmer_output"] = {
            "success": output.success,
            "generated_tools": [
                {
                    "name": tool.name,
                    "file_path": tool.file_path,
                    "language": tool.language,
                    "status": tool.status
                }
                for tool in output.result.generated_tools
            ],
            "tools_available": output.result.tools_available,
            "output_directory": output.result.output_directory
        }
        
        # Register generated files using SecureFileManager
        for tool_name, file_path in output.result.tools_available.items():
            self.file_manager.register_external_file(
                file_path=file_path,
                file_type="generated_code",
                description=f"Generated tool: {tool_name}"
            )
        
        # Add errors to state
        if output.errors:
            state["errors"].extend(output.errors)
