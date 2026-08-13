"""
Ensure MD toolchain binaries are on PATH for local agent runs.

Cluster jobs often inherit an interactive shell with ``module load`` and a
conda env; nohup / bare ``python`` launches do not. Ligand setup then fails
with ``Neither acpype nor antechamber available`` even though both exist in
``ollama_env`` or AmberTools modules.

This helper is safe to call repeatedly (idempotent).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False

# Prefer project conda env; fall back to other known local envs.
_CONDA_BIN_CANDIDATES = (
    Path.home() / "conda_envs" / "ollama_env" / "bin",
    Path.home() / "conda_envs" / "mdagent" / "bin",
    Path("/home/akp66103/conda_envs/ollama_env/bin"),
)

_AMBER_MODULES = (
    "AmberTools/23.6-foss-2023b",
    "AmberTools/23.6-foss-2023a",
    "Amber/24.3-foss-2022a-AmberTools-24.10-CUDA-12.1.1",
)

_GROMACS_MODULES = (
    "GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2",
    "GROMACS/2023.4-foss-2023a-CUDA-12.1.1",
)


def _prepend_path(entries: Iterable[Path]) -> None:
    parts = os.environ.get("PATH", "").split(":")
    for entry in entries:
        s = str(entry)
        if entry.is_dir() and s not in parts:
            parts.insert(0, s)
            logger.info("MD env: prepended %s to PATH", s)
    os.environ["PATH"] = ":".join(parts)


def _run_module_load(module_name: str) -> bool:
    """Best-effort ``module load`` via bash+Lmod; updates os.environ from stdout."""
    init_candidates = (
        "/apps/lmod/lmod/init/bash",
        "/apps/lmod/8.7.59/init/bash",
        "/usr/share/lmod/lmod/init/bash",
    )
    init = next((p for p in init_candidates if Path(p).is_file()), None)
    if not init:
        return False
    script = (
        f'source "{init}" >/dev/null 2>&1; '
        f'module load {module_name} >/dev/null 2>&1; '
        f'echo "__AGENTIC_PATH__=$PATH"; '
        f'echo "__AGENTIC_LD__=${{LD_LIBRARY_PATH-}}"; '
        f'echo "__AGENTIC_AMBERHOME__=${{AMBERHOME-}}";'
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("module load %s failed: %s", module_name, exc)
        return False
    if proc.returncode != 0:
        return False
    for line in (proc.stdout or "").splitlines():
        if line.startswith("__AGENTIC_PATH__="):
            os.environ["PATH"] = line.split("=", 1)[1]
        elif line.startswith("__AGENTIC_LD__="):
            val = line.split("=", 1)[1]
            if val:
                os.environ["LD_LIBRARY_PATH"] = val
        elif line.startswith("__AGENTIC_AMBERHOME__="):
            val = line.split("=", 1)[1]
            if val:
                os.environ["AMBERHOME"] = val
    logger.info("MD env: module load %s", module_name)
    return True


def toolchain_status() -> dict:
    return {
        "acpype": shutil.which("acpype"),
        "antechamber": shutil.which("antechamber"),
        "gmx": shutil.which("gmx") or shutil.which("gmx_mpi"),
        "python": shutil.which("python") or shutil.which("python3"),
    }


def ensure_md_toolchain(*, force: bool = False) -> dict:
    """
    Make ligand-param and GROMACS binaries discoverable for the current process.

    Order:
      1. Prepend known conda env ``bin/`` dirs that contain acpype/antechamber
      2. ``module load`` AmberTools if antechamber still missing
      3. ``module load`` GROMACS if gmx still missing
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED and not force:
        return toolchain_status()

    # 1) conda env bins (acpype lives here on this cluster)
    conda_bins: List[Path] = []
    for cand in _CONDA_BIN_CANDIDATES:
        if not cand.is_dir():
            continue
        if (cand / "acpype").is_file() or (cand / "antechamber").is_file():
            conda_bins.append(cand)
    if conda_bins:
        _prepend_path(conda_bins)

    # 2) AmberTools module for antechamber/parmchk2 if still missing
    if not shutil.which("antechamber"):
        for mod in _AMBER_MODULES:
            if _run_module_load(mod) and shutil.which("antechamber"):
                break

    # 3) GROMACS for simsetup build / analysis helpers
    if not (shutil.which("gmx") or shutil.which("gmx_mpi")):
        for mod in _GROMACS_MODULES:
            if _run_module_load(mod) and (shutil.which("gmx") or shutil.which("gmx_mpi")):
                break

    status = toolchain_status()
    missing = [k for k, v in status.items() if k in ("acpype", "antechamber", "gmx") and not v]
    # acpype OR antechamber is enough for ligands
    ligand_ok = bool(status["acpype"] or status["antechamber"])
    if not ligand_ok:
        logger.error(
            "MD env: no ligand parameterization tool on PATH "
            "(need acpype or antechamber). status=%s",
            status,
        )
    elif missing:
        logger.warning("MD env: partial toolchain — missing %s; status=%s", missing, status)
    else:
        logger.info("MD env: toolchain ready — %s", status)

    _BOOTSTRAPPED = True
    return status


def prefer_ligand_tool() -> str:
    """Return preferred ligand tool name after ensuring PATH."""
    ensure_md_toolchain()
    if shutil.which("acpype"):
        return "acpype"
    if shutil.which("antechamber"):
        return "antechamber"
    return "acpype"
