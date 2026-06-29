# Cross-Sim HPC Pool

When a multi-simulation workflow requests **preprocess + simsetup + HPC + analysis + reporter**
together, the supervisor uses a cross-simulation HPC pool instead of blocking on one simulation
at a time.

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
| `--hpc-check-interval` | `2h` | Poll interval (`2h`, `120m`, `7200`) |
| `--resume` | off | Restore `{base}/supervisor/state.jsonl` and re-enter pool monitoring |
| `--HITL error` | — | Pause on submit/SLURM failures at the HPC pool checkpoint |

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
