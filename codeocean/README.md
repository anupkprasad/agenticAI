# Code Ocean capsule — SimAgent (`SimAgent_v1.0`)

This folder packages a **reviewer-facing, cloud-runnable** subset of the
SimAgent manuscript software. It is meant for [Code Ocean](https://codeocean.com)
compute capsules linked to *Nature Computational Science* peer review.

## What is included

| Path | Role |
|------|------|
| `../` (repo root) | Full SimAgent source on branch **`SimAgent_v1.0`** |
| `environment/environment.yml` | Conda recipe (`SimAgentEnv`) |
| `data/demo/*.pdb` | Four starting structures (apo/holo panel inputs) |
| `data/features/*.csv` | Small published feature tables (5-system cohort excerpt) |
| `scripts/smoke_test.py` | Import / CLI checks (no HPC, no LLM server) |
| `scripts/regenerate_feature_heatmap.py` | Redraw a feature heatmap into `results/` |
| `run` | **Reproducible Run** entry point |
| `CODE_AVAILABILITY.md` | Draft wording for the manuscript |

## What the Reproducible Run does

```bash
bash codeocean/run
```

1. `pip install -e .`
2. Smoke-test imports + `SimAgent.py --help`
3. Write `results/pseudokin_5x2_feature_heatmap.png` from deposited CSV
4. Write `results/run_manifest.txt`

This completes in minutes on CPU and does **not** require Ollama, GPUs, or SLURM.

## What it does *not* run in the cloud

The full paper campaigns need:

- A running **Ollama** server (or `--llm-api-key` / `--no-llm`)
- **GROMACS** MD + **SLURM** HPC (see repository README)
- Trajectory storage (not shipped; provenance plots live under
  `campaigns/robustness/simagent_provenance/`)

Reviewers can still **inspect** all agent code, goals, and provenance on this
branch. To reproduce end-to-end locally, follow [example/TUTORIAL.md](../example/TUTORIAL.md)
and [docs/OLLAMA_SETUP.md](../docs/OLLAMA_SETUP.md).

## How to build the Code Ocean capsule

1. Create a capsule on Code Ocean (use the journal invite link if provided).
2. Upload **this git branch** `SimAgent_v1.0` into the capsule `/code` tree
   (keep the repository layout so `codeocean/` sits next to `SimAgent.py`).
3. Configure the environment from `codeocean/environment/environment.yml`
   (conda / Code Ocean environment UI). Then inside the env:
   `pip install -e .`
4. Set the **Reproducible Run** command to:
   ```bash
   bash codeocean/run
   ```
5. Click **Reproducible Run**, confirm `results/pseudokin_5x2_feature_heatmap.png`
   appears, then **Submit for publication** (peer-review verification).
6. Tell Code Ocean support the journal is *Nature Computational Science* if
   the invite metadata is unclear.

Optional: set `CODEOCEAN_RESULTS=/results` if your capsule maps results there.

## Branch / version pin

- Git branch: **`SimAgent_v1.0`** (manuscript freeze for reviewers)
- Prefer citing the commit SHA and, after deposit, a Zenodo or Code Ocean DOI

## License

MIT — see [LICENSE](../LICENSE).
