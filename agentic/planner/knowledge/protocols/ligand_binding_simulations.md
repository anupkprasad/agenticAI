# Ligand-Binding Simulation Protocol

## Structure
- Keep the ligand in the processed PDB when the goal is holo / ATP-bound.
- If AlphaFold has no ligand, the supervisor skips the holo case (feasibility guard).
- Parameterise non-standard ligands with ACPYPE/GAFF for AMBER FFs.

## Pocket definition (family campaigns)
1. `global_consensus_msa` — MAFFT columns with physicochemical-group similarity ≥ 0.5
   and occupancy ≥ 0.25 (override in `campaign.yaml`). Legacy name: `global_mapped`.
2. `pocket_mapped` — (reference residues within `pocket_cutoff_A` of the ligand)
   ∩ `global_consensus_msa`, mapped onto every system.

## Per-sim metrics
- `calculate_consensus_pocket_metrics` — COM distance **and** ligand axis-angle.
- Keep `calculate_ligand_pocket_distance` for generic (non-family) goals.

## Production
200 ns unless the goal names another length. Use `--rep-num` for independent seeds.
Analyse the bound replicate’s own `hpc/repXX` trajectory (see `inventory.json`).
