# AgenticAI - LLM-Powered Molecular Dynamics Workflow

This is an agentic AI system for molecular dynamics (MD) simulation workflows that uses LLM reasoning for intelligent task orchestration and human-in-the-loop decision making.

## Architecture Overview

The system uses a **LangGraph StateGraph** architecture with these key components:

- **MDSupervisor** ([agentic/md_supervisor.py](agentic/md_supervisor.py)) - LLM-powered routing and decision making
- **MDWorkflow** ([agentic/md_workflow.py](agentic/md_workflow.py)) - Main workflow orchestration
- **MDState** ([agentic/md_state.py](agentic/md_state.py)) - Central state management using TypedDict
- **LLMClient** ([agentic/llm.py](agentic/llm.py)) - Ollama/HTTP client wrapper with graceful fallbacks

### Workflow Pipeline

1. **Input Validation** → Extract PDB paths and validate user goals
2. **Supervisor Routing** → LLM-powered intelligent agent selection
3. **Agent Execution** → Preprocessing, Setup, HPC submission, Analysis
4. **Human Checkpoints** → Optional approval gates with feedback handling
5. **Final Report** → LLM-generated comprehensive summaries

## Key Patterns & Conventions

### State Management
- All workflow state flows through `MDState` TypedDict
- State fields follow naming pattern: `{stage}_{artifact}` (e.g., `cleaned_pdb`, `setup_report`)
- Control flow via `next_node` field for LangGraph routing
- Use `errors` and `warnings` lists for issue tracking

### LLM Integration
- LLM calls use structured prompts with explicit output format requirements
- Always include fallback logic for when LLM is unavailable 
- Mock mode available for testing (`_is_mock_mode` flag)
- Configuration via [agentic/configs/intelligent_supervisor.yaml](agentic/configs/intelligent_supervisor.yaml)

### Agent Registry Pattern
```yaml
agents:
  agent_name:
    capabilities: ["specific_actions"]
    input_requirements: ["required_inputs"]  
    output_provides: ["generated_outputs"]
    skip_conditions: ["when_to_skip"]
```

## Development Workflows

### Running the Workflow
```bash
# Basic test mode
python run_agenticAIWork.py --goal "Run MD simulation of test.pdb" --no-human-loop

# With LLM routing
python run_agenticAIWork.py --goal "My PDB is preprocessed" --use-llm --llm-base-url http://localhost:11434

# With human checkpoints
python run_agenticAIWork.py --goal "Complex simulation setup" --use-llm
```

### Testing
- Tests in [tests/test_enhanced_workflow.py](tests/test_enhanced_workflow.py)
- Mock LLM client for unit testing
- Test both LLM-enabled and fallback modes

### HPC Environment
- Uses SLURM job scripts ([ollama_server.sh](ollama_server.sh), [run_topology.sh](run_topology.sh))
- Singularity containers for reproducible environments
- GPU support for LLM inference

## Project-Specific Details

### File Organization
- `agentic/` - Core workflow engine
- `src/python/analysis/` - MD analysis tools (motif analysis, charge volume calculations)
- `src/tcl/` - VMD visualization scripts  
- `working_dir/` - Runtime workspace for file processing
- `docs/` - User guides and workflow documentation

### MD-Specific Conventions
- Default to GROMACS engine with AMBER99SB-ILDN force field
- TIP3P water model standard
- PDB preprocessing includes water removal, residue fixing, hydrogen addition
- Topology files use `.top` extension, coordinates use `.gro`

### Error Handling
- Graceful degradation when external dependencies unavailable
- Human-in-the-loop for critical decision points  
- Detailed logging via `conversation_logger.py`
- Mock responses for offline development

### Extension Points
- Add new agents by updating YAML registry
- Implement `{agent_name}_node()` methods in agent classes
- Follow LangGraph conditional routing patterns for new workflow branches
- Use `working_directory` state field for file operations

### Integration Notes
- Ollama server runs on HPC nodes with GPU allocation
- HTTP client handles both local and remote LLM endpoints
- Paramiko for SSH/remote execution
- Bio.PDB and MDAnalysis for molecular data processing

When modifying this codebase, maintain the LLM-powered routing paradigm while preserving fallback compatibility for non-LLM environments.