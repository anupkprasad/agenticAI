"""Assign N-lobe vs C-lobe atoms for family DCCM.

Paper default: consensus-index cut on the **full** global_mapped alignment
(``ci <= 34`` N-lobe, ``ci >= 35`` C-lobe). That only works when enough mapped
columns exist. If the map is too short, fall back to KAPCA/reference residue
numbers (PKA hinge ≈ 125), then a midpoint of present indices.

Users can override cuts or pass ``lobe_method`` explicitly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# Ment / paper defaults on the full MAFFT similarity≥0.5 map (~142 columns).
DEFAULT_N_LOBE_CI_MAX = 34
DEFAULT_C_LOBE_CI_MIN = 35
# PKA (P17612 / KAPCA) hinge: N-lobe through ~120, C-lobe from ~128.
DEFAULT_KAPCA_HINGE_RESID = 125
DEFAULT_REFERENCE_LABELS = (
    "p17612",
    "p17612_ATP",
    "KAPCA",
    "kapca",
    "PKA",
)


def assign_n_c_lobe_indices(
    meta: Sequence[Dict[str, Any]],
    *,
    alignment: Optional[Dict[str, Any]] = None,
    n_lobe_ci_max: int = DEFAULT_N_LOBE_CI_MAX,
    c_lobe_ci_min: int = DEFAULT_C_LOBE_CI_MIN,
    reference_labels: Sequence[str] = DEFAULT_REFERENCE_LABELS,
    hinge_resid: int = DEFAULT_KAPCA_HINGE_RESID,
    lobe_method: str = "auto",
) -> Tuple[List[int], List[int], Dict[str, Any]]:
    """Return ``(n_idx, c_idx, info)`` into *meta* (atom / residue rows)."""
    method = (lobe_method or "auto").lower().strip()
    cis = [int(m.get("consensus_index", i)) for i, m in enumerate(meta)]
    info: Dict[str, Any] = {
        "N_LOBE_CI_MAX": int(n_lobe_ci_max),
        "C_LOBE_CI_MIN": int(c_lobe_ci_min),
        "hinge_resid": int(hinge_resid),
    }

    if method in {"auto", "consensus_index", "ci"}:
        max_ci = max(cis) if cis else -1
        if max_ci >= int(c_lobe_ci_min) or method in {"consensus_index", "ci"}:
            n_idx = [i for i, ci in enumerate(cis) if ci <= int(n_lobe_ci_max)]
            c_idx = [i for i, ci in enumerate(cis) if ci >= int(c_lobe_ci_min)]
            info["lobe_method"] = "consensus_index"
            return n_idx, c_idx, info
        if method in {"consensus_index", "ci"}:
            info["lobe_method"] = "consensus_index"
            return (
                [i for i, ci in enumerate(cis) if ci <= int(n_lobe_ci_max)],
                [i for i, ci in enumerate(cis) if ci >= int(c_lobe_ci_min)],
                info,
            )

    if method in {"auto", "reference_resid", "kapca"}:
        n_idx, c_idx, ref_used = _split_by_reference_resid(
            meta,
            alignment,
            reference_labels=reference_labels,
            hinge_resid=int(hinge_resid),
        )
        if n_idx and c_idx:
            info["lobe_method"] = "reference_resid"
            info["reference_label"] = ref_used
            return n_idx, c_idx, info
        if method in {"reference_resid", "kapca"}:
            info["lobe_method"] = "reference_resid"
            info["reference_label"] = ref_used
            return n_idx, c_idx, info

    if cis:
        mid = 0.5 * (min(cis) + max(cis))
        n_idx = [i for i, ci in enumerate(cis) if ci <= mid]
        c_idx = [i for i, ci in enumerate(cis) if ci > mid]
    else:
        n_idx, c_idx = [], []
    info["lobe_method"] = "midpoint_fallback"
    info["midpoint_ci"] = float(mid) if cis else None
    return n_idx, c_idx, info


def _split_by_reference_resid(
    meta: Sequence[Dict[str, Any]],
    alignment: Optional[Dict[str, Any]],
    *,
    reference_labels: Sequence[str],
    hinge_resid: int,
) -> Tuple[List[int], List[int], Optional[str]]:
    if not alignment:
        return [], [], None
    from src.analysis.family_dynamics_core import mapping_for_label

    ref_map = None
    ref_used = None
    for lab in reference_labels:
        mapping = mapping_for_label(alignment, lab)
        if mapping and any(m and m.get("resid") is not None for m in mapping):
            ref_map = mapping
            ref_used = lab
            break
    if not ref_map:
        return [], [], None

    n_idx: List[int] = []
    c_idx: List[int] = []
    for i, m in enumerate(meta):
        ci = int(m.get("consensus_index", i))
        hit = ref_map[ci] if 0 <= ci < len(ref_map) else None
        resid = None
        if isinstance(hit, dict):
            resid = hit.get("resid")
        if resid is None:
            resid = m.get("resid")
        if resid is None:
            continue
        if int(resid) <= hinge_resid:
            n_idx.append(i)
        else:
            c_idx.append(i)
    return n_idx, c_idx, ref_used
