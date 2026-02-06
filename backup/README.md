# Backup Directory

This directory contains legacy and backup files from the project reorganization.

## Files

### Supervisor Reorganization (2026-02-06)
- **supervisor_old.py.bak** - Original monolithic supervisor.py before modular refactoring
- **config_supervisor.yaml.bak** - Original supervisor config before moving to supervisor/ module

### Unused Config Files (Legacy)
These config files were in `agentic/configs/` but are no longer used by the current codebase:

- **intelligent_supervisor.yaml** - Legacy agent registry (now integrated into supervisor/config.yaml)
- **error_handling.yaml** - Legacy error handling config (never implemented in code)
- **workflow_orchestration.yaml** - Legacy workflow config (never implemented in code)

## Notes

The current active configuration is now in:
- `agentic/supervisor/config.yaml` - Active supervisor and agent configuration

These files are kept for reference only and are not loaded by the application.
