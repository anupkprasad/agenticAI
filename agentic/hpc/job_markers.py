"""
Persistent SLURM job ownership markers under ``{sim}/hpc/``.

Used so the supervisor can recognize a just-submitted job before Slurm
creates ``{label}_{jobid}.out``, and so multi-sim clear logic does not
wipe a valid ``job_id`` for the active working directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

AGENTIC_JOB_MARKER = ".agentic_job_id"


def write_job_marker(hpc_dir: str | Path, job_id: str) -> Optional[Path]:
    """Write ``.agentic_job_id`` under *hpc_dir*. Returns the marker path."""
    jid = str(job_id or "").strip()
    if not jid or jid.upper() == "UNKNOWN":
        return None
    root = Path(hpc_dir).expanduser()
    try:
        root.mkdir(parents=True, exist_ok=True)
        marker = root / AGENTIC_JOB_MARKER
        marker.write_text(jid + "\n", encoding="utf-8")
        return marker
    except OSError:
        return None


def read_job_marker(hpc_dir: str | Path) -> Optional[str]:
    """Return job id stored in ``.agentic_job_id``, or None."""
    marker = Path(hpc_dir).expanduser() / AGENTIC_JOB_MARKER
    if not marker.is_file():
        return None
    try:
        text = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def marker_matches_job(hpc_dir: str | Path, job_id: Optional[str]) -> bool:
    """True when marker exists and equals *job_id*."""
    jid = str(job_id or "").strip()
    if not jid:
        return False
    stored = read_job_marker(hpc_dir)
    return bool(stored) and stored == jid
