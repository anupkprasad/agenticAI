# AgenticAI — Molecular Dynamics agentic workflow

This repository is an agentic AI system (using LangGraph-style agents) to prepare, submit/retrieve (on HPC) and analyze molecular dynamics simulations.

What's included
- `agentic/agents.py` — minimal agent classes and integration points for LangGraph.
- `config/config.yaml` — example configuration for HPC credentials and simulation defaults.
- `agentic/hpc/slurm_template.sh` — sample SLURM script template.
- `scripts/run_agent.py` — small CLI to exercise agents locally (no real HPC calls by default).
- `requirements.txt` — minimal Python dependencies to get started.
- `tests/test_agents.py` — small pytest test to validate the skeleton.

Quick start

1. Create a Python virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Edit `config/config.yaml` with your HPC credentials and desired defaults.

3. Run the local CLI to see a dry run:

```bash
python scripts/run_agent.py setup --pdb example.pdb
python scripts/run_agent.py prepare-job --out job.sh
python scripts/run_agent.py analyze --data results/
```

Integration with LangGraph

The `agentic/agents.py` file contains clear placeholders and a `create_langgraph_agent` hook where you can instantiate real LangGraph agents and attach them to the classes. The current code is intentionally minimal and safe to run locally without an LLM.

Next steps
- Replace placeholders in agent methods with real logic to call MD tools (GROMACS, NAMD, OpenMM).
- Implement secure job submission using SSH/SFTP (the `HPCJobAgent` includes starting points).
- Swap the placeholder LangGraph integration with the actual LangGraph SDK (update `requirements.txt` as needed).

Documentation
- Full user manual: `docs/USER_GUIDE.md` — contains installation steps, the full CLI reference, LLM/tunnel instructions, examples, and troubleshooting.

License: choose a license for your project.
