# HPC Tools Modular Architecture

## Overview
The HPC agent tools have been refactored to follow the same modular pattern as the SimulationSetup agent. This improves code reusability, testability, and maintainability.

## Architecture Pattern

### Before Refactoring
```
agentic/hpc/tools.py (850+ lines)
├── All 6 tools defined directly with @tool decorator
├── Monolithic structure
└── No separation of concerns
```

### After Refactoring
```
src/hpc/                          # Stable, reusable tools
├── file_copy.py                  # @tool: copy_simulation_files
├── time_estimator.py             # @tool: estimate_simulation_time
├── script_creator.py             # @tool: create_slurm_script
├── job_submitter.py              # @tool: submit_job
├── job_monitor.py                # @tool: check_job_status
├── results_downloader.py         # @tool: download_results
└── slurm_script_generator.py    # Original script generator

agentic/hpc/tools.py              # Thin wrapper
├── Import tools from src/hpc/*
├── Export via __all__
└── HPCToolExecutor class
```

## Tool Inventory

### 1. File Copy Tool (`src/hpc/file_copy.py`)
**Function**: `copy_simulation_files`
- Copy simulation files from setup directory to HPC working directory
- Default patterns: `*.gro`, `*.top`, `*.mdp`, `*.itp`
- Creates destination directory if needed
- Returns list of copied files with sizes

### 2. Time Estimator (`src/hpc/time_estimator.py`)
**Function**: `estimate_simulation_time`
- Estimate walltime based on system size and simulation length
- Uses rule of thumb: ~1 ns/day for 50k atoms on GPU
- Calculates total MD steps
- Returns SLURM time format (days-hours:min:sec)
- Includes buffer for equilibration and minimization

### 3. Script Creator (`src/hpc/script_creator.py`)
**Function**: `create_slurm_script`
- Wrapper for `slurm_script_generator.py`
- Creates SLURM submission scripts for GROMACS
- Supports 4-phase workflow: minim → NVT → NPT → MD
- GPU acceleration support
- SBATCH directives (partition, CPUs, memory, time limit)

### 4. Job Submitter (`src/hpc/job_submitter.py`)
**Function**: `submit_job`
- Submit SLURM jobs locally or remotely via SSH
- Local: uses `sbatch` command
- Remote: uses paramiko for SSH submission
- Parses job ID from submission output
- Returns job status and ID

### 5. Job Monitor (`src/hpc/job_monitor.py`)
**Function**: `check_job_status`
- Check SLURM job status via `squeue` or SSH
- Falls back to `sacct` for completed jobs
- Returns status: RUNNING, PENDING, COMPLETED, FAILED, etc.
- Includes elapsed time information

### 6. Results Downloader (`src/hpc/results_downloader.py`)
**Function**: `download_results`
- Download simulation results from HPC via SFTP
- Default patterns: `*.xtc`, `*.gro`, `*.edr`, `*.log`, `*.cpt`, `*.xvg`
- Creates local download directory
- Returns list of downloaded files with sizes

## HPCToolExecutor Class

Similar to `SimulationSetupToolExecutor`, provides:

### Features
- **Unified interface** for tool execution
- **Configuration management** with config enrichment
- **Error handling** with consistent result format
- **Parameter enrichment** from config.yaml

### Usage Example
```python
from agentic.hpc.tools import HPCToolExecutor

# Initialize with config
config = {
    "ssh": {
        "host": "sapelo2.gacrc.uga.edu",
        "user": "akp66103",
        "key_path": "~/.ssh/id_rsa"
    },
    "paths": {
        "local_hpc_dir": "working_dir/hpc",
        "local_download_dir": "working_dir/results"
    },
    "slurm_defaults": {
        "partition": "gpu_p",
        "cpus_per_task": 64,
        "memory": "40G",
        "gpu_count": 1
    }
}

executor = HPCToolExecutor(config)

# Execute tool - SSH params auto-filled from config
result = executor.execute("submit_job", script_path="working_dir/hpc/run.sh")
```

### Parameter Enrichment
The executor automatically enriches tool parameters with config defaults:

- **SSH tools** (`submit_job`, `check_job_status`, `download_results`):
  - `remote_host` from `config.ssh.host`
  - `remote_user` from `config.ssh.user`
  - `ssh_key_path` from `config.ssh.key_path`

