# pseudokin_20x2 (tier L, N=20)

Part of the robustness ladder — see `../../plan.md`.

## Contents

- `goal.txt` — locked NL prompt (20 systems)
- `labels.txt` — UniProt ids
- `campaign.conf` — paths / workers / LLM
- `seed_dual_rep.sh` — seeds into `{id}_ATP/hpc/rep01|rep02`
- `run_simagent.sh`, `launch_runs_nohup.sh`, `start_detached.sh`

## Start (after you inspect — do not auto-chain tiers)

```bash
cd /home/akp66103/workspace/agenticAI

# Seed only
bash campaigns/robustness/campaigns/pseudokin_20x2/start_detached.sh --seed-only

# Full: seed + run_01 + run_02
bash campaigns/robustness/campaigns/pseudokin_20x2/start_detached.sh
```

Monitor:

```bash
tail -f campaigns/robustness/campaigns/pseudokin_20x2/logs/orchestrator.log
```
