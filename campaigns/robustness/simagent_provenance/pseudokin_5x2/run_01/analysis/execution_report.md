================================================================================
MD TRAJECTORY ANALYSIS REPORT
================================================================================

Plan Overview: 1. Build a global MAFFT alignment and extract conserved columns (global_mapped.json). 2. Define the reference pocket (15 Å from ATP, intersected with global_mapped). 3. Map that pocket onto each protein via the MSA. 4. Export a single pocket_mapped.json containing all mapped residues. 5. Plot the full MSA and a pocket‑focused panel.
Total Steps: 4
Completed: 4
Issues: 0
Warnings: 0

================================================================================
RESULTS SUMMARY
================================================================================

BUILD_GLOBAL_MAFFT_ALIGNMENT:
  Global MSA (mafft): 5 sequences, 329 aligned columns, 213 global_mapped (similarity>=0.5)

DEFINE_REFERENCE_CONSENSUS_POCKET:
  Defined pocket_mapped: 111 residues (reference=p17612_ATP, cutoff=15.0 Å, 15Å shell=144)

AGGREGATE_POCKET_MAPPINGS:
  Mapped pocket_mapped residues to 5/5 simulations

PLOT_GLOBAL_AND_POCKET‑FOCUSED_MSAS:

================================================================================
