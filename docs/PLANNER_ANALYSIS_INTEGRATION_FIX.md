# Planner-Analysis Agent Integration Fix

## Problem
The planner was creating execution plans for analysis-only workflows using bash/GROMACS commands (e.g., `gmx rmsf`) instead of using the analysis agent's structured Python tools (e.g., `calculate_rmsf`).

**Evidence from agent_conversation.log (lines 1-135):**
- User requested: "calculate RMSF"
- Planner created plan with: bash commands, `gmx rmsf`, awk, gnuplot
- Planner's LLM prompt was missing the analysis agent's available tools
- Expected: Should use `calculate_rmsf` tool from analysis agent

## Root Cause
In [planner_agent.py](agentic/planner/planner_agent.py), the `_build_planning_prompt` method for analysis-only workflows did not include:
1. The `tools_context` parameter (list of available analysis tools)
2. Instructions to use Python tools instead of bash/GROMACS commands

## Solution Implemented

### 1. Agent-Specific Tools Discovery (Lines 198-217)
Modified `_create_plan_from_analysis` to get agent-specific tools based on `subtask_type`:

```python
# Get available tools context - agent-specific for subtask workflows
if subtask_type == "analysis_only":
    logger.info("PLANNER: Getting analysis agent tools for analysis-only workflow")
    tools_context = self._get_tools_context(agent_name="analysis")
elif subtask_type == "setup_only":
    logger.info("PLANNER: Getting setup agent tools for setup-only workflow")
    tools_context = self._get_tools_context(agent_name="simsetup")
elif subtask_type == "preprocess_only":
    logger.info("PLANNER: Getting preprocessing agent tools for preprocess-only workflow")
    tools_context = self._get_tools_context(agent_name="preprocess")
else:
    # Full workflow - get all tools
    tools_context = self._get_tools_context()
```

**Impact:** When planning for analysis-only workflows, the planner now gets only the 6 analysis tools:
- calculate_rmsd
- calculate_rmsf  
- calculate_radius_of_gyration
- analyze_energy
- extract_trajectory_metrics
- run_complete_analysis

### 2. Enhanced Analysis-Only Prompt (Lines 280-307)
Added tools context and explicit instructions to the analysis-only prompt:

```python
if subtask_type == "analysis_only":
    working_dir = state.get("working_directory", ".")
    return f"""Create an execution plan for trajectory analysis.

USER GOAL:
{structured_prompt}

TASK: Analysis-only - perform trajectory analysis on existing simulation data.
DO NOT include preprocessing, setup, or HPC agents.
ONLY create execution plan for Analysis Agent.

File Structure:
- Working Directory: {working_dir}
- Trajectory/Topology Location: {working_dir}/hpc/ (auto-discovery)
- Analysis Output Directory: {working_dir}/analysis/

**Available Analysis Agent Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS:**
- Use the analysis agent's Python tools listed above (calculate_rmsd, calculate_rmsf, etc.)
- Do NOT use bash/shell commands or GROMACS CLI tools (gmx rmsf, etc.)
- The analysis agent will handle file discovery and tool execution
- Specify WHICH tools to use and what analysis to perform
- Let the analysis agent handle the implementation details

Create a clear execution plan that tells the Analysis Agent WHICH analysis tools to use and WHY."""
```

**Impact:** The LLM now sees:
- ✅ Explicit list of available analysis tools with descriptions and parameters
- ✅ Instructions to use Python tools (calculate_rmsf) NOT bash (gmx rmsf)
- ✅ Context about file locations and agent responsibilities

### 3. Consistent Pattern for Other Subtasks
Applied the same enhancement to `setup_only` and `preprocess_only` prompts (lines 309-353) for consistency.

## Verification

### Test Results (test_end_to_end_planner_fix.py)
```
✓ 37 total tools discovered across all agents
✓ 6 analysis tools available
✓ Retrieved 4,328 chars of tools context for analysis agent
✓ All 5 core analysis tools present in context:
  • calculate_rmsd
  • calculate_rmsf  
  • calculate_radius_of_gyration
  • analyze_energy
  • extract_trajectory_metrics
✓ Prompt includes "**Available Analysis Agent Tools:**"
✓ Prompt includes critical instructions
```

