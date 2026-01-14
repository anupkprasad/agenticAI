# AgenticAI — Enhanced LLM-Powered MD Workflow User Guide

This user guide explains the enhanced LLM-powered molecular dynamics workflow system, including architecture, usage, and advanced features.

## Overview

AgenticAI is an advanced molecular dynamics simulation workflow system that uses LLM-powered agents for intelligent orchestration and automated decision-making. The system can understand natural language requests and dynamically route tasks to specialized agents.

### Key Features

#### 🧠 **LLM-Powered Decision Making**
- Uses natural language understanding to interpret user goals
- Makes dynamic routing decisions based on current workflow state
- Provides detailed reasoning for all routing decisions

#### 🎯 **Intelligent Agent Routing**
- Automatically skips steps when user indicates they're already complete
- Routes to appropriate agents based on user intent and data readiness
- Handles complex scenarios like "PDB already preprocessed" or "analyze existing trajectories"

#### 🔄 **Multi-Turn Agent Communication**
- Enables supervisor to have conversations with agents
- Allows for clarification and parameter refinement
- Supports iterative problem-solving

#### 📋 **Configuration-Driven Agent Registry**
- YAML-based agent registry with capabilities and requirements
- Dynamic agent discovery and routing
- Extensible architecture for adding new agents

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Input    │───▶│  Input Validation │───▶│   Supervisor    │
│ (Natural Lang)  │    │   (LLM Analysis)  │    │ (LLM Routing)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
                        ┌───────────────────────────────┼───────────────────────────┐
                        │                               ▼                           │
              ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
              │ Preprocessing   │  │ Simulation      │  │ HPC Execution   │  │ Analysis        │
              │ Agent           │  │ Setup Agent     │  │ Agent           │  │ Agent           │
              └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
                        │                               │                           │
                        └───────────────────────────────┼───────────────────────────┘
                                                        ▼
                                               ┌─────────────────┐
                                               │  Final Report   │
                                               │ (LLM Generated) │
                                               └─────────────────┘
```

## Core Components

### 1. Enhanced MD Supervisor (`agentic/md_supervisor.py`)

The heart of the intelligent system that makes routing decisions:

```python
from agentic.md_supervisor import MDSupervisor

supervisor = MDSupervisor()  # Auto-detects LLM availability

# The supervisor analyzes user intent and routes accordingly
state = supervisor.supervisor_node(state)
```

**Key Methods:**
- `supervisor_node()`: Main routing logic with LLM reasoning
- `input_validation_node()`: LLM-powered input analysis and extraction
- `_llm_routing_decision()`: Core LLM decision-making
- Graceful fallback to heuristic routing when LLM unavailable

### 2. Enhanced MD Workflow (`agentic/md_workflow.py`)

Complete workflow orchestration with intelligent routing:

```python
from agentic.md_workflow import MDWorkflow

workflow = MDWorkflow()

result = workflow.run(
    user_goal="My PDB is already preprocessed, just run MD simulation"
)
```

### 3. Agent Registry Configuration

YAML-based configuration defines all available agents (`agentic/configs/intelligent_supervisor.yaml`):

```yaml
agents:
  preprocessing:
    name: "PDB Preprocessor"
    description: "Clean and prepare PDB files for simulation"
    capabilities: 
      - "remove_waters"
      - "fix_residues"
      - "add_hydrogens"
    input_requirements:
      - "raw_pdb"
    output_provides:
      - "cleaned_pdb"
    skip_conditions:
      - "pdb_already_cleaned"
      - "user_says_preprocessed"
```

## Installation

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. (Optional) Set up LLM server:
   - Install ollama or compatible LLM server
   - The system gracefully falls back to heuristic routing if LLM unavailable

## Usage

### Enhanced Workflow Examples

The enhanced system understands natural language and can intelligently skip steps based on user input:

#### 1. Skip Preprocessing (Already Clean PDB)

```bash
python run_md_workflow.py --goal "My PDB is already preprocessed, just set up simulation" --use-llm
```

**What happens:** LLM recognizes preprocessing is not needed and routes directly to simulation setup.

#### 2. Analysis Only

```bash
python run_md_workflow.py --goal "I have existing trajectories and want RMSD analysis" --use-llm
```

**What happens:** LLM skips preprocessing, setup, and HPC steps, routing directly to analysis.

#### 3. Full Pipeline

```bash
python run_md_workflow.py --goal "Run complete MD simulation from raw PDB" --pdb-path /path/to/protein.pdb --use-llm
```

**What happens:** LLM recognizes need for full pipeline and routes through all steps.

#### 4. Custom Parameters

```bash
python run_md_workflow.py \
  --goal "MD simulation with CHARMM force field and 20ns runtime" \
  --pdb-path /path/to/protein.pdb \
  --force-field charmm36 \
  --use-llm
