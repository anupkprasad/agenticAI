"""Shared analysis protocol for comparative (family-scale) campaigns.

Required calculations run for every protein. The protocol is compiled once
and applied identically — the LLM does not invent a different tool list
per system.

Feature set matches paper fig3 sharedpcdyn Ward k=4 (10 columns).
Shared PKA-ref dyn is computed once at combined stage via
``run_shared_dynamics_fel_batch`` + ``compute_shared_pka_ref_dyn_features``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentic.campaign.spec import AnalysisRecipe, ArtifactContract, RecipeStep

# Required per-simulation calculations for every protein in a comparative study.
# Shared PKA-ref PCA dyn is a combined-stage step (see FAMILY_POST_CALCULATIONS).
REQUIRED_CALCULATIONS: List[str] = [
    "calculate_consensus_pocket_metrics",
    "calculate_consensus_torsions",
    "calculate_consensus_rmsf_features",
    "calculate_consensus_dccm_features",
]
FAMILY_PIN_TOOLS: List[str] = REQUIRED_CALCULATIONS  # alias: required calculations

# Combined-stage tools required for paper sharedpcdyn feature #10.
FAMILY_POST_CALCULATIONS: List[str] = [
    "run_shared_dynamics_fel_batch",
    "compute_shared_pka_ref_dyn_features",
]

FAMILY_MODULAR_DIRS: List[str] = [
    "consensus_dihedrals",
    "consensus_rmsf",
    "consensus_DCCM",
    "consensus_PCA_ref",
]

# Paper fig3 / sharedpcdyn Ward columns (exact names).
FAMILY_FEATURE_COLUMNS: List[str] = [
    "reference_pocket_ligand_distance_mean_A",
    "reference_pocket_ligand_distance_std_A",
    "reference_pocket_ligand_axis_angle_mean_deg",
    "reference_pocket_std_ligand_axis_angle_deg",
    "chi1_pocket_circ_mean_deg",
    "chi1_pocket_circ_std_deg",
    "consensus_rmsf_mean_A",
    "consensus_rmsf_std_A",
    "dccm_N_C_mean_corr",
    "pca_pka_ref_shared_dyn",
]

FAMILY_METRIC_GROUPS: List[str] = [
    "com",
    "reference_pocket",
    "consensus_rmsf",
    "consensus_torsions",
    "consensus_dccm",
    "dihedral_pca_ref",
]


def build_shared_analysis_protocol(
    gold_columns: Optional[List[str]] = None,
) -> AnalysisRecipe:
    """Shared analysis protocol cloned onto every system. Not generated per protein by an LLM."""
    steps = [
        RecipeStep(
            name="Ligand–pocket COM + axis-angle",
            tool_name="calculate_consensus_pocket_metrics",
            description="ATP COM distance and orientation vs pocket_mapped residues",
            tool_params={
                "ligand_selection": "resname ATP",
                "output_prefix": "reference_pocket",
            },
            reason="Campaign descriptor: pocket_mapped COM + axis-angle (15 Å KAPCA ∩ global_consensus_msa)",
        ),
        RecipeStep(
            name="Consensus dihedrals (φ/ψ/χ₁)",
            tool_name="calculate_consensus_torsions",
            description="Mapped φ/ψ/χ₁ circular means/std for domain and pocket",
            tool_params={"output_dir": "consensus_dihedrals"},
            reason="Family modular: pocket χ₁ mean/std + shared PCA inputs",
        ),
        RecipeStep(
            name="Consensus Cα RMSF",
            tool_name="calculate_consensus_rmsf_features",
            description="Mapped consensus Cα RMSF mean/std across the domain",
            tool_params={"output_dir": "consensus_rmsf"},
            reason="Family modular: consensus RMSF features",
        ),
        RecipeStep(
            name="Consensus DCCM N↔C",
            tool_name="calculate_consensus_dccm_features",
            description="Mapped DCCM mean absolute and N-lobe↔C-lobe correlation",
            tool_params={"output_dir": "consensus_DCCM"},
            reason="Family modular: DCCM N↔C feature",
        ),
    ]
    cols = list(gold_columns) if gold_columns else list(FAMILY_FEATURE_COLUMNS)
    return AnalysisRecipe(
        steps=steps,
        required_feature_columns=cols,
        metric_groups=list(FAMILY_METRIC_GROUPS),
    )


build_family_recipe = build_shared_analysis_protocol  # alias kept for existing imports


def family_contract() -> ArtifactContract:
    return ArtifactContract(
        modular_dirs=list(FAMILY_MODULAR_DIRS),
        analysis_markers=["analysis_summary.jsonl"],
        min_features_present=len(FAMILY_FEATURE_COLUMNS),
        min_complete_fraction=0.85,
    )


def recipe_steps_as_plan_dicts(
    *,
    topology_file: str = "md.tpr",
    trajectory_file: str = "mdWrap.xtc",
) -> List[Dict[str, Any]]:
    """Render the shared analysis protocol as analysis-agent plan step dicts."""
    out: List[Dict[str, Any]] = []
    for step in build_shared_analysis_protocol().steps:
        params = dict(step.tool_params)
        params.setdefault("topology_file", topology_file)
        params.setdefault("trajectory_file", trajectory_file)
        out.append(
            {
                "name": step.name,
                "description": step.description,
                "tool_name": step.tool_name,
                "tool_params": params,
                "reason": step.reason,
            }
        )
    return out
