# Simulation pipeline — mental model and workflow

This document explains the high-level mental map for how this project prepares,
submits, and analyzes molecular dynamics (MD) simulations via an LLM-driven
agent. Keep this file editable — you can update it and I will update the
file accordingly.

## Purpose

Give contributors (and future-you) a short, opinionated overview of how the
pipeline components fit together. The goal is to make it easy to reason about
what the agent does, where to change behavior (prompts, real setup code,
HPC submission), and how to run the CLI.

## High-level flow (mental map)

1. User provides a natural-language instruction via the prompt-driven CLI
   (`scripts/run_agent.py --prompt "..."`). The project is designed so the
   planner (LLM) decides the concrete steps to take.
2. The planner agent (LLM) returns a compact plan expressed as `tool_calls`.
   Each `tool_call` includes a `name` and `args` (for example `setup_simulation`).
3. The CLI inspects the `tool_calls` and focuses on simulation-related calls.
   For `setup_simulation` calls it will either:
   - Expand a `wdir` into individual `.pdb` files and plan setup per PDB, or
   - Run setup for an explicit `pdb` / `wdir` pair.
4. The simulation agent handles the setup logic by attempting to call the
   project's real setup implementation (lazy import of
   `src.python.setup.sim_setup.call_simulation_setup`). If the real implementation
   is available it is executed from inside the target working directory and
   receives the PDB basename to avoid exposing absolute paths to downstream
   tools. If the real implementation is not available or raises, the agent
   falls back to a lightweight, safe skeleton setup.
5. The setup step writes the output into the working directory (input copy or
   symlink, job scripts in `jobs/`, small manifest), which is then ready for
   HPC submission or local execution.
6. If requested, the agent can submit the job to an HPC agent wrapper and
   later collect results and pass them to analysis agents.

## Key components and locations

- `scripts/run_agent.py` — single entrypoint CLI. Required flag: `--prompt`.
  Useful flags: `--use-llm`, `--llm-base-url`, `--llm-log`, `--auto-approve`,
  `--dry-run`. (Optionally `--require-tool-calls` if you want strict planner-only behavior.)
- `agentic/llm.py` — LLM wrapper and parsing heuristics for streaming/NDJSON
  parsing. Maps planner language to canonical tool names (e.g. `setup_simulation`).
- `agentic/schemas.py` — pydantic schemas for tool-call validation
  (PlanSimulationParams, ToolCall, etc.).
- `agentic/simulation_agent.py` — simulation agent that exposes
  `plan_simulation(pdb, wdir)` and manages lazy import of the real setup and
  fallback setup behavior. Also contains safe file-copy/symlink logic.
- `agentic/hpc_agent.py` — HPC submission/download wrapper used for job
  submission and retrieval.
- `src/python/setup/sim_setup.py` (optional, project-provided) — the real
  heavy-weight setup implementation that the agent will call when available.

## Safety and path handling

- The agent avoids copying a PDB onto itself by comparing resolved paths;
  if source and destination are the same, it does not re-copy.
- When invoking the real setup, the agent `chdir()`s into the working directory
  and passes only the PDB basename to avoid malformed absolute path prefixes
  being forwarded to downstream binaries (this prevents issues such as
  toolchains mis-parsing "./../" prefixes).
- The fallback setup creates a minimal `jobs/run_sim.sh` and a manifest,
  ensuring development and CI remain functional without the full toolchain.

## CLI usage patterns

Recommended workflow examples (also in `README_PROMPT_USAGE.md`):

- Preview planned actions (dry-run, no execution):

```bash
python3 scripts/run_agent.py \
  --prompt "Scan /path/to/folder for PDBs and prepare setups" \
  --dry-run --use-llm --llm-base-url http://localhost:11434 --llm-log ./agentic_agent.log
```

- Run automatically for all PDBs in a folder (no interactive prompts):

```bash
python3 scripts/run_agent.py \
  --prompt "Scan /path/to/folder for PDBs and prepare setups" \
  --use-llm --llm-base-url http://localhost:11434 --auto-approve
```

- Strict planner mode (fail if no structured `tool_calls`):

```bash
python3 scripts/run_agent.py \
  --prompt "..." --use-llm --require-tool-calls
```

If your planner responds in plain language instead of JSON `tool_calls`, the
CLI may synthesize actions with a heuristic fallback unless `--require-tool-calls`
is given.

## Prompt template for reproducible tool_calls

If you want the planner to return structured `tool_calls`, include an instruction
like the following in your prompt:

```
Return a JSON object with a `tool_calls` list. Each item must be an object with
`name` and `args`. For example:
{"tool_calls": [{"name": "setup_simulation", "args": {"pdb": "/full/path/0.pdb", "wdir": "/work/dir"}}]}

Only return the JSON object, do not add explanatory text.
```

This makes the planner output deterministic and easy to validate.

## Editing and maintaining this doc

I will keep this file editable. If you update the code or change the CLI,
ask me to update this document — I will apply a patch and include the
minimal diffs. Good future edits to consider:

- Add a small ASCII or Mermaid flow diagram for visual clarity.
- Add an example of the exact `invoke_result` JSON the planner should return.
- Add unit test snippets that mock the planner and assert correct agent behavior.

## Next recommended improvements

- Add `--require-real-setup` to fail hard when the real setup implementation
  cannot be imported (prevents accidental fallback in production runs).
- Add minimal integration tests that run the CLI in `--dry-run` with a mocked
  planner returning `tool_calls` and assert the expected outputs.

---

Last updated: please ask me to update this file when you change code or
behavior and I'll keep it in sync.
