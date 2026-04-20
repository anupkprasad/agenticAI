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
- `agentic/hpc/` — HPC Agent: Job submission, monitoring, and downloads
- `agentic/analysis/` — Analysis Agent: MD trajectory analysis and reports
- `agentic/planner/` — Planner Agent: LLM-guided execution planning
- `agentic/programmer/` — Programmer Agent: Script generation
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
  --pdb-list PDB [PDB ...]  Multiple PDB files for multi-simulation mode
  --max-concurrent N         Max concurrent simulations in multi-sim mode (default: 4)
  --use-llm                   Enable LLM-powered planning (default: mock mode)
  --llm-model TEXT           LLM model name (default: gpt-oss:20b for HPC systems)
  --llm-base-url TEXT        LLM endpoint URL (default: http://127.0.0.1:11434)
  --no-human-loop           Disable human checkpoints for autonomous execution
  --force-field TEXT         Override default force field (default: amber99sb-ildn)
  --water-model TEXT         Override default water model (default: tip3p)
  --working-dir PATH         Specify working directory for all generated files
  --log-file PATH           Specify log file location (default: ./agent_conversation.log)
```

## Multi-Simulation Mode

Run multiple MD simulations in parallel from a single command. Each PDB gets its
own pipeline (preprocess → setup → hpc → analysis) in a separate directory. After
all simulations complete, a combined analysis generates comparative plots,
statistical summaries, cross-simulation PCA, and an LLM-generated report.

### Using --pdb-list

```bash
python run_agenticAIWork.py \
  --goal "Run 100 ns MD simulations at 310 K and analyse RMSD, RMSF, secondary structure" \
  --pdb-list protein_a.pdb protein_b.pdb protein_c.pdb \
  --working-dir multi_run \
  --use-llm --llm-base-url http://127.0.0.1:11434 \
  --no-human-loop --max-concurrent 4
```

### Auto-detection from --goal

If multiple PDB files are mentioned in the goal text, multi-sim mode activates
automatically:

```bash
python run_agenticAIWork.py \
  --goal "Simulate 1A.pdb, 2B.pdb, 3C.pdb for 50 ns and compare dynamics" \
  --working-dir multi_run \
  --use-llm --no-human-loop \
  --subtask preprocess simsetup hpcjob analysis reporter
```



python run_agenticAIWork.py \
  --goal "Simulation for 1A.pdb, 2B.pdb, 3C.pdb is already done for 50 ns and data is stored in the 1A, 2B and 3C repectively. Please do the analysis of trajectories and compare dynamics among them" \
  --working-dir multi_run \
  --use-llm --no-human-loop \
  --subtask analysis reporter


### Directory structure

```
multi_run/
├── protein_a/          # Per-simulation pipeline
│   ├── preprocess/
│   ├── simsetup/
│   ├── hpc/
│   ├── analysis/
│   ├── reporter/
│   └── supervisor/
├── protein_b/
│   └── ...
├── protein_c/
│   └── ...
├── combinedAnalysis/   # Cross-simulation analysis
│   ├── comparative_rmsd.png
│   ├── comparative_rmsf.png
│   ├── cross_sim_pca.png
│   ├── statistical_summary.json
│   └── combined_analysis_report.md
└── multi_sim_status.md
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

# 4. IMPORTANT: Prevent bytecode cache issues on NFS
export PYTHONDONTWRITEBYTECODE=1

# 5. Run AgenticAI workflow with LLM
python run_agenticAIWork.py \
  --goal "I want to preprocess and simulation setup of protein only. The protein is availble in the pdb file of work_di/2_h.pdb. Please setup simulation for 15 ns only. Once the simulation setup is done then please submit simulation job on HPC. Please do not do simulation analysis." \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --working-dir working_dir \
  --no-human-loop

# Alternative: Use a local environment to avoid NFS issues
# bash quick_setup_local.sh
# source /tmp/agenticai_local/bin/activate
# python run_agenticAIWork.py --goal "..." --use-llm --llm-base-url http://127.0.0.1:11434 --no-human-loop


python run_agenticAIWork.py \
  --goal "I want to preprocess and simulation setup of protein-ATP-Mg system. The structure is availble in the pdb file of work_dir_hl/2_h.pdb. Please setup simulation for 12 ns only. Once the simulation setup is done, please submit the job on HPC" \
  --subtask preprocess simsetup hpcjob \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --working-dir work_dir_hl \
  --no-human-loop


python run_agenticAIWork.py \
  --goal "The simulation setup is already done for the protein-ATP-Mg system. The structure was taken from the pdb file of work_dir_hl2/2_h.pdb. The production of simulation is 12 ns only. Please submit the job on HPC" \
  --subtask hpcjob \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --working-dir work_dir_hl2 \
  --no-human-loop



# 5.2. Run analysis-only workflow (trajectory in working_dir/hpc/)
python run_agenticAIWork.py \
  --goal "The protein availble in the pdb file of working_dir/3.pdb, was used for the simulation. The simulation production is already done and data output is stored in working_dir/hpc. Please dont preprocess, do not setup simulation and do not job submit the simulation. Only use the analysis agent to analyze and plot the center of mass of protein in 3D plot of simulation trajectory. The trajectory file is md.xtc and topology file is md.gro after analyis please use the reporter agent to make simulaiton report" \
  --subtask analysis \
  --working-dir working_dir \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --no-human-loop

# 5.2b. Run analysis + reporter together (multi-agent pipeline)
# Multiple agents are run in order: analysis first, then reporter
python run_agenticAIWork.py \
  --goal "The simulation of initial structure 2_h.pdb is already done. Simulation trajectory is in work_di_hl/hpc/. Please analyse the trajectory to calculate RMSD, RMSF, COM and secondary structure for protein only and plot those data. There is also ligand ATP, please calculate and plot the distance the center of mass of ATP to COM of protein. Once the analysis is finised then generate a scientific report by reporter agent. The given protein is human psedukinase JAK1, please find the kinase and pseudokinase related literatures that correlate dynamics. Based on literature and results make comments on in report" \
  --subtask analysis reporter \
  --working-dir work_dir_hl \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --no-human-loop

# 5.3. Run analysis-only workflow (trajectory in working_dir/hpc/)
python run_agenticAIWork.py \
  --goal "The kinase protein availble in the pdb file of working_dir/3.pdb, was used for the simulation. The simulation production and analysis is already done and data output is stored in working_dir/analysis. Please dont preprocess, do not setup simulation and do simulation analysis. Only use the reporter agent to report comprehensive results, the result summary file is analysis_summary.jsonl in working_dir/analysis/. I want to know what are the flexible region of kinase, what secondory structure most in protien wheater this kinase can do catalysis or not" \
  --subtask reporter \
  --working-dir working_dir \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --no-human-loop



# 5.4
python run_agenticAIWork.py \
  --goal "The protein availble in the pdb file of working_dir/3.pdb. Please preprocess the pdb file. Please do not setup, submit and analyisis the simulation" \
  --subtask preprocess \
  --working-dir working_dir \
  --use-llm \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b \
  --no-human-loop


# Analysis agent will:
# - Read trajectory/topology from: working_dir/hpc/
# - Write analysis results to: working_dir/analysis/

# Alternative: Use a local environment to avoid NFS issues
# bash quick_setup_local.sh
# source /tmp/agenticai_local/bin/activate
# python run_agenticAIWork.py --goal "..." --use-llm --llm-base-url http://127.0.0.1:11434 --no-human-loop

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
