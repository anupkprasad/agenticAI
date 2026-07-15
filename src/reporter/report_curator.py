"""
Goal- and data-aware curation for combined multi-simulation HTML reports.

The reporter reviews available results, filters uninformative figures (e.g. ligand
residence when ATP stays bound in every trajectory), and produces short section
summaries aligned with the user's objective.
"""
from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

_UNIPROT_ID_RE = re.compile(r"^[a-z][0-9][a-z0-9]{3,9}[0-9a-z]*$", re.IGNORECASE)
_GENE_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9\-]{1,20}$")

# Plot basename fragment → classification feature column(s) for discriminability checks.
_PLOT_FEATURE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "ligand_residence_by_cluster": ("fraction_bound", "n_unbinding_events"),
    "com_distance_by_cluster": ("ligand_pocket_distance_mean_A", "ligand_pocket_distance_std_A"),
    "contacts_by_cluster": ("mean_contacts", "mean_hbonds", "max_contacts"),
    "pocket_sasa_by_cluster": ("mean_pocket_sasa_nm2", "std_pocket_sasa_nm2"),
    "pocket_rmsf_by_cluster": ("mean_pocket_rmsf_A", "max_pocket_rmsf_A"),
    "ligand_rmsf_by_cluster": ("mean_ligand_rmsf_A", "max_ligand_rmsf_A"),
}


@dataclass
class SubsectionPlan:
    section_id: str
    title: str
    summary: str
    plot_paths: List[str] = field(default_factory=list)
    include: bool = True


@dataclass
class StructureHighlightPlan:
    """Which simulations to feature with 3D metastates, and how many each.

    Enables the reporter to embed *multiple* conformational states for the few
    proteins that matter to the story (connected via ``rationale``) rather than
    one structure for every simulation.
    """

    highlight_labels: Set[str] = field(default_factory=set)
    structures_per_label: Dict[str, int] = field(default_factory=dict)
    rationale: Dict[str, str] = field(default_factory=dict)
    default_per_sim: int = 1
    restrict_highlights: bool = False

    def structures_for(self, display_name: str) -> int:
        """Number of metastates to embed for a simulation (0 = skip)."""
        if display_name in self.structures_per_label:
            return max(0, int(self.structures_per_label[display_name]))
        if self.restrict_highlights and self.highlight_labels:
            return 0
        return self.default_per_sim


@dataclass
class CombinedReportPlan:
    headline: str
    classification_section: Optional[SubsectionPlan] = None
    comparative_summary: str = ""
    included_overlay_plots: List[str] = field(default_factory=list)
    excluded_plots: Dict[str, str] = field(default_factory=dict)
    subsection_summaries: Dict[str, str] = field(default_factory=dict)
    structure_highlight: Optional[StructureHighlightPlan] = None


