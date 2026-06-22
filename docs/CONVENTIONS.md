# Coding Conventions

Ground rules for developing and extending AgenticAI.

---

## State-Driven Architecture

- **All data flows through `MDState`** (a single TypedDict in `agentic/state.py`).
  Agents never communicate directly — they read from and write to state fields.
- **Field naming:** `{stage}_{artifact}` — e.g. `cleaned_pdb`, `setup_report`,
  `analysis_results`, `trajectory_path`.
- **Routing:** the `next_node` field tells the supervisor where to go next.
  Each agent sets it before returning.
- **Error tracking:** append to `errors` (fatal) and `warnings` (non-fatal) lists.
- **New fields:** add to `MDState` in `agentic/state.py` with an `Optional[...]`
  type annotation and a descriptive inline comment.

### Key state field groups

| Group | Fields | Written by |
|-------|--------|-----------|
| Input | `raw_pdb`, `user_goal`, `structured_prompt` | Supervisor / CLI |
| Structure | `cleaned_pdb`, `structure_request`, `domain_context`, `sim_case` | Preprocessing |
| Setup | `topology`, `coordinates`, `mdp_files` | SimSetup |
| HPC | `job_id`, `job_status`, `trajectory_path` | HPC |
| Analysis | `analysis_results` | Analysis |
| Report | `reporter_output` | Reporter |
| Multi-sim | `is_multi_simulation`, `sim_prompts`, `completed_sim_states`, `multi_sim_phase` | Supervisor |
| Plan | `execution_plan`, `*_instructions` fields | Planner |

---

## Agent Pattern

Every agent follows the same structure:

```
agentic/{agent_name}/
    __init__.py
    {agent_name}_agent.py   # Main class with a *_node() method
    tools.py                # Tool functions (auto-discovered by planner)
    schemas.py              # Pydantic input/output schemas
    config.yaml             # Agent-level configuration
```

### Adding a New Agent

1. Create the directory under `agentic/`.
2. Implement a class with a method `{agent_name}_node(self, state: MDState) -> MDState`.
3. Register the agent in `agentic/supervisor/config.yaml`:
   ```yaml
   agents:
     agent_name:
       capabilities: ["what_it_does"]
       input_requirements: ["fields_it_reads"]
       output_provides: ["fields_it_writes"]
       skip_conditions: ["when_to_skip"]
   ```
4. Add the node and edges in `agentic/workflow.py`.
5. Tools in `tools.py` are auto-discovered by `planner/tools_registry.py` — no
   manual registration needed. Decorate tool functions with LangChain `@tool`.

### Agent Output Isolation

Each agent writes to its own subdirectory:

```
working_dir/{agent_name}/
```

Use `state["working_directory"]` as the base, and the agent-specific
`{agent}_dir` field (e.g. `preprocess_dir`, `analysis_dir`) for the full path.
Use `SecureFileManager` from `agentic/utils/` for all file operations.

---

## Pluggable Registry Pattern

New structure sources and domain sources are added as registry plugins, not as
edits to the main pipeline.

### Adding a new structure source (e.g. PDB redo)

1. Create `src/preprocess/structure_sources/pdredo.py` implementing the
   base class from `structure_sources/base.py`.
2. Register it in `src/preprocess/structure_sources/registry.py`.
3. Set priority order in the registry (AlphaFold is default, RCSB is fallback).

### Adding a new domain source

1. Create `src/preprocess/domain_sources/yourdb.py` implementing the base from
   `domain_sources/base.py`.
2. Register in `src/preprocess/domain_sources/registry.py`.

No changes to the Preprocessing agent or tools needed — `acquire_protein_structure`
uses the registry automatically.

---

## LLM Integration

- **Always provide a fallback.** Every LLM call must have a deterministic code
  path for when the LLM is unreachable.
- **Mock mode:** set `_is_mock_mode = True` for testing without an LLM server.
- **Structured prompts:** include an explicit output-format instruction in every
  LLM prompt (e.g. "Return JSON with keys: ...").
- **Configuration:** `agentic/supervisor/config.yaml` for the agent registry;
  `llm_config.py` for model/URL defaults.
- **Coercion:** LLM plan fields may return lists or dicts instead of strings.
  Use `_coerce_plan_text()` in `supervisor_agent.py` to normalise them.

---

## Workflow Graph

- **Hub-and-spoke:** all agents return to the supervisor.
  Never add direct agent-to-agent edges.
- **Node wrapping:** use `_wrap_node()` to set `current_node` for tracking.
- **Conditional routing:** use LangGraph `add_conditional_edges` for branching.
- **Recursion limit:** 25 iterations. If the graph loops more, there is a bug.

---

## Multi-Simulation Conventions

- `sim_prompts` is the authoritative count of simulations (not `pdb_list`).
  `len(sim_prompts)` = total cases including all component variants.
- Each simulation gets an isolated `working_dir/{label}/` directory.
- The Supervisor loops sequentially through `sim_prompts`, resetting per-sim
  state fields (raw_pdb, cleaned_pdb, topology, etc.) between iterations.
- Skipped simulations are recorded in `completed_sim_states` with `skipped=True`
  and a `skip_reason` string — they are not silent failures.
- After all sims, `multi_sim_phase` advances to `combined_analysis` then
  `combined_reporter` automatically.

---

## Run Summary Convention

`src/utils/run_summary.py` exports:
- `build_run_summary(final_state, working_dir, goal, pdb_list, config)` → dict
- `write_run_summary(working_dir, summary)` → writes `run_summary.json` + `run_summary.md`
- `format_run_summary_terminal(summary)` → terminal-printable string

Call at workflow exit in `run_agenticAIWork.py`. Do **not** use `len(pdb_list)` for
the total simulation count — use `build_run_summary` which reads from `sim_prompts`.

---

## MD Defaults

| Setting | Default | Override |
|---------|---------|---------|
| Engine | GROMACS 2025.4 | — |
| Force field | AMBER99SB-ILDN | `--force-field` |
| Water model | TIP3P | `--water-model` |
| Temperature | 310 K | goal text |
| Pressure | 1 bar | goal text |
| NaCl concentration | 0.15 M | goal text |
| Box type | cubic, 1.2 nm buffer | goal text |
| PDB file extensions | `.top` (topology), `.gro` (coordinates) | — |

"Protein only" means only the protein component — **not** vacuum. All systems
are solvated by default. Only use vacuum if the user explicitly says so.

---

## HPC Conventions

- SLURM script name: `{job_name}_run.sh` — do not use `slurm_job.sh`.
- Script path is resolved from `state["job_script"]` or the pattern above.
  Never trust an LLM-generated script filename directly.
- Job names must be unique per simulation (derived from the `label` field).

---

## File and Path Handling

- Use `os.path.join()` with the agent directory fields from state.
- Normalise paths before storing them in state.
- Track all generated files in `file_registry` and `generated_files` state fields.
- `pdb_summary` in state may be `None` (initialised that way in `workflow.py`).
  Always use `state.get("pdb_summary") or ""` before string concatenation.

---

## Testing

- Tests live in `tests/`.
- Test both LLM-enabled and fallback (no-LLM) modes.
- Use the mock LLM client for unit tests.
- When adding a new agent, add a corresponding mock tool response fixture.

---

## General

- Keep imports at module top level.
- Use Python logging (`logger = logging.getLogger(__name__)`), not print statements.
- YAML for configuration, JSON for runtime data exchange.
- Retry counts per agent (`{agent}_retry_count` fields) prevent infinite retry loops.
- Pydantic schemas in `schemas.py` define inputs/outputs per agent stage.
