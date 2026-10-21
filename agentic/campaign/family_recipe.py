"""Shared analysis protocol for comparative (family-scale) campaigns.

Required calculations run for every protein. The protocol is compiled once
and applied identically — the LLM does not invent a different tool list
per system.

Feature packs (see ``FEATURE_PACKS``) choose gold columns and pins.
Shared-reference dynamics is a combined-stage step
(``FAMILY_POST_CALCULATIONS``), not a per-sim ``consensus_PCA/`` requirement.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agentic.campaign.spec import AnalysisRecipe, ArtifactContract, RecipeStep

# Required per-simulation calculations for every protein in a comparative study.
# Shared-ref PCA dyn is a combined-stage step (see FAMILY_POST_CALCULATIONS).
REQUIRED_CALCULATIONS: List[str] = [
    "calculate_consensus_pocket_metrics",
    "calculate_consensus_torsions",
    "calculate_consensus_rmsf_features",
    "calculate_consensus_dccm_features",
]
FAMILY_PIN_TOOLS: List[str] = REQUIRED_CALCULATIONS  # alias: required calculations

# Combined-stage tools for shared-reference dynamics (feature packs that include it).
FAMILY_POST_CALCULATIONS: List[str] = [
    "run_shared_dynamics_fel_batch",
    "compute_shared_pka_ref_dyn_features",
]

SHARED_DYN_COLUMNS = frozenset({"pca_pka_ref_shared_dyn", "pca_ref_shared_dyn"})

# Per-sim modular dirs written by pin tools. Independent dihedral PCA
# (``consensus_PCA``) is optional and not a hard per-sim gate. Shared-ref dyn
# writes ``consensus_PCA_ref`` at the combined stage.
FAMILY_MODULAR_DIRS: List[str] = [
    "consensus_dihedrals",
    "consensus_rmsf",
    "consensus_DCCM",
]
# Legacy names still accepted when present on disk.
FAMILY_MODULAR_DIR_ALIASES: Dict[str, str] = {
    "consensus_PCA_ref": "consensus_PCA",
}

# Named feature packs. ``paper_sharedpcdyn`` is the historical kinase default.
FEATURE_PACKS: Dict[str, Dict[str, Any]] = {
    "paper_sharedpcdyn": {
        "gold_columns": [
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
        ],
        "pin_tools": list(REQUIRED_CALCULATIONS),
        "modular_dirs": list(FAMILY_MODULAR_DIRS),
        "post_tools": list(FAMILY_POST_CALCULATIONS),
        "metric_groups": [
            "com",
            "reference_pocket",
            "consensus_rmsf",
            "consensus_torsions",
            "consensus_dccm",
            "dihedral_pca_ref",
        ],
    },
    "pocket_chi_rmsf_dccm": {
        "gold_columns": [
            "reference_pocket_ligand_distance_mean_A",
            "reference_pocket_ligand_distance_std_A",
            "reference_pocket_ligand_axis_angle_mean_deg",
            "reference_pocket_std_ligand_axis_angle_deg",
            "chi1_pocket_circ_mean_deg",
            "chi1_pocket_circ_std_deg",
            "consensus_rmsf_mean_A",
            "consensus_rmsf_std_A",
            "dccm_N_C_mean_corr",
        ],
        "pin_tools": list(REQUIRED_CALCULATIONS),
        "modular_dirs": list(FAMILY_MODULAR_DIRS),
        "post_tools": [],
        "metric_groups": [
            "com",
            "reference_pocket",
            "consensus_rmsf",
            "consensus_torsions",
            "consensus_dccm",
        ],
    },
    "rmsf_dccm_only": {
        "gold_columns": [
            "consensus_rmsf_mean_A",
            "consensus_rmsf_std_A",
            "dccm_N_C_mean_corr",
        ],
        "pin_tools": [
            "calculate_consensus_rmsf_features",
            "calculate_consensus_dccm_features",
        ],
        "modular_dirs": ["consensus_rmsf", "consensus_DCCM"],
        "post_tools": [],
        "metric_groups": ["consensus_rmsf", "consensus_dccm"],
    },
}


def resolve_feature_pack(name: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """Return ``(pack_name, pack_dict)``. Unknown names fall back to the paper pack."""
    key = (name or "").strip() or "paper_sharedpcdyn"
    if key not in FEATURE_PACKS:
        key = "paper_sharedpcdyn"
    return key, FEATURE_PACKS[key]


def pack_wants_shared_dyn(pack: Dict[str, Any]) -> bool:
    cols = set(pack.get("gold_columns") or [])
    tools = set(pack.get("post_tools") or [])
    return bool(cols & SHARED_DYN_COLUMNS) or bool(tools & set(FAMILY_POST_CALCULATIONS))

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
    ligand_selection: Optional[str] = None,
    pin_tools: Optional[List[str]] = None,
    metric_groups: Optional[List[str]] = None,
) -> AnalysisRecipe:
    """Shared analysis protocol cloned onto every system. Not generated per protein by an LLM."""
    lig_sel = (ligand_selection or "").strip() or None
    allowed = set(pin_tools) if pin_tools else None
    steps = []
    if lig_sel and (allowed is None or "calculate_consensus_pocket_metrics" in allowed):
        steps.append(
            RecipeStep(
                name="Ligand–pocket COM + axis-angle",
                tool_name="calculate_consensus_pocket_metrics",
                description="Ligand COM distance and orientation vs pocket_mapped residues",
                tool_params={
                    "ligand_selection": lig_sel,
                    "output_prefix": "reference_pocket",
                },
                reason="Campaign descriptor: pocket_mapped COM + axis-angle",
            )
        )
    optional = [
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
    for step in optional:
        if allowed is None or step.tool_name in allowed:
            steps.append(step)
    cols = list(gold_columns) if gold_columns else list(FAMILY_FEATURE_COLUMNS)
    groups = list(metric_groups) if metric_groups else list(FAMILY_METRIC_GROUPS)
    return AnalysisRecipe(
        steps=steps,
        required_feature_columns=cols,
        metric_groups=groups,
    )


build_family_recipe = build_shared_analysis_protocol  # alias kept for existing imports


def family_contract(
    modular_dirs: Optional[List[str]] = None,
    n_features: Optional[int] = None,
) -> ArtifactContract:
    dirs = list(modular_dirs) if modular_dirs else list(FAMILY_MODULAR_DIRS)
    nfeat = int(n_features) if n_features is not None else len(FAMILY_FEATURE_COLUMNS)
    return ArtifactContract(
        modular_dirs=dirs,
        analysis_markers=["analysis_summary.jsonl"],
        min_features_present=max(1, nfeat),
        min_complete_fraction=0.85,
    )


def build_post_combined_protocol(
    *,
    reference_label: str = "",
    post_tools: Optional[List[str]] = None,
) -> AnalysisRecipe:
    """Combined-stage pins (shared-ref dynamics). Empty when the pack omits them."""
    tools = list(post_tools) if post_tools is not None else list(FAMILY_POST_CALCULATIONS)
    steps: List[RecipeStep] = []
    ref = (reference_label or "").strip()
    if "run_shared_dynamics_fel_batch" in tools or "compute_shared_pka_ref_dyn_features" in tools:
        steps.append(
            RecipeStep(
                name="Shared-reference dynamics features",
                tool_name="compute_shared_pka_ref_dyn_features",
                description="Project every system onto the reference dynamics model",
                tool_params={"reference_label": ref} if ref else {},
                reason="Family post pin: shared-reference dyn feature",
            )
        )
    return AnalysisRecipe(steps=steps, required_feature_columns=[], metric_groups=[])


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
