"""
Extended minimization for remodelled / strained structures.

Use when gaps were filled from a model, clashes remain, or phosphate geometry
needs extra relief before NVT equilibration.
"""
import re
from pathlib import Path
from typing import Any, Dict, Optional

_EXTENDED_MINIM_GOAL_PATTERNS = tuple(
    re.compile(p, re.I)
    for p in (
        r"remodel(?:ed|led|ling)?",
        r"modelled",
        r"modeled",
        r"bad contact",
        r"clash(?:es)?",
        r"strained",
        r"bond stretch",
        r"extended minim",
        r"long(?:er)? minim",
        r"aggressive minim",
        r"extra minim",
        r"merged missing",
        r"gap fill",
        r"homology model",
        r"alphafold",
        r"af3",
    )
)

# Default MDP parameters (stage 1: restrained; stage 2: unrestrained)
EXTENDED_MINIM_STAGE1 = {
    "nsteps": 1_000_000,
    "emtol": 1000.0,
    "emstep": 0.01,
    "integrator": "steep",
    "use_posres": True,
}
EXTENDED_MINIM_STAGE2 = {
    "nsteps": 500_000,
    "emtol": 100.0,
    "emstep": 0.005,
    "integrator": "steep",
    "use_posres": False,
}
STANDARD_MINIM = {
    "nsteps": 600_000,
    "emtol": 100.0,
    "emstep": 0.01,
    "integrator": "steep",
    "use_posres": True,
}


def parse_extended_minimization_from_text(text: str = "") -> bool:
    """Return True when user goal text requests extended minimization."""
    if not text:
        return False
    lower = text.lower()
    return any(pat.search(lower) for pat in _EXTENDED_MINIM_GOAL_PATTERNS)


def should_use_extended_minimization(
    user_text: str = "",
    state: Optional[Dict[str, Any]] = None,
    preprocess_dir: Optional[str] = None,
) -> bool:
    """
    Decide whether to generate minim2.mdp and run two-stage minimization on HPC.

    Triggers: explicit goal keywords, state flag, remodel output on disk.
    """
    if state and state.get("extended_minimization"):
        return True
    combined = "\n".join(
        part for part in (
            user_text,
            (state or {}).get("user_goal", ""),
            (state or {}).get("user_goal_original", ""),
            (state or {}).get("enriched_prompt", ""),
            (state or {}).get("master_enriched_prompt", ""),
        )
        if part
    )
    if parse_extended_minimization_from_text(combined):
        return True
    dirs_to_check = []
    if preprocess_dir:
        dirs_to_check.append(Path(preprocess_dir))
    if state and state.get("working_directory"):
        wd = Path(state["working_directory"])
        dirs_to_check.append(wd / "preprocess")
    for directory in dirs_to_check:
        if (directory / "merged_missing_from_model.pdb").is_file():
            return True
    cleaned = (state or {}).get("cleaned_pdb") or ""
    if "merged_missing" in cleaned or "remodel" in cleaned.lower():
        return True
    return False


def extended_minimization_goal_hint() -> str:
    """Short phrase for planner/enricher prompts."""
    return (
        "Say 'extended minimization' or mention remodelled/modelled structure, "
        "bad contacts, or bond strain to enable two-stage minim (minim + minim2) on HPC."
    )
