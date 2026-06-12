"""
Copy GROMACS force-field directories referenced by topology #include lines.
"""
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

_INCLUDE_FF_RE = re.compile(r'#include\s+"([^"]+\.ff)/forcefield\.itp"')


def _gromacs_top_search_paths() -> List[Path]:
    paths: List[Path] = []
    for env_key in ("GMXDATA", "GMXLIB"):
        value = __import__("os").environ.get(env_key)
        if value:
            base = Path(value)
            if base.name == "top":
                paths.append(base)
            else:
                paths.append(base / "top")
                paths.append(base)
    try:
        result = subprocess.run(
            ["gmx", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        for line in result.stdout.splitlines():
            if "Data prefix:" in line:
                prefix = line.split("Data prefix:", 1)[1].strip()
                paths.append(Path(prefix) / "share" / "gromacs" / "top")
                break
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return paths


def _force_field_names_from_topology(top_path: Path) -> Set[str]:
    names: Set[str] = set()
    try:
        text = top_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return names
    for match in _INCLUDE_FF_RE.finditer(text):
        names.add(match.group(1))
    return names


def bundle_force_fields_for_topology(
    source_dir: Path,
    dest_dir: Path,
    topology_names: Optional[List[str]] = None,
) -> List[dict]:
    """
    Copy ``*.ff`` directories needed by topology #include lines into dest_dir.

    Returns a list of copied-directory records for logging.
    """
    copied: List[dict] = []
    ff_names: Set[str] = set()

    if topology_names:
        ff_names.update(topology_names)
    for top_path in source_dir.glob("*.top"):
        ff_names.update(_force_field_names_from_topology(top_path))

    if not ff_names:
        return copied

    search_roots = [source_dir] + _gromacs_top_search_paths()

    for ff_name in sorted(ff_names):
        dest_ff = dest_dir / ff_name
        if dest_ff.is_dir():
            continue
        src_ff: Optional[Path] = None
        for root in search_roots:
            candidate = root / ff_name
            if candidate.is_dir():
                src_ff = candidate
                break
        if src_ff is None:
            logger.warning("Force field directory not found for topology include: %s", ff_name)
            continue
        shutil.copytree(src_ff, dest_ff)
        copied.append(
            {
                "source": str(src_ff.resolve()),
                "destination": str(dest_ff.resolve()),
                "force_field": ff_name,
            }
        )
        logger.info("Bundled force field %s → %s", ff_name, dest_dir)

    return copied