```

### Programmatic Usage

```python
from agentic.md_workflow import MDWorkflow

# Create workflow instance
workflow = MDWorkflow()

# Run with natural language goal
result = workflow.run(
    user_goal="I need to analyze protein dynamics using existing simulation files",
    config={
        "trajectory_path": "/data/traj.xtc",
        "topology_path": "/data/system.tpr"
    }
)

# Check results
if result.get("workflow_complete"):
    print("Success!")
    print(result["final_report"])
else:
    print("Errors:", result.get("errors", []))
```

### Configuration

#### Agent Registry Configuration

Create or modify `agentic/configs/intelligent_supervisor.yaml`:

```yaml
supervisor:
  llm_config:
    model: "llama3:8b"
    system_prompt: "You are an expert MD workflow supervisor"
  conversation:
    log_all_interactions: true

workflow:
  default_pipeline: ["preprocessing", "setup", "hpc", "analysis"]
  entry_points: ["preprocessing", "analysis"]

agents:
  preprocessing:
    name: "PDB Preprocessor"
    capabilities: ["remove_waters", "fix_residues", "add_hydrogens"]
    skip_conditions: ["pdb_already_cleaned", "user_says_preprocessed"]
  # ... additional agents
```

## Benefits Over Heuristic System

| Feature | Before | After |
|---------|--------|--------|
| **Routing Logic** | Rule-based if/else | Natural language understanding |
| **Step Skipping** | Fixed workflow | Intelligent based on user input |
| **Input Processing** | Simple pattern matching | LLM-powered parameter extraction |
| **Error Handling** | Basic fallback | Intelligent troubleshooting suggestions |
| **Reasoning** | Hard-coded logic | Transparent LLM explanations |
| **Extensibility** | Hardcoded agents | Configuration-driven registry |

## Advanced Features

### Intelligent Routing Examples

The LLM supervisor can handle complex scenarios:

- **"PDB already preprocessed"** → Skips to simulation setup
- **"Analyze existing trajectories"** → Skips to analysis only  
- **"Only preprocess my protein"** → Stops after preprocessing
- **"My simulation keeps crashing"** → Routes to troubleshooting

### Backward Compatibility

The enhanced system maintains full backward compatibility:

```bash
# Old style usage still works
python run_md_workflow.py --pdb /path/to/protein.pdb --no-human-loop

# Enhanced usage with LLM
python run_md_workflow.py --goal "Natural language description" --use-llm
```

### Logging and Monitoring

All decisions and reasoning are logged:

```
2026-01-14 18:05:21 - LLM_SUPERVISOR_ROUTING: Skip preprocessing, user indicated PDB already clean
2026-01-14 18:05:22 - ROUTING_DECISION: input_validation → setup
2026-01-14 18:05:23 - LLM_REASONING: User indicated PDB is already preprocessed, skipping to simulation setup
```

## Project Structure

```
agenticAI/
├── agentic/                          # Core workflow system
│   ├── md_supervisor.py              # Enhanced LLM-powered supervisor
│   ├── md_workflow.py               # Enhanced LangGraph workflow
│   ├── md_state.py                  # Workflow state management
│   ├── llm.py                       # LLM client with fallback
│   ├── preprocessing_agent.py        # PDB preprocessing agent
│   ├── setup_agent.py              # Simulation setup agent
│   ├── human_checkpoints.py         # Human-in-the-loop checkpoints
│   ├── conversation_logger.py       # Conversation logging
│   ├── workflow_visualizer.py       # Workflow visualization
│   └── configs/                     # Configuration files
│       └── intelligent_supervisor.yaml
├── docs/
│   ├── USER_GUIDE.md               # This guide
│   └── workflow.md                 # Workflow documentation
├── examples/
│   └── enhanced_workflow_examples.py # Usage examples
├── tests/
│   └── test_enhanced_workflow.py   # Test suite
├── src/                            # Custom analysis tools
│   ├── python/                     # Python utilities
│   └── tcl/                        # VMD scripts
├── working_dir/                    # Simulation files
├── run_md_workflow.py             # Main CLI interface
├── requirements.txt               # Python dependencies
└── README.md                      # Project overview
```

## Migration from Previous Versions

The enhanced system maintains backward compatibility while adding LLM capabilities:

### What Changed
- ✅ **md_supervisor.py**: Enhanced with LLM-powered routing
- ✅ **md_workflow.py**: Added intelligent final reports  
- ✅ **Removed redundant files**: All "intelligent_*" files merged into existing ones
- ✅ **Clean architecture**: Single source of truth for each component

### What Stayed the Same
- ✅ **CLI interface**: `run_md_workflow.py` works exactly as before
- ✅ **Agent interfaces**: Existing agents work without changes
- ✅ **State management**: Same MDState structure
- ✅ **Configuration**: Existing configs still supported

## Troubleshooting

### LLM Not Available

System automatically falls back to heuristic routing:

```
Warning: LLM not available, using heuristic routing
```

### Invalid User Input

System provides helpful error messages:

```
Could not extract PDB path from user goal. Please specify a .pdb file path.
```

### Configuration Issues

Check YAML syntax and agent definitions:

```bash
python -c "import yaml; yaml.safe_load(open('agentic/configs/intelligent_supervisor.yaml'))"
```

## Summary

The enhanced AgenticAI system provides:

🧠 **Intelligent Understanding**: Natural language processing for complex user requests  
🎯 **Smart Routing**: Dynamic workflow decisions based on user intent  
🔄 **Adaptive Execution**: Automatic step skipping and error recovery  
📊 **Enhanced Reporting**: LLM-generated comprehensive workflow summaries  
🛡️ **Robust Fallback**: Graceful degradation to heuristic routing  
⚙️ **Easy Configuration**: YAML-based agent registry for extensibility

## CLI reference (important flags)

Global LLM & prompt flags (available for CLI subcommands):

- `--use-llm` — enable LLM-assisted mapping of natural-language prompts to actions.
- `--llm-base-url` — base URL of your local/tunneled LLM server (e.g. `http://localhost:11434`).
- `--llm-model` — model identifier used by the LLM server (e.g. `gpt-oss:120b`).
- `--prompt` — a natural-language instruction; when provided, the CLI will try to map it to one of the agent actions.
- `--llm-log` — path to append raw LLM responses (useful for debugging streamed NDJSON output).

