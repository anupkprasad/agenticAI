# Campaign contracts and tool retrieval

**This file is the family-scale reliability design.** It explains the compiled
`CampaignSpec`, science completeness gates, and hybrid embedding tool search
added so N-protein studies do not depend on lucky per-sim LLM prompts.

**In this file:** compile-once program, artifact contracts, the shared
analysis protocol (required calculations for every protein), required
shared setup (MSA/pocket before per-protein MD), embedding tool +
knowledge retrieval, `campaign.yaml`, file tools restricted to the
study directory, and per-stage inventory.

**Not in this file:** LangGraph nodes ([ARCHITECTURE.md](ARCHITECTURE.md)),
pool sizing ([POOLS.md](POOLS.md)), analysis theory
([ANALYSIS_TOOLS.md](ANALYSIS_TOOLS.md)).

**Terms used in this file**

| Term | Meaning |
|------|---------|
| **Required calculations** | Measurements that must run for every protein (pocket COM/orientation, RMSF, DCCM, dihedral PCA). The LLM cannot skip them. |
| **Shared analysis protocol** | The same compiled tool list and output directories applied to every protein. |
| **Required shared setup** | Structure-only work done once before per-protein MD (MSA, pocket definition, residue map). |
| **Restricted to the study directory** | File tools can only list/read inside this campaign or the current protein folder. |

---

## Compile once, map many

The natural-language `--goal` is compiled **once** into `state["campaign_spec"]`:

| Field | Role |
|-------|------|
| `mode` | `family_modular` or `generic` |
| `shared_analysis_protocol` (`analysis_recipe`) | Same calculations and output dirs for every protein |
| `contract` | Required `consensus_*` dirs and feature-column density |
| `required_calculations` | Measurements that must run for every protein (not optional LLM choices) |
| `required_shared_setup` | Structure-only setup every simulation consumes (MSA, pocket, residue map) |
| `allow_partial_combined` | Science-report flag only. Dendrogram + heatmap still plot from whatever columns exist |

Per-sim workers receive `user_goal_original` **and** `campaign_spec`. They do
not invent a new analysis shopping list.

LLM `sim_prompts` that contain `(same as above)` or drop family keywords are
**discarded**. The compact deterministic prompt (identity stanza + shared
science excerpt) is used instead.

## Science completeness

`run_summary.md` now has a **Science completeness** table. Process success
(HTML + `analysis_summary.jsonl`) is not enough for family campaigns.

A system is science-complete only when:

1. The modular directories from the shared analysis protocol exist
   (`consensus_dihedrals`, `consensus_rmsf`, `consensus_DCCM`, `consensus_PCA`)
2. Every **required calculation** has left its artifact contract (including
   pocket metrics: `reference_pocket_metrics.json` /
   `ligand_pocket_distance.csv`, typically under `analysis/repXX/` or
   `analysis/reference_pocket/`)

A family campaign *prefers* the 9 gold columns when they are filled. Combined
Ward still runs on any usable table (≥2 systems and ≥2 numeric columns) so a
generic goal that only asks for RMSF / χ₁ / entropy still gets a
dendrogram+heatmap. Missing gold columns are a **warning** in `run_summary`
and a **science banner** in `combined_report.html`, not a plot block
(`--allow-partial` only changes the science-OK flag).

Resume / parallel workers treat a family system as incomplete until those
artifacts exist — HTML alone does not skip re-analysis.
## Shared analysis protocol (comparative / family studies)

When the goal is a comparative protein-family study, every system runs the
**same** analysis protocol (compiled once, applied to all). The LLM does not
invent a different tool list per protein. The protocol is:

1. `calculate_consensus_pocket_metrics` → COM + axis-angle (`ligand_pocket_distance.csv` alias)
2. `calculate_consensus_torsions` → `consensus_dihedrals/`
3. `calculate_consensus_rmsf_features` → `consensus_rmsf/`
4. `calculate_consensus_dccm_features` → `consensus_DCCM/`
5. `run_independent_dynamics_fel` (dihedral PCA) → `consensus_PCA/`

`--reuse-hpc` also skips LLM preprocess/setup planning (deterministic fallback).

Resume/skip checks use the science contract. HTML + RMSD no longer mark a
family system complete. The shared analysis protocol is complete when the
four `consensus_*` directories **and** the required pocket-metric files exist
(RMSD is not required). Combined Ward always includes the 9 preferred
columns so the LLM cannot drop axis-angle / RMSF / χ₁ / DCCM / entropy from
the collected table — empty columns are recorded as unavailable instead.
Per-sim **success is artifact-gated**. `plot_md_data` / other `plot_*`
failures are warnings. A failed H-bond/SASA plot does not fail the
simulation or trigger a 3× replan. Retries reuse the compiled plan,
skip plots, and skip required calculations whose `consensus_*` dirs (or
pocket metric files) already exist.

**Required calculations** are registered on the **per-simulation** tool
executor (including `calculate_consensus_pocket_metrics`). Batch helpers
such as `run_consensus_pocket_metrics_batch` remain combined/shared tools.