### Before vs After

**BEFORE (from agent_conversation.log):**
```
Planner's LLM Prompt:
TASK: Analysis-only - perform trajectory analysis on existing simulation data.
DO NOT include preprocessing, setup, or HPC agents.
ONLY create execution plan for Analysis Agent.

Create a clear execution plan for the Analysis Agent to perform the requested analysis.
```
→ Result: LLM created bash script with `gmx rmsf` commands

**AFTER (with fix):**
```
Planner's LLM Prompt:
TASK: Analysis-only - perform trajectory analysis on existing simulation data.
...

**Available Analysis Agent Tools:**

- **calculate_rmsf**
  Calculate RMSF (Root Mean Square Fluctuation) for a trajectory.
  RMSF measures per-residue flexibility over the simulation.
  
  Parameters:
    • trajectory_file (required): Path to trajectory file (.xtc, .trr)
    • topology_file (required): Path to topology file (.tpr, .pdb)
    ...

**CRITICAL INSTRUCTIONS:**
- Use the analysis agent's Python tools listed above (calculate_rmsd, calculate_rmsf, etc.)
- Do NOT use bash/shell commands or GROMACS CLI tools (gmx rmsf, etc.)
```
→ Result: LLM will create structured tool calls using `calculate_rmsf`

## Files Modified

1. **[agentic/planner/planner_agent.py](agentic/planner/planner_agent.py)** 
   - Lines 198-217: Agent-specific tools discovery
   - Lines 280-353: Enhanced subtask-specific prompts with tools context

## Testing

Run verification tests:
```bash
# Debug tools discovery
python tests/debug_tools_discovery.py

# End-to-end integration test
python tests/test_end_to_end_planner_fix.py
```

## Impact

### For Analysis-Only Workflows:
- ✅ Planner sees analysis agent's 6 Python tools
- ✅ Execution plans use structured tool calls (calculate_rmsf)
- ✅ No more bash/GROMACS command scripts (gmx rmsf)
- ✅ Analysis agent receives tool invocations it can execute directly

### For Setup-Only Workflows:
- ✅ Planner sees 14 setup agent tools (generate_topology, etc.)
- ✅ Execution plans reference proper setup tools

### For Preprocess-Only Workflows:
- ✅ Planner sees 5 preprocessing agent tools (remove_waters, etc.)
- ✅ Execution plans reference proper preprocessing tools

## Architecture Alignment

This fix completes the integration pattern established by the simsetup agent:

1. **Tool Metadata Functions** (analysis/tools.py)
   - `get_analysis_tools()` - Returns list of StructuredTool objects
   - `get_tool_metadata()` - Extracts tool metadata for registry

2. **Tools Registry** (planner/tools_registry.py)
   - Discovers tools from all agents' tools.py files
   - Provides `get_tools_for_planner(agent_name)` for agent-specific tools

3. **LLM Planning Prompts** (planner/planner_agent.py)
   - Include {tools_list} with agent-specific tools
   - Explicit instructions to use structured tools

4. **Field Agent Orchestration** (analysis/analysis_agent.py)
   - Receives planner's instructions
   - Creates execution plan using available tools via LLM
   - Executes tools using ToolExecutor

## Next Steps

1. **Test with Live Workflow**: Run end-to-end analysis-only workflow to verify LLM generates proper tool calls
2. **Monitor Logs**: Check that planner's execution plans now reference analysis tools
3. **Validate Analysis Agent**: Ensure analysis agent successfully executes the structured tool calls

## Related Documentation

- [ANALYSIS_AGENT_IMPLEMENTATION.md](docs/ANALYSIS_AGENT_IMPLEMENTATION.md)
- [SIMSETUP_COMPONENT_WORKFLOW.md](docs/SIMSETUP_COMPONENT_WORKFLOW.md) - Pattern we followed
- [SUPERVISOR_USAGE_GUIDE.md](docs/SUPERVISOR_USAGE_GUIDE.md)
