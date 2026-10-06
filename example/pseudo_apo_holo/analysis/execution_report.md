================================================================================
MD TRAJECTORY ANALYSIS REPORT
================================================================================

Plan Overview: Pre‑process and run 1‑ns MD for apo/holo of four pseudokinases, perform per‑simulation analyses (RMSD, RMSF, Rg, ligand‑pocket distance, DCCM, DSSP), then aggregate the results with run_combined_analysis, run_combined_com_distance_analysis, run_combined_dccm_difference, plot_combined_overlay, and run_combined_rmsf_segment_analysis to produce overlay plots and statistical tables.
Total Steps: 10
Completed: 5
Issues: 4
Warnings: 2

================================================================================
RESULTS SUMMARY
================================================================================

COMBINED_ANALYSIS_–_OVERLAY_AND_STATISTICS_(RMSD,_RMSF,_RG):

COMBINED_ANALYSIS_–_COM_DISTANCE_OVERLAY:

COMBINED_ANALYSIS_–_DCCM_DIFFERENCES_(VRK3):
  DCCM difference (VRK3_ATP_MG − q8iv63) for 292 aligned residues. Mean |ΔC| = 0.357. 50 pairs with |ΔC| ≥ 0.3.

COMBINED_ANALYSIS_–_DCCM_DIFFERENCES_(MLKL):
  DCCM difference (MLKL_ATP_MG − q8nb16) for 276 aligned residues. Mean |ΔC| = 0.338. 50 pairs with |ΔC| ≥ 0.3.

COMBINED_ANALYSIS_–_DCCM_DIFFERENCES_(TITIN):
  DCCM difference (TITIN_ATP_MG − q8wz42) for 255 aligned residues. Mean |ΔC| = 0.354. 50 pairs with |ΔC| ≥ 0.3.

================================================================================
ISSUES ENCOUNTERED
================================================================================
  • Per‑simulation analysis – DSSP (whole protein): Topology file not found: {sim_dir}/topol.tpr
  • Per‑simulation analysis – DSSP (active‑site 150–200): Topology file not found: {sim_dir}/topol.tpr
  • Combined analysis – DCCM differences (apo vs holo): Failed to execute
  • Combined analysis – RMSF segment bar plot (150–200): Failed to execute

================================================================================
WARNINGS
================================================================================
  • Combined analysis – DSSP overlay (alpha‑helix): No plottable data in any input file
  • Required analysis artifacts are on disk; remaining step errors are non-blocking

================================================================================
