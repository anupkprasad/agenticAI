# cross_sim/ — shared pre-combined artifacts

These files are produced **before** per-simulation trajectory analysis so every
system can reuse the same **pocket_mapped** and **global_mapped** residue lists.

## Two maps (independent)

| Map | Meaning |
|-----|---------|
| **pocket_mapped** | Residues of the ATP-binding pocket used for analysis: (reference residues within 15 Å of ligand ATP) **∩ global_mapped**, transferred to every system via the MSA. |
| **global_mapped** | Residues mapped across the common sequence alignment: MAFFT columns with occupancy ≥ 0.25 and physicochemical-group **similarity ≥ 0.5** (paper default; identity / BLOSUM optional). |

## Files

| File | Purpose |
|------|---------|
| `pocket_mapped.json` (`pocket_map.json`) | Per-sim pocket residue lists + MDAnalysis `selection` strings. |
| `global_mapped.json` (`consensus_residues.json`) | Compact similarity-filtered MSA columns (v2). |
| `global_msa.json` | Full reference-indexed MSA (every aligned column) used to transfer the 15 Å pocket. |
| `global_msa.fasta` (`consensus_msa.fasta`) | Gapped MSA (reference first). |
| `pocket_mapped.csv` / `reference_pocket_definition.json` | Full pocket definition + audit from the 15 Å ligand filter. |
| `pre_combined_complete.json` | Gate marker (`success: true` required to advance). |

## `pocket_mapped.json` (human-friendly)

```json
{
  "reference_label": "p17612_ATP",
  "reference_selection": "resname ATP",
  "mapping_kind": "pocket_mapped",
  "per_sim": {
    "p17612_ATP": {
      "resids": [5, 6, 7, 8],
      "selection": "resid 5 6 7 8"
    }
  }
}
```

Python helper: `pocket_selection_for_label(pocket_map, label)`.

## `global_mapped.json` (compact v2)

Instead of one object per consensus index, arrays are stored together:

- `consensus_indices`, `msa_cols`, `reference_resids`, `reference_aas`
- `per_sim[label].resids` / `.aas` / `.seq_indices` (parallel arrays)

Expand to the legacy list-of-dicts form with:

```python
from src.analysis.cross_sim_artifacts import expand_consensus_positions
positions = expand_consensus_positions(json.load(open("global_mapped.json")))
```

MSA defaults: **MAFFT** alignment; `global_mapped` columns kept when
physicochemical-group `similarity` (or `identity` / `blosum` if requested)
≥ `min_conservation` (default **0.5**) and occupancy ≥ `min_coverage`
(default **0.25**). `pocket_mapped` = 15 Å ligand shell ∩ those columns.

## Typical workflow

1. `build_global_mapped_alignment` → `global_msa.*` + `global_mapped.*`
2. `define_pocket_mapped_residues` → 15 Å ATP pocket transferred via full MSA
3. Harvest / normalize → `pocket_mapped.json` + `global_mapped.json` here
4. Per-sim analysis auto-discovers this directory for pocket selections