def parse_label_name_map_strict(
    text: str,
    sim_labels: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """
    Parse ``uniprot_id:GeneName`` pairs without false positives from paths or prose.

    Prefer an explicit ``id:name map`` block; otherwise accept only UniProt-style
    keys mapped to gene names (uppercase values).
    """
    if not text:
        return {}

    sim_set = {s.lower() for s in (sim_labels or []) if s}
    mapping: Dict[str, str] = {}

    block_match = re.search(
        r"(?:id\s*:\s*name\s+map|id:name\s+map)\s+([^\n.]+)",
        text,
        re.IGNORECASE,
    )
    search_text = block_match.group(1) if block_match else text

    for m in re.finditer(
        r"\b([A-Za-z0-9_\-]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})\b",
        search_text,
    ):
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        if key in {"id", "name", "map"} or val.lower() in {"name", "map"}:
            continue
        if not _UNIPROT_ID_RE.match(key):
            continue
        if not _GENE_NAME_RE.match(val):
            continue
        if sim_set and key not in sim_set:
            continue
        mapping[key] = val

    return mapping


def display_names_for_sims(
    sim_labels: Sequence[str],
    label_name_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Resolve human-readable names for each simulation label."""
    from src.reporter.combined_reporter import resolve_display_label

    lmap = label_name_map or {}
    return [resolve_display_label(lbl, lmap) for lbl in sim_labels]


def build_report_headline(
    sim_labels: Sequence[str],
    label_name_map: Optional[Dict[str, str]] = None,
    user_goal: str = "",
) -> str:
    """Headline uses actual simulation count, not spurious parsed name entries."""
    n = len(sim_labels)
    names = display_names_for_sims(sim_labels, label_name_map)
    unique = sorted(set(names))
    if n == 0:
        return "Multi-Simulation Report"
    if len(unique) == 1:
        return f"{unique[0]} — Multi-Simulation Report"
    if len(unique) <= 4:
        return f"{' / '.join(unique)} — Multi-Simulation Comparison"
    goal_l = (user_goal or "").lower()
    if "pseudokinase" in goal_l:
        kind = "Pseudokinases"
    elif "kinase" in goal_l:
        kind = "Kinases"
    else:
        kind = "Systems"
    return f"{n} {kind} — Multi-Simulation Comparison"


def _load_features_table(base_analysis_dir: Path) -> List[Dict[str, str]]:
    for name in (
        "ref_fel_pock_features.csv",
        "reference_grouping_features.csv",
        "classification_features.csv",
        "classification_features_zscore.csv",
    ):
        path = base_analysis_dir / name
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    return []


def _load_cluster_assignments(base_analysis_dir: Path) -> Dict[str, int]:
    for fname in (
        "ref_fel_pock_cluster_assignments.csv",
        "reference_cluster_assignments.csv",
        "classification_cluster_assignments.csv",
    ):
        path = base_analysis_dir / fname
        if not path.is_file():
            continue
        out: Dict[str, int] = {}
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                label = (row.get("label") or "").strip().lower()
                try:
                    cid = int(row.get("cluster_id", ""))
                except (TypeError, ValueError):
                    continue
                if label:
                    out[label] = cid
        if out:
            return out
    return {}


def _load_cluster_summary(base_analysis_dir: Path) -> Dict[str, Any]:
    for fname in ("ref_fel_pock_clusters.json", "reference_clusters.json", "classification_clusters.json"):
        path = base_analysis_dir / fname
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                continue
            data = _apply_representative_overrides_to_summary(data, base_analysis_dir)
            return data
        except Exception:
            continue
    return {}


def _apply_representative_overrides_to_summary(
    summary: Dict[str, Any],
    base_analysis_dir: Path,
) -> Dict[str, Any]:
    """Merge optional manual representative overrides into cluster summary JSON."""
    try:
        from src.analysis.classification_clustering import (
            _apply_representative_overrides,
            _load_representative_overrides,
        )
    except ImportError:
        return summary

    overrides = _load_representative_overrides(base_analysis_dir)
    if not overrides:
        return summary

    labels = summary.get("labels") or []
    display_names = summary.get("display_names") or []
    assignments = summary.get("cluster_assignments") or {}
    if not labels or not display_names or len(labels) != len(display_names):
        return summary

    cluster_ids = [int(assignments.get(lbl, 0)) for lbl in labels]
    reps = summary.get("cluster_representatives") or {}
    updated = _apply_representative_overrides(
        reps,
        overrides,
        labels,
        display_names,
        cluster_ids,
    )
    if updated != reps:
        merged = dict(summary)
        merged["cluster_representatives"] = updated
        return merged
    return summary


def is_reference_archetype_study(base_analysis_dir: Optional[Path]) -> bool:
    return bool(
        base_analysis_dir
        and base_analysis_dir.is_dir()
        and (base_analysis_dir / "ref_fel_pock_clusters.json").is_file()
    )


def _load_cluster_assignment_rows(base_analysis_dir: Path) -> List[Dict[str, str]]:
    for fname in (
        "ref_fel_pock_cluster_assignments.csv",
        "reference_cluster_assignments.csv",
        "classification_cluster_assignments.csv",
    ):
        path = base_analysis_dir / fname
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    return []


def _infer_archetype_title(profile: Dict[str, float]) -> str:
    """Heuristic archetype label from cluster-mean pocket + FEL scalars."""
    com_p95 = profile.get("reference_pocket_ligand_distance_p95_A")
    bound = profile.get("reference_pocket_fraction_bound")
    angle_std = profile.get("reference_pocket_std_ligand_axis_angle_deg")
    angle_p95 = profile.get("reference_pocket_ligand_axis_angle_p95_deg")
    ent = profile.get("ref_landscape_entropy")
    major = profile.get("ref_major_basin_population")
    if com_p95 is not None and com_p95 > 25.0:
        return "Dissociated / non-productive ATP coupling"
    if (
        bound is not None
        and bound > 0.85
        and angle_std is not None
        and angle_std < 12.0
        and ent is not None
        and ent < 0.85
    ):
        return "Single-basin / low-entropy binder"
    if com_p95 is not None and com_p95 > 20.0:
        return "Loosely coupled / excursion-prone"
    if angle_p95 is not None and angle_p95 > 80.0 and (angle_std or 0) > 15.0:
        return "Orientation-unstable binder"
    if bound is not None and bound < 0.45:
        return "Loosely coupled / partial residence"
    return "Canonical stable binder"


def build_reference_archetype_narrative(base_analysis_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Build overall + per-cluster narrative for reference FEL+pocket archetype studies.

    Returns None when ``ref_fel_pock_clusters.json`` is absent.
    """
    if not is_reference_archetype_study(base_analysis_dir):
        return None

    summary = _load_cluster_summary(base_analysis_dir)
    rows = _load_cluster_assignment_rows(base_analysis_dir)
    features = _load_features_table(base_analysis_dir)
    if not rows:
        return None

    feat_by_label: Dict[str, Dict[str, str]] = {}
    for row in features:
        lbl = (row.get("label") or "").strip().lower()
        if lbl:
            feat_by_label[lbl] = row

    by_cluster: Dict[int, List[Dict[str, str]]] = {}
    for row in rows:
        try:
            cid = int(row.get("cluster_id", ""))
        except (TypeError, ValueError):
            continue
        by_cluster.setdefault(cid, []).append(row)

    rep_map = summary.get("cluster_representatives") or {}
    cluster_blocks: List[Dict[str, Any]] = []
    for cid in sorted(by_cluster):
        members = by_cluster[cid]
        display_names = sorted(
            {(m.get("display_name") or m.get("label") or "").strip() for m in members}
            - {""}
        )
        profile: Dict[str, float] = {}
        for key in (
            "reference_pocket_ligand_distance_std_A",
            "reference_pocket_ligand_distance_p95_A",
            "reference_pocket_fraction_bound",
            "reference_pocket_std_ligand_axis_angle_deg",
            "reference_pocket_ligand_axis_angle_p95_deg",
            "ref_landscape_entropy",
            "ref_major_basin_population",
        ):
            vals = []
            for m in members:
                raw = (feat_by_label.get((m.get("label") or "").lower(), {}) or {}).get(key)
                if raw not in (None, ""):
                    try:
                        vals.append(float(raw))
                    except ValueError:
                        pass
            if vals:
                profile[key] = sum(vals) / len(vals)

        rep_entry = rep_map.get(str(cid), rep_map.get(cid, {}))
        if isinstance(rep_entry, dict):
            rep_uid = (rep_entry.get("label") or "").strip()
            rep_display = (rep_entry.get("display_name") or rep_uid).strip()
        else:
            rep_uid = str(rep_entry or "").strip()
            rep_display = rep_uid

        cluster_blocks.append(
            {
                "cluster_id": cid,
                "n_members": len(members),
                "members_display": display_names,
                "archetype_title": _infer_archetype_title(profile),
                "profile": profile,
                "representative_uid": rep_uid,
                "representative_display": rep_display,
            }
        )

    n_total = len(rows)
    n_clusters = len(by_cluster)
    overall = (
        f"Reference-structure clustering (MLKL-projected FEL + mapped reference pocket) "
        f"partitioned {n_total} holo pseudokinases into {n_clusters} dynamic archetypes. "
        f"Clustering used curated binding descriptors (COM distance, H-bonds, residence, "
        f"pocket RMSF) plus reference FEL entropy and major-basin population. "
        f"One centroid-nearest representative per cluster is highlighted below with "
        f"reference FEL metastate summaries and 3D basin structures."
    )

    return {
        "overall_summary": overall,
        "n_simulations": n_total,
        "n_clusters": n_clusters,
        "clusters": cluster_blocks,
        "feature_columns": summary.get("feature_columns") or [],
    }


def _cluster_metric_range(
    features: List[Dict[str, str]],
    clusters: Dict[str, int],
    column: str,
) -> Tuple[float, float, float]:
    """Return (min_cluster_mean, max_cluster_mean, global_range) for a feature column."""
    by_cluster: Dict[int, List[float]] = {}
    all_vals: List[float] = []
    for row in features:
        label = (row.get("label") or "").strip().lower()
        if label not in clusters:
            continue
        raw = row.get(column)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        cid = clusters[label]
        by_cluster.setdefault(cid, []).append(val)
        all_vals.append(val)

    if not by_cluster:
        return 0.0, 0.0, 0.0

    cluster_means = [sum(v) / len(v) for v in by_cluster.values() if v]
    if not cluster_means:
        return 0.0, 0.0, 0.0

    lo, hi = min(cluster_means), max(cluster_means)
    global_range = (max(all_vals) - min(all_vals)) if len(all_vals) > 1 else 0.0
    return lo, hi, global_range


def assess_plot_informativeness(
    plot_path: str,
    base_analysis_dir: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Return (include, reason). False when the plot adds no discriminative insight.
    """
    name = Path(plot_path).name.lower()
    base = Path(base_analysis_dir) if base_analysis_dir else None

    # Ligand residence: skip when ATP remains bound for the full trajectory in all systems.
    if "ligand_residence" in name and base and base.is_dir():
        features = _load_features_table(base)
        if features:
            frac_vals = []
            unbind_vals = []
            for row in features:
                try:
                    frac_vals.append(float(row.get("fraction_bound") or 0))
                    unbind_vals.append(float(row.get("n_unbinding_events") or 0))
                except ValueError:
                    pass
            if frac_vals and all(f >= 0.99 for f in frac_vals) and all(u == 0 for u in unbind_vals):
                return (
                    False,
                    "Ligand remained bound throughout every trajectory (no unbinding events); "
                    "cluster comparison would not be informative.",
                )

    if base and base.is_dir() and "by_cluster" in name:
        fragment = next((k for k in _PLOT_FEATURE_COLUMNS if k in name), None)
        if fragment:
            features = _load_features_table(base)
            clusters = _load_cluster_assignments(base)
            if features and clusters and len(clusters) >= 2:
                cols = _PLOT_FEATURE_COLUMNS[fragment]
                ranges = [_cluster_metric_range(features, clusters, c) for c in cols]
                max_between = max(r[1] - r[0] for r in ranges)
                max_global = max(r[2] for r in ranges)
                # No separation between cluster means and negligible overall spread.
                if max_between < 1e-6 and max_global < 1e-6:
                    return False, "Feature values are uniform across clusters and simulations."
                if fragment == "ligand_residence_by_cluster":
                    lo_frac, hi_frac, _ = _cluster_metric_range(features, clusters, "fraction_bound")
                    if lo_frac >= 0.99 and hi_frac >= 0.99:
                        return (
                            False,
                            "All clusters show fully bound ligand with no unbinding — "
                            "no dynamic contrast to compare.",
                        )

    return True, ""


def filter_informative_plots(
    overlay_plots: Sequence[str],
    base_analysis_dir: Optional[str] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """Drop plots that are not scientifically informative."""
    kept: List[str] = []
    excluded: Dict[str, str] = {}
    for path in overlay_plots:
        ok, reason = assess_plot_informativeness(path, base_analysis_dir)
        if ok:
            kept.append(path)
        else:
            excluded[str(path)] = reason
            logger.info("Report curator: excluding %s — %s", Path(path).name, reason)
    return kept, excluded


def _rule_based_classification_summary(
    base_analysis_dir: Path,
    plot_paths: Sequence[str],
    display_names: Sequence[str],
) -> str:
    from src.analysis.reference_labels import build_uniprot_display_map

    clusters = _load_cluster_assignments(base_analysis_dir)
    features = _load_features_table(base_analysis_dir)
    summary = _load_cluster_summary(base_analysis_dir)
    n_sims = len(display_names)
    n_clusters = len(set(clusters.values())) if clusters else 0
    representatives = summary.get("cluster_representatives") or {}
    uid_to_disp = build_uniprot_display_map(base_analysis_dir)
    ref_study = any(
        Path(p).name.lower().startswith("ref_fel_pock_") for p in plot_paths
    ) or (base_analysis_dir / "ref_fel_pock_features.csv").is_file()

    if ref_study:
        narrative = build_reference_archetype_narrative(base_analysis_dir)
        if narrative and narrative.get("overall_summary"):
            return narrative["overall_summary"]
        parts = [
            f"Reference-structure classification (MLKL-projected FEL + mapped pocket "
            f"features) grouped {n_sims} holo systems into "
            f"{n_clusters or 'several'} dynamic archetype(s)."
        ]
    else:
        parts = [
            f"Unsupervised clustering grouped {n_sims} holo systems into "
            f"{n_clusters or 'several'} dynamic regime(s) using binding-site and "
            f"conformational features derived from the trajectories."
        ]

    if clusters and features:
        by_c: Dict[int, List[str]] = {}
        for row in features:
            lbl = (row.get("label") or "").strip().lower()
            if lbl in clusters:
                disp = uid_to_disp.get(lbl, lbl.upper())
                by_c.setdefault(clusters[lbl], []).append(disp)
        if by_c:
            cluster_bits = []
            for cid in sorted(by_c):
                members = ", ".join(sorted(set(by_c[cid])))
                cluster_bits.append(f"cluster {cid} ({members})")
            parts.append("Assignments: " + "; ".join(cluster_bits) + ".")

    if representatives:
        rep_bits = []
        for cid in sorted(representatives, key=lambda x: int(x) if str(x).isdigit() else x):
            rep_entry = representatives[cid]
            if isinstance(rep_entry, dict):
                rep_disp = (
                    rep_entry.get("display_name")
                    or rep_entry.get("label")
                    or ""
                ).strip()
            else:
                rep_disp = str(rep_entry or "").strip()
            if rep_disp:
                rep_bits.append(f"cluster {cid} → {rep_disp}")
        if rep_bits:
            parts.append(
                "Cluster representatives (closest to centroid in feature space): "
                + "; ".join(rep_bits) + "."
            )

    if any("ref_fel_pock_dendrogram_heatmap" in Path(p).name.lower() for p in plot_paths):
        parts.append(
            "The combined dendrogram and feature heatmap share row order (top→bottom); "
            "protein names appear on the colored cluster bar with z-scored features to the right."
        )
    elif any("ref_fel_pock_phylo" in Path(p).name.lower() for p in plot_paths):
        parts.append(
            "The similarity tree reflects joint FEL + reference-pocket feature distances; "
            "the feature heatmap shows per-simulation z-scores with matching cluster colors."
        )
    elif any("ref_fel_pock_features_heatmap" in Path(p).name.lower() for p in plot_paths):
        parts.append(
            "The feature heatmap summarises z-scored pocket and FEL descriptors per simulation, "
            "with cluster colors aligned to the dendrogram leaf order."
        )
    elif any("phylo" in Path(p).name.lower() for p in plot_paths):
        parts.append(
            "The unrooted phylogenetic tree summarises FEL-based conformational "
            "relationships — the primary basis for separating dynamic classes."
        )
    return " ".join(parts)


def _subsection_summary_for_plots(
    section_id: str,
    plot_paths: Sequence[str],
    base_analysis_dir: Optional[Path],
) -> str:
    if not plot_paths:
        return ""
    names = [Path(p).name.lower() for p in plot_paths]
    if section_id == "cluster_trajectories":
        bits = []
        if any("com_distance" in n for n in names):
            bits.append(
                "ATP–catalytic pocket COM distance separates clusters with distinct "
                "binding-site tightness and coupling strength."
            )
        if any("contacts" in n for n in names):
            bits.append(
                "Protein–ATP contact patterns highlight differences in hydrogen-bond "
                "networks and persistent interactions between clusters."
            )
        if any("pocket_sasa" in n for n in names):
            bits.append(
                "Pocket solvent exposure varies between clusters, reflecting different "
                "degrees of burial at the nucleotide-binding site."
            )
        return " ".join(bits) if bits else (
            "Cluster-resolved trajectory metrics compare binding-site behaviour "
            "within each dynamic class."
        )
    if section_id == "cluster_rmsf":
        return (
            "Pocket and ligand RMSF profiles by cluster reveal which dynamic classes "
            "show higher local flexibility at the ATP-binding site versus rigid, "
            "locked conformations."
        )
    if section_id == "classification_summary":
        return (
            "PCA projection, horizontal dendrogram, feature heatmap, and similarity tree "
            "visualise how simulations partition into conformationally related groups."
        )
    return ""


def _float_or_none(row: Dict[str, str], key: str) -> Optional[float]:
    raw = row.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_structure_highlight_plan(
    sim_dirs: Sequence[str],
    sim_labels: Sequence[str],
    base_analysis_dir: Optional[str] = None,
    label_name_map: Optional[Dict[str, str]] = None,
    user_goal: str = "",
    enriched_prompt: str = "",
    narrative: Any = None,
    llm_client: Any = None,
    literature_snippet: str = "",
) -> StructureHighlightPlan:
    """Decide which proteins to feature with multiple 3D metastates.

    Small cohorts (or non-classification studies) keep the previous behaviour —
    every simulation contributes up to two structures. For large cohorts or
    classification-driven studies the plan restricts the 3D viewer / per-sim
    highlights to a story-relevant subset: one representative per dynamic
    cluster (most conformationally diverse) plus binding-site extremes. When an
    LLM is available it refines the subset and the connecting rationale.
    """
    display_names = display_names_for_sims(sim_labels, label_name_map)
    disp_by_label = {sl.lower(): dn for sl, dn in zip(sim_labels, display_names)}
    n_sims = len(sim_labels)

    base = Path(base_analysis_dir) if base_analysis_dir else None
    features = _load_features_table(base) if base and base.is_dir() else []
    clusters = _load_cluster_assignments(base) if base and base.is_dir() else {}
    feat_by_label: Dict[str, Dict[str, str]] = {}
    for row in features:
        lbl = (row.get("label") or "").strip().lower()
        if lbl:
            feat_by_label[lbl] = row

    classification_primary = bool(getattr(narrative, "classification_primary", False))
    max_fel = int(getattr(narrative, "max_fel_per_sim", 2) or 2)
    ref_archetype_study = is_reference_archetype_study(base)

    # Small / non-classification cohort → keep every simulation (up to 2 states).
    if n_sims <= 8 and not classification_primary and not ref_archetype_study:
        return StructureHighlightPlan(
            default_per_sim=min(2, max(max_fel, 1)),
            restrict_highlights=False,
        )

    # Large / classification cohort → feature a story-relevant subset.
    highlight: Set[str] = set()
    per_label: Dict[str, int] = {}
    rationale: Dict[str, str] = {}

    def _feature_up(display: str, n: int, reason: str) -> None:
        highlight.add(display)
        per_label[display] = max(per_label.get(display, 0), n)
        rationale.setdefault(display, reason)

    # Reference archetype study → exactly one representative per cluster (FEL metastates).
    if ref_archetype_study and clusters:
        summary = _load_cluster_summary(base) if base and base.is_dir() else {}
        rep_map = summary.get("cluster_representatives") or {}
        uid_to_disp: Dict[str, str] = {}
        if base and base.is_dir():
            from src.analysis.reference_labels import build_uniprot_display_map

            uid_to_disp = build_uniprot_display_map(base)

        narrative_ctx = build_reference_archetype_narrative(base) if base else None
        title_by_cid = {
            c["cluster_id"]: c["archetype_title"]
            for c in (narrative_ctx or {}).get("clusters") or []
        }

        for cid_key in sorted(rep_map, key=lambda x: int(x) if str(x).isdigit() else x):
            rep_entry = rep_map[cid_key]
            if not isinstance(rep_entry, dict):
                continue
            rep_uid = (rep_entry.get("label") or "").strip().lower()
            disp = (
                rep_entry.get("display_name")
                or uid_to_disp.get(rep_uid)
                or disp_by_label.get(rep_uid, rep_uid)
            )
            try:
                cid_int = int(cid_key)
            except (TypeError, ValueError):
                cid_int = cid_key
            title = title_by_cid.get(cid_int, "dynamic archetype")
            _feature_up(
                str(disp),
                3,
                f"Cluster {cid_key} representative ({title}) — embed major FEL "
                f"metastates to illustrate ATP–pocket coupling for this archetype.",
            )

    # Large / classification cohort → feature cluster representatives (+ optional extremes).
    elif clusters and feat_by_label:
        summary = _load_cluster_summary(base) if base and base.is_dir() else {}
        rep_map = summary.get("cluster_representatives") or {}
        uid_to_disp = {}
        if base and base.is_dir():
            from src.analysis.reference_labels import build_uniprot_display_map
            uid_to_disp = build_uniprot_display_map(base)

        members_by_cluster: Dict[int, List[str]] = {}
        for lbl, cid in clusters.items():
            members_by_cluster.setdefault(cid, []).append(lbl)

        for cid, members in sorted(members_by_cluster.items()):
            rep_entry = rep_map.get(str(cid), rep_map.get(cid, {}))
            if isinstance(rep_entry, dict):
                rep = (rep_entry.get("label") or "").strip().lower()
            else:
                rep = str(rep_entry or "").lower()
            if rep and rep in feat_by_label:
                pass
            else:
                def _diversity(lbl: str) -> float:
                    row = feat_by_label.get(lbl, {})
                    ent = _float_or_none(row, "ref_landscape_entropy")
                    if ent is None:
                        ent = _float_or_none(row, "landscape_entropy")
                    nb = _float_or_none(row, "ref_n_basins")
                    if nb is None:
                        nb = _float_or_none(row, "n_basins")
                    return (ent if ent is not None else 0.0) + 0.01 * (nb or 0.0)

                rep = max(members, key=_diversity)
            disp = uid_to_disp.get(rep, disp_by_label.get(rep, rep))
            _feature_up(
                disp, min(3, max(max_fel, 2)),
                f"Cluster {cid} representative — FEL metastates and reference-pocket "
                f"dynamics illustrate this dynamic archetype.",
            )

        # Binding-site extremes across the cohort (widest excursion, most flexible pocket).
        def _extreme(col: str, want_max: bool) -> Optional[str]:
            vals = [
                (lbl, _float_or_none(row, col))
                for lbl, row in feat_by_label.items()
            ]
            vals = [(l, v) for l, v in vals if v is not None]
            if not vals:
                return None
            return (max if want_max else min)(vals, key=lambda kv: kv[1])[0]

        widest = _extreme("ligand_pocket_distance_mean_A", True)
        if widest:
            _feature_up(
                disp_by_label.get(widest, widest), 2,
                "Widest ATP–pocket COM excursion — key binding-site outlier.",
            )
        flexible = _extreme("mean_pocket_rmsf_A", True)
        if flexible:
            _feature_up(
                disp_by_label.get(flexible, flexible), 2,
                "Most flexible ATP-binding pocket in the cohort.",
            )

    # Fallback when no features/clusters: feature the first several systems.
    if not highlight:
        for disp in display_names[: min(6, n_sims)]:
            _feature_up(disp, 1, "Representative system.")

    # Cap the featured subset so the report stays focused.
    max_highlights = max(3, len(set(clusters.values())) + 2) if clusters else 6
    if len(highlight) > max_highlights:
        kept = sorted(highlight, key=lambda d: -per_label.get(d, 0))[:max_highlights]
        highlight = set(kept)
        per_label = {d: n for d, n in per_label.items() if d in highlight}
        rationale = {d: r for d, r in rationale.items() if d in highlight}

    plan = StructureHighlightPlan(
        highlight_labels=highlight,
        structures_per_label=per_label,
        rationale=rationale,
        default_per_sim=0,
        restrict_highlights=True,
    )

    if llm_client and getattr(llm_client, "available", True) and not ref_archetype_study:
        try:
            plan = _llm_refine_structure_highlights(
                llm_client,
                plan=plan,
                user_goal=user_goal,
                display_names=display_names,
                feat_by_label=feat_by_label,
                disp_by_label=disp_by_label,
                clusters=clusters,
                literature_snippet=literature_snippet,
            )
        except Exception as exc:
            logger.warning("LLM structure-highlight refinement failed: %s", exc)

    return plan


def _llm_refine_structure_highlights(
    llm_client,
    *,
    plan: StructureHighlightPlan,
    user_goal: str,
    display_names: Sequence[str],
    feat_by_label: Dict[str, Dict[str, str]],
    disp_by_label: Dict[str, str],
    clusters: Dict[str, int],
    literature_snippet: str,
) -> StructureHighlightPlan:
    """Ask the LLM which proteins deserve multiple metastates, tied to the story."""
    rows = []
    for lbl, row in feat_by_label.items():
        disp = disp_by_label.get(lbl, lbl)
        rows.append({
            "protein": disp,
            "cluster": clusters.get(lbl),
            "atp_pocket_dist_A": _float_or_none(row, "ligand_pocket_distance_mean_A"),
            "pocket_rmsf_A": _float_or_none(row, "mean_pocket_rmsf_A"),
            "n_fel_basins": _float_or_none(row, "n_basins"),
            "fel_entropy": _float_or_none(row, "landscape_entropy"),
        })
    rows = rows[:40]

    prompt = f"""You are curating the 3D structure viewer of a combined MD report.
Choose only the proteins that matter to the scientific story and, for each,
how many conformational metastates (FEL basins, 1-3) to embed. Do NOT include
every simulation — favour cluster representatives and clear outliers.

**User goal:** {user_goal[:1500]}

**Per-simulation features (JSON):**
{json.dumps(rows, indent=1)[:4000]}

**Literature context:** {literature_snippet[:800] if literature_snippet else "None"}

Return JSON only:
{{
  "restrict": true,
  "highlights": {{
    "PROTEIN_NAME": {{"n_structures": 2, "reason": "one concise sentence tying it to the story"}}
  }}
}}

Rules:
- 3-10 proteins max. Give conformationally diverse / outlier systems 2-3 states; others 1.
- reason must connect the structure(s) to the narrative (e.g. cryptic pocket, unbinding, activation-loop rearrangement)."""

    raw = llm_client.prompt_raw(prompt, temperature=0.2, max_tokens=1500, format="json")
    text = raw if isinstance(raw, str) else str(raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return plan
    parsed = json.loads(text[start : end + 1])

    highlights = parsed.get("highlights") or {}
    if not isinstance(highlights, dict) or not highlights:
        return plan

    valid_names = set(display_names)
    new_per_label: Dict[str, int] = {}
    new_rationale: Dict[str, str] = dict(plan.rationale)
    for name, spec in highlights.items():
        if name not in valid_names:
            continue
        try:
            n = int((spec or {}).get("n_structures", 1))
        except (TypeError, ValueError):
            n = 1
        new_per_label[name] = max(1, min(3, n))
        reason = (spec or {}).get("reason")
        if isinstance(reason, str) and reason.strip():
            new_rationale[name] = reason.strip()

    if not new_per_label:
        return plan

    return StructureHighlightPlan(
        highlight_labels=set(new_per_label),
        structures_per_label=new_per_label,
        rationale=new_rationale,
        default_per_sim=0,
        restrict_highlights=bool(parsed.get("restrict", True)),
    )


def build_combined_report_plan(
    overlay_plots: Sequence[str],
    sim_dirs: Sequence[str],
    sim_labels: Sequence[str],
    user_goal: str = "",
    enriched_prompt: str = "",
    base_analysis_dir: Optional[str] = None,
    label_name_map: Optional[Dict[str, str]] = None,
    llm_client: Any = None,
    literature_snippet: str = "",
) -> CombinedReportPlan:
    """
    Review results and goal; decide which figures to include and section summaries.
    """
    from src.reporter.figure_selector import (
        dedupe_redundant_overlay_plots,
        partition_combined_overlay_plots,
        resolve_report_narrative,
    )

    base = Path(base_analysis_dir) if base_analysis_dir else None
    narrative = resolve_report_narrative(
        user_goal, enriched_prompt=enriched_prompt, n_simulations=len(sim_labels),
    )

    deduped = dedupe_redundant_overlay_plots(list(overlay_plots), narrative)
    filtered, excluded = filter_informative_plots(
        deduped,
        str(base) if base else None,
    )

    parts = partition_combined_overlay_plots(filtered)
    display_names = display_names_for_sims(sim_labels, label_name_map)
    headline = build_report_headline(sim_labels, label_name_map, user_goal=user_goal)

    summary_plots = parts.get("classification_summary") or []
    traj_plots = parts.get("cluster_trajectories") or []
    rmsf_plots = parts.get("cluster_rmsf") or []

    subsection_summaries: Dict[str, str] = {}
    if summary_plots or traj_plots or rmsf_plots:
        intro = _rule_based_classification_summary(
            base, summary_plots + traj_plots + rmsf_plots, display_names,
        ) if base and base.is_dir() else (
            "Unsupervised classification grouped simulations by shared dynamic features."
        )
        if summary_plots:
            subsection_summaries["classification_summary"] = _subsection_summary_for_plots(
                "classification_summary", summary_plots, base,
            )
        if traj_plots:
            subsection_summaries["cluster_trajectories"] = _subsection_summary_for_plots(
                "cluster_trajectories", traj_plots, base,
            )
        if rmsf_plots:
            subsection_summaries["cluster_rmsf"] = _subsection_summary_for_plots(
                "cluster_rmsf", rmsf_plots, base,
            )
    else:
        intro = ""

    classification = None
    if summary_plots or traj_plots or rmsf_plots:
        classification = SubsectionPlan(
            section_id="classification",
            title=(
                "Reference-Structure Classification (FEL + Pocket)"
                if (base and (base / "ref_fel_pock_features.csv").is_file())
                else "Dynamic Classification & Cluster Analysis"
            ),
            summary=intro,
            plot_paths=summary_plots + traj_plots + rmsf_plots,
            include=True,
        )

    # Optional LLM refinement of summaries and inclusion (when available).
    if llm_client and getattr(llm_client, "available", True):
        try:
            classification, subsection_summaries, excluded = _llm_refine_plan(
                llm_client,
                user_goal=user_goal,
                headline=headline,
                classification=classification,
                subsection_summaries=subsection_summaries,
                excluded=excluded,
                display_names=display_names,
                literature_snippet=literature_snippet,
                parts=parts,
            )
        except Exception as exc:
            logger.warning("LLM report curation failed, using rule-based plan: %s", exc)

    structure_highlight = build_structure_highlight_plan(
        sim_dirs,
        sim_labels,
        base_analysis_dir=str(base) if base else None,
        label_name_map=label_name_map,
        user_goal=user_goal,
        enriched_prompt=enriched_prompt,
        narrative=narrative,
        llm_client=llm_client,
        literature_snippet=literature_snippet,
    )

    return CombinedReportPlan(
        headline=headline,
        classification_section=classification,
        included_overlay_plots=filtered,
        excluded_plots=excluded,
        subsection_summaries=subsection_summaries,
        structure_highlight=structure_highlight,
    )


def _llm_refine_plan(
    llm_client,
    *,
    user_goal: str,
    headline: str,
    classification: Optional[SubsectionPlan],
    subsection_summaries: Dict[str, str],
    excluded: Dict[str, str],
    display_names: Sequence[str],
    literature_snippet: str,
    parts: Dict[str, List[str]],
) -> Tuple[Optional[SubsectionPlan], Dict[str, str], Dict[str, str]]:
    """Ask the LLM to refine section summaries and confirm plot inclusion."""
    available = {
        "classification_summary": [Path(p).name for p in parts.get("classification_summary") or []],
        "cluster_trajectories": [Path(p).name for p in parts.get("cluster_trajectories") or []],
        "cluster_rmsf": [Path(p).name for p in parts.get("cluster_rmsf") or []],
    }
    already_excluded = {Path(k).name: v for k, v in excluded.items()}

    prompt = f"""You are curating a combined MD simulation HTML report.

**User goal:** {user_goal[:2000]}

**Systems ({len(display_names)}):** {", ".join(display_names)}

**Available figure groups:** {json.dumps(available, indent=2)}

**Already excluded (data-driven):** {json.dumps(already_excluded, indent=2)}

**Literature context (snippet):** {literature_snippet[:1200] if literature_snippet else "None"}

Return JSON only:
{{
  "headline_ok": true,
  "classification_intro": "2-3 sentence summary of classification findings for the report section",
  "subsection_summaries": {{
    "classification_summary": "1-2 sentences",
    "cluster_trajectories": "1-2 sentences on what cluster trajectory plots show",
    "cluster_rmsf": "1-2 sentences or empty if not meaningful"
  }},
  "exclude_plots": {{"plot_basename.png": "brief reason"}},
  "include_plots": {{"plot_basename.png": true}}
}}

Rules:
- Align with the user goal; if classification/clustering is the objective, emphasise FEL/phylo tree and cluster contrasts.
- Exclude any plot that adds no discriminative insight (e.g. residence when ligand never unbinds).
- Do not mention plots that are excluded.
- Keep summaries factual and concise."""

    raw = llm_client.prompt_raw(prompt, temperature=0.25, max_tokens=2048, format="json")
    text = raw if isinstance(raw, str) else str(raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return classification, subsection_summaries, excluded
    parsed = json.loads(text[start : end + 1])

    new_summaries = dict(subsection_summaries)
    for key, val in (parsed.get("subsection_summaries") or {}).items():
        if isinstance(val, str) and val.strip():
            new_summaries[key] = val.strip()

    if classification and parsed.get("classification_intro"):
        classification = SubsectionPlan(
            section_id=classification.section_id,
            title=classification.title,
            summary=str(parsed["classification_intro"]).strip(),
            plot_paths=list(classification.plot_paths),
            include=classification.include,
        )

    exclude_extra = parsed.get("exclude_plots") or {}
    include_map = parsed.get("include_plots") or {}
    new_excluded = dict(excluded)

    if classification:
        kept: List[str] = []
        for p in classification.plot_paths:
            base = Path(p).name
            if base in exclude_extra:
                new_excluded[p] = str(exclude_extra[base])
                continue
            if include_map and base in include_map and include_map[base] is False:
                new_excluded[p] = "Excluded by reporter review (not aligned with study goal)."
                continue
            kept.append(p)
        classification = SubsectionPlan(
            section_id=classification.section_id,
            title=classification.title,
            summary=classification.summary,
            plot_paths=kept,
            include=bool(kept),
        )

    return classification, new_summaries, new_excluded