Family mode also **forces** the pre-combined *stage* on. The LLM still
**compiles** which combined tools run there (pocket definition, MSA, or any
other shared calculation). The engine then executes that compiled protocol
once. A hardcoded MSA+pocket chain is only the fallback if compile is empty.

## Embedding tool search

When the goal is **not** a compiled shared analysis protocol (or for planner context),
tools are retrieved instead of dumping the full catalog into the LLM:

1. **Hashed character n-grams** (256-d, MD5-stable, no extra model)
2. **Lexical Jaccard** on tokens
3. Hybrid score: `0.65 * cosine + 0.35 * overlap`
4. Optional **Ollama dense embeddings** if `AGENTIC_EMBED_MODEL` is set
   (e.g. `nomic-embed-text`); blended at 45% when the server answers

Required calculations for the study are always included, then the top-k (~16)
ranked tools.

This is how general-purpose planning stays fast and accurate: the LLM sees
only the tools that match the goal, not every RMSD/H-bond/SLURM helper.

The same embedder retrieves **knowledge chunks**. Planner context is
`[kb:category.doc#heading]` citations, not a 6–10k dump of every manual.
The index is `planner/knowledge_index.json` (next to
`agentic/planner/knowledge/`, copied into the campaign `planner/` folder).

```bash
export AGENTIC_EMBED_MODEL=nomic-embed-text   # optional dense blend
# hashed n-grams always run; Ollama failure falls back silently
```

`retrieval_k` (default 16) and `embed_model` live in `campaign.yaml`.

## campaign.yaml

One file for mapping / retrieval / HITL knobs. Agent YAMLs stay for prompts.

Precedence (later wins): shipped `agentic/campaign/campaign.yaml` →
`{working-dir}/campaign.yaml` → `--campaign-yaml PATH` → `AGENTIC_*` env →
CLI `--HITL`.

| Key | Default | Role |
|-----|---------|------|
| `conservation_metric` | `similarity` | MSA column score (similarity / identity / blosum / coverage) |
| `min_conservation` | `0.5` | Score threshold |
| `min_coverage` | `0.25` | Column occupancy floor |
| `pocket_cutoff_A` | `15` | Reference ligand shell (Å) |
| `lobe_method` | `auto` | N/C lobe split |
| `retrieval_k` | `16` | Top-k tools (knowledge uses k/2) |
| `embed_model` | `""` | Optional Ollama embed model |
| `gold_columns` | paper 9 | Preferred Ward columns (not a plot gate) |
| `hitl` | `null` | `error` / `all` if CLI `--HITL` is omitted |

A family run can change 0.5 / 0.25 / 15 Å without editing Python.

## File tools and inventories

Field agents (not only HITL) can list, search, and read the file inventory.
Paths are **restricted to this study’s directories** (the campaign base or
the current protein folder). They cannot read files outside the study.
`write_file` stays HITL-only.

Prior errors and fixes from this campaign are stored in
`campaign/memory.jsonl` and shown to the planner on the next failure.

With `--HITL all`, a human can review (1) the compiled analysis protocol,
(2) the shared MSA/pocket mapping, and (3) the cross-system comparison,
before the next stage starts.

After each stage the engine writes `{stage}/inventory.json` (absolute
topology, trajectory, `pocket_mapped`, `global_mapped`, and the files in
that folder). HITL `pwd` prints that inventory. Analysis resolves
`pocket_mapped.json` from inventory first; the parent-folder walk is the
fallback. Discovery looks under both the current protein folder and the
campaign base (`cross_sim/`, `analysis/`), so combined-reporter inventories
at `{base}/reporter/` also resolve shared maps.

Per-rep analysis still writes `analysis/repXX/inventory.json` after wrap
and fan-out. Campaign snapshots remain `campaign/state.json` and
`{label}/state.json`. Token usage is written to `llm_usage.json` and
tagged by workflow node (`planner`, `analysis`, `reporter`, …).
## Pre-combined: LLM compiles, engine executes

Pre-combined is **not** a hardcoded kinase-only pocket path.

| Role | Who | What |
|------|-----|------|
| Compile | LLM (once) | Chooses combined/shared tools: `define_reference_consensus_pocket`, a custom pocket tool, MSA, phylo, or any other structure-only setup every sim will consume |
| Required shared setup | Family `CampaignSpec` | MSA + reference pocket + residue map + MSA plots are **added if omitted**, never used to delete LLM extras |
| Execute | Engine | Runs the compiled shared setup protocol identically on retry |
| Fallback | Deterministic MSA+pocket | Only if the LLM plan is empty or leaves no `cross_sim/` artifacts |

Traj overlays, Ward clustering, and `run_consensus_pocket_metrics_batch` are
blocked in pre-combined (they need trajectories). They run in post-combined
or per-sim analysis.

Generic (non-family) campaigns: the LLM may turn pre-combined on and pick
any allowed combined tools; nothing is pinned.

Code: `agentic/campaign/` (`campaign.yaml`, `config.py`, `pre_combined.py`),
`agentic/retrieval/` (tools + knowledge), `agentic/utils/sandbox_files.py`,
`src/analysis/inventory.py`.
