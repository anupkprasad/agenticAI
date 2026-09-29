"""Pre-combined compile/execute helpers.

The LLM *compiles* which combined/shared tools define the pocket, MSA, or
any other calculation every simulation will consume. The engine then
*executes* that shared setup protocol once. A hardcoded MSA+pocket chain is
only the fallback when compile produces nothing usable.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from agentic.analysis.tool_buckets import COMBINED_TOOL_NAMES
from agentic.campaign.spec import AnalysisRecipe, RecipeStep

# Structure-only shared setup that family campaigns always need.
REQUIRED_SHARED_SETUP: List[str] = [
    "build_global_mapped_alignment",
    "define_pocket_mapped_residues",
    "map_pocket_mapped_residues",
    "plot_global_mapped_alignment",
]
FAMILY_PRE_PIN_TOOLS: List[str] = REQUIRED_SHARED_SETUP  # alias: required shared setup

# Legacy tool names still registered; treat as the same required shared setup.
PRE_TOOL_ALIASES: Dict[str, str] = {
    "build_consensus_sequence_alignment": "build_global_mapped_alignment",
    "build_global_consensus_msa": "build_global_mapped_alignment",
    "define_reference_consensus_pocket": "define_pocket_mapped_residues",
    "map_consensus_pocket_residues": "map_pocket_mapped_residues",
    "plot_reference_msa_alignment": "plot_global_mapped_alignment",
}


def canonical_pre_tool(name: str) -> str:
    n = (name or "").strip()
    return PRE_TOOL_ALIASES.get(n, n)

# Traj overlays / reduce / batch metrics — these need per-sim trajectories
# and belong in post_combined, not pre_combined.
PRE_COMBINED_TRAJ_BLOCK = frozenset(COMBINED_TOOL_NAMES) - {
    "build_sequence_phylo_tree",
    "build_structure_phylo_tree",
} | {
    "run_consensus_pocket_metrics_batch",
    "calculate_consensus_pocket_metrics",
    "run_consensus_torsions_batch",
    "run_consensus_local_fel_batch",
    "run_shared_dynamics_fel_batch",
    "project_simulations_reference_pca",
    "build_shared_reference_fel_landscapes",
    "cluster_reference_fel_landscapes",
    "run_reference_landscape_pipeline",
    "fit_reference_pca_model",
    "fit_dynamics_model",
}


def pre_combined_tool_allowed(tool_name: str) -> bool:
    """True for LLM-chosen setup tools, including programmer-generated unknowns.

    Blocks per-sim ``calculate_*`` and known traj/post-combined tools. Does
    **not** restrict the LLM to a pocket/MSA allowlist.
    """
    name = (tool_name or "").strip()
    if not name:
        return False
    if name in PRE_COMBINED_TRAJ_BLOCK:
        return False
    if name.startswith("calculate_"):
        return False
    return True


def family_pre_combined_pin_steps(
    *,
    labels: Optional[Sequence[str]] = None,
    sim_dirs: Optional[Sequence[str]] = None,
    reference_label: str = "",
    settings: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Required shared setup: MSA → pocket definition → residue map → MSA plots."""
    labels = list(labels or [])
    sim_dirs = list(sim_dirs or [])
    ref = reference_label or (labels[0] if labels else "reference")
    ref_sim = sim_dirs[0] if sim_dirs else "."
    if ref in labels and sim_dirs:
        ref_sim = sim_dirs[labels.index(ref)]
    metric = "similarity"
    min_cons = 0.5
    min_cov = 0.25
    cutoff = 15.0
    if settings is not None:
        metric = getattr(settings, "conservation_metric", None) or (
            settings.get("conservation_metric") if isinstance(settings, dict) else metric
        ) or metric
        min_cons = float(
            getattr(settings, "min_conservation", None)
            or (settings.get("min_conservation") if isinstance(settings, dict) else min_cons)
            or min_cons
        )
        min_cov = float(
            getattr(settings, "min_coverage", None)
            or (settings.get("min_coverage") if isinstance(settings, dict) else min_cov)
            or min_cov
        )
        cutoff = float(
            getattr(settings, "pocket_cutoff_A", None)
            or (settings.get("pocket_cutoff_A") if isinstance(settings, dict) else cutoff)
            or cutoff
        )
    return [
        {
            "name": "Build global consensus MSA",
            "description": (
                f"MAFFT MSA; global_consensus_msa = columns with {metric} ≥ {min_cons}"
            ),
            "tool_name": "build_global_mapped_alignment",
            "tool_params": {
                "working_dir": ".",
                "reference_label": ref,
                "labels": labels,
                "sim_dirs": sim_dirs,
                "alignment_json": "global_consensus_msa.json",
                "consensus_json": "global_consensus_msa.json",
                "alignment_fasta": "global_msa.fasta",
                "residue_map_csv": "global_consensus_msa.csv",
                "conservation_metric": metric,
                "min_conservation": min_cons,
                "min_coverage": min_cov,
            },
            "reason": (
                f"global_consensus_msa = MAFFT columns with {metric} ≥ {min_cons} "
                f"(occupancy ≥ {min_cov})"
            ),
        },
        {
            "name": "Define pocket mapped residues",
            "description": (
                f"{cutoff:g} Å ligand shell ∩ global_consensus_msa, "
                "transferred to every system"
            ),
            "tool_name": "define_pocket_mapped_residues",
            "tool_params": {
                "working_dir": ".",
                "reference_label": ref,
                "sim_dir": ref_sim,
                "consensus_json": "global_consensus_msa.json",
                "ligand_selection": "resname ATP",
                "pocket_cutoff_A": cutoff,
                "pocket_filter": "global_consensus_msa",
                "labels": labels,
                "sim_dirs": sim_dirs,
            },
            "reason": (
                f"pocket_mapped = (ATP {cutoff:g} Å) ∩ global consensus, "
                "mapped onto all proteins"
            ),
        },
        {
            "name": "Export pocket mapped residue lists",
            "description": "Per-label pocket residue lists / pocket_mapped.json",
            "tool_name": "map_pocket_mapped_residues",
            "tool_params": {
                "working_dir": ".",
                "definition_json": "pocket_mapped_definition.json",
                "labels": labels,
            },
            "reason": "Harvested into cross_sim/ for per-sim pocket tools",
        },
        {
            "name": "Plot global and pocket MSA",
            "description": "global_consensus_msa + pocket_mapped MSA panels",
            "tool_name": "plot_global_mapped_alignment",
            "tool_params": {
                "working_dir": ".",
                "alignment_fasta": "global_msa.fasta",
                "consensus_json": "global_consensus_msa.json",
                "pocket_definition_json": "pocket_mapped_definition.json",
                "full_plot_file": "global_consensus_msa.png",
                "focused_plot_file": "pocket_mapped_msa.png",
            },
            "reason": "Plot calculated consensus and pocket columns (not unfiltered MSA)",
        },
    ]


