"""Science completeness gates — process success is not enough."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from agentic.campaign.family_recipe import FAMILY_FEATURE_COLUMNS, FAMILY_MODULAR_DIRS
from agentic.campaign.spec import CampaignSpec, spec_from_state

logger = logging.getLogger(__name__)

# Visualisation-only tools. A failed plot must not fail the simulation.
NONCRITICAL_ANALYSIS_TOOLS = frozenset(
    {
        "plot_md_data",
        "plot_md_multipanel",
        "plot_multipanel",
        "plot_pca_projection",
        "plot_sasa",
        "plot_dccm_comparison",
        "plot_dccm_difference",
        "plot_combined_data",
        "plot_reference_msa_alignment",
        "plot_global_mapped_alignment",
    }
)

FAMILY_TOOL_OUTPUT_DIRS = {
    "calculate_consensus_torsions": "consensus_dihedrals",
    "calculate_consensus_rmsf_features": "consensus_rmsf",
    "calculate_consensus_dccm_features": "consensus_DCCM",
    "run_independent_dynamics_fel": "consensus_PCA",
    "calculate_consensus_pocket_metrics": "reference_pocket",
}

FAMILY_TOOL_OUTPUT_FILES = {
    "calculate_consensus_pocket_metrics": (
        "reference_pocket_metrics.json",
        "ligand_pocket_distance.csv",
    ),
}


def is_noncritical_analysis_tool(tool_name: str) -> bool:
    name = (tool_name or "").strip()
    if not name:
        return False
    if name in NONCRITICAL_ANALYSIS_TOOLS:
        return True
    return name.startswith("plot_")


def decide_analysis_success(*, artifact_ok: bool, critical_issues: Sequence[str]) -> bool:
    """Pass if required artifacts exist, or if only non-critical steps failed."""
    if artifact_ok:
        return True
    return not bool(critical_issues)


def _dir_has_output(root: Path, name: str) -> bool:
    target = root / name
    if not target.is_dir():
        return False
    return any(
        target.glob(pat) for pat in ("*.json", "*.csv", "*.dat", "*.npz")
    )


def _search_dirs(working_dir: str) -> List[Path]:
    analysis = Path(working_dir) / "analysis"
    dirs = [analysis]
    if (analysis / "avg").is_dir():
        dirs.append(analysis / "avg")
    dirs.extend(sorted(analysis.glob("rep*")))
    return dirs


def modular_output_present(analysis_dir: str, name: str) -> bool:
    """True when one modular output dir under analysis/ (or avg/rep*) has files."""
    root = Path(analysis_dir)
    candidates = [root, root / "avg", *sorted(root.glob("rep*"))]
    if root.name != "analysis" and (root / "analysis").is_dir():
        candidates = _search_dirs(str(root))
    return any(_dir_has_output(d, name) for d in candidates)


def family_tool_already_done(analysis_dir: str, tool_name: str) -> bool:
    mapped = FAMILY_TOOL_OUTPUT_DIRS.get(tool_name or "")
    if mapped and modular_output_present(analysis_dir, mapped):
        return True
    files = FAMILY_TOOL_OUTPUT_FILES.get(tool_name or "")
    if files:
        root = Path(analysis_dir)
        candidates = [root, root / "avg", *sorted(root.glob("rep*"))]
        if root.name != "analysis" and (root / "analysis").is_dir():
            candidates = _search_dirs(str(root))
        for d in candidates:
            if any((d / name).is_file() and (d / name).stat().st_size > 0 for name in files):
                return True
    return False


def per_sim_modular_complete(working_dir: str, modular_dirs: Sequence[str]) -> bool:
    search = _search_dirs(working_dir)
    if not search:
        return False
    needed = list(modular_dirs) or list(FAMILY_MODULAR_DIRS)
    for d in search:
        if all(_dir_has_output(d, name) for name in needed):
            return True
    return all(any(_dir_has_output(d, name) for d in search) for name in needed)


def per_sim_science_complete(
    working_dir: str,
    spec: Optional[CampaignSpec] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return ``{ok, missing, reason}`` for one simulation directory."""
    spec = spec or spec_from_state(state)
    wd = Path(working_dir)
    if not wd.is_dir():
        return {"ok": False, "missing": ["working_dir"], "reason": "missing working_dir"}

    if spec is None or not spec.family_modular:
        summary = wd / "analysis" / "analysis_summary.jsonl"
        ok = summary.is_file()
        return {
            "ok": ok,
            "missing": [] if ok else ["analysis/analysis_summary.jsonl"],
            "reason": "" if ok else "no analysis_summary.jsonl",
        }

    missing: List[str] = []
    analysis = wd / "analysis"
    if not per_sim_modular_complete(str(wd), spec.contract.modular_dirs):
        missing.append("consensus_* modular dirs")
    # Required calculations (general MD): each must leave its artifact contract.
    for tool in list(spec.pin_tools or []):
        if tool not in FAMILY_TOOL_OUTPUT_DIRS and tool not in FAMILY_TOOL_OUTPUT_FILES:
            continue
        if family_tool_already_done(str(analysis), tool):
            continue
        if family_tool_already_done(str(wd), tool):
            continue
        missing.append(tool)
    summary = analysis / "analysis_summary.jsonl"
    if not summary.is_file() and not any(wd.glob("analysis/rep*/analysis_summary.jsonl")):
        missing.append("analysis_summary.jsonl")
    ok = not missing
    return {
        "ok": ok,
        "missing": missing,
        "reason": "" if ok else "; ".join(missing),
    }


