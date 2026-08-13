"""
Trajectory PBC Wrapper - Correct periodic boundary condition artefacts

Uses GROMACS ``trjconv`` to center the **protein+ligand complex** (not protein
alone) in the box and apply ``-pbc mol``.  Centering on protein only leaves
ligands (e.g. ATP) split across periodic images — the same failure mode that
``tmp/conv_sim.sh`` fixes.

If ``mdWrap.xtc`` already exists and is non-empty, wrapping is skipped unless
``force=True``.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

# Tried in order when ligand is omitted / not found (kinase–ATP campaigns first).
_COMMON_LIGAND_NAMES: Tuple[str, ...] = (
    "ATP",
    "ADP",
    "GTP",
    "GDP",
    "AMP",
    "ANP",
    "CNP",
    "LIG",
)


def _run_gmx(args: list, stdin: str = "", cwd: Optional[str] = None) -> tuple:
    """Run a GROMACS command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        args,
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


def _parse_group_id(text: str, group_name: str) -> Optional[str]:
    """
    Extract the integer group ID for *group_name* from ``gmx make_ndx`` output.

    Matches lines like: ``  5 Protein   ( 1234 atoms)`` — exact word-boundary
    match, case-insensitive (same as ``conv_sim.sh``).
    """
    pattern = re.compile(
        r"^\s*(\d+)\s+" + re.escape(group_name) + r"\b",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(1) if m else None


def _list_make_ndx_groups(
    tpr_path: Path,
    work: Path,
    index_path: Optional[Path] = None,
) -> str:
    """Return combined stdout+stderr group listing from ``gmx make_ndx``."""
    cmd = ["gmx", "make_ndx", "-f", str(tpr_path)]
    if index_path and index_path.is_file():
        cmd += ["-n", str(index_path)]
    cmd += ["-o", "/dev/null"]
    _rc, stdout, stderr = _run_gmx(cmd, stdin="q\n", cwd=str(work))
    return stdout + stderr


def _resolve_ligand_group(
    ndx_output: str,
    ligand: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve ligand group id + canonical name from make_ndx listing.

    Tries the caller-provided name first, then common nucleotide / LIG names.
    """
    candidates: List[str] = []
    if ligand and str(ligand).strip() and str(ligand).strip().lower() not in (
        "auto",
        "none",
        "null",
    ):
        candidates.append(str(ligand).strip())
    candidates.extend(_COMMON_LIGAND_NAMES)

    seen = set()
    for name in candidates:
        key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        lig_id = _parse_group_id(ndx_output, name)
        if lig_id is not None:
            return lig_id, name
    return None, None


def _build_protein_ligand_index(
    tpr_path: Path,
    work: Path,
    prot_id: str,
    lig_id: str,
    ligand_name: str,
    ndx_output: str,
) -> Tuple[Path, str, str]:
    """
    Create ``index_wrap.ndx`` with a named ``Protein_<LIG>`` group.

    Mirrors ``tmp/conv_sim.sh``:
      ``$PROT_ID | $LIGAND_ID`` then ``name <new> Protein_$LIGAND``.
    """
    index_path = work / "index_wrap.ndx"
    merged_name = f"Protein_{ligand_name}"

    existing_ids = [int(x) for x in re.findall(r"^\s*(\d+)\s+\S+", ndx_output, re.MULTILINE)]
    new_id = (max(existing_ids) + 1) if existing_ids else 0

    ndx_stdin = f"{prot_id} | {lig_id}\nname {new_id} {merged_name}\nq\n"
    rc, out, err = _run_gmx(
        ["gmx", "make_ndx", "-f", str(tpr_path), "-o", str(index_path)],
        stdin=ndx_stdin,
        cwd=str(work),
    )
    if rc != 0 and not index_path.exists():
        raise RuntimeError(f"gmx make_ndx merge failed (rc={rc}): {err[:500]}")

    listed = _list_make_ndx_groups(tpr_path, work, index_path=index_path)
    center_id = _parse_group_id(listed, merged_name)
    if center_id is None:
        # Fallback: last numeric group (newly appended merge).
        group_ids = re.findall(r"^\s*(\d+)\s+\S+", listed, re.MULTILINE)
        center_id = group_ids[-1] if group_ids else prot_id
        logger.warning(
            "wrap_trajectory: could not find named group %s — using id=%s",
            merged_name,
            center_id,
        )
    return index_path, center_id, merged_name


def _wrap_trajectory_impl(
    tpr_file: str,
    trajectory_file: str,
    output_file: Optional[str] = None,
    ligand: Optional[str] = "ATP",
    dt: int = 100,
    working_dir: Optional[str] = None,
    skip: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Wrap a GROMACS trajectory to fix periodic boundary conditions (PBC).

    Centers the **protein+ligand complex** (Protein | ATP by default) with
    ``gmx trjconv -pbc mol -center``, matching ``tmp/conv_sim.sh``.  Protein-only
    centering is used only when no ligand group can be found.

    If the output ``mdWrap.xtc`` already exists and is non-empty, wrapping is
    **skipped** unless ``force=True`` (or ``skip=True`` which always skips).

    Args:
        tpr_file:         GROMACS run-input file (.tpr).
        trajectory_file:  Input trajectory (.xtc / .trr), typically ``md.xtc``.
        output_file:      Output name (default ``mdWrap.xtc``) inside *working_dir*.
        ligand:           Ligand index-group / residue name (default ``\"ATP\"``).
                          Pass ``\"auto\"`` to scan common ligands, or ``None`` /
                          ``\"\"`` for protein-only centering.
        dt:               Output frame interval in ps (default 100).
        working_dir:      Where index + wrapped traj are written (default: traj dir).
        skip:             If True, return *trajectory_file* unchanged (no I/O).
        force:            If True, rebuild wrap even when ``mdWrap.xtc`` exists.

    Returns:
        Dict with ``success``, ``wrapped_trajectory``, ``centering_group``,
        ``skipped`` (bool), ``message``, and ``error`` on failure.
    """
    if skip:
        logger.info("wrap_trajectory: skip=True — returning original trajectory")
        return {
            "success": True,
            "wrapped_trajectory": str(Path(trajectory_file).resolve()),
            "centering_group": "skipped",
            "output_group": "skipped",
            "skipped": True,
            "message": "Wrapping skipped by caller (skip=True).",
        }

    tpr_path = Path(tpr_file).resolve()
    traj_path = Path(trajectory_file).resolve()

    if not tpr_path.exists():
        return {"success": False, "error": f"TPR file not found: {tpr_path}"}
    if not traj_path.exists():
        return {"success": False, "error": f"Trajectory not found: {traj_path}"}

    work = Path(working_dir).resolve() if working_dir else traj_path.parent
    work.mkdir(parents=True, exist_ok=True)

    if not output_file:
        output_file = "mdWrap.xtc"
    out_path = (work / output_file).resolve()

    # Already pointing at a wrapped traj — do not re-wrap into itself.
    if not force and traj_path.name == Path(output_file).name and traj_path.stat().st_size > 0:
        logger.info(
            "wrap_trajectory: input is already %s — reusing, not recreating",
            traj_path.name,
        )
        return {
            "success": True,
            "wrapped_trajectory": str(traj_path),
            "centering_group": "existing",
            "output_group": "System",
            "skipped": True,
            "message": f"Input trajectory is already wrapped ({traj_path.name}).",
        }

    # Existing mdWrap.xtc in working_dir — reuse (idempotent).
    if not force and out_path.is_file() and out_path.stat().st_size > 0:
        # If source is newer than wrap, rebuild (raw traj was replaced).
        try:
            src_mtime = traj_path.stat().st_mtime
            out_mtime = out_path.stat().st_mtime
        except OSError:
            src_mtime, out_mtime = 0.0, 1.0
        if out_mtime + 1.0 >= src_mtime:
            logger.info(
                "wrap_trajectory: %s already exists — reusing (force=False)",
                out_path.name,
            )
            return {
                "success": True,
                "wrapped_trajectory": str(out_path),
                "centering_group": "existing",
                "output_group": "System",
                "skipped": True,
                "message": (
                    f"Wrapped trajectory already exists ({out_path.name}); "
                    "skipped recreation. Pass force=True to rebuild."
                ),
            }
        logger.info(
            "wrap_trajectory: existing %s is older than source — rebuilding",
            out_path.name,
        )

    # ── Discover Protein + ligand groups (conv_sim.sh steps 1–3) ───────────
    logger.info("wrap_trajectory: listing index groups via gmx make_ndx …")
    ndx_output = _list_make_ndx_groups(tpr_path, work)

    prot_id = _parse_group_id(ndx_output, "Protein")
    if prot_id is None:
        return {
            "success": False,
            "error": "Could not detect 'Protein' group in make_ndx output",
        }

    lig_id: Optional[str] = None
    ligand_name: Optional[str] = None
    if ligand is None or str(ligand).strip() == "":
        lig_id, ligand_name = None, None
    else:
        lig_id, ligand_name = _resolve_ligand_group(ndx_output, ligand)
        if lig_id is None:
            logger.warning(
                "wrap_trajectory: ligand group %r not found — centering on Protein only",
                ligand,
            )

    index_path: Optional[Path] = None
    if lig_id is not None and ligand_name is not None:
        try:
            index_path, center_id, center_label = _build_protein_ligand_index(
                tpr_path, work, prot_id, lig_id, ligand_name, ndx_output
            )
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}
    else:
        center_id = prot_id
        center_label = "Protein"

    # ── trjconv: center on complex, write System (conv_sim.sh step 6) ─────
    trjconv_cmd = [
        "gmx",
        "trjconv",
        "-s",
        str(tpr_path),
        "-f",
        str(traj_path),
        "-o",
        str(out_path),
        "-dt",
        str(dt),
        "-pbc",
        "mol",
        "-center",
    ]
    if index_path and index_path.exists():
        trjconv_cmd += ["-n", str(index_path)]

    trjconv_stdin = f"{center_id}\n0\n"
    logger.info(
        "wrap_trajectory: gmx trjconv -center %s(id=%s) -dt %s → %s",
        center_label,
        center_id,
        dt,
        out_path.name,
    )
    rc4, _out4, err4 = _run_gmx(trjconv_cmd, stdin=trjconv_stdin, cwd=str(work))

    if rc4 != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        return {
            "success": False,
            "error": f"gmx trjconv failed (rc={rc4}): {err4[:500]}",
        }

    logger.info("wrap_trajectory: done → %s", out_path)
    result: Dict[str, Any] = {
        "success": True,
        "wrapped_trajectory": str(out_path),
        "centering_group": center_label,
        "output_group": "System",
        "skipped": False,
        "ligand_group": ligand_name,
        "message": (
            f"Trajectory wrapped with PBC correction. "
            f"Centering group: {center_label}. Output: {out_path.name}"
        ),
    }

    try:
        append_analysis_summary(
            working_dir=str(work),
            analysis_type="trajectory_wrapping",
            result=result,
            stats={
                "centering_group": center_label,
                "ligand_group": ligand_name,
                "dt_ps": dt,
                "output_file": str(out_path),
            },
        )
    except Exception:
        pass

    return result


@tool
def wrap_trajectory(
    tpr_file: str,
    trajectory_file: str,
    output_file: Optional[str] = None,
    ligand: Optional[str] = "ATP",
    dt: int = 100,
    working_dir: Optional[str] = None,
    skip: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    PBC-wrap a trajectory by centering the protein+ligand complex (Protein|ATP).

    Use before RMSD/RMSF/PCA/FEL so the ligand is not split across box edges.
    If ``mdWrap.xtc`` already exists, recreation is skipped unless ``force=True``.

    Args:
        tpr_file: Topology / run-input (.tpr).
        trajectory_file: Raw trajectory (usually ``hpc/md.xtc``).
        output_file: Wrapped name (default ``mdWrap.xtc``).
        ligand: Ligand index name (default ``ATP``). Use ``auto`` to detect.
        dt: Output spacing in ps (default 100).
        working_dir: Output directory (default: trajectory directory / ``hpc/``).
        skip: Skip wrapping entirely.
        force: Rebuild even if ``mdWrap.xtc`` already exists.
    """
    return _wrap_trajectory_impl(
        tpr_file=tpr_file,
        trajectory_file=trajectory_file,
        output_file=output_file,
        ligand=ligand,
        dt=dt,
        working_dir=working_dir,
        skip=skip,
        force=force,
    )
