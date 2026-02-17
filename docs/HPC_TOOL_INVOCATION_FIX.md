# HPC Agent Tool Invocation Fix

## Issue Summary
After refactoring HPC tools to modular architecture, the HPC agent failed with:
```
ERROR - Tool execution failed: copy_simulation_files - 'StructuredTool' object is not callable
ERROR - LLM planning failed: 'LLMClient' object has no attribute 'chat_completion'
```

## Root Causes

### 1. Incorrect Tool Invocation
**File**: `agentic/hpc/hpc_agent.py` line 517

**Problem**: Tools were being called directly with `tool_func(**tool_params)`

**Why It Failed**: After refactoring, tools are now LangChain `StructuredTool` objects (created by `@tool` decorator). These cannot be called directly like regular functions.

**Solution**: Changed to `tool_func.invoke(tool_params)` to use the proper LangChain tool invocation method.

### 2. Wrong LLM Method Name
**File**: `agentic/hpc/hpc_agent.py` line 228

**Problem**: Code was calling `self.llm.chat_completion()`

**Why It Failed**: The `LLMClient` class only has a `prompt()` method, not `chat_completion()`.

**Solution**: Changed to `self.llm.prompt()` to match the actual LLM client API.

## Changes Made

### Change 1: Fix Tool Invocation
**Location**: `agentic/hpc/hpc_agent.py:517` in `_execute_tool()` method

**Before**:
```python
# Execute tool
result = tool_func(**tool_params)
return result
```

**After**:
```python
# Execute tool using .invoke() method for LangChain tools
result = tool_func.invoke(tool_params)
return result
```

**Explanation**: LangChain tools created with `@tool` decorator are `StructuredTool` objects that must be invoked using `.invoke(dict)` method, not called directly.

### Change 2: Fix LLM Method Call
**Location**: `agentic/hpc/hpc_agent.py:228` in `_create_execution_plan()` method

**Before**:
```python
response = self.llm.chat_completion(
    prompt,
    temperature=0.1,
    max_tokens=2000
)
```

**After**:
```python
response = self.llm.prompt(
    prompt,
    temperature=0.1
)
```

**Explanation**: The `LLMClient` class uses `prompt()` as the method name for LLM calls, not `chat_completion()`. The `max_tokens` parameter is not needed.

## Verification

### Test Suite Created
**File**: `tests/test_hpc_tool_invocation_fix.py`

**Tests**:
1. ✅ Tool invocation with `.invoke()` works
2. ✅ Tools are `StructuredTool` objects with `.invoke()` method
3. ✅ HPC agent can access all 6 tools correctly

**Results**: All tests passing

### Test Output
```
============================================================
HPC Agent Tool Invocation Fix Verification
============================================================
Testing HPC tool invocation...

1. Testing estimate_simulation_time.invoke()...
   ✅ Tool invoked successfully
   Estimated: 303.6 hours
   SLURM time: 12-15:36:00

2. Checking tool type...
   Tool type: <class 'langchain_core.tools.structured.StructuredTool'>
   Has .invoke(): True
   ✅ Tool has .invoke() method

3. Testing HPC agent tool access...
   Found 6 tools
   ✅ copy_simulation_files: has .invoke() = True
   ✅ estimate_simulation_time: has .invoke() = True
   ✅ create_slurm_script: has .invoke() = True
   ✅ submit_job: has .invoke() = True
   ✅ check_job_status: has .invoke() = True
   ✅ download_results: has .invoke() = True

============================================================
Summary
============================================================
✅ All tests passed - tool invocation fix verified!
```

## Impact Analysis

### Files Modified
1. **agentic/hpc/hpc_agent.py** (2 changes)
   - Line 517: Changed tool invocation to use `.invoke()`
   - Line 228: Changed LLM call to use `.prompt()`

### Files Not Changed
- All tool files in `src/hpc/*.py` - unchanged
- `agentic/hpc/tools.py` - unchanged
- All other agent files - unchanged

### Backward Compatibility
✅ **No breaking changes** to tool signatures or public APIs

## Technical Details

### LangChain Tool Pattern
When you use the `@tool` decorator:
```python
from langchain.tools import tool

@tool
def my_tool(param1: str) -> Dict[str, Any]:
    """Tool description"""
    return {"result": param1}
```

It creates a `StructuredTool` object with:
- `.name` - Tool name
- `.description` - Tool description
- `.args_schema` - Pydantic schema for validation
- `.invoke(dict)` - Method to execute the tool

### Why .invoke(dict) Instead of **kwargs?
LangChain tools expect a dictionary input:
```python
# ✅ Correct
result = tool.invoke({"param1": "value"})

# ❌ Wrong
result = tool(param1="value")  # TypeError: 'StructuredTool' object is not callable
```

### LLMClient API
The `LLMClient` class signature:
```python
def prompt(self, prompt: str, system: Optional[str] = None, **kwargs) -> str:
    """Execute LLM prompt and return response"""
```

Parameters like `temperature` can be passed in `**kwargs`.

## Related Issues

### Why This Happened
The refactoring moved tools to `src/hpc/*.py` with `@tool` decorators, making them LangChain `StructuredTool` objects. However, the HPC agent's `_execute_tool()` method was still calling them like regular Python functions.

### Other Agents
This pattern is **correctly implemented** in:
- **Preprocessing Agent**: Uses tool executor class
- **SimSetup Agent**: Uses `SimulationSetupToolExecutor` with `.invoke()`
- **Planner Agent**: Uses tool registry with proper invocation

The HPC agent was the only one with direct tool calls that needed updating.

## Lessons Learned

### Best Practice for LangChain Tools
When using `@tool` decorator:
1. Always invoke with `.invoke(dict_params)`
2. Pass parameters as dictionary, not kwargs
3. Check tool type with `isinstance(tool, StructuredTool)`

### Tool Executor Pattern
For consistency, consider using an executor class (like `HPCToolExecutor`) instead of direct tool calls in agent code. This:
- Centralizes tool invocation logic
- Makes parameter enrichment easier
- Provides consistent error handling

## Next Steps

### Immediate
- ✅ Fix applied and tested
- ✅ All tests passing
- ✅ HPC agent operational

### Future Improvements
- Consider refactoring HPC agent to use `HPCToolExecutor` instead of direct tool calls
- Add integration tests with mock SSH/SLURM environment
- Add more comprehensive error handling for tool invocation failures

## Summary

**Issue**: HPC agent tools not callable after modular refactoring
**Root Cause**: Tools are now `StructuredTool` objects requiring `.invoke()` method
**Fix**: Changed from `tool_func(**params)` to `tool_func.invoke(params)`
**Status**: ✅ Fixed and verified
**Testing**: 3/3 tests passing
