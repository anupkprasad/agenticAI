#!/usr/bin/env bash
# Remove stale COMBINED-LEVEL pseudoKin analysis so --combined-only can rebuild
# reference MSA, reference FEL, reference pocket, and reference-based clustering.
#
# Does NOT touch per-simulation trajectories or per-sim analysis/ (independent FEL,
# ligand-pocket metrics, etc.). Optional second pass removes legacy mirrored reference
# copies under each {uniprot}/analysis/ (see CLEAN_PER_SIM_MIRROR below).
#
# Usage (from repo root):
#   bash scripts/clean_pseudokin_combined_analysis.sh
#   bash scripts/clean_pseudokin_combined_analysis.sh --per-sim-mirror

set -euo pipefail
BASE="${1:-pseudoKin}"
AN="${BASE}/analysis"
CLEAN_PER_SIM_MIRROR="${CLEAN_PER_SIM_MIRROR:-0}"
if [[ "${1:-}" == "--per-sim-mirror" ]]; then
  CLEAN_PER_SIM_MIRROR=1
  BASE="pseudoKin"
  AN="${BASE}/analysis"
fi

if [[ ! -d "$AN" ]]; then
  echo "No $AN — nothing to clean."
  exit 0
fi

echo "Cleaning combined analysis under $AN ..."

# Legacy classification outputs (non-reference or auto sqrt-k runs)
rm -f "$AN"/classification_*

# Reference-based grouping + clustering (rebuilt by --combined-only)
rm -f "$AN"/reference_grouping_features*
rm -f "$AN"/reference_cluster_assignments.csv
rm -f "$AN"/reference_clusters.json
rm -f "$AN"/reference_clusters_*.png
rm -f "$AN"/ref_fel_pock_features*
rm -f "$AN"/ref_fel_pock_cluster_assignments.csv
rm -f "$AN"/ref_fel_pock_clusters.json
rm -f "$AN"/ref_fel_pock_*.png
rm -f "$AN"/ref_fel_features_table.json
rm -f "$AN"/ref_fel_cluster_assignments.csv
rm -f "$AN"/ref_fel_clusters.json
rm -f "$AN"/ref_fel_*.png

# Legacy archetype naming
rm -f "$AN"/reference_archetype*
rm -f "$AN"/reference_archetypes*

# MSA / alignment inputs (rebuilt from sequences)
rm -f "$AN"/reference_msa_alignment.*
rm -f "$AN"/reference_msa_residue_map.csv
rm -f "$AN"/consensus_alignment.*
rm -f "$AN"/consensus_residue_map.csv

# Reference landscape (legacy + current layout)
rm -rf "$AN"/reference_fel "$AN"/reference_fel_features "$AN"/reference_projected_pca
rm -rf "$AN"/reference_shared_fel
rm -f "$AN"/reference_fel_*.png "$AN"/reference_fel_*.json "$AN"/reference_fel_*.csv
rm -f "$AN"/reference_pca_model.json

# Reference-mapped pocket (combined-only tree)
rm -rf "$AN"/reference_pocket
rm -f "$AN"/reference_pocket_definition.json "$AN"/reference_pocket_residue_map.csv
rm -f "$AN"/reference_pocket_batch_manifest.json
rm -f "$AN"/reference_pocket_*_by_cluster.png
rm -f "$AN"/consensus_pocket_*

# Mixed / legacy cluster validation plots
rm -f "$AN"/com_distance_by_cluster.png "$AN"/contacts_by_cluster.png
rm -f "$AN"/pocket_sasa_by_cluster.png "$AN"/ligand_residence_by_cluster.png
rm -f "$AN"/pocket_rmsf_by_cluster.png "$AN"/ligand_rmsf_by_cluster.png
rm -f "$AN"/consensus_*_by_cluster.png
rm -rf "$AN"/_com_clean

# Ad-hoc batch logs from manual reruns
rm -f "$AN"/refine_pocket_15A.log

echo "Combined cleanup done."

if [[ "$CLEAN_PER_SIM_MIRROR" == "1" ]]; then
  echo "Removing legacy mirrored reference-pocket copies under per-sim analysis/ ..."
  find "$BASE" -mindepth 2 -maxdepth 2 -type d -name analysis | while read -r adir; do
    rm -f "$adir"/reference_fel_* "$adir"/reference_pca_*
    rm -f "$adir"/consensus_pocket_*
    rm -f "$adir"/reference_pocket_*
  done
  echo "Per-sim mirror cleanup done."
fi

echo "Ready for: python SimAgent.py ... --combined-only"
