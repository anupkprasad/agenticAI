# clean_and_opt — change log

Branch: **`clean_and_opt`** (forked from `main` @ `73238bd`).  
Goal: strip campaign/legacy junk into `archive/`, clarify analysis/reporter tool scopes (**per_sim / combined / shared**), ship missing basics for family-scale MD, and make programmer tool-creation more automatic — without breaking active `pseudo_JAK` work.

User lock-ins: junk → `archive/` (not delete); scope includes `src/`/`agentic/`; more automatic programmer + ship missing std tools; add general-purpose basics; layout `per_sim`/`combined`/`shared`; living log here; **no push until review**.

---

## Phase 1 — Archive (done)

Moved (not deleted) so the framework tree stays focused.

| From | To | Why |
|------|-----|-----|
| `pseudoKin/`, `robustness/`, `dclk3_*`, `docs/ment/` | `archive/campaigns/` then **restored to `campaigns/` at repo root** | Active sims + paper draft (`ment/`); kept gitignored |
| `backup/`, `tmp/`, `garbage/`, empty root `programmer/` | `archive/legacy/` | Old backups and scratch |
| `src/python/`, `src/tcl/` | `archive/legacy/` | Pre-agentic setup/analysis; superseded by `src/simsetup` + agentic |
| `scripts/*` regenerators / holo campaign wrappers | `archive/scripts/pseudokin/` | One-off pseudoKin regenerators |
| `ligand_preprocessor.py`, `workflow_memory.py`, `validate_tools.py` | `archive/orphans/` | Unused / unwired modules |
| `docs/user_goal_snapshot.html`, root `run_simagent.sh`, `server.log` | `archive/docs_snapshots/` or `archive/ops/` | Snapshot / site-specific ops |
| (`ollama_server.slurm` archived then **restored to repo root** for HPC Ollama launches) | `archive/ops/` copy kept | Active ops script |

**Kept in place:** `pseudo_JAK/` (active test campaign), `campaigns/` (sims + `ment/` paper draft), core `SimAgent.py` / `agentic/` / `src/{analysis,hpc,preprocess,reporter,simsetup,supervisor,utils}/`.

See [`archive/README.md`](../archive/README.md).

---

## Phase 2 — Tool taxonomy (done)

- `agentic/analysis/tool_buckets.py` — PER_SIM / COMBINED / SHARED
- `agentic/reporter/tool_buckets.py` — same for reporter (HTML + literature)
- `get_analysis_tools(include_combined=..., include_shared=...)`
- `get_reporter_tools(include_combined=..., include_shared=...)`
- Combined campaigns get combined + shared family tools

---

## Phase 3 — Ship basic MD tools (done)

| Tool | Bucket | Purpose |
|------|--------|---------|
| `calculate_ligand_rmsd` | per_sim | Ligand RMSD after protein alignment |
| `run_trajectory_qc` | per_sim | Frames, dt, box, protein CA RMSD drift |
| `calculate_native_contacts` | per_sim | Native contact fraction vs reference |
| `calculate_backbone_dihedrals` | per_sim | φ/ψ time series |
| `run_consensus_local_fel_batch` | shared | Was scripts-only; LangChain-registered |

Planner metric map + standard output filenames updated for the new metrics.

---

## Phase 4 — Programmer / planner (done)

- `max_tool_creation_iterations`: 2 → **4**
- Extra missing-tool indicators; prompts prefer creating over omitting science
- `scripts/promote_programmer_tool.py` — copy generated `@tool` → `src/analysis/` (manual registry edit)
- Example launcher: `scripts/examples/run_simagent_example.sh`

---

## Phase 5 — Family-scale goal routing (done, light)

- `get_family_scale_planning_guide()` injected into multi-sim master-plan prompt
- Planner analysis capabilities list includes family metrics
- Active campaign trees live under `campaigns/` (restored from archive); README examples may still say `./pseudoKin` — use `./campaigns/pseudoKin` or symlink as needed

---

## Intentionally not done yet

- Deleting `pseudo_JAK` or merging all `run_combined_*` wrappers
- Auto-promoting programmer tools into git without review
- Pushing this branch (awaiting your check)

---

## How to review

```bash
git checkout clean_and_opt
git status
ls archive/
python -c "from agentic.analysis.tool_buckets import summarize_buckets; print(summarize_buckets())"
python -c "from agentic.analysis.tools import get_analysis_tools; print(len(get_analysis_tools()), len(get_analysis_tools(True)))"
```
