# HPC Tools Architecture - Before and After

## Architecture Transformation

### BEFORE: Monolithic Structure
```
agentic/hpc/
├── tools.py (850+ lines) ❌
│   ├── @tool copy_simulation_files
│   ├── @tool estimate_simulation_time
│   ├── @tool create_slurm_script
│   ├── @tool submit_job
│   ├── @tool check_job_status
│   └── @tool download_results
├── hpc_agent.py
├── schemas.py
└── config.yaml

src/hpc/
└── slurm_script_generator.py (standalone)

Problems:
- All tools in one 850+ line file
- Hard to maintain and test
- Poor code organization
- Inconsistent with simsetup agent
```

### AFTER: Modular Structure
```
agentic/hpc/
├── tools.py (144 lines) ✅
│   ├── Imports from src/hpc/*
│   ├── __all__ exports
│   └── HPCToolExecutor class
├── hpc_agent.py (unchanged)
├── schemas.py
└── config.yaml

src/hpc/
├── file_copy.py (79 lines)
│   └── @tool copy_simulation_files
├── time_estimator.py (112 lines)
│   └── @tool estimate_simulation_time
├── script_creator.py (73 lines)
│   └── @tool create_slurm_script (wrapper)
├── job_submitter.py (130 lines)
│   └── @tool submit_job
├── job_monitor.py (132 lines)
│   └── @tool check_job_status
├── results_downloader.py (117 lines)
│   └── @tool download_results
└── slurm_script_generator.py (338 lines)
    └── generate_slurm_script (logic)

Benefits:
✅ Modular: 1 file = 1 tool
✅ Reusable: Tools in src/ for any context
✅ Testable: Each tool independently testable
✅ Consistent: Matches simsetup pattern
✅ Maintainable: Easy to locate and modify
```

## Line Count Comparison

### Before
```
agentic/hpc/tools.py:     850+ lines (ALL TOOLS)
src/hpc/:                  338 lines (script generator only)
─────────────────────────────────
Total:                    1188 lines
```

### After
```
agentic/hpc/tools.py:      144 lines (wrapper + executor)
src/hpc/file_copy.py:       79 lines
src/hpc/time_estimator.py: 112 lines
src/hpc/script_creator.py:  73 lines
src/hpc/job_submitter.py:  130 lines
src/hpc/job_monitor.py:    132 lines
src/hpc/results_downloader: 117 lines
src/hpc/slurm_script_gen:  338 lines
─────────────────────────────────
Total:                    1125 lines
```

**Result**: Better organized with similar total lines, but now modular!

## Import Flow Diagram

### Old Import Pattern
```
hpc_agent.py
    ↓
agentic/hpc/tools.py
    ├── copy_simulation_files (defined here)
    ├── estimate_simulation_time (defined here)
    ├── create_slurm_script (defined here)
    ├── submit_job (defined here)
    ├── check_job_status (defined here)
    └── download_results (defined here)
```

### New Import Pattern
```
hpc_agent.py
    ↓
agentic/hpc/tools.py (thin wrapper)
    ↓
src/hpc/ (modular tools)
    ├── file_copy.py → copy_simulation_files
    ├── time_estimator.py → estimate_simulation_time
    ├── script_creator.py → create_slurm_script
    │       ↓
    │   slurm_script_generator.py
    ├── job_submitter.py → submit_job
    ├── job_monitor.py → check_job_status
    └── results_downloader.py → download_results
```

## Tool Execution Flow

### Using HPCToolExecutor
```
User Code
    ↓
HPCToolExecutor.execute(tool_name, **kwargs)
    ↓
_enrich_parameters(tool_name, kwargs)
    ├── Add SSH config (host, user, key_path)
    ├── Add path config (dest_dir, local_dir)
    └── Add SLURM defaults (partition, CPUs, memory)
    ↓
tool_func.invoke(enriched_kwargs)
    ↓
Execute actual tool from src/hpc/
    ↓
Return result dict
```

## Direct Tool Usage
```python
# Option 1: Import from agentic wrapper
from agentic.hpc.tools import estimate_simulation_time
result = estimate_simulation_time.invoke({"production_ns": 10.0})

# Option 2: Import directly from src
from src.hpc.time_estimator import estimate_simulation_time
result = estimate_simulation_time.invoke({"production_ns": 10.0})

# Option 3: Use executor with config enrichment
from agentic.hpc.tools import HPCToolExecutor
executor = HPCToolExecutor(config)
result = executor.execute("estimate_simulation_time", production_ns=10.0)
```

## Consistency with SimulationSetup Agent

### Both Follow Same Pattern
```
SimulationSetup Agent          HPC Agent
══════════════════════         ═════════════════
src/simsetup/                  src/hpc/
├── topology_builder.py        ├── file_copy.py
├── ion_adder.py               ├── time_estimator.py
├── mdp_generator.py           ├── script_creator.py
├── solvator.py                ├── job_submitter.py
├── box_builder.py             ├── job_monitor.py
├── ... (15 tools total)       └── results_downloader.py
                                   (6 tools total)

agentic/simsetup/              agentic/hpc/
└── tools.py                   └── tools.py
    ├── Import from src/           ├── Import from src/
    ├── __all__ export             ├── __all__ export
    └── ToolExecutor class         └── HPCToolExecutor class
```

## Test Coverage

### Test Suite Results
```
Test 1: Import Tools                    ✅ PASS
Test 2: HPCToolExecutor Init            ✅ PASS
Test 3: Tool Signatures                 ✅ PASS
Test 4: Time Estimator Tool             ✅ PASS
Test 5: Modular Architecture            ✅ PASS
─────────────────────────────────────────────
Results: 5/5 passed (100%)
```

## Configuration Integration

### HPCToolExecutor with Config
```yaml
# config.yaml
ssh:
  host: sapelo2.gacrc.uga.edu
  user: akp66103
  key_path: ~/.ssh/id_rsa

paths:
  local_hpc_dir: working_dir/hpc
  remote_work_dir: /scratch/akp66103/md_runs
  local_download_dir: working_dir/results

slurm_defaults:
  partition: gpu_p
  cpus_per_task: 64
  memory: 40G
  time_limit: "2-00:00:00"
  gpu_count: 1
  gromacs_module: GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2
```

```python
# Executor enriches tool calls with config
executor = HPCToolExecutor(config)

# User only provides script_path
# Executor adds: remote_host, remote_user, ssh_key_path from config
result = executor.execute("submit_job", script_path="run.sh")
```

## Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Files** | 1 (tools.py) | 7 (modular) | Better organization |
| **Lines per file** | 850+ | 73-144 | Easier to read |
| **Testability** | Monolithic | Modular | Each tool testable |
| **Reusability** | Limited | High | Tools in src/ |
| **Consistency** | Different | Matches simsetup | Standard pattern |
| **Maintainability** | Hard | Easy | 1 file = 1 concern |

**Result**: Successfully transformed HPC agent tools to modular architecture! ✅