def _finite(value: str) -> bool:
    raw = (value or "").strip()
    if not raw or raw.lower() in {"nan", "none", "null", "inf", "-inf"}:
        return False
    try:
        float(raw)
        return True
    except ValueError:
        return False


def clustering_table_usable(
    csv_path: str,
    *,
    min_rows: int = 2,
    min_cols: int = 2,
) -> Dict[str, Any]:
    """True when a dendrogram + heatmap can be drawn from whatever columns exist.

    General-purpose: users will not always compute the family gold set. Two
    simulations and two finite numeric columns are enough to plot.
    """
    path = Path(csv_path)
    skip = {"label", "sim_directory", "n_features_present"}
    if not path.is_file():
        return {
            "ok": False,
            "n_rows": 0,
            "n_feature_cols": 0,
            "reason": f"missing {path}",
        }
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return {"ok": False, "n_rows": 0, "n_feature_cols": 0, "reason": "empty feature table"}
    cols = [c for c in (rows[0].keys()) if c and c not in skip]
    usable_cols = []
    for col in cols:
        n_fin = sum(1 for row in rows if _finite(row.get(col, "")))
        if n_fin >= min_rows:
            usable_cols.append(col)
    n_rows = len(rows)
    ok = n_rows >= min_rows and len(usable_cols) >= min_cols
    reason = ""
    if not ok:
        reason = (
            f"need ≥{min_rows} rows and ≥{min_cols} numeric columns "
            f"(have {n_rows} rows, {len(usable_cols)} usable)"
        )
    return {
        "ok": ok,
        "n_rows": n_rows,
        "n_feature_cols": len(usable_cols),
        "usable_columns": usable_cols,
        "reason": reason,
    }


def family_feature_matrix_ready(
    csv_path: str,
    spec: Optional[CampaignSpec] = None,
    *,
    required_columns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """True when enough rows have the required family columns filled."""
    path = Path(csv_path)
    required = list(required_columns or (spec.analysis_recipe.required_feature_columns if spec else FAMILY_FEATURE_COLUMNS))
    min_frac = spec.contract.min_complete_fraction if spec else 0.85
    allow_partial = bool(spec and spec.allow_partial_combined)
    if not path.is_file():
        return {
            "ok": False,
            "n_rows": 0,
            "n_complete": 0,
            "fraction": 0.0,
            "reason": f"missing {path}",
            "allow_partial": allow_partial,
        }

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return {
            "ok": False,
            "n_rows": 0,
            "n_complete": 0,
            "fraction": 0.0,
            "reason": "empty feature table",
            "allow_partial": allow_partial,
        }

    header = set(rows[0].keys()) if rows else set()
    present_required = [c for c in required if c in header]
    n_complete = 0
    for row in rows:
        if required and all(_finite(row.get(c, "")) for c in required):
            n_complete += 1
    n_rows = len(rows)
    fraction = n_complete / n_rows if n_rows else 0.0
    ok = fraction >= min_frac and n_complete >= 2
    if allow_partial and n_complete >= 2:
        ok = True
    reason = ""
    if not ok:
        reason = (
            f"feature matrix incomplete: {n_complete}/{n_rows} rows have all "
            f"{len(required)} required columns "
            f"({len(present_required)} present in table; need ≥{min_frac:.0%})"
        )
    return {
        "ok": ok,
        "n_rows": n_rows,
        "n_complete": n_complete,
        "fraction": fraction,
        "reason": reason,
        "allow_partial": allow_partial,
        "required_columns": present_required,
    }


def campaign_science_report(
    base_dir: str,
    spec: Optional[CampaignSpec] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Campaign-level science completeness for run_summary / combined gate."""
    spec = spec or spec_from_state(state)
    base = Path(base_dir)
    labels = list((spec.labels if spec else []) or [])
    if not labels:
        labels = [
            p.name
            for p in sorted(base.iterdir())
            if p.is_dir() and (p / "analysis").is_dir()
        ]
    per_sim: List[Dict[str, Any]] = []
    n_ok = 0
    for label in labels:
        wd = base / label
        rec = per_sim_science_complete(str(wd), spec=spec)
        rec["label"] = label
        per_sim.append(rec)
        if rec.get("ok"):
            n_ok += 1
    feat = base / "analysis" / "classification_features.csv"
    matrix = family_feature_matrix_ready(str(feat), spec) if spec and spec.family_modular else {
        "ok": True,
        "n_rows": 0,
        "n_complete": 0,
        "fraction": 1.0,
        "reason": "",
    }
    n_total = len(labels) or 1
    ok = n_ok == len(labels) and bool(matrix.get("ok"))
    if spec and spec.allow_partial_combined:
        ok = n_ok > 0
    return {
        "ok": ok,
        "family_modular": bool(spec.family_modular) if spec else False,
        "n_science_complete": n_ok,
        "n_systems": len(labels),
        "science_fraction": n_ok / n_total,
        "incomplete_labels": [r["label"] for r in per_sim if not r.get("ok")],
        "matrix": matrix,
        "per_sim": per_sim,
    }