def build_shared_setup_protocol(settings: Optional[Any] = None) -> AnalysisRecipe:
    """Required shared setup compiled once: MSA, pocket definition, residue map, plots."""
    steps = [
        RecipeStep(
            name=str(s["name"]),
            tool_name=str(s["tool_name"]),
            description=str(s.get("description") or ""),
            tool_params=dict(s.get("tool_params") or {}),
            reason=str(s.get("reason") or ""),
        )
        for s in family_pre_combined_pin_steps(settings=settings)
    ]
    return AnalysisRecipe(steps=steps)


build_family_pre_combined_recipe = build_shared_setup_protocol  # alias kept for existing imports


def merge_pre_combined_steps(
    llm_steps: Iterable[Dict[str, Any]],
    *,
    pin_steps: Optional[Sequence[Dict[str, Any]]] = None,
    labels: Optional[Sequence[str]] = None,
    sim_dirs: Optional[Sequence[str]] = None,
    pin: bool = True,
) -> List[Dict[str, Any]]:
    """Keep LLM extras; prepend required shared setup the LLM omitted.

    For pocket / MSA tools the LLM already planned, **normalize** critical
    contract params (cutoff, pocket_filter, consensus_json, conservation)
    from the pin recipe onto the LLM step. Independent runs may redefine the
    pocket themselves, but they must honour the *same goal-derived contract*
    (e.g. 15 Å ∩ global_consensus_msa) so definitions stay comparable — not the raw
    proximity shell (`pocket_filter='none'`), which silently inflates residue
    counts.
    """
    pins = list(pin_steps or family_pre_combined_pin_steps(labels=labels, sim_dirs=sim_dirs))
    pin_by_canon: Dict[str, Dict[str, Any]] = {}
    for step in pins:
        tool = str(step.get("tool_name") or "")
        canon = canonical_pre_tool(tool)
        if canon:
            pin_by_canon[canon] = dict(step)

    # Params that define the transferable pocket / MSA contract.
    _CONTRACT_KEYS = (
        "pocket_cutoff_A",
        "pocket_filter",
        "consensus_json",
        "alignment_json",
        "ligand_selection",
        "conservation_metric",
        "min_conservation",
        "min_coverage",
        "reference_label",
    )

    kept: List[Dict[str, Any]] = []
    seen = set()
    for step in llm_steps or []:
        tool = str((step or {}).get("tool_name") or "")
        canon = canonical_pre_tool(tool)
        if not tool or canon in seen:
            continue
        if not pre_combined_tool_allowed(tool):
            continue
        step_out = dict(step)
        # Overlay goal/pin contract onto LLM-planned pocket/MSA tools.
        if canon in pin_by_canon:
            pin_params = dict(pin_by_canon[canon].get("tool_params") or {})
            params = dict(step_out.get("tool_params") or {})
            for key in _CONTRACT_KEYS:
                if key in pin_params and pin_params[key] not in (None, ""):
                    prev = params.get(key)
                    params[key] = pin_params[key]
                    if prev is not None and prev != pin_params[key]:
                        # Prefer pin (goal-derived) over LLM drift.
                        step_out.setdefault(
                            "reason",
                            step_out.get("reason") or pin_by_canon[canon].get("reason") or "",
                        )
            # Keep LLM labels/sim_dirs if provided; fill from pin otherwise.
            for key in ("labels", "sim_dirs", "sim_dir", "working_dir"):
                if key in pin_params and (key not in params or params[key] in (None, "", [])):
                    params[key] = pin_params[key]
            step_out["tool_params"] = params
            # Canonical tool name (legacy aliases → current)
            step_out["tool_name"] = pin_by_canon[canon].get("tool_name") or tool
        kept.append(step_out)
        seen.add(canon)

    if pin:
        prepend: List[Dict[str, Any]] = []
        for step in pins:
            tool = str(step.get("tool_name") or "")
            canon = canonical_pre_tool(tool)
            if tool and canon not in seen:
                prepend.append(dict(step))
                seen.add(canon)
        kept = prepend + kept
    return kept


def recipe_from_step_dicts(steps: Sequence[Dict[str, Any]]) -> AnalysisRecipe:
    return AnalysisRecipe(
        steps=[
            RecipeStep(
                name=str(s.get("name") or s.get("tool_name") or "step"),
                tool_name=str(s.get("tool_name") or ""),
                description=str(s.get("description") or ""),
                tool_params=dict(s.get("tool_params") or {}),
                reason=str(s.get("reason") or ""),
            )
            for s in steps
            if s and s.get("tool_name")
        ]
    )
