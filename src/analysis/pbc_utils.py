"""
Periodic-boundary-condition (PBC) helpers for distance analyses.

Center-of-mass distances between two atom groups can show sharp, transient
spikes when one group (e.g. a ligand) is imaged to a periodic copy on the far
side of the box, or when the trajectory wrapping splits a molecule across a
boundary. These artifacts inflate the mean/variance of metrics such as the
ligand–pocket COM distance and produce ugly, misleading overlay plots.

Two complementary tools are provided:

- ``minimum_image_distance`` — compute the PBC-correct (minimum-image) distance
  between two points, used at the source when iterating a trajectory.
- ``clean_pbc_distance_series`` — remove residual transient spikes from an
  already-computed distance series (used when reading CSVs written by earlier
  runs that did not apply the minimum-image convention).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    HAS_NUMPY = False


def minimum_image_distance(point_a, point_b, box=None) -> float:
    """Minimum-image distance between two points respecting PBC.

    Args:
        point_a, point_b: length-3 coordinate arrays (Å).
        box: MDAnalysis-style box vector ``[lx, ly, lz, alpha, beta, gamma]``
            (``Timestep.dimensions``). When ``None`` or degenerate, falls back
            to the plain Euclidean distance.

    Returns:
        Distance in Å.
    """
    a = np.asarray(point_a, dtype=float)
    b = np.asarray(point_b, dtype=float)

    valid_box = (
        box is not None
        and len(box) >= 3
        and all(float(box[i]) > 0.0 for i in range(3))
    )
    if not valid_box:
        return float(np.linalg.norm(a - b))

    # Prefer MDAnalysis' implementation (handles triclinic boxes correctly).
    try:
        from MDAnalysis.lib.distances import calc_bonds

        return float(
            calc_bonds(
                a.astype(np.float32),
                b.astype(np.float32),
                box=np.asarray(box, dtype=np.float32),
            )
        )
    except Exception:
        # Orthorhombic minimum-image fallback.
        lengths = np.asarray(box, dtype=float)[:3]
        d = a - b
        d -= lengths * np.round(d / lengths)
        return float(np.linalg.norm(d))


def clean_pbc_distance_series(
    distances: Sequence[float],
    *,
    window: int = 7,
    k: float = 6.0,
    abs_floor: float = 2.0,
) -> Tuple["np.ndarray", "np.ndarray", int]:
    """Remove transient PBC spikes from a distance time series.

    Uses a rolling-median baseline so that *sustained* changes (real binding /
    unbinding, drift) are preserved, while *isolated* jumps that deviate far
    from their local neighbourhood (the hallmark of a PBC imaging artifact) are
    replaced by the local median.

    Args:
        distances: 1-D sequence of per-frame distances (Å).
        window: Odd rolling-median window (frames). Even values are bumped +1.
        k: Robust (MAD-scaled) threshold multiplier for flagging spikes.
        abs_floor: Minimum absolute residual (Å) required to flag a point, so
            that near-constant series are not over-cleaned by numerical noise.

    Returns:
        ``(cleaned, spike_mask, n_removed)`` where ``cleaned`` is the de-spiked
        array, ``spike_mask`` marks replaced frames, and ``n_removed`` is the
        number of frames replaced.
    """
    x = np.asarray(distances, dtype=float)
    n = x.size
    if n < 5:
        return x.copy(), np.zeros(n, dtype=bool), 0

    w = window if window % 2 == 1 else window + 1
    half = w // 2

    med_filt = np.empty(n)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        med_filt[i] = np.median(x[lo:hi])

    resid = x - med_filt
    mad = np.median(np.abs(resid - np.median(resid)))
    sigma = 1.4826 * mad if mad > 0 else 0.0
    thresh = max(k * sigma, abs_floor)

    spike = np.abs(resid) > thresh
    cleaned = x.copy()
    cleaned[spike] = med_filt[spike]
    return cleaned, spike, int(spike.sum())


def clean_distance_csv(
    src_path: str,
    dst_path: str,
    *,
    distance_columns: Optional[Sequence[str]] = None,
) -> Tuple[bool, int]:
    """Read a per-frame distance CSV, de-spike the distance column, and rewrite.

    Handles the standard ``frame,time_ns,distance_angstrom`` layout produced by
    the COM/ligand-pocket tools, falling back to common alternative column names.

    Args:
        src_path: Input CSV path.
        dst_path: Output CSV path (may equal ``src_path`` to clean in place).
        distance_columns: Candidate distance column names to search, in order.

    Returns:
        ``(success, n_removed)``.
    """
    import csv

    candidates = list(distance_columns or (
        "distance_angstrom", "distance_A", "distance",
    ))
    try:
        with open(src_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except Exception as exc:
        logger.warning("clean_distance_csv: cannot read %s: %s", src_path, exc)
        return False, 0

    dist_col = next((c for c in candidates if c in fieldnames), None)
    if not dist_col or not rows:
        return False, 0

    try:
        values = [float(r[dist_col]) for r in rows]
    except (KeyError, TypeError, ValueError):
        return False, 0

    cleaned, _, n_removed = clean_pbc_distance_series(values)
    for row, val in zip(rows, cleaned):
        row[dist_col] = f"{val:.4f}"

    try:
        with open(dst_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as exc:
        logger.warning("clean_distance_csv: cannot write %s: %s", dst_path, exc)
        return False, 0

    if n_removed:
        logger.info(
            "clean_distance_csv: removed %d PBC spike(s) from %s",
            n_removed, src_path,
        )
    return True, n_removed


_DISTANCE_CSV_NAMES = (
    "ligand_pocket_distance.csv",
    "pocket_distance.csv",
    "com_distance.csv",
)


def distance_stats_from_csv(csv_path: str) -> Optional[dict]:
    """Return mean/std/min/max/n_frames from a distance CSV."""
    import csv

    candidates = ("distance_angstrom", "distance_A", "distance")
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            col = next((c for c in candidates if c in (reader.fieldnames or [])), None)
            if not col:
                return None
            vals = [float(row[col]) for row in reader if row.get(col) not in (None, "")]
    except Exception:
        return None
    if not vals:
        return None
    arr = np.asarray(vals, dtype=float)
    return {
        "n_frames": len(arr),
        "mean_distance_angstrom": round(float(np.mean(arr)), 4),
        "std_distance_angstrom": round(float(np.std(arr)), 4),
        "min_distance_angstrom": round(float(np.min(arr)), 4),
        "max_distance_angstrom": round(float(np.max(arr)), 4),
    }


def patch_ligand_pocket_summary_stats(analysis_dir: str, csv_name: str = "ligand_pocket_distance.csv") -> bool:
    """Update the latest Ligand_Pocket_COM_Distance block in analysis_summary.jsonl."""
    import json

    summary_path = Path(analysis_dir) / "analysis_summary.jsonl"
    if not summary_path.is_file():
        return False
    stats = distance_stats_from_csv(str(Path(analysis_dir) / csv_name))
    if not stats:
        return False

    text = summary_path.read_text(encoding="utf-8", errors="replace")
    chunks = [c.strip() for c in text.split("---") if c.strip()]
    if not chunks:
        return False

    updated = False
    parsed: list = []
    for chunk in chunks:
        if not chunk.startswith("{"):
            chunk = "{" + chunk
        if not chunk.endswith("}"):
            chunk = chunk + "}"
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            parsed.append(chunk)
            continue
        parsed.append(obj)

    for i in range(len(parsed) - 1, -1, -1):
        obj = parsed[i]
        if not isinstance(obj, dict):
            continue
        if obj.get("analysis_type") != "Ligand_Pocket_COM_Distance":
            continue
        st = obj.setdefault("statistics", {})
        for key in (
            "mean_distance_angstrom",
            "std_distance_angstrom",
            "min_distance_angstrom",
            "max_distance_angstrom",
        ):
            if key in stats:
                st[key] = stats[key]
        if "n_frames" in stats:
            st["n_frames"] = stats["n_frames"]
        updated = True
        break

    if not updated:
        return False

    out_parts = []
    for obj in parsed:
        if isinstance(obj, dict):
            out_parts.append(json.dumps(obj, indent=2))
        else:
            out_parts.append(str(obj))
    summary_path.write_text("\n---\n".join(out_parts) + "\n", encoding="utf-8")
    return True


def _needs_com_recompute(csv_path: Path, *, max_threshold: float = 15.0, mean_threshold: float = 8.0) -> bool:
    """True when de-spiked CSV still has unphysical ligand–pocket distances."""
    stats = distance_stats_from_csv(str(csv_path))
    if not stats:
        return False
    return (
        stats["max_distance_angstrom"] > max_threshold
        or stats["mean_distance_angstrom"] > mean_threshold
    )


def recompute_ligand_pocket_distance_csv(sim_dir: str, ligand_selection: str = "resname ATP") -> bool:
    """Recompute ligand–pocket COM distance with minimum-image PBC correction."""
    sim = Path(sim_dir).resolve()
    hpc = sim / "hpc"
    tpr = hpc / "md.tpr"
    xtc = hpc / "mdWrap.xtc"
    if not xtc.is_file():
        xtc = hpc / "md.xtc"
    analysis_dir = sim / "analysis"
    if not tpr.is_file() or not xtc.is_file() or not analysis_dir.is_dir():
        logger.warning("recompute_ligand_pocket_distance_csv: missing inputs for %s", sim_dir)
        return False

    from src.analysis.com_distance_calculator import calculate_ligand_pocket_distance

    logger.info("Recomputing ligand-pocket distance for %s (minimum-image PBC)", sim.name)
    result = calculate_ligand_pocket_distance.func(
        topology_file=str(tpr),
        trajectory_file=str(xtc),
        ligand_selection=ligand_selection,
        output_file="ligand_pocket_distance.csv",
        working_dir=str(analysis_dir),
    )
    if not result.get("success"):
        logger.warning(
            "recompute_ligand_pocket_distance_csv failed for %s: %s",
            sim.name, result.get("error"),
        )
        return False
    patch_ligand_pocket_summary_stats(str(analysis_dir))
    return True


def clean_com_distance_csv_tree(
    base_dir: str,
    *,
    dry_run: bool = False,
    patch_summary: bool = True,
    recompute_broken: bool = True,
    ligand_selection: str = "resname ATP",
) -> dict:
    """De-spike all per-sim COM / ligand-pocket distance CSVs under *base_dir*.

    Walks ``{base}/{label}/analysis/`` for standard distance filenames and
    rewrites each CSV in place. Optionally refreshes
    ``analysis_summary.jsonl`` statistics for ``Ligand_Pocket_COM_Distance``.

    Returns a summary dict with counts and per-file spike removals.
    """
    base = Path(base_dir)
    results = {
        "base_dir": str(base.resolve()),
        "files_found": 0,
        "files_cleaned": 0,
        "total_spikes_removed": 0,
        "summaries_patched": 0,
        "files_recomputed": 0,
        "details": [],
    }

    for sim_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        analysis_dir = sim_dir / "analysis"
        if not analysis_dir.is_dir():
            continue
        for name in _DISTANCE_CSV_NAMES:
            csv_path = analysis_dir / name
            if not csv_path.is_file():
                continue
            results["files_found"] += 1
            if dry_run:
                import csv as _csv
                with csv_path.open(newline="", encoding="utf-8") as fh:
                    reader = _csv.DictReader(fh)
                    col = next(
                        (c for c in ("distance_angstrom", "distance_A", "distance")
                         if c in (reader.fieldnames or [])),
                        None,
                    )
                    vals = [float(r[col]) for r in reader] if col else []
                if vals:
                    _, _, n = clean_pbc_distance_series(vals)
                    results["details"].append({
                        "sim": sim_dir.name,
                        "file": name,
                        "spikes_would_remove": n,
                    })
                    results["total_spikes_removed"] += n
                continue

            ok, n_removed = clean_distance_csv(str(csv_path), str(csv_path))
            if ok:
                results["files_cleaned"] += 1
                results["total_spikes_removed"] += n_removed
                detail = {
                    "sim": sim_dir.name,
                    "file": name,
                    "spikes_removed": n_removed,
                }
                if (
                    recompute_broken
                    and name.startswith("ligand_pocket")
                    and _needs_com_recompute(csv_path)
                ):
                    if recompute_ligand_pocket_distance_csv(
                        str(sim_dir), ligand_selection=ligand_selection
                    ):
                        results["files_recomputed"] += 1
                        detail["recomputed"] = True
                        stats = distance_stats_from_csv(str(csv_path))
                        if stats:
                            detail["max_after_recompute"] = stats["max_distance_angstrom"]
                            detail["mean_after_recompute"] = stats["mean_distance_angstrom"]
                results["details"].append(detail)
                if patch_summary and name.startswith("ligand_pocket"):
                    if patch_ligand_pocket_summary_stats(str(analysis_dir), name):
                        results["summaries_patched"] += 1
            break  # one distance CSV per sim dir

    return results


if __name__ == "__main__":
    import argparse
    import json as _json
    from pathlib import Path as _Path

    parser = argparse.ArgumentParser(
        description="Remove PBC spikes from per-sim ligand-pocket COM distance CSVs.",
    )
    parser.add_argument(
        "base_dir",
        help="Multi-simulation base directory (e.g. ./pseudoKin)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report spikes that would be removed without writing files",
    )
    parser.add_argument(
        "--no-patch-summary",
        action="store_true",
        help="Do not update analysis_summary.jsonl statistics",
    )
    parser.add_argument(
        "--no-recompute",
        action="store_true",
        help="Skip trajectory recomputation for sims still unphysical after de-spiking",
    )
    parser.add_argument(
        "--ligand-selection",
        default="resname ATP",
        help="MDAnalysis ligand selection for recomputation (default: resname ATP)",
    )
    args = parser.parse_args()
    summary = clean_com_distance_csv_tree(
        args.base_dir,
        dry_run=args.dry_run,
        patch_summary=not args.no_patch_summary,
        recompute_broken=not args.no_recompute,
        ligand_selection=args.ligand_selection,
    )
    print(_json.dumps(summary, indent=2))
