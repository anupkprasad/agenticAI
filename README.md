# AgenticAI — Enhanced LLM-Powered MD Workflow

This repository provides an advanced, LLM-powered agentic AI system for molecular dynamics simulation workflows. The system uses intelligent reasoning to understand complex user requests and dynamically orchestrate MD simulation preparation, execution, and analysis with human-in-the-loop capabilities.

## 🚀 Enhanced Features

### 🧠 **LLM-Powered Supervisor**
- **Natural Language Understanding**: Interprets complex requests like "PDB already preprocessed" or "analyze existing trajectories"
- **Intelligent Routing**: Makes dynamic decisions about which agents to call and when to skip steps
- **Reasoning Transparency**: Provides clear explanations for all routing decisions
- **Fallback Compatibility**: Gracefully falls back to heuristic routing when LLM unavailable

### 🎯 **Smart Workflow Orchestration** 
- **Automatic Step Skipping**: Skips preprocessing if user indicates data is already clean
- **Context-Aware Routing**: Routes based on user intent, current state, and agent capabilities
- **Enhanced Error Handling**: Intelligent troubleshooting and recovery suggestions
- **Configuration-Driven**: YAML-based agent registry for easy extensibility

## What's included

### Enhanced Workflow Features

#### **🧠 LLM-Powered Supervisor (`agentic/supervisor.py`)**
- **Natural Language Understanding**: Interprets complex requests like "PDB already preprocessed"
- **Intelligent Routing**: Dynamic decisions about which agents to call and when to skip steps  
- **Enhanced Input Validation**: Extracts PDB paths, parameters, and requirements from natural language
- **Reasoning Transparency**: Clear explanations for all routing decisions
- **Fallback Compatibility**: Graceful fallback to heuristic routing when LLM unavailable

#### **🎯 Smart Workflow Orchestration (`agentic/workflow.py`)**
- **Automatic Step Skipping**: Skips preprocessing if user indicates data is already clean
- **Context-Aware Routing**: Routes based on user intent, current state, and agent capabilities
- **Enhanced Final Reports**: LLM-generated comprehensive workflow summaries
- **Configuration-Driven**: YAML-based agent registry for easy extensibility

## Key Enhancements Made

✅ **Reorganized agentic package with agent-specific directories**  
✅ **Renamed core modules: `md_state.py` → `state.py`, `md_supervisor.py` → `supervisor.py`, `md_workflow.py` → `workflow.py`**  
✅ **Created utils package for shared utilities (logging, visualization)**  
✅ **Centralized configuration in `run_agenticAIWork.py` main entry point**  
✅ **LLM-powered routing with heuristic fallback**  
✅ **Enhanced input validation and parameter extraction**  
✅ **Comprehensive logging and reasoning transparency**  
✅ **Configuration-driven agent registry**

### Agent Framework (Modular Design)
- `agentic/preprocess/` — Preprocessing Agent: PDB cleaning, water removal, hydrogen addition
- `agentic/simsetup/` — Setup Agent: Topology and MDP file generation
- `agentic/hpc/` — HPC Agent: Job submission and remote execution (stub)
- `agentic/analysis/` — Analysis Agent: MD trajectory analysis (stub)
- `agentic/utils/` — Shared utilities: logging, visualization, helper functions

### Custom Analysis Tools
- `src/python/analysis/` — MD analysis utilities (RMSD, motif analysis, charge calculations)
- `src/python/setup/` — Simulation setup tools
- `src/python/utilities/` — Protein utilities and helper functions
- `src/tcl/` — VMD TCL scripts for visualization

### Main Entry Point
- `run_agenticAIWork.py` — Main CLI interface for executing workflows

### Documentation & Configuration
- `requirements.txt` — Python dependencies including LangGraph
- `setup.py` — Package installation configuration
- `docs/` — User guides and workflow documentation
- `.github/copilot-instructions.md` — AI assistant development guidelines

## Quick start

1. **Set up Python environment:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Run a basic workflow (test mode):**

```bash
python run_agenticAIWork.py --goal "I need to run an MD simulation of protein my_project/protein.pdb in water with 150mM NaCl" --no-human-loop --working-dir /path/to/my_project
```

3. **Run with LLM planning enabled (with Ollama server):**

```bash
# First, make sure Ollama server is running with a model (e.g., on HPC)
# Example HPC setup with SLURM:
srun --jobid=YOUR_JOB_ID --pty bash
conda activate ~/conda_envs/ollama_env/
# Then run the workflow with LLM
python run_agenticAIWork.py \
  --goal "Prepare MD simulation for ATP.pdb with AMBER force field in working_dir/ATP.pdb/" \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --working-dir working_dir/ATP.pdb/
```

4. **Run with human checkpoints:**

```bash
python run_agenticAIWork.py \
  --goal "Setup MD simulation for complex_protein.pdb in /scratch/md_work/" \
  --use-llm \
  --working-dir /scratch/md_work
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
python run_agenticAIWork.py [OPTIONS]

Required:
  --goal TEXT                 Natural language description of your MD simulation goal

Optional:
  --use-llm                   Enable LLM-powered planning (default: mock mode)
  --llm-model TEXT           LLM model name (default: gpt-oss:20b for HPC systems)
  --llm-base-url TEXT        LLM endpoint URL (default: http://127.0.0.1:11434)
  --no-human-loop           Disable human checkpoints for autonomous execution
  --force-field TEXT         Override default force field (default: amber99sb-ildn)
  --water-model TEXT         Override default water model (default: tip3p)
  --working-dir PATH         Specify working directory for all generated files
  --log-file PATH           Specify log file location (default: ./agent_conversation.log)
```

## HPC Integration with Ollama

For HPC systems with GPU access and Ollama server:

```bash
# 1. Connect to HPC and request GPU resources
srun --jobid=YOUR_JOB_ID --pty bash

# 2. Activate environment with Ollama
conda activate ~/conda_envs/ollama_env/

# 3. Verify Ollama server and available models
curl -s http://127.0.0.1:11434/api/tags

# 4. Run AgenticAI workflow with LLM
python run_agenticAIWork.py \
  --goal "MD simulation for protein.pdb in project directory" \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --working-dir /path/to/project/directory
```

## Integration with Your Custom Tools

The `src/` directory structure is organized for different workflow stages:

- **`src/preprocess/`** — Add PDB preprocessing and ligand tools here
- **`src/simsetup/`** — Add custom simulation setup utilities  
- **`src/hpc/`** — Add HPC job management and monitoring tools
- **`src/analysis/`** — Add post-simulation analysis tools
- **`src/python/analysis/`** — Your existing MD analysis tools
- **`src/python/setup/`** — Your existing simulation setup utilities
- **`src/tcl/`** — VMD scripts and TCL utilities

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
