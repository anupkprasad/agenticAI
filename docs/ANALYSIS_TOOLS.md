# Analysis Tools Reference

**This file is the analysis-tool handbook.** For each trajectory tool it
states the observable, the theory, standard output filenames, and how tools
are combined in multi-simulation / classification studies. Implementation
lives in `src/analysis/*.py` and is registered in `agentic/analysis/tools.py`.

**In this file:** multi-chain selection reminder, tool index, global and
binding-site metrics, collective motion, plotting, combined/multi-sim
tools, classification workflow, output names, reporter HTML, source map.

**Not in this file:** GROMACS/MDAnalysis versions and the full chain-map
mechanism ([TOOLS.md](TOOLS.md#multi-chain-residue-map)), agent routing
([ARCHITECTURE.md](ARCHITECTURE.md)), worker/SLURM pools ([POOLS.md](POOLS.md)).

---

## Multi-chain selections (PDB vocabulary → trajectory `resindex`)

GROMACS `.tpr` / `.gro` / `.xtc` files do not store PDB chain IDs. Setup writes
`simsetup/chain_residue_map.json`; analysis translates `chainID B and resid 50:75`
to `resindex …` before `select_atoms`. Full mechanism (build, JSON schema,
phospho/TER cleanup vs this map, what not to do):
[TOOLS.md](TOOLS.md#multi-chain-residue-map).

| User / LLM selection | Trajectory selection |
| --- | --- |
| `chainID B and resid 50:75` | `resindex 389:414` (example) |
| `chainID A and resid 1:10 and name CA` | `name CA and resindex 0:9` |
| `protein` / `resname ATP` | unchanged |

Always include `chainID` when residue numbers overlap across chains.

---

## Quick index

| Category          | Tools                                                                          |
| ----------------- | ------------------------------------------------------------------------------ |
| Global structure  | RMSD, RMSF, Rg, SASA, DSSP, energy                                             |
| Binding / pocket  | COM distance, contacts, pocket SASA/RMSF, residence, consensus pocket          |
| Collective motion | Cartesian PCA/FEL, **modular family dynamics** (torsions, dihedral/cart PCA·tICA) |
| Family consensus  | MSA alignment, consensus torsions, consensus RMSF/DCCM features                 |
| Combined / class. | Overlays, feature table, Ward/k-means clustering                               |
| Interface / proximity | nearby residues (frame 0), min heavy-atom distance, generic COM            |
| Binding site      | ligand-pocket distance, contacts, pocket SASA, residence, pocket RMSF          |
| Collective motion | DCCM, PCA, FEL, FEL features                                                   |
| Plotting          | plot_md_data, plot_pca_projection, combined overlays                           |
| Multi-simulation  | collect_metric_files, compute_comparison_table, collect_fel_features_table, … |

---

## Global structural metrics

### `calculate_rmsd`

**Observable:** Root-mean-square deviation of selected atoms vs a reference structure.

\[
\mathrm{RMSD}(t) = \sqrt{\frac{1}{N}\sum_{i=1}^{N}\left|\mathbf{r}_i(t)-\mathbf{r}_i(\mathrm{ref})\right|^2}
\]

**Default selection:** `protein and name CA`
**Output:** `rmsd.dat`, `rmsd.png` (overall); subset e.g. `rmsd_B_1to34.dat`, `rmsd_B_1to34.png`
**Interpretation:** Low, stable RMSD → folded, equilibrated structure. Large drift → unfolding or domain motion.

---

### `calculate_rmsf`

**Observable:** Per-residue root-mean-square fluctuation after alignment.

\[
\mathrm{RMSF}_i = \sqrt{\left\langle\left|\mathbf{r}_i(t)-\langle\mathbf{r}_i\rangle\right|^2\right\rangle}
\]

**Output:** `rmsf.dat`, `rmsf.png` (overall); subset e.g. `rmsf_1to34.dat`, `rmsf_1to34.png`
**Interpretation:** High RMSF → flexible loops; low RMSF → rigid core or secondary structure.

For a residue range, chain, or proximity subset, **do not overwrite** `rmsf.dat`. Use a qualifier: `rmsf_1to34.dat` / `rmsf_1to34.png`. Overall protein RMSF still uses `rmsf.dat` / `rmsf.png`.

---

### `identify_nearby_residues`

**Observable:** Residues of group *N* that lie within cutoff *d* of query group *Q* at one frame (default frame 0). The neighbor set is **frozen** for later RMSF / COM / min-distance.

**Parameters:** `query_selection`, `neighbor_selection`, `cutoff` (Å), `frame`
**Output:** `nearby_residues.json` + `nearby_residues.csv` (overall); subset e.g. `nearby_residues_A_near_B1to34.json`
**JSON fields:** `mda_selection`, `mda_selection_ca`, `mda_selection_heavy`, residue table
**Downstream:** `calculate_rmsf(..., selection_from_file=...)`, `calculate_com_distance(..., selection2_from_file=...)`, `calculate_min_heavy_atom_distance(...)`.

This is the protein–protein analogue of the ligand-pocket freeze at frame 0. Do **not** re-evaluate `around` every frame if the user asked for “those residues” identified at frame 0.

---

### `calculate_min_heavy_atom_distance`

**Observable:** Per-frame minimum distance between heavy atoms of two selections.

**Output:** `min_distance.csv`, `min_distance.png` (overall); subset e.g. `min_distance_B1to34_vs_nearbyA.csv`
**Interpretation:** Rising min-distance → groups separating; stable low values → interface remains packed.

Use this for protein–protein (or any two groups). Protein–ligand contact counts stay on `calculate_protein_ligand_contacts`.

---

### `calculate_hbond_occupancy`

**Observable:** Hydrogen-bond occupancy between two protein selections (D–A ≤ 3.5 Å, angle ≥ 150°).

**Parameters:** `selection1`, `selection2`, `label1`, `label2`, `d_a_cutoff`, `angle_cutoff`
**Output:** `hbond_occupancy.csv` + `.png` (overall); subset e.g. `hbond_occupancy_B1to34_vs_A.csv`
**Also writes:** `{stem}_atoms.csv`, `{stem}_count.csv` / `{stem}_count.png`
**Interpretation:** High occupancy residue pairs are the persistent H-bond interaction partners.

Do **not** use `calculate_protein_ligand_contacts` for chain–chain H-bonds.

---

### `calculate_salt_bridge_distances`

**Observable:** Minimum charged-atom distance for complementary pairs (Arg/Lys/His/N-terminus vs Asp/Glu). Occupancy = fraction of frames below 4 Å.

**Output:** `saltbridge_occupancy.csv` + `.png`; subset e.g. `saltbridge_occupancy_B1to34_vs_A.csv`
**Also writes:** `{stem}_distances.csv` / `{stem}_distances.png`
**Interpretation:** Occupancy ≥ ~50% and a flat short distance → a stability-determining salt bridge.

---

### `calculate_radius_of_gyration`

**Observable:** Radius of gyration \(R_g\) — compactness of an atom group.

\[
R_g = \sqrt{\frac{\sum_i m_i |\mathbf{r}_i-\mathbf{r}_{\mathrm{COM}}|^2}{\sum_i m_i}}
\]

**Output:** `gyration.dat`, `gyration.png`

---

### `calculate_sasa`

**Observable:** Solvent-accessible surface area via GROMACS `gmx sasa` (Shrake–Rupley algorithm).

**Output:** `sasa.csv`
**Interpretation:** Increased SASA → unfolding or pocket opening.

---

### `analyze_secondary_structure` (DSSP)

**Observable:** Secondary-structure fractions per frame (helix, sheet, coil).

**Output:** `dssp.dat`, `dssp.png`

---

### `analyze_energy`

**Observable:** Potential energy and temperature from GROMACS `.edr` file.

**Output:** `energy.dat`, `energy.png`

---

## Binding-site & protein–ligand tools

All pocket-based tools use the **same pocket definition**:

> At **frame 0**, pocket atoms = protein atoms within `pocket_cutoff` Å (default 5 Å) of the ligand.

This matches `calculate_ligand_pocket_distance`.

---

### `calculate_ligand_pocket_distance`

**Observable:** Distance between ligand centre-of-mass and pocket centre-of-mass.

**Output:** `ligand_pocket_distance.csv`
**Use:** Binding-site stability; compare mean/std across 35 systems.

---

### `calculate_protein_ligand_contacts`

**Observables (per frame):**

| Column         | Definition                                                                                     |
| -------------- | ---------------------------------------------------------------------------------------------- |
| `n_hbonds`   | Protein↔ligand hydrogen bonds (MDAnalysis`HydrogenBondAnalysis`, d ≤ 3 Å, angle ≥ 150°) |
| `n_contacts` | Heavy-atom pairs with distance ≤ 4 Å                                                         |

**Output:** `protein_ligand_contacts.csv`
**Summary stats:** mean/max contacts and H-bonds; frames with any H-bond.

**Interpretation:** Persistent H-bonds and high contact counts → stable binding footprint.

---

### `calculate_pocket_sasa`

**Observable:** SASA of **pocket subset only** (not whole protein), via `gmx sasa` + generated index group.

**Requires:** `.tpr` topology
**Output:** `pocket_sasa.csv` (time_ns, pocket_sasa_nm²)

**Interpretation:** Lower pocket SASA → buried/closed pocket; increase over time → pocket opening or ligand exposure.

---

### `analyze_ligand_residence`

**Bound criterion (per frame):** ligand has ≥ 1 heavy-atom contact within 5 Å of protein **or** ligand COM within 5 Å of pocket COM.

**Metrics:**

| Metric                  | Meaning                            |
| ----------------------- | ---------------------------------- |
| `fraction_bound`      | Fraction of trajectory spent bound |
| `n_unbinding_events`  | Bound → unbound transitions       |
| `longest_bound_ns`    | Longest continuous bound period    |
| `mean_bound_event_ns` | Mean duration of bound episodes    |

**Outputs:** `ligand_residence.csv`, `ligand_residence.json`

---

### `calculate_pocket_rmsf`

**Observable:** RMSF for **Cα atoms of pocket residues only** (after protein Cα alignment).

**Output:** `pocket_rmsf.dat` (Residue, ResName, RMSF), `pocket_rmsf.png`
**Interpretation:** Flexible pocket vs rigid lock-and-key binding across protein family.

Note: `.dat` files include string columns (`ResName`); `plot_md_data` parses numeric columns automatically.

---

### `calculate_ligand_rmsf`

**Observable:** Per-atom RMSF of **ligand heavy atoms** after aligning trajectory on protein Cα.

\[
\mathrm{RMSF}_i = \sqrt{\left\langle\left|\mathbf{r}_i(t)-\langle\mathbf{r}_i\rangle\right|^2\right\rangle}
\]

**Outputs:** `ligand_rmsf.dat`, `ligand_rmsf.json` (mean/max/std summary), `ligand_rmsf.png`

**Interpretation:** High mean ligand RMSF → flexible ATP in the pocket; low → rigidly anchored ligand. Use **`mean_ligand_rmsf_A`** in the classification table alongside pocket RMSF and residence time.

---

## Collective motion

### `calculate_dccm`

**Observable:** Dynamic cross-correlation matrix of Cα motions.

\[
C_{ij} = \frac{\langle \Delta\mathbf{r}_i \cdot \Delta\mathbf{r}_j \rangle}{\sqrt{\langle|\Delta\mathbf{r}_i|^2\rangle\langle|\Delta\mathbf{r}_j|^2\rangle}}
\]

**Output:** `dccm_matrix.csv`, `dccm_heatmap.png`

---

### `calculate_trajectory_pca`

**Method:** Align trajectory; build covariance of atomic coordinates; diagonalise → principal components.

**Defaults:** Cα selection, 10 components, every frame (`frame_interval=1`)
**Outputs:** `pca_projections.dat`, `pca_variance.dat`

---

### `calculate_free_energy_landscape`

**Method:** 2D histogram of PC1 and PC2 → probability \(P\); convert to free energy:

\[
F = -k_B T \ln P \quad\text{(kJ/mol, minimum set to 0)}
\]

**Defaults:** PC1 vs PC2, 50 bins, T = 310 K
**Outputs:** `fel_pc1_pc2.png`, `fel_pc1_pc2_grid.csv`

---

### `analyze_fel_landscape_features`

Extracts **classification features** from the FEL for comparing conformational diversity across simulations.

#### How basins are counted (max 8)

The reported **`n_basins`** (alias `n_minima`) is **not** the raw count of every grid dip. The algorithm is:

1. **Smooth** F with a Gaussian filter (σ = 2.0 by default).
2. **Detect local minima** on the smoothed surface (each cell lower than all 8 neighbours, with minimum **prominence** ≥ 1.5 kJ/mol or 8% of the F range).
3. **Assign basins:** steepest descent from each grid cell to its nearest minimum; **population** \(p_i\) = sum of probability in that basin.
4. **Filter & merge:**
   - Drop basins with population < 5% (default).
   - While more than 8 basins remain, merge the **smallest** basin into the **largest**.
   - Stop when ≤ 8 basins and all meet the population threshold.

Only these **final numbered basins (1…n)** appear on `fel_basins.png` as red stars with labels.

#### Metrics

| Metric                 | Formula / definition                                               |
| ---------------------- | ------------------------------------------------------------------ |
| Basin depth            | max F in basin − F at minimum (kJ/mol)                            |
| Basin area             | Grid-cell fraction; population = frame occupancy                   |
| Barrier height         | Saddle F along path between minima − lower minimum                |
| Major basin population | max(pᵢ)                                                           |
| Landscape entropy      | \(S = -\sum_i p_i \ln p_i\) over **final** basin populations |

**Outputs:** `fel_features.json`, `fel_features.csv`, `fel_basins.csv`, `fel_basins.png`

Higher **landscape entropy** → more evenly distributed conformational states → higher diversity.

---

### `export_fel_basin_structures`

**Purpose:** Write one **representative PDB per numbered FEL basin** (same basins as `fel_basins.png`, max 8) so you can load transient conformations in PyMOL/Chimera.

**Algorithm:**

1. Read basin minima from `fel_features.json` (`min_x`, `min_y` on the PC1/PC2 grid)
2. Find the trajectory frame whose (PC1, PC2) is closest to each basin minimum
3. Extract that frame from `hpc/mdWrap.xtc` (protein + ligand, aligned)

**Outputs** (under `{sim}/analysis/`):

| File                                   | Description                                                     |
| -------------------------------------- | --------------------------------------------------------------- |
| `basin_01.pdb`, `basin_02.pdb`, … | One structure per basin (in`{sim}/analysis/`)                 |
| `fel_basin_structures.csv`           | basin_id, population, PC coords, frame_index, time_ns, pdb_file |

```python
from src.analysis.pca_analyzer import export_fel_basin_structures
export_fel_basin_structures.func(
    working_dir="agenticB5R1/o15197/analysis",
    topology_file=".../hpc/md.tpr",
    trajectory_file=".../hpc/mdWrap.xtc",
)
```

Runs automatically after `analyze_fel_landscape_features` when FEL is requested.

---

## Plotting helpers

| Tool                    | Purpose                                  |
| ----------------------- | ---------------------------------------- |
| `plot_md_data`        | Line plot from`.dat` / `.csv`        |
| `plot_pca_projection` | PCx vs PCy scatter (time-coloured)       |
| `plot_md_multipanel`  | Multi-panel figures                      |
| `wrap_trajectory`     | PBC-correct traj centering Protein+ATP (`gmx trjconv`); skip if `mdWrap.xtc` exists |

---

## Multi-simulation (combined) tools

Run at `{base}/analysis/` after all per-simulation runs complete.

| Tool                                      | Purpose                                                                                       |
| ----------------------------------------- | --------------------------------------------------------------------------------------------- |
| `collect_metric_files`                  | Gather standard filenames from each`{base}/{label}/analysis/`                               |
| `plot_combined_overlay`                 | Overlay RMSD/RMSF/Rg/energy traces                                                            |
| `compute_comparison_table`              | Mean/std/min/max per metric per simulation                                                    |
| `run_combined_com_distance_analysis`    | Overlay ligand-pocket distances                                                               |
| `run_combined_binding_rmsf_overlay`     | Overlay pocket or ligand RMSF profiles across holo sims                                       |
| `run_combined_rmsf_segment_analysis`    | Bar chart for residue window                                                                  |
| `collect_fel_features_table`            | One CSV of FEL features for all sims → clustering / ML                                       |
| `collect_classification_features_table` | **Full feature matrix** — binding + FEL scalars; raw + z-score CSV + XLSX              |
| `cluster_classification_features`       | Hierarchical (default) or k-means on z-score matrix + labeled PCA/dendrogram/phylo-tree plots |
| `plot_cluster_feature_trajectories`     | After clustering: one PNG per time-series metric,**one subplot per cluster**            |
| `plot_cluster_rmsf_profiles`            | After clustering: pocket/ligand RMSF profiles,**one subplot per cluster**               |
| `build_sequence_phylo_tree`             | **On request**: sequence-based phylogenetic tree from sequences extracted from each input PDB (pairwise % identity → UPGMA) |
| `build_structure_phylo_tree`            | **On request**: structure-based phylogenetic tree from CA coordinates (sequence-guided superposition → CA-RMSD → UPGMA)     |
| `build_consensus_sequence_alignment`    | Star MSA to a reference (PDB list / FASTA / sim_dirs) → `consensus_alignment.fasta` + `consensus_residue_map.csv` |
| `plot_reference_msa_alignment`          | Plot full star-MSA + high-consensus/pocket column panels (after alignment; optional pocket JSON) |
| `fit_reference_pca_model`               | Fit PCA on consensus Cα from a reference trajectory |
| `project_simulations_reference_pca`     | Project all trajectories onto the reference PCA basis |
| `build_shared_reference_fel_landscapes` | FEL in a **shared** PC1/PC2 grid from reference-projected PCA |
| `cluster_reference_fel_landscapes`      | Cluster shared-reference FEL features → dendrogram + phylo tree |
| `run_reference_landscape_pipeline`      | End-to-end wrapper: alignment → PCA → shared FEL → clustering |

---

## Reference-mapped pocket

When ATP does not sit uniformly in the nucleotide pocket across pseudokinases,
define the pocket on a **reference** structure and map residues to all systems
via ``consensus_alignment.json``.

| Tool | Purpose |
| --- | --- |
| `define_reference_consensus_pocket` | Reference pocket = star-MSA consensus positions whose reference resid is within ``pocket_cutoff_A`` (default 15 Å) of the ligand at frame 0 |
| `map_consensus_pocket_residues` | Per-simulation PDB resid lists + coverage audit |
| `calculate_consensus_pocket_metrics` | One sim: COM distance, pocket SASA, pocket-restricted contacts, residence, pocket RMSF |
| `run_consensus_pocket_metrics_batch` | End-to-end for all simulations |
| `plot_reference_msa_alignment` | Visualize star MSA (full + filtered pocket/high-consensus columns) |

**Outputs:** ``{base}/analysis/reference_pocket_definition.json``,
``reference_pocket_residue_map.csv``, and per-protein metrics under:
``{base}/analysis/reference_pocket/{uniprot}/reference_pocket_*.csv/dat/json``.
This is a combined-analysis tree; reference-pocket outputs are not written to
``{uniprot}/analysis/``.

**Classification:** use metric group ``reference_pocket`` in
``collect_classification_features_table`` (columns prefixed
``reference_pocket_``).

Requires prior ``build_consensus_sequence_alignment`` and holo trajectories with ATP.

---

## Reference-projected landscape clustering

For cross-simulation comparison when per-simulation PCA/FEL live in
incomparable coordinate systems, use the **reference landscape** tools.
Triggered when the user goal mentions *reference-projected PCA*,
*consensus sequence alignment*, *shared reference FEL*, or
``run_reference_landscape_pipeline`` (see ``detect_reference_landscape_requested``
in ``agentic/planner/planning_guidelines.py``).

**Typical workflow (modular or single wrapper):**

| Step | Tool | Outputs (`{base}/analysis/`) |
| --- | --- | --- |
| 1 | `build_consensus_sequence_alignment` | `consensus_alignment.fasta`, `consensus_residue_map.csv`, `consensus_alignment.json` |
| 2 | `fit_reference_pca_model` | `reference_pca_model.json` |
| 3 | `project_simulations_reference_pca` | `reference_fel/{label}/reference_pca_projections.dat` |
| 4 | `build_shared_reference_fel_landscapes` | `reference_fel/{label}/reference_fel_pc1_pc2.png`, `reference_fel/{label}/reference_fel_basins.png`, `reference_fel/{label}/fel_features.json`, `reference_fel_features_table.json` |
| 5 | `cluster_reference_fel_landscapes` | `reference_fel_cluster_assignments.csv`, `reference_fel_dendrogram.png`, `reference_fel_phylo_tree.png` |

Or run **`run_reference_landscape_pipeline`** with ``reference_label`` (e.g.
``q8nb16`` for MLKL). After clustering, the agent runs
``plot_cluster_feature_trajectories`` and ``plot_cluster_rmsf_profiles`` using
``reference_fel_cluster_assignments.csv`` for mechanistic validation.

**Consensus alignment inputs (one of):**

- ``pdb_files`` + ``labels``
- ``fasta_file`` (reference label must appear in FASTA)
- ``sim_dirs`` + ``labels`` (PDB auto-resolved)

Consensus columns = reference residues mapped in ≥ ``min_coverage`` fraction of
sequences (default 0.95). Review ``consensus_residue_map.csv`` before PCA.

**Reference PCA:** consensus Cα only (no ATP in coordinates). Each trajectory
is Kabsch-aligned to the reference consensus Cα frame before projection.

---

## Phylogenetic trees (sequence & structure)

Two on-demand combined-analysis tools build phylogenetic trees across all
simulations. They run **only when the user explicitly asks** for a
phylogenetic / sequence / structure tree — the request is detected by
`detect_phylo_tree_requested()` in `agentic/planner/planning_guidelines.py`
(a bare "phylogenetic tree" defaults to the sequence tree). These are distinct
from the FEL-feature `classification_phylo_tree.png`, which is derived from
dynamics features rather than the provided structures.

Both tools resolve a PDB per simulation (base-level `{base}/{label}.pdb` first,
then per-sim reporter frames / FEL basins), extract sequences with Biopython,
and reuse the circular phylogram renderer from `classification_clustering.py`
so the figures match the existing tree style.

| Tool | Distance metric | Outputs (in `{base}/analysis/`) |
| --- | --- | --- |
| `build_sequence_phylo_tree`  | `1 − pairwise % identity` (BLOSUM62 global alignment) | `sequence_phylo_tree.png`, `sequence_phylo_tree.nwk`, `sequence_phylo_distance_matrix.csv` |
| `build_structure_phylo_tree` | CA-RMSD after sequence-guided Kabsch superposition of common residues | `structure_phylo_tree.png`, `structure_phylo_tree.nwk`, `structure_phylo_distance_matrix.csv` |

Trees are clustered with UPGMA (`scipy` average linkage), colored by up to six
sub-clusters, and logged to `analysis_summary.jsonl` as
`Sequence_Phylogenetic_Tree` / `Structure_Phylogenetic_Tree`. The combined
report renders them in a dedicated **Phylogenetic Trees** section.

---

## Modular family dynamics (torsions / PCA / tICA)

Atomic tools for family-level MD. The **planner schedules only tools named in the
user goal** — there is no hard-wired mega feature list.

| Tool | Scope | Role |
| --- | --- | --- |
| `calculate_consensus_torsions` | per_sim | Consensus-mapped φ/ψ/χ₁ (+ sin/cos matrix, circular means) |
| `run_consensus_torsions_batch` | shared | Batch torsions for all sims under a base directory |
| `run_independent_dynamics_fel` | per_sim | PCA or tICA on **dihedral** or **cartesian** space → FEL + `grid_entropy` |
| `fit_dynamics_model` | shared | Fit shared-reference PCA/tICA on one `reference_label` |
| `project_dynamics_model` | per_sim | Project one sim onto a fitted model → FEL |
| `run_shared_dynamics_fel_batch` | shared | Fit + project all labels |
| `calculate_consensus_rmsf_features` | per_sim | Mapped Cα RMSF mean/std |
| `calculate_consensus_dccm_features` | per_sim | Mapped DCCM scalars (incl. N↔C lobe mean corr) |

**Kwargs that control flexibility**

- `space`: `dihedral` \| `cartesian`
- `method`: `pca` \| `tica`
- Independent vs shared: choose `run_independent_dynamics_fel` **or**
  `fit_dynamics_model` + `project_dynamics_model` (goal text: “independent” vs
  “shared reference / project onto …”).

**Output dirs** (under `{label}/analysis/`): `consensus_dihedrals/`,
`consensus_PCA/`, `consensus_TICA/`, `consensus_cart_PCA/`, `consensus_cart_TICA/`,
and `*_ref` variants for shared-reference mode.

**Classification collection**

- Pass `requested_metric_groups` such as `dihedral_pca`, `consensus_torsions`,
  `consensus_rmsf`, `consensus_dccm`, `cart_tica`, …
- Or exact `feature_columns=[...]`
- Or `auto_discover=True` to include modular scalars found on disk
- Do **not** assume a fixed ment-style 9/12-feature bundle

Example goal:

> For all systems: consensus φ/ψ/χ₁, independent dihedral PCA FEL entropy, pocket
> χ₁ circular mean, reference pocket COM/angle, consensus RMSF mean/std, DCCM N–C;
> then Ward-cluster on those columns.

---

## Classification: how to use the data together

### Step 1 — Per simulation (×35)

Run the same pipeline in each `{base}/{label}/analysis/`:

```
ligand_pocket_distance → protein_ligand_contacts → pocket_sasa →
analyze_ligand_residence → pocket_rmsf → calculate_ligand_rmsf →
calculate_trajectory_pca → calculate_free_energy_landscape →
analyze_fel_landscape_features
```

Each tool writes **scalar summaries** (JSON or CSV stats) plus time series where needed.

### Step 2 — Consolidate (only if user requested classification)

The framework runs `collect_classification_features_table` **only** when the goal
explicitly mentions classification, clustering, unsupervised analysis, or a feature
matrix. It is **not** part of default combined analysis.

**Which columns appear** depends on metrics named in the goal:

| User says                                      | Metric groups featurized                                                      |
| ---------------------------------------------- | ----------------------------------------------------------------------------- |
| "unsupervised classification" (no list)        | Default: com, contacts, pocket_sasa, residence, pocket_rmsf, ligand_rmsf, fel |
| "classify using RMSF and pocket distance only" | `pocket_rmsf`, `com` only                                                 |
| "classification with FEL and contacts"         | `fel`, `contacts` (+ run PCA/FEL per sim first)                           |

```python
from src.analysis.classification_collector import collect_classification_features_table
collect_classification_features_table.func(
    base_directory="/path/to/agenticB5R1",
    working_dir="/path/to/agenticB5R1/analysis",
    requested_metric_groups=["pocket_rmsf", "com"],  # optional; omit for default bundle
)
```

**Outputs:**

| File                                   | Use                                                               |
| -------------------------------------- | ----------------------------------------------------------------- |
| `classification_features.csv`        | Raw values (Å, nm², fractions) — interpret physically          |
| `classification_features_zscore.csv` | Z-scores across simulations —**input for clustering / ML** |
| `classification_features.xlsx`       | Same data + feature dictionary (README, Raw, ZScore sheets)       |
| `classification_features.json`       | Column list, definitions, normalization notes                     |

**Which file is used for classification?**

`cluster_classification_features` reads **`classification_features_zscore.csv`** by default (`features_file` parameter). The raw CSV is never fed directly into hierarchical clustering or k-means — only z-scored columns are used so features on different scales (contacts ~50, entropy ~1.5, distance ~Å) contribute equally.

**One row = one protein–ATP system.** Which columns appear depends on `requested_metric_groups` in the user goal (default bundle below).

---

### Classification feature dictionary

All possible columns are defined in `CLASSIFICATION_FEATURE_DEFINITIONS` (`src/analysis/classification_collector.py`). Metric groups map to columns as follows:

| Metric group    | Columns                                                                                                                     | Per-sim source                  | Calculation summary                                                                        |
| --------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------ |
| `com`         | `ligand_pocket_distance_mean_A`, `ligand_pocket_distance_std_A`                                                         | `ligand_pocket_distance.csv`  | Mean / std of ligand–pocket COM distance over frames (Å)                                 |
| `contacts`    | `mean_contacts`, `mean_hbonds`, `max_contacts`                                                                        | `protein_ligand_contacts.csv` | Mean of`n_contacts`, mean of `n_hbonds`, max contacts                                  |
| `pocket_sasa` | `mean_pocket_sasa_nm2`, `std_pocket_sasa_nm2`                                                                           | `pocket_sasa.csv`             | Mean / std of pocket SASA (nm²)                                                           |
| `residence`   | `fraction_bound`, `n_unbinding_events`, `longest_bound_ns`, `mean_bound_event_ns`                                   | `ligand_residence.json`       | Bound fraction, unbinding count, longest/mean bound duration (ns)                          |
| `pocket_rmsf` | `mean_pocket_rmsf_A`, `max_pocket_rmsf_A`                                                                               | `pocket_rmsf.dat`             | Mean / max per-residue RMSF in pocket (Å)                                                 |
| `ligand_rmsf` | `mean_ligand_rmsf_A`, `max_ligand_rmsf_A`                                                                               | `ligand_rmsf.json` / `.dat` | Mean / max ligand atom RMSF (Å)                                                           |
| `fel`         | `n_basins`, `landscape_entropy`, `major_basin_population`, `max_barrier_height_kJ_mol`, `mean_basin_depth_kJ_mol` | `fel_features.json`           | Basin count, S = −Σ p ln p, largest basin occupancy, max barrier and mean depth (kJ/mol) |
| `rmsd`        | `mean_rmsd_A`, `std_rmsd_A`                                                                                             | `rmsd.dat`                    | Mean / std protein Cα RMSD (Å)                                                           |
| `rmsf`        | `mean_protein_rmsf_A`, `max_protein_rmsf_A`                                                                             | `rmsf.dat`                    | Mean / max protein Cα RMSF (Å) —**overlays only; not used for classification**    |
| `rg`          | `mean_rg_A`, `std_rg_A`                                                                                                 | `gyration.dat`                | Mean / std radius of gyration (Å)                                                         |
| `sasa`        | `mean_protein_sasa_nm2`, `std_protein_sasa_nm2`                                                                         | `sasa.csv` / `sasa.dat`     | Mean / std whole-protein SASA (nm²)                                                       |
| `energy`      | `mean_potential_energy_kJ_mol`                                                                                            | `energy.dat`                  | Mean potential energy (kJ/mol)                                                             |
| `dccm`        | `mean_abs_dccm`                                                                                                           | `dccm_summary.json`           | Mean\|cross-correlation\| of Cα fluctuations (0–1)                                       |

**Default classification bundle** (when the goal says "classification" without naming metrics):

`com`, `contacts`, `pocket_sasa`, `residence`, `pocket_rmsf`, `ligand_rmsf`, `fel` — **20 features**.

Whole-protein RMSF (`rmsf` group: `mean_protein_rmsf_A`, `max_protein_rmsf_A`) is **not** used for classification. Pocket flexibility is captured by `pocket_rmsf` (`mean_pocket_rmsf_A`, `max_pocket_rmsf_A`). If the user goal mentions generic "RMSF", the collector maps that to `pocket_rmsf`, not whole-protein `rmsf`.

Each row also includes:

| Column                 | Meaning                                               |
| ---------------------- | ----------------------------------------------------- |
| `label`              | Simulation folder name (e.g.`p23458`)               |
| `sim_directory`      | Absolute path to`{base}/{label}/`                   |
| `n_features_present` | Count of non-null feature columns for that simulation |

---

### Z-scores: definition and calculation

A **z-score** expresses how many standard deviations a simulation's feature value is from the cohort mean for that feature:

\[
z_i = \frac{x_i - \mu}{\sigma}
\]

where:

- \(x_i\) = raw scalar for simulation \(i\) and feature column \(j\)
- \(\mu\) = mean of column \(j\) across **all simulations with a non-null value**
- \(\sigma\) = standard deviation of column \(j\) across those same simulations (if \(\sigma < 10^{-12}\), use 1.0 to avoid division by zero)

**Important rules:**

1. Z-scoring is **across simulations**, one value per feature per sim — **not** within a single trajectory time series.
2. Simulations with missing data for a column are **excluded from μ and σ** for that column but still get a z-score if their raw value exists.
3. If fewer than two simulations have a value for a column, z-scores are left blank for that column.
4. **`fraction_bound`**, **`n_unbinding_events`**, etc. are z-scored like any other numeric column when they vary across sims; when all sims share the same value (e.g. all `fraction_bound = 1.0`), σ ≈ 0 and z-scores become 0.

**Example** (`agenticB5R1`, default bundle, 8 holo systems):

| File                                   | Role                                                                                |
| -------------------------------------- | ----------------------------------------------------------------------------------- |
| `classification_features.csv`        | Raw:`ligand_pocket_distance_mean_A = 2.64` (o15197), `mean_contacts = 51.2`, … |
| `classification_features_zscore.csv` | Normalized: same row might show`-0.61` for distance mean, `-0.71` for contacts  |
| `classification_features.xlsx`       | Sheets:`README`, `Feature_Definitions`, `Raw_Features`, `ZScore_Features`   |

---

### Step 3 — Normalization for classification

**Yes — features are normalized before clustering.** The pipeline automatically writes z-scores; you do **not** need a separate normalization step.

| Method                           | Recommended input                                                        |
| -------------------------------- | ------------------------------------------------------------------------ |
| k-means, hierarchical clustering | `classification_features_zscore.csv` or XLSX `ZScore_Features` sheet |
| PCA / UMAP visualization         | z-score columns                                                          |
| Random forest / SVM (supervised) | z-score or raw (tree models handle scales; SVM prefers z-score)          |
| Reporting / thresholds           | `classification_features.csv` (raw)                                    |

**Do not** z-score within a single simulation time series — only **across simulations** for each summary feature.

### Step 4 — Clustering (`cluster_classification_features`)

After the feature table is built, run **`cluster_classification_features`** on the z-score CSV (automatic in combined analysis when classification is requested).

| Parameter          | Default                 | Notes                                                         |
| ------------------ | ----------------------- | ------------------------------------------------------------- |
| `method`         | `hierarchical`        | Set`kmeans` if the goal mentions k-means                    |
| `linkage_method` | `ward`                | Ward, average, or complete (hierarchical only)                |
| `n_clusters` (k) | auto (√n, capped 2–8) | Number of groups to cut the tree into; e.g. k=3 → 3 clusters |
| `user_goal`      | —                      | Parses`p23458:JAK1` style maps for plot labels              |

**Outputs** (under `{base}/analysis/`):

| File                                       | Description                                                                |
| ------------------------------------------ | -------------------------------------------------------------------------- |
| `classification_cluster_assignments.csv` | label, display_name, cluster_id, method                                    |
| `classification_clusters_pca.png`        | 2D PCA scatter, colored by cluster,**protein name annotations**      |
| `classification_dendrogram.png`          | Hierarchical dendrogram with protein names (hierarchical only)             |
| `classification_phylo_tree.png`          | Unrooted circular phylogenetic tree colored by cluster (hierarchical only) |
| `classification_clusters.json`           | Parameters + assignment summary                                            |

**What does k mean on the dendrogram?**

In hierarchical clustering, **k** is the **number of clusters** (groups) you want. The dendrogram shows how simulations merge step-by-step from bottom (most similar pairs) to top (everything in one group). The plot title `Hierarchical clustering dendrogram (k=3)` means the tree was **cut into 3 groups** using `scipy.cluster.hierarchy.fcluster(..., criterion="maxclust")`.

- **k = 3** → each protein is assigned to cluster 1, 2, or 3 (see `classification_cluster_assignments.csv`)
- **Auto k** (when not specified): `k = round(√n)` capped between 2 and 8. For 8 proteins, auto k = 3.
- **Change k**: pass `n_clusters=5` or write "5 clusters" in the user goal

The dendrogram itself shows merge **heights** (dissimilarity); k is the cut level that yields that many final groups — not a parameter of the linkage algorithm itself.

### Step 4b — Cluster-wise trajectory plots (`plot_cluster_feature_trajectories`)

After cluster assignments exist, run **`plot_cluster_feature_trajectories`** to compare **time-series** features grouped by cluster. Each metric produces one figure with **k subplots** (one panel per cluster); proteins in the same cluster are overlaid in that panel.

| Metric group    | Output file                         | Y-axis                                   |
| --------------- | ----------------------------------- | ---------------------------------------- |
| `pocket_sasa` | `pocket_sasa_by_cluster.png`      | Pocket SASA (nm²) vs time               |
| `com`         | `com_distance_by_cluster.png`     | Ligand–pocket COM distance (Å) vs time |
| `contacts`    | `contacts_by_cluster.png`         | Heavy-atom contacts vs time              |
| `residence`   | `ligand_residence_by_cluster.png` | Bound state (0/1) vs time                |

Time-series metrics use **`plot_cluster_feature_trajectories`**. Pocket/ligand RMSF uses **`plot_cluster_rmsf_profiles`** (ordinal residue/atom index on x; one line per protein per cluster panel).

| Profile         | Cluster output                 | Combined output             |
| --------------- | ------------------------------ | --------------------------- |
| `pocket_rmsf` | `pocket_rmsf_by_cluster.png` | `pocket_rmsf_overlay.png` |
| `ligand_rmsf` | `ligand_rmsf_by_cluster.png` | `ligand_rmsf_overlay.png` |

Runs automatically after clustering in combined analysis.

```python
from src.analysis.classification_clustering import (
    plot_cluster_feature_trajectories,
    plot_cluster_rmsf_profiles,
)
plot_cluster_feature_trajectories.func(
    working_dir="agenticB5R1/analysis",
    metric_groups=["pocket_sasa", "com", "contacts"],
)
plot_cluster_rmsf_profiles.func(
    working_dir="agenticB5R1/analysis",
    profile_types=["pocket_rmsf", "ligand_rmsf"],
)
```

```python
from src.analysis.combined_analysis import run_combined_binding_rmsf_overlay
run_combined_binding_rmsf_overlay.func(
    sim_dirs=[...],
    labels=["EPHB6", "JAK1"],
    working_dir="agenticB5R1/analysis",
    profile_type="pocket_rmsf",
)
```

```python
from src.analysis.classification_clustering import cluster_classification_features
cluster_classification_features.func(
    working_dir="agenticB5R1/analysis",
    features_file="classification_features_zscore.csv",
    method="hierarchical",
    user_goal="p23458:JAK1, p29597:TYK2",
)
```

### Step 5 — Classification approaches

**Unsupervised (no labels yet):**

- Load z-score matrix → sims with missing features are skipped automatically
- `cluster_classification_features` (hierarchical default) → inspect cluster assignments and PCA/dendrogram/phylo-tree plots
- Compare clusters to binding/residence/FEL metrics in the raw CSV

**Supervised (when you have labels):**

- Add a `class` column to the CSV (e.g. `stable`, `cryptic`, `active-like`)
- Train random forest or logistic regression on z-score features
- Use cross-validation; keep 5–10 labeled systems as hold-out

**Optional:** merge with literature-based labels (kinase family, pseudokinase, etc.) as categorical features.

### Missing data

`n_features_present` in the CSV counts filled columns. If a sim skipped `pocket_sasa` (no `.tpr`), that column is blank — either impute (column median) or exclude that feature for clustering.

---

## Recommended workflow: 35 protein–ATP classification

**Per simulation** (`{base}/{label}/`):

```
1. calculate_rmsf, calculate_radius_of_gyration
2. calculate_ligand_pocket_distance
3. calculate_protein_ligand_contacts
4. calculate_pocket_sasa          (needs md.tpr)
5. analyze_ligand_residence
6. calculate_pocket_rmsf
7. calculate_ligand_rmsf
8. calculate_trajectory_pca → calculate_free_energy_landscape → analyze_fel_landscape_features
9. plot_md_data (for key CSVs)
```

**Combined** (`{base}/`):

```
collect_classification_features_table
compute_comparison_table
run_combined_com_distance_analysis
```

**Example feature vector per protein** (one row in `classification_features.csv`):

```
ligand_pocket_distance_mean_A, mean_contacts, mean_hbonds, mean_pocket_sasa_nm2,
fraction_bound, n_unbinding_events, mean_pocket_rmsf_A, mean_ligand_rmsf_A,
n_basins, landscape_entropy, major_basin_population, max_barrier_height_kJ_mol
```

---

## Standard output filenames (multi-sim)

Use **identical overall basenames** in every `{label}/analysis/` directory so combined tools can collect them. Subset analyses (one chain, a residue range, residues within X Å) use a **qualifier** and must not overwrite the overall file.

See `agentic/planner/planning_guidelines.py` → `STANDARD_OUTPUT_FILES`.

| Metric                | Overall data file                               | Subset example                         |
| --------------------- | ----------------------------------------------- | -------------------------------------- |
| Analysis summary      | `analysis_summary.jsonl`                        | —                                      |
| RMSD                  | `rmsd.dat`                                      | `rmsd_B_1to34.dat`                     |
| RMSF                  | `rmsf.dat`                                      | `rmsf_1to34.dat`, `rmsf_A_near_B1to34.dat` |
| Rg                    | `gyration.dat`                                | `gyration_chainB.dat`                  |
| Nearby residues       | `nearby_residues.json` (+ `.csv`)             | `nearby_residues_A_near_B1to34.json`   |
| Min heavy-atom dist.  | `min_distance.csv`                            | `min_distance_B1to34_vs_nearbyA.csv`   |
| H-bond occupancy      | `hbond_occupancy.csv`                         | `hbond_occupancy_B1to34_vs_A.csv`      |
| Salt-bridge occupancy | `saltbridge_occupancy.csv`                    | `saltbridge_occupancy_B1to34_vs_A.csv` |
| Generic COM           | `com_distance.csv`                            | `com_distance_B1to34_vs_nearbyA.csv`   |
| Ligand pocket         | `ligand_pocket_distance.csv`                  | —                                      |
| Contacts              | `protein_ligand_contacts.csv`                 |
| Pocket SASA           | `pocket_sasa.csv`                             |
| Residence             | `ligand_residence.csv`                        |
| Pocket RMSF           | `pocket_rmsf.dat`                             |
| Ligand RMSF           | `ligand_rmsf.dat`, `ligand_rmsf.json`       |
| Classification matrix | `{base}/analysis/classification_features.csv` |
| PCA                   | `pca_projections.dat`                         |
| FEL                   | `fel_pc1_pc2_grid.csv`                        |
| FEL features          | `fel_features.json`                           |

Do **not** prefix with simulation label (use `rmsf.dat`, not `p23458_rmsf.dat`).

---

## HTML report outputs (Reporter)

Per-simulation and combined reports use **fixed filenames** so agents, resume logic, and
`--combined-only` can discover them without globbing arbitrary names.

| Scope            | Path                                      | Completion marker                          |
| ---------------- | ----------------------------------------- | ------------------------------------------ |
| Per simulation   | `{base}/{label}/reporter/report.html`     | `analysis_summary.jsonl` + `report.html`   |
| Combined (multi) | `{base}/reporter/combined_report.html`    | `combined_report.html` at project base     |

The Reporter agent always writes per-sim reports as `report.html` (not protein-specific names
like `kinase_report.html`). Combined mode writes `combined_report.html` at the project base.

**Multi-sim phases:** after all per-sim analysis/reporter work, the supervisor advances
`multi_sim_phase` to `combined_analysis` then `combined_reporter`. Combined reporter
completeness is checked only against `{base}/reporter/combined_report.html` — not against
per-sim `report.html` files in individual simulation directories.

**Resume / skip:** parallel pool and `--resume` treat a per-sim reporter as done when
`{label}/analysis/analysis_summary.jsonl` and `{label}/reporter/report.html` both exist.
Combined reporter is done when `{base}/reporter/combined_report.html` exists.

See also [README.md](../README.md) (Output Layout) and [CONVENTIONS.md](CONVENTIONS.md)
(multi-sim phases).

---

## Verifying tools in a checkout

List registered tools:

```bash
python3 -c "from agentic.analysis.tools import get_analysis_tools; print([t.name for t in get_analysis_tools()])"
```

Run a single tool manually:

```python
from src.analysis.binding_site_analyzer import calculate_pocket_rmsf
calculate_pocket_rmsf.func(
    topology_file="/path/to/md.tpr",
    trajectory_file="/path/to/mdWrap.xtc",
    working_dir="/path/to/analysis",
)
```

---

## Source files

| File                             | Tools                                                |
| -------------------------------- | ---------------------------------------------------- |
| `rmsd_calculator.py`           | RMSD                                                 |
| `rmsf_calculator.py`           | RMSF                                                 |
| `gyration_calculator.py`       | Rg                                                   |
| `sasa_calculator.py`           | SASA (whole protein)                                 |
| `com_distance_calculator.py`   | COM distance, ligand-pocket distance                 |
| `proximity_analyzer.py`        | Nearby residues (frame 0), min heavy-atom distance   |
| `binding_site_analyzer.py`     | Contacts, pocket SASA, residence, pocket/ligand RMSF |
| `classification_collector.py`  | `collect_classification_features_table`            |
| `classification_clustering.py` | `cluster_classification_features`                  |
| `dccm_calculator.py`           | DCCM                                                 |
| `pca_analyzer.py`              | PCA, FEL, FEL features                               |
| `dssp_analyzer.py`             | Secondary structure                                  |
| `energy_analyzer.py`           | Energy, trajectory metrics                           |
| `combined_analysis.py`         | Cross-simulation pipelines                           |