Common subcommands: `setup`, `prepare-job`, `submit`, `download`, `analyze`.

See `scripts/run_agent.py` for the exact argument names and behaviors.

## LLM integration & tunneling

The project includes a small LLM wrapper `agentic/llm.py` that prefers a non-streaming Ollama-like endpoint `/api/generate` with `{"stream": false}`. If that endpoint is not available, it falls back to more generic chat endpoints and performs a tolerant assembly of streamed fragments.

If your LLM server runs on a remote host (for example: `ruili@172.22.149.139:11434`), create an SSH tunnel so the CLI can talk to it at `localhost:11434`.

### Handling streamed responses

Some LLM servers stream partial output as NDJSON fragments which the CLI logs to `--llm-log`. The wrapper tries to reassemble these fragments but for best results ask the model to return a single compact JSON object or use the non-streaming `/api/generate` endpoint.

## Safety and validation

- The project currently treats LLM outputs as suggestions. Do not run `submit` against production clusters until you implement validation and confirmation.
- Recommended next steps before using for real submissions:
  - Add schema validation (pydantic) for LLM-returned action+params and reject malformed outputs.
  - Require explicit confirmation for `submit` (interactive prompt) or provide a `--auto-approve` flag to skip confirmation.
  - Replace `HPCJobAgent` mocks with an SSH/SFTP implementation that supports private-key auth and dry-run mode.

## Logging & debugging

- Raw LLM responses (including streamed NDJSON) can be appended to a file via `--llm-log logs/llm_responses.log` for audit and debugging.
- The wrapper stores the last raw response in `LLMClient._last_raw_response` for programmatic inspection.

## Examples

1. Dry-run setup with LLM assistance (tunneled server):

```bash
# Start tunnel first, then:
python scripts/run_agent.py --use-llm --llm-base-url http://localhost:11434 --llm-model gpt-oss:120b --prompt "setup a simulation for ./em_wc.pdb" --llm-log logs/llm_responses.log
```

2. Non-LLM dry-run:

```bash
python scripts/run_agent.py setup --pdb ./em_wc.pdb
```

## Troubleshooting

- Module import errors when running `scripts/run_agent.py` directly: run it from the project root or ensure the project root is on `PYTHONPATH`. The script prepends the project root to `sys.path` when run directly.
- If the LLM returns many small JSON fragments, prefer `/api/generate` with `stream=false`, or inspect `logs/llm_responses.log` to see raw fragments.
- If `pytest` isn't found, install dev dependencies in your venv: `pip install pytest`.

## Contributing and next steps

If you want, I can:

- Add pydantic validation for LLM outputs and require interactive confirmation before `submit`.
- Implement a Paramiko-based `HPCJobAgent` with SFTP downloads and a dry-run mode.
- Add unit tests for the LLM non-streaming and streaming code paths.

Please tell me which of the above you'd like next and I will implement it.
