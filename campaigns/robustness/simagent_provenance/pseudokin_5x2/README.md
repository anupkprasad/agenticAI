# pseudokin_5x2 (tier S, N=5)

Part of the robustness ladder — see `../../plan.md`.

## Contents

- `goal.txt` — locked NL prompt (5 systems)
- `labels.txt` — UniProt ids
- `campaign.conf` — paths / workers / LLM
- `seed_dual_rep.sh` — seeds into `{id}_ATP/hpc/rep01|rep02`
- `run_simagent.sh`, `launch_runs_nohup.sh`, `start_detached.sh`

## Notes

- Uses `--skip-hpc-submit` (not `--reuse-hpc`): preprocess + simsetup run
  normally; sbatch is blocked; analysis uses seeded `hpc/repXX` trajs.
- Master plan is LLM-built (pre/post combined flags + plans).
- After HPC staging, **pre_combined** (pocket/MSA → `cross_sim/`) runs
  before the per-sim analysis pool.

## Start (after you inspect — do not auto-chain tiers)

```bash
cd /home/akp66103/workspace/agenticAI

# Seed only
bash campaigns/robustness/campaigns/pseudokin_5x2/start_detached.sh --seed-only

# Full: seed + run_01 + run_02
bash campaigns/robustness/campaigns/pseudokin_5x2/start_detached.sh
```

Monitor:

```bash
tail -f campaigns/robustness/campaigns/pseudokin_5x2/logs/orchestrator.log
```
