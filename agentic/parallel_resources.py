"""
Adaptive parallel worker sizing from host CPU and memory.

Used by the cross-simulation parallel pool to decide how many independent
simulation jobs (prep, analysis/reporter) may run concurrently without
overwhelming the machine.

Override via CLI ``--parallel-workers``, ``--parallel-mem-gb``,
``--parallel-cpus``, and ``--llm-concurrency``, or environment variables:

  AGENTIC_PARALLEL_WORKERS=4
  AGENTIC_PARALLEL_MEM_GB=3
  AGENTIC_PARALLEL_CPUS=2
  AGENTIC_LLM_CONCURRENCY=4
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Cores kept for the orchestrator, Ollama, and OS headroom.
RESERVE_CPUS = 2
# GiB reserved for orchestrator + OS.
RESERVE_MEM_GB = 2.0
# Do not allocate more than this fraction of total RAM.
MEM_USABLE_FRACTION = 0.85
# Upper bound when ``parallel_workers=auto`` (override via AGENTIC_PARALLEL_MAX_AUTO).
MAX_AUTO_WORKERS = int(os.environ.get("AGENTIC_PARALLEL_MAX_AUTO", "16"))
# Default Ollama parallel slots when ``llm_concurrency=auto``.
DEFAULT_LLM_CONCURRENCY = int(os.environ.get("AGENTIC_LLM_CONCURRENCY_DEFAULT", "8"))
# Phases where each worker frequently calls the shared LLM server.
LLM_HEAVY_PHASES = frozenset({"prep", "analysis"})

# Default per-job footprints by workflow phase.
PHASE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "prep": {"cpus_per_job": 2.0, "mem_gb_per_job": 4.0},
    "analysis": {"cpus_per_job": 2.0, "mem_gb_per_job": 3.0},
    "hpc": {"cpus_per_job": 1.0, "mem_gb_per_job": 0.5},
}

WorkerSetting = Union[str, int, None]


@dataclass(frozen=True)
class SystemResources:
    cpu_count: int
    cpu_available: int
    mem_total_gb: float
    mem_available_gb: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_count": self.cpu_count,
            "cpu_available": self.cpu_available,
            "mem_total_gb": round(self.mem_total_gb, 2),
            "mem_available_gb": round(self.mem_available_gb, 2),
        }


@dataclass(frozen=True)
class WorkerEstimate:
    max_workers: int
    cpus_per_job: float
    mem_gb_per_job: float
    phase: str
    resources: SystemResources
    limiting_factor: str
    llm_concurrency: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "max_workers": self.max_workers,
            "cpus_per_job": self.cpus_per_job,
            "mem_gb_per_job": self.mem_gb_per_job,
            "phase": self.phase,
            "resources": self.resources.to_dict(),
            "limiting_factor": self.limiting_factor,
        }
        if self.llm_concurrency is not None:
            out["llm_concurrency"] = self.llm_concurrency
        return out


def _read_linux_meminfo() -> tuple[float, float]:
    """Return (total_gb, available_gb) from /proc/meminfo on Linux."""
    total_kb = avail_kb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
    except OSError:
        pass
    if total_kb is None:
        return 16.0, 8.0
    total_gb = total_kb / (1024 * 1024)
    if avail_kb is None:
        avail_gb = total_gb * 0.5
    else:
        avail_gb = avail_kb / (1024 * 1024)
    return total_gb, avail_gb


def get_system_resources() -> SystemResources:
    """Probe CPU count and available memory (Linux /proc or psutil fallback)."""
    cpu_count = os.cpu_count() or 4
    cpu_available = max(1, cpu_count - RESERVE_CPUS)

    mem_total_gb = mem_avail_gb = None
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        mem_total_gb = vm.total / (1024**3)
        mem_avail_gb = vm.available / (1024**3)
    except ImportError:
        mem_total_gb, mem_avail_gb = _read_linux_meminfo()

    usable = max(0.5, mem_avail_gb - RESERVE_MEM_GB)
    usable = min(usable, mem_total_gb * MEM_USABLE_FRACTION)
    return SystemResources(
        cpu_count=cpu_count,
        cpu_available=cpu_available,
        mem_total_gb=mem_total_gb,
        mem_available_gb=usable,
    )


def _phase_footprint(phase: str, state: Optional[Dict[str, Any]]) -> tuple[float, float]:
    defaults = PHASE_DEFAULTS.get(phase, PHASE_DEFAULTS["analysis"])
    cpus = float(defaults["cpus_per_job"])
    mem = float(defaults["mem_gb_per_job"])
    if state:
        if state.get("parallel_cpus_per_job") is not None:
            cpus = float(state["parallel_cpus_per_job"])
        if state.get("parallel_mem_gb_per_job") is not None:
            mem = float(state["parallel_mem_gb_per_job"])
    env_cpus = os.environ.get("AGENTIC_PARALLEL_CPUS")
    env_mem = os.environ.get("AGENTIC_PARALLEL_MEM_GB")
    if env_cpus:
        cpus = float(env_cpus)
    if env_mem:
        mem = float(env_mem)
    return max(0.5, cpus), max(0.5, mem)


def _resolve_llm_concurrency(state: Optional[Dict[str, Any]]) -> Optional[int]:
    """Resolved Ollama parallel slot cap for LLM-heavy phases (``None`` = no cap)."""
    if not state:
        return DEFAULT_LLM_CONCURRENCY
    setting = state.get("llm_concurrency")
    if setting is None:
        env = os.environ.get("AGENTIC_LLM_CONCURRENCY")
        if env:
            if env.lower() == "auto":
                return DEFAULT_LLM_CONCURRENCY
            try:
                return max(1, int(env))
            except ValueError:
                return DEFAULT_LLM_CONCURRENCY
        return DEFAULT_LLM_CONCURRENCY
    if isinstance(setting, str) and setting.lower() == "auto":
        return DEFAULT_LLM_CONCURRENCY
    try:
        return max(1, int(setting))
    except (TypeError, ValueError):
        return DEFAULT_LLM_CONCURRENCY


def _resolve_user_cap(state: Optional[Dict[str, Any]]) -> Optional[int]:
    if not state:
        return None
    setting: WorkerSetting = state.get("parallel_workers")
    if setting is None:
        env = os.environ.get("AGENTIC_PARALLEL_WORKERS")
        if env and env.lower() != "auto":
            try:
                return max(1, int(env))
            except ValueError:
                pass
        return None
    if isinstance(setting, str) and setting.lower() == "auto":
        return None
    try:
        return max(1, int(setting))
    except (TypeError, ValueError):
        return None


def estimate_workers(
    phase: str,
    state: Optional[Dict[str, Any]] = None,
    *,
    pending_jobs: Optional[int] = None,
) -> WorkerEstimate:
    """
    Compute a safe concurrent worker count for *phase*.

    ``pending_jobs`` caps the result when fewer simulations remain than slots.
    """
    resources = get_system_resources()
    cpus_per_job, mem_gb_per_job = _phase_footprint(phase, state)

    by_cpu = max(1, int(resources.cpu_available // cpus_per_job))
    by_mem = max(1, int(resources.mem_available_gb // mem_gb_per_job))
    auto_workers = max(1, min(by_cpu, by_mem))
    auto_workers = min(auto_workers, MAX_AUTO_WORKERS)

    limiting = "cpu" if by_cpu <= by_mem else "memory"
    if auto_workers < min(by_cpu, by_mem):
        limiting = "auto_cap"
    user_cap = _resolve_user_cap(state)
    workers = auto_workers
    if user_cap is not None:
        workers = max(1, min(auto_workers, user_cap))
        if user_cap < auto_workers:
            limiting = "user_cap"

    if pending_jobs is not None:
        workers = max(1, min(workers, pending_jobs))
        if pending_jobs < workers:
            limiting = "pending_jobs"

    llm_cap: Optional[int] = None
    if phase in LLM_HEAVY_PHASES:
        llm_cap = _resolve_llm_concurrency(state)
        if llm_cap is not None and workers > llm_cap:
            workers = max(1, llm_cap)
            limiting = "llm_concurrency"

    logger.info(
        "Parallel resources [%s]: workers=%s (cpu_limit=%s mem_limit=%s cap=%s llm=%s) "
        "cpus/job=%.1f mem/job=%.1fGiB avail=%s",
        phase,
        workers,
        by_cpu,
        by_mem,
        user_cap,
        llm_cap,
        cpus_per_job,
        mem_gb_per_job,
        resources.to_dict(),
    )
    return WorkerEstimate(
        max_workers=workers,
        cpus_per_job=cpus_per_job,
        mem_gb_per_job=mem_gb_per_job,
        phase=phase,
        resources=resources,
        limiting_factor=limiting,
        llm_concurrency=llm_cap,
    )


def resolve_allowed_hpc_jobs(state: Dict[str, Any]) -> int:
    """Resolve SLURM pool size — auto from resources when not explicitly set."""
    explicit = state.get("allowed_hpc_jobs")
    if explicit is not None and state.get("_allowed_hpc_jobs_explicit"):
        return max(1, int(explicit))
    est = estimate_workers("hpc", state)
    return est.max_workers


def should_use_parallel_pool(state: Dict[str, Any]) -> bool:
    """True when multi-sim local parallelism is enabled."""
    if state.get("parallel_pool_disabled"):
        return False
    if not state.get("is_multi_simulation"):
        return False
    if state.get("combined_only"):
        return False
    if state.get("human_in_loop"):
        return False
    sims = state.get("sim_prompts") or []
    if len(sims) < 2:
        return False
    cap = _resolve_user_cap(state)
    if cap == 1:
        return False
    setting = state.get("parallel_workers", "auto")
    if setting == 1 or setting == "1":
        return False
    return True
