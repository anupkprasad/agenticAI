"""
Trajectory PBC Wrapper - Correct periodic boundary condition artefacts

Uses GROMACS trjconv to center the protein+ligand complex in the box
and apply PBC molecule wrapping.  This should be run BEFORE any analysis
to avoid spurious jumps and broken molecules.
"""
import os
import re
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from langchain.tools import tool
from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
    Extract the integer group ID for *group_name* from `gmx make_ndx` output.
    Matches lines like:   5 Protein   ( 1234 atoms)
    Uses exact word boundary match, case-insensitive.
    """
    pattern = re.compile(
        r"^\s*(\d+)\s+" + re.escape(group_name) + r"\b",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Public @tool
# ---------------------------------------------------------------------------

def _wrap_trajectory_impl(
    tpr_file: str,
    trajectory_file: str,
    output_file: Optional[str] = None,
    ligand: Optional[str] = "LIG",
    dt: int = 100,
    working_dir: Optional[str] = None,
    skip: bool = False,
) -> Dict[str, Any]:
    """
    Wrap a GROMACS trajectory to fix periodic boundary conditions (PBC).

    Centers the protein+ligand complex in the simulation box using
    ``gmx trjconv -pbc mol -center``.  This must be done before RMSD,
    RMSF, Rg or any other structural analysis to avoid artefacts from
    molecules split across box boundaries.

    Steps performed:
      1. ``gmx make_ndx`` to list all index groups.
      2. Detect the Protein group ID and the ligand group ID (exact name
         match, case-insensitive).  If no ligand group is found the
         centering group falls back to Protein only.
      3. Build a combined ``Protein_<LIGAND>`` index group.
      4. ``gmx trjconv -pbc mol -center`` to produce the wrapped output.

    Args:
        tpr_file:         GROMACS run-input file (.tpr) — full path.
        trajectory_file:  Input trajectory (.xtc / .trr) — full path.
        output_file:      Output filename only (default: ``mdWrap.xtc``).
                          Written inside *working_dir*.
        ligand:           Residue / group name of the ligand (default
                          ``"LIG"``).  Pass ``None`` or ``""`` to center
                          on Protein only.
        dt:               Frame output interval in ps (default 100).
        working_dir:      Directory where output and index files are
                          written (default: directory of *trajectory_file*).
        skip:             If ``True`` skip wrapping and return the original
                          trajectory path unchanged.  Use this when
                          the trajectory was already wrapped.

    Returns:
        Dict with keys:
          - ``success`` (bool)
          - ``wrapped_trajectory`` (str): absolute path to the output file
          - ``centering_group`` (str): GROMACS group used for centering
          - ``output_group`` (str): GROMACS group written to output (``System``)
          - ``message`` (str)
          - ``error`` (str, only on failure)
    """
    if skip:
        logger.info("wrap_trajectory: skip=True, returning original trajectory unchanged")
        return {
            "success": True,
            "wrapped_trajectory": str(Path(trajectory_file).resolve()),
            "centering_group": "skipped",
            "output_group": "skipped",
            "message": "Wrapping skipped by caller.",
        }

    # ── Resolve paths ──────────────────────────────────────────────────────
    tpr_path = Path(tpr_file).resolve()
    traj_path = Path(trajectory_file).resolve()

    if not tpr_path.exists():
        return {"success": False, "error": f"TPR file not found: {tpr_path}"}
    if not traj_path.exists():
        return {"success": False, "error": f"Trajectory not found: {traj_path}"}

    # Default working dir to trajectory's parent if not given
    if working_dir:
        work = Path(working_dir).resolve()
    else:
        work = traj_path.parent
    work.mkdir(parents=True, exist_ok=True)

    if not output_file:
        output_file = "mdWrap.xtc"
    out_path = work / output_file

    # ── Step 1 & 2: discover group IDs ────────────────────────────────────
    logger.info("wrap_trajectory: running gmx make_ndx to list groups …")
    rc, stdout, stderr = _run_gmx(
        ["gmx", "make_ndx", "-f", str(tpr_path), "-o", "/dev/null"],
        stdin="q\n",
        cwd=str(work),
    )
    ndx_output = stdout + stderr  # make_ndx writes group list to stderr

    prot_id = _parse_group_id(ndx_output, "Protein")
    if prot_id is None:
        return {"success": False, "error": "Could not detect 'Protein' group in make_ndx output"}

    lig_id: Optional[str] = None
    if ligand:
        lig_id = _parse_group_id(ndx_output, ligand)
        if lig_id is None:
            logger.warning(
                f"wrap_trajectory: ligand group '{ligand}' not found — "
                "centering on Protein only"
            )

    # ── Step 3: build combined index (Protein + Ligand) ──────────────────
    index_path = work / "index_wrap.ndx"
    if lig_id is not None:
        merged_name = f"Protein_{ligand}"
        ndx_stdin = f"{prot_id} | {lig_id}\nname {len(ndx_output)} {merged_name}\nq\n"
        # Use a high number for the name command — GROMACS assigns name to
        # the *last* group by default when we use "name <idx> <name>"
        # Safer: let GROMACS auto-assign, then find the new ID.
        ndx_stdin = f"{prot_id} | {lig_id}\nq\n"
        rc2, out2, err2 = _run_gmx(
            ["gmx", "make_ndx", "-f", str(tpr_path), "-o", str(index_path)],
            stdin=ndx_stdin,
            cwd=str(work),
        )
        if rc2 != 0 and not index_path.exists():
            logger.warning(f"wrap_trajectory: make_ndx step 3 returned rc={rc2}: {err2}")

        # Find the newly created merged group ID
        rc3, out3, err3 = _run_gmx(
            ["gmx", "make_ndx", "-f", str(tpr_path), "-n", str(index_path), "-o", "/dev/null"],
            stdin="q\n",
            cwd=str(work),
        )
        merged_output = out3 + err3

        # The merged group is the last numeric group before 'q'
        group_ids = re.findall(r"^\s*(\d+)\s+\S+", merged_output, re.MULTILINE)
        center_id = group_ids[-1] if group_ids else prot_id
        center_label = merged_name
    else:
        # No ligand — use Protein directly, no custom index needed
        index_path = None
        center_id = prot_id
        center_label = "Protein"

    # ── Step 4: trjconv ───────────────────────────────────────────────────
    # Output group = 0 (System)
    trjconv_cmd = [
        "gmx", "trjconv",
        "-s", str(tpr_path),
        "-f", str(traj_path),
        "-o", str(out_path),
        "-dt", str(dt),
        "-pbc", "mol",
        "-center",
    ]
    if index_path and index_path.exists():
        trjconv_cmd += ["-n", str(index_path)]

    # stdin: centering group first, then output group (System = 0)
    trjconv_stdin = f"{center_id}\n0\n"

    logger.info(
        f"wrap_trajectory: gmx trjconv -center {center_label}(id={center_id}) "
        f"-dt {dt} → {out_path.name}"
    )
    rc4, out4, err4 = _run_gmx(trjconv_cmd, stdin=trjconv_stdin, cwd=str(work))

    if rc4 != 0 or not out_path.exists():
        return {
            "success": False,
            "error": f"gmx trjconv failed (rc={rc4}): {err4[:500]}",
        }

    logger.info(f"wrap_trajectory: done → {out_path}")

    result = {
        "success": True,
        "wrapped_trajectory": str(out_path),
        "centering_group": center_label,
        "output_group": "System",
        "message": (
            f"Trajectory wrapped with PBC correction. "
            f"Centering group: {center_label}. "
            f"Output: {out_path.name}"
        ),
    }

    # Log to analysis summary
    try:
        append_analysis_summary(
            working_dir=str(work),
            analysis_type="trajectory_wrapping",
            result=result,
            stats={
                "centering_group": center_label,
                "dt_ps": dt,
                "output_file": str(out_path),
            },
        )
    except Exception:
        pass

    return result


# LangChain @tool for LLM tool-binding (StructuredTool) — keeps the same
# interface but wraps the plain function so callers that need a direct
# Python call can use _wrap_trajectory_impl() instead.
@tool
def wrap_trajectory(
    tpr_file: str,
    trajectory_file: str,
    output_file: Optional[str] = None,
    ligand: Optional[str] = "LIG",
    dt: int = 100,
    working_dir: Optional[str] = None,
    skip: bool = False,
) -> Dict[str, Any]:
    """
    Wrap a GROMACS trajectory to fix periodic boundary conditions (PBC).
    See _wrap_trajectory_impl for full documentation.
    """
    return _wrap_trajectory_impl(
        tpr_file=tpr_file,
        trajectory_file=trajectory_file,
        output_file=output_file,
        ligand=ligand,
        dt=dt,
        working_dir=working_dir,
        skip=skip,
    )
