"""
Analysis tool scope buckets for family-scale MD.

- per_sim: run inside one simulation directory
- combined: cross-sim overlays / tables / clustering after all per-sim work
- shared: family reference utilities (MSA, shared PCA/FEL, consensus pocket);
  exposed with combined tools, and documented as usable in both modes
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Set

# Plot aliases kept out of LLM-facing lists (use plot_md_* instead).
INTERNAL_ALIASES = frozenset({"plot_data", "plot_multipanel", "plot_3d"})

PER_SIM_TOOL_NAMES: FrozenSet[str] = frozenset({
    "calculate_rmsd",
    "calculate_rmsf",
    "calculate_radius_of_gyration",
    "calculate_sasa",
    "plot_sasa",
    "analyze_energy",
    "extract_trajectory_metrics",
    "analyze_secondary_structure",
    "plot_md_data",
    "plot_md_multipanel",
    "plot_combined_data",  # per-sim multi-file plot (name is historical)
    "calculate_com_distance",
    "calculate_ligand_pocket_distance",
    "identify_nearby_residues",
    "calculate_min_heavy_atom_distance",
    "calculate_hbond_occupancy",
    "calculate_salt_bridge_distances",
    "calculate_dccm",
    "plot_dccm_comparison",
    "plot_dccm_difference",
    "wrap_trajectory",
    "calculate_trajectory_pca",
    "plot_pca_projection",
    "calculate_free_energy_landscape",
    "analyze_fel_landscape_features",
    "export_fel_basin_structures",
    "calculate_protein_ligand_contacts",
    "calculate_pocket_sasa",
    "analyze_ligand_residence",
    "calculate_pocket_rmsf",
    "calculate_ligand_rmsf",
    "calculate_ligand_rmsd",
    "run_trajectory_qc",
    "calculate_native_contacts",
    "calculate_backbone_dihedrals",
})

COMBINED_TOOL_NAMES: FrozenSet[str] = frozenset({
    "collect_metric_files",
    "plot_combined_overlay",
    "compute_comparison_table",
    "run_combined_analysis",
    "run_combined_dccm_analysis",
    "run_combined_dccm_difference",
    "plot_combined_rmsf_segment_bars",
    "run_combined_rmsf_segment_analysis",
    "run_combined_com_distance_analysis",
    "plot_rmsf_apo_holo_comparison",
    "run_combined_rmsf_apo_holo_analysis",
    "run_combined_dccm_apo_holo_analysis",
    "run_combined_rmsf_segment_apo_holo_analysis",
    "run_combined_binding_rmsf_overlay",
    "collect_fel_features_table",
    "collect_classification_features_table",
    "cluster_classification_features",
    "plot_cluster_feature_trajectories",
    "plot_cluster_rmsf_profiles",
    "build_sequence_phylo_tree",
    "build_structure_phylo_tree",
})

SHARED_TOOL_NAMES: FrozenSet[str] = frozenset({
    "build_consensus_sequence_alignment",
    "fit_reference_pca_model",
    "project_simulations_reference_pca",
    "build_shared_reference_fel_landscapes",
    "cluster_reference_fel_landscapes",
    "run_reference_landscape_pipeline",
    "define_reference_consensus_pocket",
    "map_consensus_pocket_residues",
    "calculate_consensus_pocket_metrics",
    "run_consensus_pocket_metrics_batch",
    "plot_reference_msa_alignment",
    "run_consensus_local_fel_batch",
})


def tool_bucket(name: str) -> str:
    """Return 'per_sim' | 'combined' | 'shared' | 'unknown'."""
    if name in PER_SIM_TOOL_NAMES:
        return "per_sim"
    if name in COMBINED_TOOL_NAMES:
        return "combined"
    if name in SHARED_TOOL_NAMES:
        return "shared"
    return "unknown"


def names_for_scope(
    *,
    include_combined: bool = False,
    include_shared: bool = False,
) -> Set[str]:
    names = set(PER_SIM_TOOL_NAMES)
    if include_combined:
        names |= set(COMBINED_TOOL_NAMES)
    if include_shared or include_combined:
        # Combined campaigns always see shared/family tools.
        names |= set(SHARED_TOOL_NAMES)
    return names


def summarize_buckets() -> Dict[str, List[str]]:
    return {
        "per_sim": sorted(PER_SIM_TOOL_NAMES),
        "combined": sorted(COMBINED_TOOL_NAMES),
        "shared": sorted(SHARED_TOOL_NAMES),
    }


def filter_tools_by_names(tools: Iterable, allowed: Set[str]) -> list:
    out = []
    for t in tools:
        name = getattr(t, "name", None) or getattr(t, "__name__", "")
        if name in allowed and name not in INTERNAL_ALIASES:
            out.append(t)
    return out
