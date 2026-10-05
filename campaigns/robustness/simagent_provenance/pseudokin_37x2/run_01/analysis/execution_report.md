================================================================================
MD TRAJECTORY ANALYSIS REPORT
================================================================================

Plan Overview: Create consensus MSA, pocket mapping, per‑system residue lists, visualizations, and shared‑reference PCA features for the 37 holo kinase structures.
Total Steps: 5
Completed: 4
Issues: 1
Warnings: 0

================================================================================
RESULTS SUMMARY
================================================================================

BUILD_GLOBAL_CONSENSUS_MSA:
  Global MSA (mafft): 37 sequences, 140 global_consensus_msa columns (similarity>=0.5, occupancy>=0.25)

DEFINE_REFERENCE_POCKET:
  Defined pocket_mapped: 85 residues (reference=p17612_ATP, cutoff=15.0 Å, 15Å shell=144)

MAP_POCKET_RESIDUES_TO_EACH_SYSTEM:
  Mapped pocket_mapped residues to 37/37 simulations

PLOT_CONSENSUS_AND_POCKET_MSAS:

================================================================================
ISSUES ENCOUNTERED
================================================================================
  • Compute shared‑reference dihedral PCA features: No consensus_dihedrals with consensus_index schema for reference p17612_ATP under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p17612_ATP/analysis. Run calculate_consensus_torsions first.

================================================================================
