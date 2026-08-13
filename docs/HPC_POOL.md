# Cross-Sim HPC Pool

When a workflow requests **preprocess + simsetup + HPC + analysis + reporter**
together, the supervisor uses an HPC pool that **waits for SLURM completion**
before starting analysis/reporter. This applies to **multi-sim and singlesim**.

For multi-sim, prep runs across simulations and jobs are submitted up to N at a
time. For singlesim, the same pool machinery runs with one synthetic
`sim_prompts` entry so analysis never starts before `md.xtc` (or equivalent)
exists.

## Behavior

1. **Master plan** — planner builds per-sim prompts as usual.
2. **Prep (sequential, all sims)** — each simulation runs preprocess → simsetup one at a time until **every** sim is ready. No SLURM jobs are submitted during this phase.
3. **Submit (parallel up to N)** — after all prep is complete, jobs are submitted as slots free (up to `--allowed-hpc-jobs`).
4. **Poll** — while jobs run, the workflow sleeps and re-checks SLURM every `--hpc-check-interval`
   (default **2h** / 7200s).
5. **Post-HPC (sequential)** — after all jobs complete (or are skipped because trajectories already exist),
   per-sim analysis → reporter runs, then combined analysis/reporter at project base.

Sims with existing trajectories under `{sim}/hpc/*.xtc` are **skipped** for submission.

## CLI

```bash
python run_agenticAIWork.py \
  --goal "..." \
  --pdb-list a.pdb b.pdb c.pdb \
  --simtype multisim \
  --allowed-hpc-jobs 5 \
  --hpc-check-interval 2h
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--allowed-hpc-jobs` | 5 | Max concurrent SLURM jobs in the pool |
| `--hpc-check-interval` | `2h` | Poll interval (`2h`, `120m`, `7200`); use a shorter value while debugging |
| `--resume` | off | Restore `{base}/supervisor/state.jsonl` and re-enter pool monitoring |
| `--HITL error` | — | Pause on submit/SLURM failures at the HPC pool checkpoint |

Set `hpc_pool_disabled=True` in state (or omit analysis/reporter from `--subtask`) to
skip the pool and use the legacy per-agent HPC path. `download_results` is **not**
part of the default pool or HPC agent plan; analysis reads trajectories from
`{sim}/hpc/` on the shared filesystem unless the user explicitly asks to download.

## Hybrid execution / resume

- While the process is **running**, the pool wait node sleeps for the check interval, then polls
  `sq --me` (or `squeue -u $USER`).
- If the process is **killed**, restart with the same `--working-dir` and `--resume`. Pool state
  in `state.jsonl` restores job IDs and prep status; the supervisor syncs SLURM and continues.

## HITL on failures

Submit failures or SLURM terminal failures (`FAILED`, `TIMEOUT`, etc.) set `awaiting_hitl` on the
pool. With **`--HITL error`** or **`--HITL all`**, the workflow pauses at `human_hpc_pool_check` where you can:

- `status` — show pool summary
- `continue` / `retry` / `resubmit` — clear the pause, re-sync SLURM, and resume submission/monitoring

## State

Pool metadata lives in `{base}/supervisor/state.jsonl` under `hpc_pool`:

```json
{
  "max_concurrent": 5,
  "check_interval_sec": 7200,
  "sims": {
    "p23458": {
      "prep_status": "done",
      "hpc_status": "running",
      "job_id": "46388398"
    }
  }
}
```

`multi_sim_phase` is `"hpc_pool"` during prep/submit/monitor, then `"executing_sims"` with
`post_hpc_analysis_only=true` for analysis/reporter.
