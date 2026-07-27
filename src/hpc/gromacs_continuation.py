"""Safe, idempotent tools for extending checkpointed GROMACS simulations."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from langchain.tools import tool


_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_ACTIVE_STATES = {"PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED"}
_SUCCESS_STATES = {"COMPLETED"}
_FAILURE_STATES = {
    "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY",
    "PREEMPTED", "BOOT_FAIL", "DEADLINE",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_component(value: str, field: str) -> str:
    value = str(value or "").strip()
    if not value or not _SAFE_NAME.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"Unsafe {field}: {value!r}")
    return value


def _resolve_simulation_dir(simulation_dir: str) -> Path:
    path = Path(simulation_dir).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Simulation directory does not exist: {path}")
    return path


def _resolve_inside(root: Path, filename: str, field: str) -> Path:
    name = _safe_component(filename, field)
    path = (root / name).resolve()
    if path.parent != root or path.is_symlink():
        raise ValueError(f"{field} must be a non-symlink file directly under {root}")
    return path


def _require_nonempty(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"Missing or empty {label}: {path}")


def _parse_log_run(log_path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "log_path": str(log_path),
        "dt_ps": None,
        "nsteps": None,
        "configured_total_ns": None,
        "finished_mdrun": False,
    }
    if not log_path.is_file():
        return result
    text = log_path.read_text(encoding="utf-8", errors="replace")
    dt_matches = re.findall(r"^\s*dt\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
    nsteps_matches = re.findall(r"^\s*nsteps\s*=\s*(\d+)", text, re.MULTILINE)
    if dt_matches:
        result["dt_ps"] = float(dt_matches[-1])
    if nsteps_matches:
        result["nsteps"] = int(nsteps_matches[-1])
    if result["dt_ps"] is not None and result["nsteps"] is not None:
        result["configured_total_ns"] = (
            float(result["dt_ps"]) * int(result["nsteps"]) / 1000.0
        )
    result["finished_mdrun"] = "Finished mdrun" in text
    return result


def _target_tag(target_total_ns: float) -> str:
    rounded = round(float(target_total_ns), 6)
    text = f"{rounded:g}".replace(".", "p")
    return f"{text}ns"


def _load_manifest(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Continuation manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid continuation manifest: {path}")
    return data


def _manifest_path(
    simulation_dir: Path,
    target_total_ns: float,
    manifest_name: Optional[str] = None,
) -> Path:
    name = manifest_name or f"continuation_{_target_tag(target_total_ns)}.json"
    return _resolve_inside(simulation_dir, name, "manifest_name")


def _inspect_impl(simulation_dir: str, deffnm: str = "md") -> Dict[str, Any]:
    root = _resolve_simulation_dir(simulation_dir)
    prefix = _safe_component(deffnm, "deffnm")
    tpr = _resolve_inside(root, f"{prefix}.tpr", "source_tpr")
    cpt = _resolve_inside(root, f"{prefix}.cpt", "checkpoint")
    log = _resolve_inside(root, f"{prefix}.log", "log")
    xtc = _resolve_inside(root, f"{prefix}.xtc", "trajectory")
    _require_nonempty(tpr, "source TPR")
    _require_nonempty(cpt, "checkpoint")

    log_info = _parse_log_run(log)
    manifests = sorted(root.glob("continuation_*ns.json"))
    manifest_summaries = []
    for path in manifests:
        try:
            data = _load_manifest(path)
            manifest_summaries.append(
                {
                    "path": str(path),
                    "target_total_ns": data.get("target_total_ns"),
                    "status": data.get("status"),
                    "job_id": data.get("job_id"),
                }
            )
        except Exception as exc:
            manifest_summaries.append({"path": str(path), "error": str(exc)})

    return {
        "success": True,
        "ready": True,
        "simulation_dir": str(root),
        "deffnm": prefix,
        "source_tpr": str(tpr),
        "checkpoint": str(cpt),
        "log": str(log) if log.is_file() else None,
        "trajectory": str(xtc) if xtc.is_file() else None,
        "source_tpr_size": tpr.stat().st_size,
        "checkpoint_size": cpt.stat().st_size,
        **log_info,
        "continuation_manifests": manifest_summaries,
    }


@tool
def inspect_gromacs_continuation(
    simulation_dir: str,
    deffnm: str = "md",
) -> Dict[str, Any]:
    """Inspect whether an existing GROMACS run can be extended from checkpoint.

    This is read-only. It requires nonempty ``<deffnm>.tpr`` and
    ``<deffnm>.cpt`` files and reports the configured duration parsed from the
    GROMACS log plus any existing continuation manifests.
    """
    try:
        return _inspect_impl(simulation_dir, deffnm)
    except Exception as exc:
        return {"success": False, "ready": False, "error": str(exc)}


@tool
def prepare_gromacs_continuation(
    simulation_dir: str,
    target_total_ns: Optional[float] = None,
    extend_ns: Optional[float] = None,
    deffnm: str = "md",
    manifest_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an idempotent manifest for extending a checkpointed GROMACS run.

    Supply exactly one of ``target_total_ns`` or ``extend_ns``. A target total
    time is preferred because repeated planning cannot accidentally add another
    extension. The extended TPR is created by the generated SLURM script using
    ``gmx convert-tpr`` on the compute node.
    """
    try:
        if (target_total_ns is None) == (extend_ns is None):
            raise ValueError("Provide exactly one of target_total_ns or extend_ns")
        inspection = _inspect_impl(simulation_dir, deffnm)
        current_ns = inspection.get("configured_total_ns")
        if current_ns is None:
            raise ValueError(
                "Could not determine current duration from md.log; "
                "use a log containing dt and nsteps"
            )
        if target_total_ns is None:
            if float(extend_ns) <= 0:
                raise ValueError("extend_ns must be > 0")
            target_total_ns = float(current_ns) + float(extend_ns)
        target_total_ns = float(target_total_ns)
        if target_total_ns <= float(current_ns) + 1e-9:
            raise ValueError(
                f"Target {target_total_ns:g} ns must exceed current "
                f"{float(current_ns):g} ns"
            )

        root = Path(inspection["simulation_dir"])
        extension_ns = target_total_ns - float(current_ns)
        tag = _target_tag(target_total_ns)
        extended_tpr = _resolve_inside(
            root, f"{deffnm}_extend_{tag}.tpr", "extended_tpr"
        )
        marker = _resolve_inside(root, f".continuation_{tag}.complete", "marker")
        manifest_path = _manifest_path(root, target_total_ns, manifest_name)
        source_tpr = Path(inspection["source_tpr"])
        checkpoint = Path(inspection["checkpoint"])

        desired = {
            "schema_version": 1,
            "action": "gromacs_continuation",
            "simulation_dir": str(root),
            "deffnm": deffnm,
            "source_tpr": str(source_tpr),
            "source_checkpoint": str(checkpoint),
            "source_tpr_sha256": _sha256(source_tpr),
            "source_checkpoint_sha256": _sha256(checkpoint),
            "current_total_ns": float(current_ns),
            "target_total_ns": target_total_ns,
            "extension_ns": extension_ns,
            "extension_ps": extension_ns * 1000.0,
            "extended_tpr": str(extended_tpr),
            "completion_marker": str(marker),
            "status": "PREPARED",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        if manifest_path.is_file():
            existing = _load_manifest(manifest_path)
            invariant_keys = (
                "simulation_dir", "deffnm", "source_tpr_sha256",
                "source_checkpoint_sha256", "current_total_ns",
                "target_total_ns", "extension_ps", "extended_tpr",
            )
            conflicts = [
                key for key in invariant_keys
                if existing.get(key) != desired.get(key)
            ]
            if conflicts:
                raise ValueError(
                    f"Existing manifest conflicts on {conflicts}: {manifest_path}"
                )
            return {
                "success": True,
                "cached": True,
                "manifest_path": str(manifest_path),
                **existing,
            }

        _atomic_json_write(manifest_path, desired)
        return {
            "success": True,
            "cached": False,
            "manifest_path": str(manifest_path),
            **desired,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _validate_slurm_value(value: str, pattern: str, field: str) -> str:
    text = str(value)
    if not re.fullmatch(pattern, text):
        raise ValueError(f"Invalid {field}: {text!r}")
    return text


@tool
def create_gromacs_continuation_script(
    manifest_path: str,
    job_name: Optional[str] = None,
    partition: str = "gpu_p",
    nodes: int = 1,
    ntasks: int = 1,
    cpus_per_task: int = 64,
    memory: str = "40G",
    time_limit: str = "5-00:00:00",
    gpu_count: int = 1,
    gromacs_module: str = (
        "GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2"
    ),
    email: Optional[str] = None,
    output_script: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a continuation-only SLURM script from a prepared manifest.

    The script runs ``gmx convert-tpr`` and then checkpoint continuation with
    ``gmx mdrun -cpi ... -append``. It skips completed targets, validates source
    files, and writes a target-specific completion marker.
    """
    try:
        manifest_file = Path(manifest_path).expanduser().resolve()
        manifest = _load_manifest(manifest_file)
        root = Path(manifest["simulation_dir"]).resolve()
        if manifest_file.parent != root:
            raise ValueError("Manifest must be stored in its simulation directory")
        source_tpr = Path(manifest["source_tpr"]).resolve()
        checkpoint = Path(manifest["source_checkpoint"]).resolve()
        extended_tpr = Path(manifest["extended_tpr"]).resolve()
        marker = Path(manifest["completion_marker"]).resolve()
        for path in (source_tpr, checkpoint, extended_tpr, marker):
            if path.parent != root:
                raise ValueError(f"Manifest path escapes simulation directory: {path}")
        _require_nonempty(source_tpr, "source TPR")
        _require_nonempty(checkpoint, "checkpoint")
        if _sha256(source_tpr) != manifest["source_tpr_sha256"]:
            raise ValueError("Source TPR changed after manifest preparation")
        if _sha256(checkpoint) != manifest["source_checkpoint_sha256"]:
            raise ValueError("Checkpoint changed after manifest preparation")

        target_tag = _target_tag(float(manifest["target_total_ns"]))
        raw_job_name = job_name or f"{root.parent.name}_{root.name}_ext_{target_tag}"
        safe_job = _validate_slurm_value(raw_job_name, r"[A-Za-z0-9_.-]{1,80}", "job_name")
        partition = _validate_slurm_value(partition, r"[A-Za-z0-9_.-]+", "partition")
        memory = _validate_slurm_value(memory, r"[0-9]+[KMGTP]?", "memory")
        time_limit = _validate_slurm_value(
            time_limit, r"(?:[0-9]+-)?[0-9]{1,2}:[0-9]{2}:[0-9]{2}", "time_limit"
        )
        module = _validate_slurm_value(
            gromacs_module, r"[A-Za-z0-9_./+-]+", "gromacs_module"
        )
        for field, value in (
            ("nodes", nodes), ("ntasks", ntasks),
            ("cpus_per_task", cpus_per_task), ("gpu_count", gpu_count),
        ):
            if int(value) < 0 or (field != "gpu_count" and int(value) < 1):
                raise ValueError(f"{field} has invalid value: {value}")

        if output_script:
            script = Path(output_script).expanduser().resolve()
            if script.parent != root:
                raise ValueError("output_script must be directly under simulation_dir")
        else:
            script = root / f"{safe_job}.sh"
        if script.is_symlink():
            raise ValueError(f"Refusing symlink output script: {script}")

        q = shlex.quote
        mail = ""
        if email:
            email = _validate_slurm_value(email, r"[^@\s]+@[^@\s]+", "email")
            mail = f"#SBATCH --mail-user={email}\n#SBATCH --mail-type=END,FAIL\n"
        gpu_line = f"#SBATCH --gres=gpu:{int(gpu_count)}\n" if int(gpu_count) else ""
        content = f"""#!/bin/bash
#SBATCH --job-name={safe_job}
#SBATCH --partition={partition}
#SBATCH --nodes={int(nodes)}
#SBATCH --ntasks={int(ntasks)}
#SBATCH --cpus-per-task={int(cpus_per_task)}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output=%x_%j.out
{gpu_line}{mail}set -eo pipefail

module load {module}
# GMXRC references optional unset vars; enable nounset only after sourcing.
source "$EBROOTGROMACS/bin/GMXRC"
set -u
cd {q(str(root))}

SOURCE_TPR={q(source_tpr.name)}
CHECKPOINT={q(checkpoint.name)}
EXTENDED_TPR={q(extended_tpr.name)}
MARKER={q(marker.name)}

if [[ -s "$MARKER" ]]; then
    echo "Target already completed: $MARKER"
    exit 0
fi
[[ -s "$SOURCE_TPR" ]] || {{ echo "Missing $SOURCE_TPR" >&2; exit 2; }}
[[ -s "$CHECKPOINT" ]] || {{ echo "Missing $CHECKPOINT" >&2; exit 2; }}

echo "Preparing continuation to {float(manifest['target_total_ns']):g} ns"
gmx convert-tpr -s "$SOURCE_TPR" \\
    -extend {float(manifest['extension_ps']):.6f} \\
    -o "$EXTENDED_TPR"

export OMP_PLACES=cores
OMP_THREADS="${{SLURM_CPUS_PER_TASK:-{int(cpus_per_task)}}}"
if [[ "$OMP_THREADS" -gt 16 ]]; then OMP_THREADS=16; fi
export OMP_NUM_THREADS="$OMP_THREADS"

echo "Continuing from checkpoint with append checksum validation"
gmx mdrun -v -s "$EXTENDED_TPR" -deffnm {q(manifest['deffnm'])} \\
    -cpi "$CHECKPOINT" -append \\
    -ntmpi 1 -ntomp "$OMP_THREADS" -nb gpu -pme gpu -bonded cpu -update cpu

printf 'completed_at=%s\\ntarget_total_ns={float(manifest["target_total_ns"]):g}\\n' \\
    "$(date --iso-8601=seconds)" > "$MARKER"
echo "Continuation completed: $MARKER"
"""
        if script.is_file():
            existing = script.read_text(encoding="utf-8")
            if existing != content:
                raise ValueError(f"Conflicting SLURM script already exists: {script}")
            cached = True
        else:
            script.write_text(content, encoding="utf-8")
            os.chmod(script, 0o750)
            cached = False

        manifest["job_script"] = str(script)
        manifest["job_name"] = safe_job
        manifest["status"] = (
            manifest.get("status")
            if manifest.get("status") in {"SUBMITTED", "RUNNING", "COMPLETED"}
            else "SCRIPT_READY"
        )
        manifest["updated_at"] = _utc_now()
        _atomic_json_write(manifest_file, manifest)
        return {
            "success": True,
            "cached": cached,
            "script_path": str(script),
            "manifest_path": str(manifest_file),
            "job_name": safe_job,
            "target_total_ns": manifest["target_total_ns"],
            "status": manifest["status"],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@tool
def submit_gromacs_continuation(
    manifest_path: str,
    script_path: Optional[str] = None,
    allow_resubmit_failed: bool = False,
) -> Dict[str, Any]:
    """Submit a prepared continuation once and persist its SLURM job ID.

    Repeated calls are idempotent: active or completed manifests are not
    resubmitted. Failed jobs require ``allow_resubmit_failed=True``.
    """
    try:
        from src.hpc.job_monitor import check_job_status
        from src.hpc.job_submitter import submit_job

        manifest_file = Path(manifest_path).expanduser().resolve()
        manifest = _load_manifest(manifest_file)
        root = Path(manifest["simulation_dir"]).resolve()
        if manifest_file.parent != root:
            raise ValueError("Manifest must be stored in its simulation directory")
        marker = Path(manifest["completion_marker"])
        if marker.is_file() and marker.stat().st_size > 0:
            manifest["status"] = "COMPLETED"
            manifest["updated_at"] = _utc_now()
            _atomic_json_write(manifest_file, manifest)
            return {
                "success": True,
                "submitted": False,
                "status": "COMPLETED",
                "job_id": manifest.get("job_id"),
                "manifest_path": str(manifest_file),
            }

        existing_job = str(manifest.get("job_id") or "").strip()
        existing_status = str(manifest.get("status") or "").upper()
        if existing_job and existing_job.isdigit():
            status_result = check_job_status.invoke({"job_id": existing_job})
            scheduler_status = str(status_result.get("status") or "").split("+")[0].upper()
            if scheduler_status in _ACTIVE_STATES:
                manifest["status"] = scheduler_status
                manifest["updated_at"] = _utc_now()
                _atomic_json_write(manifest_file, manifest)
                return {
                    "success": True,
                    "submitted": False,
                    "job_id": existing_job,
                    "status": scheduler_status,
                    "message": "Continuation already submitted",
                    "manifest_path": str(manifest_file),
                }
            if scheduler_status in _SUCCESS_STATES:
                return {
                    "success": False,
                    "submitted": False,
                    "job_id": existing_job,
                    "status": "VERIFY_REQUIRED",
                    "error": "SLURM completed but completion marker is absent",
                }
            if (
                scheduler_status in _FAILURE_STATES or existing_status in _FAILURE_STATES
            ) and not allow_resubmit_failed:
                return {
                    "success": False,
                    "submitted": False,
                    "job_id": existing_job,
                    "status": scheduler_status or existing_status,
                    "error": (
                        "Previous continuation failed; set "
                        "allow_resubmit_failed=True to resubmit"
                    ),
                }
            if (
                scheduler_status not in _FAILURE_STATES
                and existing_status not in _FAILURE_STATES
            ):
                return {
                    "success": False,
                    "submitted": False,
                    "job_id": existing_job,
                    "status": scheduler_status or existing_status or "UNKNOWN",
                    "error": (
                        "A job ID is already recorded but its terminal state could "
                        "not be verified; refusing a duplicate submission"
                    ),
                }

        script = Path(script_path or manifest.get("job_script") or "").expanduser().resolve()
        if script.parent != root or not script.is_file():
            raise ValueError(f"Continuation script not found under simulation_dir: {script}")
        result = submit_job.invoke({"script_path": str(script)})
        if not result.get("success"):
            return result
        job_id = str(result.get("job_id") or "")
        if not job_id.isdigit():
            raise ValueError(f"SLURM returned invalid job ID: {job_id!r}")
        manifest["job_id"] = job_id
        manifest["status"] = "SUBMITTED"
        manifest["submitted_at"] = _utc_now()
        manifest["updated_at"] = _utc_now()
        _atomic_json_write(manifest_file, manifest)
        return {
            **result,
            "submitted": True,
            "manifest_path": str(manifest_file),
        }
    except Exception as exc:
        return {"success": False, "submitted": False, "error": str(exc)}


@tool
def monitor_gromacs_continuation(manifest_path: str) -> Dict[str, Any]:
    """Check SLURM and completion-marker status for a continuation manifest."""
    try:
        from src.hpc.job_monitor import check_job_status

        manifest_file = Path(manifest_path).expanduser().resolve()
        manifest = _load_manifest(manifest_file)
        marker = Path(manifest["completion_marker"])
        if marker.is_file() and marker.stat().st_size > 0:
            status = "COMPLETED"
            scheduler = None
        else:
            job_id = str(manifest.get("job_id") or "")
            if not job_id.isdigit():
                raise ValueError("Manifest has no submitted numeric job_id")
            scheduler = check_job_status.invoke({"job_id": job_id})
            if not scheduler.get("success"):
                return {
                    "success": False,
                    "manifest_path": str(manifest_file),
                    **scheduler,
                }
            scheduler_status = str(scheduler.get("status") or "UNKNOWN").split("+")[0].upper()
            status = scheduler_status
            if scheduler_status in _SUCCESS_STATES:
                status = "VERIFY_FAILED"
            elif scheduler_status in _FAILURE_STATES:
                status = scheduler_status

        manifest["status"] = status
        manifest["last_checked_at"] = _utc_now()
        manifest["updated_at"] = _utc_now()
        if status == "COMPLETED":
            manifest["completed_at"] = _utc_now()
        _atomic_json_write(manifest_file, manifest)
        return {
            "success": status not in _FAILURE_STATES and status != "VERIFY_FAILED",
            "manifest_path": str(manifest_file),
            "job_id": manifest.get("job_id"),
            "status": status,
            "terminal": status in _SUCCESS_STATES | _FAILURE_STATES | {"VERIFY_FAILED"},
            "completion_marker": str(marker),
            "scheduler": scheduler,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