- **File operations** (`copy_simulation_files`, `download_results`):
  - `dest_dir` from `config.paths.local_hpc_dir`
  - `local_dir` from `config.paths.local_download_dir`

- **SLURM script** (`create_slurm_script`):
  - All SBATCH parameters from `config.slurm_defaults`

## Benefits of Modular Architecture

### 1. **Reusability**
- Tools can be imported and used in other contexts
- Example: Use `estimate_simulation_time` in analysis scripts
- Example: Use `download_results` in standalone downloader

### 2. **Testability**
- Each tool can be unit tested independently
- Mock SSH connections for job submission tests
- Test time estimation with different system sizes

### 3. **Maintainability**
- Clear separation of concerns (1 file = 1 tool)
- Easier to locate and modify specific functionality
- Reduced file size (from 850+ lines to <150 lines each)

### 4. **Extensibility**
- Add new tools by creating new files in `src/hpc/`
- Import in `agentic/hpc/tools.py`
- Add to `HPCToolExecutor.tools` dict

### 5. **Consistency**
- Follows same pattern as `simsetup` agent
- Developers familiar with one agent understand the other
- Standardized tool result format

## Integration with HPC Agent

The HPC agent (`agentic/hpc/hpc_agent.py`) imports from `agentic/hpc/tools.py`:

```python
from .tools import (
    copy_simulation_files,
    estimate_simulation_time,
    create_slurm_script,
    submit_job,
    check_job_status,
    download_results
)
```

No changes required to `hpc_agent.py` - imports remain the same!

## Comparison with SimulationSetup Agent

| Aspect | SimulationSetup Agent | HPC Agent |
|--------|----------------------|-----------|
| Tool Location | `src/simsetup/*.py` | `src/hpc/*.py` |
| Wrapper | `agentic/simsetup/tools.py` | `agentic/hpc/tools.py` |
| Executor | `SimulationSetupToolExecutor` | `HPCToolExecutor` |
| Tool Count | 15 tools | 6 tools |
| Pattern | @tool decorator, imports | @tool decorator, imports |

## Migration Notes

### What Changed
- Tools moved from `agentic/hpc/tools.py` to `src/hpc/*.py`
- Each tool now in separate file
- `@tool` decorators preserved
- HPCToolExecutor class added

### What Stayed the Same
- Tool signatures (parameters and return types)
- Import statements in `hpc_agent.py`
- Tool functionality and behavior
- Configuration structure in `config.yaml`

### Backward Compatibility
✅ Full backward compatibility maintained
- All imports work the same
- Tool invocations unchanged
- Config format unchanged

## Future Enhancements

### Potential New Tools
1. **Job Cancellation**: `cancel_job(job_id)` - Cancel running/pending jobs
2. **Disk Usage Monitor**: `check_disk_usage(remote_dir)` - Monitor space usage
3. **Log Analyzer**: `analyze_job_logs(job_id)` - Parse errors from log files
4. **Checkpoint Manager**: `manage_checkpoints(job_id)` - Restart from checkpoints
5. **Queue Inspector**: `inspect_queue(partition)` - Get partition status

### Enhancement Ideas
- Add retry logic to download_results for failed transfers
- Support for alternative job schedulers (PBS, LSF)
- Compression of large trajectory files before download
- Real-time log streaming via SSH
- Job dependency management for multi-stage workflows

## Related Files

### Documentation
- `docs/HPC_AGENT_UPDATE.md` - Original HPC agent overhaul documentation
- `docs/REMOTE_VISUALIZATION_GUIDE.md` - Remote visualization guide
- `.github/copilot-instructions.md` - Project architecture overview

### Configuration
- `agentic/hpc/config.yaml` - HPC agent configuration
- `agentic/hpc/schemas.py` - Pydantic validation schemas

### Agent Files
- `agentic/hpc/hpc_agent.py` - Main HPC agent orchestrator
- `agentic/hpc/tools.py` - Tool wrapper (this refactoring)
- `src/hpc/slurm_script_generator.py` - SLURM script generation

## Summary

This refactoring achieves:
- ✅ Modular architecture matching `simsetup` agent
- ✅ Stable, reusable tools in `src/hpc/`
- ✅ Thin wrapper in `agentic/hpc/tools.py`
- ✅ HPCToolExecutor for unified tool execution
- ✅ Full backward compatibility
- ✅ Improved maintainability and testability
- ✅ Consistent project structure

The HPC agent now follows best practices for tool organization while maintaining all existing functionality.
