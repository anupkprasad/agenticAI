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
class CombinedReportPlan:
    headline: str
    classification_section: Optional[SubsectionPlan] = None
    comparative_summary: str = ""
    included_overlay_plots: List[str] = field(default_factory=list)
    excluded_plots: Dict[str, str] = field(default_factory=dict)
    subsection_summaries: Dict[str, str] = field(default_factory=dict)


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
    for name in ("classification_features.csv", "classification_features_zscore.csv"):
        path = base_analysis_dir / name
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    return []


def _load_cluster_assignments(base_analysis_dir: Path) -> Dict[str, int]:
    path = base_analysis_dir / "classification_cluster_assignments.csv"
    if not path.is_file():
        return {}
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
    return out


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
    clusters = _load_cluster_assignments(base_analysis_dir)
    features = _load_features_table(base_analysis_dir)
    n_sims = len(display_names)
    n_clusters = len(set(clusters.values())) if clusters else 0

    parts = [
        f"Unsupervised clustering grouped {n_sims} holo systems into "
        f"{n_clusters or 'several'} dynamic regime(s) using binding-site and "
        f"conformational features derived from the trajectories."
    ]

    if clusters and features:
        by_c: Dict[int, List[str]] = {}
        for row in features:
            lbl = (row.get("label") or "").lower()
            if lbl in clusters:
                by_c.setdefault(clusters[lbl], []).append(
                    row.get("display_name") or lbl
                )
        if by_c:
            cluster_bits = []
            for cid in sorted(by_c):
                members = ", ".join(sorted(set(by_c[cid])))
                cluster_bits.append(f"cluster {cid} ({members})")
            parts.append("Assignments: " + "; ".join(cluster_bits) + ".")

    if any("phylo" in Path(p).name.lower() for p in plot_paths):
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
            "PCA projection, dendrogram, and phylogenetic tree visualise how simulations "
            "partition into conformationally related groups."
        )
    return ""


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
            title="Dynamic Classification & Cluster Analysis",
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

    return CombinedReportPlan(
        headline=headline,
        classification_section=classification,
        included_overlay_plots=filtered,
        excluded_plots=excluded,
        subsection_summaries=subsection_summaries,
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
