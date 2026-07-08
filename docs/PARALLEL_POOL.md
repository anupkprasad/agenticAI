# Cross-Sim Parallel Worker Pool

When a multi-simulation workflow runs **independent per-simulation stages**
(prep or analysis+reporter), AgenticAI can execute them concurrently on the
local machine. Worker count is chosen **automatically** from CPU and memory.

## What runs in parallel

| Stage | Parallel? | Notes |
|-------|-----------|-------|
| Preprocess + simsetup (pre-HPC) | Yes | Up to N workers; then HPC pool submits SLURM jobs |
| Analysis + reporter (post-HPC / analysis-only) | Yes | Skips sims with artifacts already on disk |
| HPC (GROMACS MD) | Yes (SLURM) | Separate cross-sim HPC pool; also auto-sized when `--allowed-hpc-jobs` omitted |
| Combined analysis + report | No | Runs once after all per-sim work completes |
| Human-in-the-loop (`--HITL`) | No | Falls back to sequential execution |

## Automatic resource detection

The framework probes:

- **CPU:** `os.cpu_count()` minus 2 cores reserved for orchestrator + Ollama
- **Memory:** `/proc/meminfo` on Linux (or `psutil` if installed)

It computes:

```
workers = min(floor(avail_cpus / cpus_per_job),
              floor(avail_mem / mem_gb_per_job),
              user_cap,
              llm_concurrency,   # prep / analysis only
              pending_simulations)
```

For **prep** and **analysis+reporter**, worker count is also capped by
`--llm-concurrency` (default `auto` = 4) so fewer simulations block on the
shared Ollama server. Set `OLLAMA_NUM_PARALLEL` on the Ollama host to the same
value (see `ollama_server.slurm`).

Default per-job estimates:

| Phase | CPUs | RAM |
|-------|------|-----|
| Prep (preprocess + simsetup) | 2 | 4 GiB |
| Analysis + reporter | 2 | 3 GiB |
| HPC pool (SLURM slots) | 1 | 0.5 GiB |

## CLI

```bash
python run_agenticAIWork.py \
  --goal "..." \
  --working-dir ./study \
  --simtype multisim \
  --pdb-list a.pdb b.pdb c.pdb \
  --parallel-workers auto \
  --llm-concurrency auto \
  --subtask analysis reporter
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--parallel-workers auto` | `auto` | Auto-detect; use integer to cap (`1` = sequential) |
| `--parallel-mem-gb` | phase default | Override GiB RAM estimate per worker |
| `--parallel-cpus` | phase default | Override CPU cores estimate per worker |
| `--llm-concurrency auto` | `auto` (4) | Cap workers for LLM-heavy phases; match `OLLAMA_NUM_PARALLEL` |
| `--allowed-hpc-jobs` | auto | SLURM concurrency when omitted and `--parallel-workers auto` |

Auto mode caps workers at **8** by default (override: `AGENTIC_PARALLEL_MAX_AUTO=16`).

Environment overrides:

```bash
export AGENTIC_PARALLEL_WORKERS=4
export AGENTIC_PARALLEL_MEM_GB=3
export AGENTIC_PARALLEL_CPUS=2
export AGENTIC_LLM_CONCURRENCY=4
```

## Ollama server

Parallel workers share one LLM endpoint. On the Ollama host, set (see `ollama_server.slurm`):

```bash
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_MAX_QUEUE=512
export OLLAMA_KEEP_ALIVE=-1
```

Restart the Ollama server after changing these. Use the same value for
`--llm-concurrency` (or `AGENTIC_LLM_CONCURRENCY`).

## Behaviour

1. **Master plan** — planner builds per-sim prompts as usual.
2. **Parallel pool** — up to N worker processes each run one simulation's agents.
3. **Poll** — main process updates ``parallel_pool_status`` in ``state.jsonl`` every 30s (no terminal/log spam).
4. **Combined work** — after all per-sim jobs finish, combined analysis/reporter runs at base dir.

Monitor live workers:

```bash
watch -n 5 cat pseudoKin/supervisor/pool_status.json
# or
tail -1 pseudoKin/supervisor/state.jsonl | jq '.state.parallel_pool_status'
```

Sims with existing outputs (`analysis_summary.jsonl`, `report.html`, or simsetup files) are **skipped**.

Use `--resume` to continue after interruption; stale `running` records are re-queued.

On **Ctrl+C / kill / disconnect**, the framework saves an interrupt checkpoint:
`running` workers become `pending`, `multi_sim_progress` is synced from pool +
disk, and `workflow_status` is set to `in_progress:interrupted`. Run again
with `--resume` and the same `--working-dir`.

While the pool runs, `parallel_pool_status` (and `pool_status.json`) are the
live source of truth for worker slots. `multi_sim_progress` is kept in sync on
every checkpoint so both sections of `state.jsonl` agree.

## State

Pool metadata lives in `{base}/supervisor/state.jsonl` under `parallel_pool`:

```json
{
  "phase": "analysis",
  "max_workers": 4,
  "resource_estimate": {
    "max_workers": 4,
    "limiting_factor": "memory",
    "cpus_per_job": 2.0,
    "mem_gb_per_job": 3.0
  },
  "sims": {
    "p21860": { "status": "done", "working_dir": "..." }
  }
}
```

`multi_sim_phase` is `"parallel_pool"` while workers run.

## Logging

Pool events are written to `{base}/agent_conversation.log` with agent name `parallel_pool`.
