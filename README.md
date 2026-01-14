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

#### **🧠 LLM-Powered Supervisor (`md_supervisor.py`)**
- **Natural Language Understanding**: Interprets complex requests like "PDB already preprocessed"
- **Intelligent Routing**: Dynamic decisions about which agents to call and when to skip steps  
- **Enhanced Input Validation**: Extracts PDB paths, parameters, and requirements from natural language
- **Reasoning Transparency**: Clear explanations for all routing decisions
- **Fallback Compatibility**: Graceful fallback to heuristic routing when LLM unavailable

#### **🎯 Smart Workflow Orchestration (`md_workflow.py`)**
- **Automatic Step Skipping**: Skips preprocessing if user indicates data is already clean
- **Context-Aware Routing**: Routes based on user intent, current state, and agent capabilities
- **Enhanced Final Reports**: LLM-generated comprehensive workflow summaries
- **Configuration-Driven**: YAML-based agent registry for easy extensibility

## Key Enhancements Made

✅ **Merged intelligent features into existing `md_supervisor.py` and `md_workflow.py`**  
✅ **Maintained original naming convention (removed "intelligent" prefixes)**  
✅ **Backward compatibility with existing workflow interface**  
✅ **LLM-powered routing with heuristic fallback**  
✅ **Enhanced input validation and parameter extraction**  
✅ **Comprehensive logging and reasoning transparency**  
✅ **Configuration-driven agent registry**

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
