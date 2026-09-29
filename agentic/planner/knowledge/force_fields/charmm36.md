# CHARMM36 / CHARMM36m Force Field

Use when the goal names CHARMM, lipids, or CHARMM-GUI inputs.

## GROMACS name
- Protein: `charmm36-jul2022` / `charmm36` (site-specific port) or `charmm27` in older installs.
- Water: **TIP3P** CHARMM-modified (CHARMM TIP3P), not the AMBER TIP3P default.

## When to use
- Membrane proteins and lipid bilayers (CHARMM36 lipid parameters).
- Systems prepared in CHARMM-GUI.
- Comparisons that must match a CHARMM publication.

## When not to use
- Default SimAgent protein-only or protein–ATP campaigns use **AMBER99SB-ILDN + TIP3P**.
- Do not mix AMBER protein with CHARMM lipids in one topology.

## Ligands
CHARMM CGenFF / CHARMM-GUI ligand reader. Not ACPYPE/GAFF (those pair with AMBER).

## CLI
`--force-field charmm36` (or the installed port name) `--water-model tip3p`.
Confirm `pdb2gmx` lists the FF before submitting HPC.
