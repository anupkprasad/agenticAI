# Capsule data

## `demo/`

Starting PDBs for the four-pseudokinase apo/holo example (`p21860`, `q8iv63`,
`q8nb16`, `q8wz42`). Same inputs as `example/pseudo_apo_holo/`. For inspection
only — the Reproducible Run does **not** re-run ACPYPE parameterization or
GROMACS MD setup from these files (too heavy for a typical Code Ocean capsule).

## `example_overlays/`

Summary statistics **deposited from the already completed** worked example
(not recomputed in the cloud):

- Source: `example/pseudo_apo_holo/analysis/rmsd_stats.csv`
- Source: `example/pseudo_apo_holo/analysis/rmsf_stats.csv`
- Source: `example/pseudo_apo_holo/analysis/rg_stats.csv`

The Reproducible Run regenerates bar-chart PNGs from these tables so reviewers
get an executable figure step without re-parameterizing ligands or re-running MD.

## `features/`

Excerpt of classification feature tables from published robustness provenance
(`pseudokin_5x2` / `run_01`). Absolute local paths were stripped. Used for the
feature-heatmap regeneration step.
