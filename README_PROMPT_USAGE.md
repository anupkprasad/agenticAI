# Using the prompt-driven CLI for simulation setup

This project uses a single, prompt-driven CLI entrypoint: `scripts/run_agent.py`.
The CLI always takes a natural-language `--prompt` which the planner (LLM) uses
to produce a compact plan expressed as tool_calls (for example `setup_simulation`).

This short guide shows common usages to prepare simulation setups using prompts.

Prerequisites
- Run from the project root (where `scripts/` lives).
- Activate the project's virtualenv if you use one (example):

```bash
source .venv/bin/activate
```

Core flags
- `--prompt`   : (required) natural language instruction to the planner.
- `--use-llm`  : enable contacting a local/remote LLM via `LLMClient`.
- `--llm-base-url` : base URL for an LLM endpoint (e.g. `http://host:11434`).
- `--llm-log`  : path to append raw LLM responses and the parsed `invoke_result`.
- `--auto-approve` : run planned actions without interactive confirmation.
- `--dry-run`  : print planned actions only; do not execute them.

Examples

1) Preview (dry-run) — scan a folder and show planned setups without running:

```bash
python3 scripts/run_agent.py \
  --prompt "Scan the folder /home/anup/workspace/temp/sim_test for PDB files and prepare simulation setups for each" \
  --dry-run --use-llm --llm-base-url http://172.22.149.139:11434 --llm-log ./agentic_agent.log
```

2) Execute automatically (no prompts) — scan a folder and run setups for each PDB:

```bash
python3 scripts/run_agent.py \
  --prompt "Scan the folder /home/anup/workspace/temp/sim_test for PDB files and prepare simulation setups for each" \
  --use-llm --llm-base-url http://172.22.149.139:11434 --llm-log ./agentic_agent.log --auto-approve
```

3) Prepare a single PDB in a specific working directory:

```bash
python3 scripts/run_agent.py \
  --prompt "Prepare simulation setup for /home/anup/workspace/temp/sim_test/0.pdb in working directory /home/anup/workspace/temp/sim_test" \
  --use-llm --llm-base-url http://172.22.149.139:11434 --auto-approve
```

Notes and behavior
- The planner returns tool_calls. The CLI focuses on `setup_simulation` (and synonyms).
- If a tool_call contains only `wdir` (no `pdb`), the CLI scans that directory for
  `*.pdb` files and executes `plan_simulation` for each discovered file.
- `--dry-run` prints the planned tool_calls (and any per-PDB expansion) without executing.
- `--auto-approve` skips interactive confirmations and runs the setups immediately.
- Raw LLM responses and the parsed `invoke_result` are appended to the file given
  with `--llm-log` for auditing and debugging.

Real setup vs fallback
- The simulation agent will try to lazy-import the real `call_simulation_setup` (if
  your project provides it). When available, the real implementation is invoked from
  inside the workdir and receives the PDB basename (to avoid exposing absolute paths
  to downstream tools). If import or execution fails, the agent falls back to a
  lightweight/safe skeleton setup to keep development/test flows working.

If you want a strict mode that fails when the real setup is not available, say so
and I can add a `--require-real-setup` flag that will make the CLI error out instead
of silently falling back.

Troubleshooting
- If a downstream tool complains about paths (e.g. Rosetta errors mentioning ".///...")
  make sure you're running the project with the virtualenv and that any real setup
  implementation expects relative/basename input (the agent already runs the real
  setup from inside the `wdir`).
- Inspect `./agentic_agent.log` (or whatever path you pass to `--llm-log`) for the
  planner's raw response and the parsed tool_calls.

Contact
- If you want, I can add example unit tests that mock the planner and the real
  setup to verify the behavior (dry-run, auto-approve, fallback). I can also add
  the `--require-real-setup` flag.
