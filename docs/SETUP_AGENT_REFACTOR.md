# Simulation Setup Agent Refactoring Summary

## Overview
Refactored `setup_agent.py` to follow the same modular, LLM-guided workflow pattern as `preprocessing_agent.py`.

## Key Changes

### 1. **Updated `simsetup/schemas.py`**
Added workflow orchestration schemas matching preprocessing agent pattern:
- `SimSetupStep` - Single step in execution plan (like `PreprocessingStep`)
- `SimSetupPlan` - LLM-generated plan with reasoning, overview, steps (like `PreprocessingPlan`)
- `SimSetupResult` - Execution results with coordinates, topology, MDP files (like `PreprocessingResult`)
- `SimSetupAgentInput` - Structured input from workflow state (like `PreprocessingAgentInput`)
- `SimSetupAgentOutput` - Structured output with plan, result, supervisor_update (like `PreprocessingAgentOutput`)

### 2. **Completely Rewrote `setup_agent.py`**
**Removed:**
- ❌ Hardcoded MDP file contents in `_generate_default_mdp_files()` (150+ lines of redundant parameters)
- ❌ `_generate_setup_plan()` with section-based LLM prompts (BOX_SETUP, SOLVATION, etc.)
- ❌ `_execute_setup_plan()` with manual command construction
- ❌ Direct `self.tools.build_topology()` calls mixing high-level and low-level logic

**Added:**
- ✅ `_create_setup_plan()` - LLM generates structured `SimSetupPlan` with JSON steps
- ✅ `_execute_plan()` - Step-by-step execution using `tool_executor.execute_tool()` with:
  - Retry logic (max 2 retries per tool)
  - File chaining (output of step N becomes input of step N+1)
  - Hardcoded directory isolation (all outputs → `working_dir/simsetup/`)
  - Detailed execution logging
- ✅ `_analyze_system()` - Detect system type (protein_only, protein_ligand, protein_ligand_ion)
- ✅ `_build_planning_prompt()` - Support both planner instructions and config-based prompts
- ✅ `_create_fallback_plan()` - Template-based plan when LLM unavailable
- ✅ `_extract_plan_json()` - Parse LLM response into structured plan
- ✅ Uses `generate_mdp_files` tool exclusively (no hardcoded MDP content)

### 3. **Updated `simsetup/config.yaml`**
Added comprehensive LLM planning prompt template:
```yaml
llm:
  planning_prompt_template: |
    You are a GROMACS molecular dynamics expert...
    [Detailed instructions for LLM to generate setup plans]
```

**Prompt includes:**
- System information and analysis
- Available tools (dynamically generated from `tools.py`)
- Critical workflow rules (topology → box → solvate → MDP → ions)
- Directory isolation rules (all outputs to simsetup/)
- JSON output format specification
- Example workflow for protein+ligand systems

## Workflow Pattern Comparison

### Before (Old setup_agent.py)
```
setup_node()
  ↓
_generate_setup_plan() → LLM returns text sections
  ↓
_execute_setup_plan() → Manual tool calls
  ↓
Direct method calls: self.tools.build_topology()
```

### After (New setup_agent.py)
```
setup_node()
  ↓
_run_setup_workflow()
  ↓
_create_setup_plan() → LLM returns JSON steps
  ↓
_execute_plan() → Loop through steps
  ↓
tool_executor.execute_tool(tool_name, params)
```

**Now matches preprocessing_agent.py exactly!**

## Benefits

### 1. **Modular Tool Usage**
- All tools accessed via `tool_executor.execute_tool(name, params)`
- No redundant MDP file content (uses `mdp_generator.py` tool)
- Easy to add new tools without modifying agent code

### 2. **LLM-Guided Planning**
- LLM generates structured plans as JSON
- Plans include reasoning, potential issues, recommendations
- Supports both planner instructions and standalone mode

### 3. **Robust Execution**
- Retry logic per tool (max 2 retries)
- File chaining between steps
- Detailed execution logging
- Fail-fast option for debugging

### 4. **Directory Isolation**
- All outputs hardcoded to `working_dir/simsetup/`
- LLM cannot specify wrong paths
- Automatic file copying from `preprocess/` directory

### 5. **Consistent Architecture**
- Same workflow pattern as preprocessing agent
- Same schema structure (Plan, Step, Result, AgentInput, AgentOutput)
- Same LLM interaction pattern (planning → execution)
- Easy to understand and maintain

## File Organization

```
agentic/simsetup/
├── setup_agent.py        # NEW: Modular LLM-guided agent (500 lines)
├── schemas.py            # UPDATED: Added workflow orchestration schemas
├── config.yaml           # UPDATED: Added llm.planning_prompt_template
└── tools.py              # UNCHANGED: Already modular with @tool decorators

backup/
└── setup_agent_old.py    # OLD: Hardcoded MDP approach (508 lines)

src/simsetup/
├── mdp_generator.py      # Used by agent (no longer hardcoded)
├── topology_builder.py   # Used via tools.py
├── box_builder.py        # Used via tools.py
├── solvator.py           # Used via tools.py
├── ion_adder.py          # Used via tools.py
└── ...                   # All other modular tools
```

## Testing Recommendations

1. **Test LLM Planning**:
   ```python
   # Agent should generate structured plan for protein+ligand system
   agent = SimulationSetupAgent()
   plan = agent._create_setup_plan(agent_input, state)
   assert len(plan.steps) > 0
   assert all(step.tool_name in available_tools for step in plan.steps)
   ```

2. **Test Tool Execution**:
   ```python
   # Agent should execute plan step-by-step
   result = agent._execute_plan(agent_input, plan, state)
   assert result.success
   assert result.coordinates  # Final system.gro file
   assert result.topology     # Final topol.top file
   assert len(result.mdp_files) >= 4  # minim, nvt, npt, md
   ```

3. **Test Directory Isolation**:
   ```python
   # All outputs should be in simsetup/
   assert all("simsetup" in path for path in result.generated_files.keys())
   ```

4. **Test Fallback Mode**:
   ```python
   # Agent should work without LLM
   agent = SimulationSetupAgent(llm_client=MockLLMClient())
   result = agent._create_fallback_plan(agent_input, analysis)
   assert len(result.steps) > 0
   ```

## Migration Notes

**For users of old setup_agent.py:**
- Old file moved to `backup/setup_agent_old.py`
- New agent uses same entry point: `setup_node(state)`
- New agent requires same state fields: `cleaned_pdb`, `force_field`, `water_model`
- New agent produces same outputs: `coordinates`, `topology`, `mdp_files`
- **Breaking change**: No longer has `_generate_default_mdp_files()` method - use `mdp_generator.py` tool instead

**For integration with workflow:**
- No changes needed to workflow.py
- Agent still returns same state updates
- Agent still supports human-in-the-loop checkpoints
- Agent still logs to conversation_logger.py

## Summary

The refactored setup agent is now:
- ✅ **Modular**: Uses tools from `tools.py`, no hardcoded MDP content
- ✅ **Intelligent**: LLM-guided planning with structured JSON output
- ✅ **Consistent**: Matches preprocessing agent architecture exactly
- ✅ **Robust**: Retry logic, error handling, detailed logging
- ✅ **Maintainable**: Clear separation of planning and execution logic

Old `setup_agent_old.py` = 508 lines with 150+ lines of hardcoded MDP parameters  
New `setup_agent.py` = 500 lines with modular tool usage and LLM planning
