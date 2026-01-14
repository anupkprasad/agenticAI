# AgenticAI — Molecular Dynamics LangGraph Workflow

This repository provides a clean, LangGraph-based agentic AI system for molecular dynamics simulation workflows. The system uses a state-driven approach to orchestrate MD simulation preparation, execution planning, and analysis with human-in-the-loop capabilities.

## What's included

### Core LangGraph Architecture
- `agentic/md_workflow.py` — Main LangGraph StateGraph workflow orchestration
- `agentic/md_supervisor.py` — Finite-state controller for workflow routing
- `agentic/md_state.py` — Central state management with TypedDict
- `agentic/preprocessing_agent.py` — PDB preprocessing with LLM-powered planning
- `agentic/setup_agent.py` — Simulation system setup with adaptive protocols
- `agentic/human_checkpoints.py` — Human-in-the-loop intervention points
- `agentic/llm.py` — LLM client with mock mode for testing
- `run_md_workflow.py` — Clean command-line interface

### Custom Analysis Tools (Preserved)
- `src/python/analysis/` — Your MD analysis utilities and scripts
- `src/python/setup/` — Your simulation setup tools
- `src/python/utilities/` — Your utility functions
- `src/tcl/` — VMD TCL scripts for visualization
- `scripts/` — Directory for additional custom scripts

### Documentation & Configuration
- `requirements.txt` — Python dependencies including LangGraph
- `setup.py` — Package installation configuration
- `docs/` — User guides and workflow documentation

## Quick start

1. **Set up Python environment:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Run a basic workflow (test mode):**

```bash
python run_md_workflow.py --goal "I need to run an MD simulation of protein test.pdb in water with 150mM NaCl" --no-human-loop
```

3. **Run with LLM planning enabled:**

```bash
python run_md_workflow.py \
  --goal "Prepare MD simulation for my_protein.pdb with AMBER force field" \
  --use-llm \
  --llm-base-url http://localhost:11434
```

4. **Run with human checkpoints:**

```bash
python run_md_workflow.py \
  --goal "Setup MD simulation for complex_protein.pdb with custom protocols" \
  --use-llm
```

## LangGraph Architecture

The workflow uses a clean LangGraph StateGraph with the following nodes:

1. **Input Validation** — Extract PDB files and validate user goals
2. **Preprocessing** — Clean PDB structure, remove waters, fix residues
3. **Setup** — Generate topology, add solvent/ions, create MDP protocols
4. **Human Checkpoints** — Optional approval points for critical decisions
5. **Final Report** — Comprehensive workflow completion summary

### State Management

The workflow maintains a single `MDState` TypedDict containing:
- Input files and user goals
- Preprocessing results and cleaned structures
- Simulation setup parameters and generated files
- Execution logs and validation reports
- Error handling and human feedback

## Configuration Options

The workflow provides sensible GROMACS defaults:
- **Force Field**: AMBER99SB-ILDN
- **Water Model**: TIP3P  
- **Human-in-the-Loop**: Configurable checkpoints
- **Working Directory**: Automatically managed
- **Logging**: Structured workflow logs

## Command-Line Interface

```bash
python run_md_workflow.py [OPTIONS]

Required:
  --goal TEXT                 Natural language description of your MD simulation goal

Optional:
  --use-llm                   Enable LLM-powered planning (default: mock mode)
  --llm-model TEXT           LLM model name (default: llama3.1)
  --llm-base-url TEXT        LLM endpoint URL (default: http://localhost:11434)
  --no-human-loop           Disable human checkpoints for autonomous execution
  --force-field TEXT         Override default force field (default: amber99sb-ildn)
  --water-model TEXT         Override default water model (default: tip3p)
  --working-dir PATH         Specify working directory (default: current directory)
  --log-file PATH           Specify log file location (default: ./md_workflow.log)
```

## Integration with Your Custom Tools

The `src/` directory structure is preserved for your custom analysis and utility scripts:

- **`src/python/analysis/`** — Add your MD analysis tools here
- **`src/python/setup/`** — Add custom simulation setup utilities
- **`src/tcl/`** — VMD scripts and TCL utilities
- **`scripts/`** — Additional custom scripts and tools

The LangGraph workflow can be extended to call your custom tools by modifying the agent nodes.

## Next Steps

- **HPC Integration**: Extend with job submission and monitoring agents
- **Analysis Pipeline**: Add post-simulation analysis agents  
- **Custom Protocols**: Integrate your simulation setup tools from `src/`
- **Real LLM**: Connect to your preferred LLM endpoint for intelligent planning

## Documentation

- Full workflow guide: `docs/workflow.md`
- User manual: `docs/USER_GUIDE.md`

## License

Choose a license for your project.
