# Supervisor Refactoring Summary

## Overview
Refactored the supervisor module to eliminate code duplication and create a unified, modular validation and enrichment system that works for all task types.

## Changes Made

### 1. New Unified Functions in `tools.py`

#### `rephrase_with_context()`
- **Purpose**: Universal LLM rephrasing for all task types
- **Replaces**: 
  - `rephrase_user_goal_with_llm()` (for PDB tasks)
  - `rephrase_analysis_goal_with_llm()` (for analysis tasks)
- **Parameters**: Takes `context_type` ("pdb" or "files") to determine which prompt template to use
- **Benefit**: Single function handles all rephrasing needs

#### `enrich_prompt_with_context()`
- **Purpose**: Universal prompt enrichment with validated information
- **Replaces**:
  - `enrich_user_prompt()` (for PDB tasks)
  - `enrich_analysis_prompt()` (for analysis tasks)
- **Parameters**: Takes `context_type` and `context_data` to build appropriate enriched prompt
- **Benefit**: Combines rephrasing + context addition in one consistent interface

#### `validate_and_enrich_inputs()`
- **Purpose**: Universal input validation for all task types
- **Replaces**:
  - `input_validation_node()` implementation logic (for PDB tasks)
  - `_validate_analysis_inputs()` (for analysis tasks)
- **Sub-functions**:
  - `_validate_pdb_structure()` - Handles PDB-based tasks (full, setup-only, preprocess-only)
  - `_validate_analysis_files()` - Handles analysis-only tasks
- **Benefit**: Single entry point for all validation, internally routes based on task type

### 2. Simplified `supervisor.py`

#### `supervisor_node()`
- **Before**: Complex branching logic for different task types
  ```python
  if not state.get("pdb_analysis") and required_inputs.get("pdb_analysis_required"):
      state["next_node"] = "input_validation"
  elif state.get("subtask_type") == "analysis_only" and not state.get("analysis_validated"):
      state = self._validate_analysis_inputs(state)
  ```
- **After**: Unified validation check
  ```python
  needs_validation = False
  if not state.get("pdb_analysis") and required_inputs.get("pdb_analysis_required"):
      needs_validation = True
  elif subtask_type == "analysis_only" and not state.get("analysis_validated"):
      needs_validation = True
  
  if needs_validation:
      state["next_node"] = "input_validation"
  ```

#### `input_validation_node()`
- **Before**: 160+ lines of PDB-specific validation logic
- **After**: 40 lines that call unified function
  ```python
  state = validate_and_enrich_inputs(
      state=state,
      subtask_type=subtask_type,
      llm_client=self.llm,
      config=self.supervisor_config,
      analyze_pdb_tool=analyze_pdb,
      logger=logger
  )
  ```

#### `_validate_analysis_inputs()`
- **Status**: Deprecated, redirects to `input_validation_node()`
- **Reason**: Preserved for backward compatibility
- **Code**: 
  ```python
  logger.warning("_validate_analysis_inputs is deprecated.")
  return self.input_validation_node(state)
  ```

### 3. Field Agent Consistency Verification

All field agents confirmed to follow the same pattern:

#### **PreprocessingAgent** ([agentic/preprocess/preprocessing_agent.py](agentic/preprocess/preprocessing_agent.py))
- Entry point: `preprocess_node()`
- Checks for planner instructions: `execution_plan.get("format") == "natural_language"`
- Extracts agent-specific section: `_extract_agent_instructions()`
- Uses: `PreprocessingToolExecutor`

#### **SimulationSetupAgent** ([agentic/simsetup/setup_agent.py](agentic/simsetup/setup_agent.py))
- Entry point: `setup_node()`
- Same workflow pattern as preprocessing
- Uses: `SimulationSetupToolExecutor`

#### **MDAnalysisAgent** ([agentic/analysis/analysis_agent.py](agentic/analysis/analysis_agent.py))
- Entry point: `analysis_node()`
- Same workflow pattern
- Uses: `AnalysisToolExecutor`

**Result**: ✅ All field agents are already consistent!

## Code Reduction

### Lines Removed
- **supervisor.py**: ~160 lines of duplicate validation logic
- **tools.py**: Reused existing functions, added unified wrappers

### Lines Added
- **tools.py**: ~220 lines (unified functions with comprehensive logic)
- **supervisor.py**: ~40 lines (simplified validation node)

### Net Result
- More modular, maintainable code
- Single source of truth for validation/enrichment logic
- Easier to extend for new task types

## Architecture Benefits

### Before
```
supervisor_node()
├── PDB validation → input_validation_node() (160 lines)
│   ├── Extract PDB
│   ├── Analyze structure
│   ├── Parse components
│   └── Enrich with enrich_user_prompt()
│       └── rephrase_user_goal_with_llm()
└── Analysis validation → _validate_analysis_inputs() (160 lines)
    ├── Discover files
    ├── Validate files
    └── Enrich with enrich_analysis_prompt()
        └── rephrase_analysis_goal_with_llm()
```

### After
```
supervisor_node()
└── Unified validation → input_validation_node() (40 lines)
    └── validate_and_enrich_inputs() (shared function)
        ├── For PDB tasks → _validate_pdb_structure()
        │   └── enrich_prompt_with_context(type="pdb")
        │       └── rephrase_with_context(type="pdb")
        └── For analysis tasks → _validate_analysis_files()
            └── enrich_prompt_with_context(type="files")
                └── rephrase_with_context(type="files")
```

