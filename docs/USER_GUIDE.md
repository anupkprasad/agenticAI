# agenticAI — User Guide

This user guide explains the workflow, CLI usage, LLM integration, and safety practices for the agenticAI scaffold in this repository.

## Overview

agenticAI is a minimal, safe scaffold to prepare, submit, retrieve and analyze molecular dynamics (MD) simulations using small "agents":

- SimulationSetupAgent — prepares simulation inputs and writes a SLURM job script.
- HPCJobAgent — (placeholder) handles submission and result retrieval from an HPC cluster.
- AnalysisAgent — provides a minimal analysis summary and can call an LLM for a narrative summary.

The included CLI (`scripts/run_agent.py`) exposes the main actions and can optionally call a local LLM server to map natural-language prompts to agent actions.

## Installation

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Edit `config/config.yaml` to set your HPC host, user and preferred defaults. The repository uses safe mocks by default.

## Basic workflow (dry-run)

Examples below show the safe dry-run behavior that uses local files and mock HPC actions.

1. Prepare a simulation plan and generate a SLURM job script:

```bash
python scripts/run_agent.py setup --pdb path/to/your.pdb
# Writes jobs/run_sim.sh and prints the plan
```

2. Prepare a job file (if applicable):

```bash
python scripts/run_agent.py prepare-job --out jobs/job.sh
```

3. Analyze results (placeholder):

```bash
python scripts/run_agent.py analyze --data results/
```

Note: `HPCJobAgent.submit_job()` and `download_results()` are safe mocks in this scaffold. Replace with your SSH/SFTP logic before using on a real cluster.

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
