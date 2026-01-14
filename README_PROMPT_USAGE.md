# LangGraph MD Workflow Usage Guide

This project uses a clean LangGraph-based workflow for molecular dynamics simulation preparation. The system uses natural language goals to orchestrate preprocessing, setup, and simulation planning with optional human-in-the-loop checkpoints.

## Core Command Interface

The main entry point is `run_md_workflow.py`, which takes natural language goals and executes a state-driven LangGraph workflow.

### Prerequisites

- Run from the project root directory
- Activate the virtual environment:

```bash
source .venv/bin/activate
```

### Essential Flags

- `--goal` : (required) Natural language description of your MD simulation
- `--use-llm` : Enable LLM-powered intelligent planning
- `--llm-base-url` : LLM endpoint URL (e.g., `http://localhost:11434`)
- `--llm-model` : LLM model name (default: `llama3.1`)
- `--no-human-loop` : Disable human checkpoints for autonomous execution
- `--force-field` : Override force field (default: `amber99sb-ildn`)
- `--water-model` : Override water model (default: `tip3p`)
- `--working-dir` : Specify working directory
- `--log-file` : Specify log file location

## Common Usage Examples

### 1. Basic Test Run (Mock Mode)

Test the workflow without LLM using built-in mock responses:

```bash
python run_md_workflow.py \
  --goal "I need to run an MD simulation of protein my_protein.pdb in water with 150mM NaCl" \
  --no-human-loop
```

### 2. LLM-Powered Workflow

Use LLM for intelligent preprocessing and setup planning:

```bash
python run_md_workflow.py \
  --goal "Prepare MD simulation for membrane_protein.pdb in POPC lipid bilayer" \
  --use-llm \
  --llm-base-url http://localhost:11434
```

### 3. Interactive with Human Checkpoints

Run with human approval at critical decision points:

```bash
python run_md_workflow.py \
  --goal "Setup complex MD simulation for protein_complex.pdb with custom force field" \
  --use-llm \
  --llm-base-url http://localhost:11434
```

### 4. Custom Configuration

Override defaults for specific simulation requirements:

```bash
python run_md_workflow.py \
  --goal "MD simulation of DNA-protein complex in 100mM KCl solution" \
  --use-llm \
  --force-field amber14sb \
  --water-model tip4pew \
  --working-dir ./dna_simulations
```

### 5. Batch Processing Example

Process multiple PDB files in a directory:

```bash
for pdb in /path/to/pdbs/*.pdb; do
  python run_md_workflow.py \
    --goal "Prepare MD simulation for $(basename $pdb) in water with physiological salt" \
    --use-llm \
    --no-human-loop \
    --working-dir "./sims/$(basename $pdb .pdb)"
done
```

## Workflow Stages

The LangGraph workflow progresses through these stages:

1. **Input Validation** — Extract PDB file references from natural language goal
2. **Preprocessing** — Clean PDB structure using LLM-generated adaptive plans
3. **Setup** — Generate simulation system with protocols based on LLM analysis
4. **Human Checkpoints** — Optional approval for preprocessing/setup decisions
5. **Final Report** — Comprehensive summary of generated files and next steps

## Human-in-the-Loop Interactions

When human checkpoints are enabled, you'll be prompted at key decision points:

```
Human Checkpoint: Preprocessing Review
=====================================
The preprocessing agent has analyzed your PDB and suggests:
- Removing 150 water molecules
- Adding missing hydrogen atoms
- Fixing 2 non-standard residues

Options:
- approve: Continue with current plan
- retry: Rerun preprocessing with different parameters  
- modify: Provide specific modifications

Your choice [approve/retry/modify]: approve
```

## State Management

The workflow maintains a comprehensive state including:
- **Input**: Original PDB files and user goals
- **Preprocessing**: Cleaned structures, topology files, processing logs
- **Setup**: System coordinates, MDP protocols, simulation parameters
- **Validation**: Error reports, warnings, human feedback
- **Output**: File paths, execution logs, completion status

## Output Files

The workflow generates standard GROMACS files:
- `processed.gro` — Cleaned and processed structure
- `topol.top` — Molecular topology
- `*.mdp` — Simulation parameter files (minimization, NVT, NPT, production)
- `system.gro` — Final solvated system coordinates

## Integration with Custom Tools

The workflow can be extended to use your custom tools in `src/`:

- **Analysis Tools**: `src/python/analysis/` — Your MD analysis scripts
- **Setup Utilities**: `src/python/setup/` — Custom simulation preparation tools
- **TCL Scripts**: `src/tcl/` — VMD visualization and analysis scripts

## Error Handling

The workflow provides comprehensive error handling:
- **Validation Errors**: Missing files, invalid PDB structures
- **Processing Errors**: Failed preprocessing or setup steps
- **LLM Errors**: Fallback to mock mode if LLM unavailable
- **Human Override**: Ability to modify or retry failed steps

## Logging and Debugging

Detailed logs are saved to `md_workflow.log` (or specified file):
- Workflow progression and routing decisions
- LLM interactions and generated plans
- File operations and validations
- Error messages and warnings

## Troubleshooting

### LLM Connection Issues
If LLM is unavailable, the system automatically falls back to mock mode:
```
2026-01-13 14:22:09,405 - agentic.llm - INFO - ChatOllama client not available; LLMClient will run in mock mode
```

### File Path Issues
Ensure PDB files are accessible and use absolute paths in goals:
```bash
python run_md_workflow.py \
  --goal "Prepare simulation for /full/path/to/protein.pdb in water"
```

### Permission Issues
Make sure the working directory is writable:
```bash
chmod 755 /path/to/working/directory
```

## Advanced Usage

### Custom LLM Endpoints
```bash
# Local Ollama
python run_md_workflow.py --goal "..." --llm-base-url http://localhost:11434

# Remote LLM service
python run_md_workflow.py --goal "..." --llm-base-url https://api.example.com/v1

# Different model
python run_md_workflow.py --goal "..." --llm-model codellama:13b
```

### Development and Testing
```bash
# Test workflow logic without LLM
python run_md_workflow.py --goal "test simulation" --no-human-loop

# Debug with verbose logging
python run_md_workflow.py --goal "..." --use-llm --log-file debug.log
```

This LangGraph-based approach provides a clean, extensible framework for MD simulation workflows with intelligent planning and human oversight capabilities.