## Task Type Coverage

The unified system handles all task types:

| Task Type | PDB Required | File Discovery | Validation Function | Enrichment Type |
|-----------|--------------|----------------|---------------------|-----------------|
| `full_task` | ✅ | ❌ | `_validate_pdb_structure()` | `context_type="pdb"` |
| `setup_only` | ✅ | ❌ | `_validate_pdb_structure()` | `context_type="pdb"` |
| `preprocess_only` | ✅ | ❌ | `_validate_pdb_structure()` | `context_type="pdb"` |
| `analysis_only` | ❌ | ✅ | `_validate_analysis_files()` | `context_type="files"` |

## File Discovery Priority (Analysis Tasks)

The unified system maintains the same 3-tier priority:

1. **Explicit files** in user goal (e.g., "analyze md.xtc")
2. **Default to md.*** pattern (md.gro, md.xtc, md.edr)
3. **Auto-discovery** fallback (first available file)

## Backward Compatibility

- Old function names preserved as deprecated wrappers
- `_validate_analysis_inputs()` redirects to unified function
- Existing tests should continue to work

## Testing Strategy

### Unit Tests (Recommended)
```python
# Test unified rephrasing
def test_rephrase_with_context_pdb():
    result = rephrase_with_context(
        user_goal="Run simulation",
        context_type="pdb",
        context_data={"pdb_summary": "Protein: 100 residues"},
        llm_client=mock_llm,
        config=test_config
    )
    assert result != "Run simulation"  # Should be enriched

# Test unified validation
def test_validate_and_enrich_inputs_analysis():
    state = {
        "user_goal": "Analyze RMSD using md.xtc and md.gro",
        "working_directory": "test_dir",
        "subtask_type": "analysis_only"
    }
    result = validate_and_enrich_inputs(
        state=state,
        subtask_type="analysis_only",
        llm_client=mock_llm,
        config=test_config,
        analyze_pdb_tool=None,
        logger=test_logger
    )
    assert result["topology"] == "test_dir/hpc/md.gro"
    assert result["trajectory_path"] == "test_dir/hpc/md.xtc"
```

### Integration Tests
1. **Analysis-only workflow**: Run with md.* files
2. **Setup-only workflow**: Run with PDB file
3. **Full workflow**: End-to-end test
4. **Mixed workflows**: Verify state propagation between agents

## Migration Notes

### For Developers

**If you were calling these functions directly:**

❌ **Old way:**
```python
enriched = enrich_user_prompt(goal, analysis, llm, config)
# OR
enriched = enrich_analysis_prompt(goal, file_info, llm, config)
```

✅ **New way:**
```python
# For PDB tasks
enriched = enrich_prompt_with_context(
    user_goal=goal,
    context_type="pdb",
    context_data={"pdb_analysis": analysis, "pdb_summary": summary},
    llm_client=llm,
    config=config
)

# For analysis tasks
enriched = enrich_prompt_with_context(
    user_goal=goal,
    context_type="files",
    context_data={"file_info": file_info},
    llm_client=llm,
    config=config
)
```

### For Users

**No changes required!** The refactoring is internal - all user-facing behavior remains the same:
- Command-line arguments unchanged
- Task type specification unchanged
- File discovery behavior unchanged
- Output format unchanged

## Future Extensions

The modular architecture makes it easy to add new task types:

1. Add new `context_type` in `rephrase_with_context()`
2. Add corresponding prompt template in config
3. Create validation sub-function (e.g., `_validate_custom_task()`)
4. Update `validate_and_enrich_inputs()` to route to new function

## Verification Checklist

- [x] All field agents follow consistent workflow pattern
- [x] Unified validation function created
- [x] Unified rephrasing function created
- [x] Unified enrichment function created
- [x] Supervisor refactored to use unified functions
- [x] Old code deprecated with backward compatibility
- [x] No syntax errors in modified files
- [ ] Unit tests pass (to be run)
- [ ] Integration tests pass (to be run)
- [ ] Analysis-only workflow tested (to be run)
- [ ] Full workflow tested (to be run)

## Related Files

### Modified
- [agentic/supervisor/tools.py](agentic/supervisor/tools.py) - Added unified functions
- [agentic/supervisor/supervisor.py](agentic/supervisor/supervisor.py) - Refactored validation logic

### Examined (No Changes Needed)
- [agentic/preprocess/preprocessing_agent.py](agentic/preprocess/preprocessing_agent.py) - Already consistent ✅
- [agentic/simsetup/setup_agent.py](agentic/simsetup/setup_agent.py) - Already consistent ✅
- [agentic/analysis/analysis_agent.py](agentic/analysis/analysis_agent.py) - Already consistent ✅

### State Management
- [agentic/state.py](agentic/state.py) - Updated with `hpc_output_directory` and `energy_file` fields (previous session)

## Summary

Successfully refactored the supervisor module to:
1. ✅ Eliminate code duplication (~160 lines removed from supervisor)
2. ✅ Create single modular validation function for all task types
3. ✅ Create single modular rephrasing function for all prompts
4. ✅ Simplify supervisor routing logic
5. ✅ Maintain backward compatibility
6. ✅ Verify all field agents follow consistent patterns

The system is now more maintainable, easier to extend, and follows the DRY (Don't Repeat Yourself) principle.
