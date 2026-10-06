# Code Ocean capsule — SimAgent (`SimAgent_v1.0`)

## 1. What is `codeocean/` vs the rest of the repo?

| Location                                                                                         | Role for reviewers                                                                          |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| **`codeocean/`**                                                                         | Capsule packaging: Reproducible Run script, small deposited tables, docs for Code Ocean     |
| **Everything else** (`SimAgent.py`, `agentic/`, `src/`, `example/`, `docs/`, …) | The **full SimAgent framework** and manuscript materials on branch `SimAgent_v1.0` |

So: `codeocean/` is the **cloud entry point**. The parent repository is the complete software + worked example + provenance. Reviewers get both when the capsule contains this branch.

> ### Important — inspect the full combined report
>
> After opening the capsule (or this git branch), **open the worked-example HTML
> report** to review scientific results and narrative:
>
> **`example/pseudo_apo_holo/reporter/combined_report.html`**
>
> - **On Code Ocean:** use the capsule **file browser** → navigate to that path →
>   open / download the file and view it in a browser.
> - **On GitHub (`SimAgent_v1.0`):**  
>   [View file in repository](https://github.com/anupkprasad/agenticAI/blob/SimAgent_v1.0/example/pseudo_apo_holo/reporter/combined_report.html)  
>   · [Try rendered preview](https://htmlpreview.github.io/?https://raw.githubusercontent.com/anupkprasad/agenticAI/SimAgent_v1.0/example/pseudo_apo_holo/reporter/combined_report.html)  
>   (third-party `htmlpreview`; large ~8–10 MB reports may be slow or fail — then
>   download the file from GitHub and open it locally.)
>
> The Reproducible Run below only regenerates a few summary PNGs. The
> **combined report is the main delivered result** of the apo/holo example.

## 2. Environment on Code Ocean

You **should** create **`SimAgentEnv`** in the capsule from
`codeocean/environment/environment.yml` (then `pip install -e .`). That proves
the scientific stack installs.

Do **not** expect to run in the capsule:

- Ollama / LLM server
- SLURM / HPC job submission
- Full ligand **ACPYPE** parameterization + **GROMACS** MD system setup and
  production for the eight apo/holo systems

Those steps are **computationally heavy** (CPU/GPU time, disk, and I/O) relative
to a typical Code Ocean machine. The capsule therefore uses **already produced**
tables and figures from the worked example instead of re-parameterizing or
re-simulating.

## 3. What the Reproducible Run does (limited resources)

```bash
bash codeocean/run
```

1. `pip install -e .` (into the capsule `SimAgentEnv`)
2. Smoke-test imports + `SimAgent.py --help` (confirms `--no-llm` exists)
3. Regenerate **RMSD / RMSF / Rg** summary bar charts from deposited stats(from `example/pseudo_apo_holo/analysis/*_stats.csv`)
4. Regenerate a small **feature-matrix heatmap** from a robustness CSV excerpt
5. Write `results/run_manifest.txt`

This finishes in minutes on **CPU**.

### Why deposited data instead of a full `pseudo_apo_holo` re-run?

| Stage                                    | Why not in Code Ocean                            |
| ---------------------------------------- | ------------------------------------------------ |
| ACPYPE ligand parameterization           | Slow QM/charge fitting; large intermediate trees |
| GROMACS preprocess / solvate / ions / MD | Long walltime; often GPU; large trajectories     |
| Ollama LLM planning                      | Needs a separate GPU model server                |
| SLURM HPC pool                           | Not available in the capsule                     |

The Reproducible Run **recreates selected summary figures from already-completed
campaign tables**. Full outputs remain in the repository for inspection.

### Where is the full demonstration?

| Path | What reviewers should look at |
|------|-------------------------------|
| **[`example/pseudo_apo_holo/reporter/combined_report.html`](../example/pseudo_apo_holo/reporter/combined_report.html)** | **Primary result** — comparative HTML report (open in Code Ocean file browser or via GitHub links above) |
| [`example/pseudo_apo_holo/`](../example/pseudo_apo_holo/) | Full 8-simulation campaign tree (analysis PNGs, logs, per-sim reports) |
| [`example/TUTORIAL.md`](../example/TUTORIAL.md) | How to re-run the example locally with SimAgentEnv + Ollama + HPC |
| [`campaigns/robustness/simagent_provenance/`](../campaigns/robustness/simagent_provenance/) | Paper-scale agent provenance (no trajectories) |

**`--no-llm`:** Supported for offline heuristic planning on a local/HPC machine,
but MD setup and analysis still need GROMACS (and trajectories). The capsule
does not claim a full MD redo in the cloud.

## 4. Capsule contents

| Path                                      | Role                                                         |
| ----------------------------------------- | ------------------------------------------------------------ |
| `run`                                   | Reproducible Run entry point                                 |
| `environment/environment.yml`           | Conda recipe (`SimAgentEnv`) — use this on Code Ocean     |
| `data/demo/*.pdb`                       | Starting structures (same proteins as the worked example)    |
| `data/example_overlays/*.csv`           | RMSD/RMSF/Rg stats deposited from`example/pseudo_apo_holo` |
| `data/features/*.csv`                   | Small 5-system feature tables (robustness excerpt)           |
| `scripts/smoke_test.py`                 | Import / CLI checks                                          |
| `scripts/regenerate_overlay_stats.py`   | Bar charts from example stats                                |
| `scripts/regenerate_feature_heatmap.py` | Feature heatmap from CSV                                     |
| `CODE_AVAILABILITY.md`                  | Draft manuscript wording                                     |

## 5. How to build the Code Ocean capsule

1. Create a capsule (journal invite link if provided).
2. Upload branch **`SimAgent_v1.0`** into `/code` (keep repo layout: `codeocean/` next to `SimAgent.py`).
3. Create **`SimAgentEnv`** from `codeocean/environment/environment.yml`, then `pip install -e .`.
4. Reproducible Run command:
   ```bash
   bash codeocean/run
   ```
5. Confirm PNGs under `codeocean/results/` (or `/results` if mapped).
6. **Investigate results:** open
   `example/pseudo_apo_holo/reporter/combined_report.html` in the capsule
   file browser (download and open in a web browser if needed).
7. Submit for Code Ocean verification. Tell Code Ocean the journal is
   *Nature Computational Science* if metadata is unclear.

Optional: `CODEOCEAN_RESULTS=/results` when the platform mounts results there.

## Branch / license

- Branch: **`SimAgent_v1.0`**
- License: MIT — [LICENSE](../LICENSE)
