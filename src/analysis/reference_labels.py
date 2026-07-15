"""Resolve UniProt simulation IDs vs reference-pipeline display labels."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Set


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_reference_pca_manifest(base_analysis: Path) -> Dict[str, Any]:
    return _load_json(base_analysis / "reference_fel" / "reference_pca_manifest.json")


def uniprot_to_reference_fel_label(sim_uid: str, base_analysis: Path) -> str:
    """Map ``{uniprot}/`` directory name to ``reference_fel/{label}/`` folder name."""
    sim_uid_l = str(sim_uid).lower()
    manifest = load_reference_pca_manifest(base_analysis)
    for fel_label, sim_path in (manifest.get("sim_directories") or {}).items():
        if Path(str(sim_path)).name.lower() == sim_uid_l:
            return str(fel_label)
    return str(sim_uid)


def reference_fel_paths_for_sim(
    sim_uid: str,
    base_analysis: Path,
    filename: str,
) -> list[Path]:
    """Candidate paths under the combined ``reference_fel/`` tree."""
    fel_label = uniprot_to_reference_fel_label(sim_uid, base_analysis)
    root = base_analysis / "reference_fel"
    return [
        root / fel_label / filename,
        root / sim_uid / filename,
    ]


def build_uniprot_display_map(base_analysis: Path) -> Dict[str, str]:
    """``uniprot_id`` → display label (e.g. ``q8nb16`` → ``MLKL``)."""
    manifest = load_reference_pca_manifest(base_analysis)
    out: Dict[str, str] = {}
    for disp, sim_path in (manifest.get("sim_directories") or {}).items():
        uid = Path(str(sim_path)).name
        out[uid.lower()] = str(disp)
    return out


def _normalize_label_set(values: Optional[Set[str]]) -> Set[str]:
    return {str(v).lower() for v in (values or set()) if v}


def is_reference_pocket_usable(
    sim_uid: str,
    manifest: Dict[str, Any],
    *,
    base_analysis: Optional[Path] = None,
) -> bool:
    """
    True when reference-pocket metrics for ``sim_uid`` should be read/plotted.

    Manifest ``usable_labels`` stores display names; per-sim outputs live under
    ``reference_pocket/{uniprot}/``.
    """
    usable_labels = _normalize_label_set(set(manifest.get("usable_labels") or []))
    usable_ids = _normalize_label_set(set(manifest.get("usable_sim_ids") or []))
    if not usable_labels and not usable_ids:
        return True

    sim_uid_l = str(sim_uid).lower()
    if sim_uid_l in usable_ids or sim_uid_l in usable_labels:
        return True

    if base_analysis is not None:
        disp = build_uniprot_display_map(base_analysis).get(sim_uid_l, "")
        if disp.lower() in usable_labels:
            return True
    return False
