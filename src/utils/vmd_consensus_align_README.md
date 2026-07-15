# VMD consensus alignment — examples

Script: `src/utils/vmd_consensus_align.tcl`  
Alias table: `src/utils/protein_aliases.csv` (UniProt → display name)

## Why `load_pdbs ./` loaded 0

Residue maps use **display names** (`MLKL`, `JAK1`), but PDBs copied from
`pseudoKin/` are usually named by **UniProt ID** (`q8nb16.pdb`, `p23458.pdb`).
Also `load_pdbs` takes a **directory**, not a glob (`./\*.pdb` is invalid).

## Correct usage

```tcl
source /path/to/vmd_consensus_align.tcl

load_map reference_msa_residue_map.csv
# Map q8nb16.pdb → MLKL, p23458.pdb → JAK1, …
load_aliases protein_aliases.csv
# or: load_aliases reference_pca_manifest.json

load_pdbs .                 ;# directory only — NOT ./*.pdb
align_all MLKL
show JAK1 JAK3 MLKL
show_consensus JAK1 JAK3 MLKL
```

## One file

```tcl
load_pdb JAK1 ./p23458.pdb
# or after aliases:
load_pdb MLKL ./q8nb16.pdb
```

## Files to copy next to your PDBs

| File | Role |
|------|------|
| `reference_msa_residue_map.csv` or `reference_pocket_residue_map.csv` | consensus residues |
| `protein_aliases.csv` | UniProt ↔ display name |
| `*.pdb` | structures (`q8nb16.pdb`, …) |
