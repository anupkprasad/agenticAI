"""
Parse deterministic GROMACS system-setup parameters from natural-language goals.

The simsetup agent must not rely on LLM guesses for box geometry, ion concentration,
temperature, or per-simulation production length when the user goal already specifies them.
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_BOX_TYPE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"dodecahedron|dodecahedral", re.I), "dodecahedron"),
    (re.compile(r"octahedron|octahedral", re.I), "octahedron"),
    (re.compile(r"\bcubic\b|\bcube\b", re.I), "cubic"),
)

_DONOR_STEM_RE = re.compile(
    r"(?:^|[_-])(?:af3|alphafold|model)(?:[_-]|$)",
    re.IGNORECASE,
)

_REMODEL_DONOR_GOAL_RE = re.compile(
    r"donor[_\s-]?pdb|detect_missing_structure|missing_structure_elements|"
    r"merged.?missing|homology model|model structure|"
    r"(?:^|\s)af3\b|alphafold",
    re.IGNORECASE,
)


def _combined_text(*parts: Optional[str]) -> str:
    return "\n".join(p for p in parts if p)


def parse_box_type_from_text(text: str = "") -> Optional[str]:
    if not text:
        return None
    for pattern, name in _BOX_TYPE_PATTERNS:
        if pattern.search(text):
            return name
    return None


def parse_box_distance_from_text(text: str = "") -> Optional[float]:
    if not text:
        return None
    patterns = [
        re.compile(
            r"(?:clearance|distance)\s+(?:from|of)?\s*(?:the\s+)?(?:protein\s+)?"
            r"(?:on\s+all\s+)?sides?\s*(?:with|of)?\s*(\d+(?:\.\d+)?)\s*nm",
            re.I,
        ),
        re.compile(r"(\d+(?:\.\d+)?)\s*nm\s+(?:clearance|distance)", re.I),
        re.compile(r"(?:box\s+with|with)\s+(\d+(?:\.\d+)?)\s*nm", re.I),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def parse_ion_concentration_from_text(text: str = "") -> Optional[float]:
    if not text:
        return None
    lower = text.lower()
    if re.search(
        r"no additional salt|without additional salt|neutraliz(?:e|ation)\s+only|"
        r"neutralization only|only neutraliz|neutralize with .+ only",
        lower,
    ):
        return 0.0
    # Explicit concentration, e.g. "0.15 M salt" or "ion concentration 0.15"
    match = re.search(
        r"(?:salt|ion)\s+concentration\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*m?",
        lower,
    )
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            pass
    return None


def parse_temperature_from_text(text: str = "") -> Optional[float]:
    if not text:
        return None
    match = re.search(r"temperature\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*k\b", text, re.I)
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            pass
    return None


def parse_pressure_from_text(text: str = "") -> Optional[float]:
    if not text:
        return None
    match = re.search(
        r"pressure\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:bar)?\b",
        text,
        re.I,
    )
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            pass
    return None


def extract_production_ns_pairs(text: str = "") -> List[Tuple[str, float]]:
    """Parse '1739 ns for dephosphorylated' style mappings."""
    if not text:
        return []
    pairs: List[Tuple[str, float]] = []
    for match in re.finditer(
        r"(\d+(?:\.\d+)?)\s*ns\s+for\s+(dephosphorylated|phosphorylated|\w+)",
        text,
        re.I,
    ):
        try:
            pairs.append((match.group(2).lower(), float(match.group(1))))
        except (TypeError, ValueError):
            continue
    return pairs


def production_ns_for_sim(
    text: str = "",
    pdb_path: Optional[str] = None,
    label: Optional[str] = None,
) -> Optional[float]:
    """Pick production length when the goal assigns different ns per system."""
    stem = Path(pdb_path or "").stem.lower()
    label_l = (label or "").lower()
    identity = stem or label_l

    pairs = extract_production_ns_pairs(text)
    if pairs and identity:
        if "phos" in identity:
            for qualifier, ns in pairs:
                if "dephosph" in qualifier:
                    continue
                if "phosph" in qualifier:
                    return ns
        for qualifier, ns in pairs:
            if "dephosph" in qualifier:
                return ns

    patterns = [
        re.compile(
            r"(?:production|simulation|run)\s*(?:time|length|duration|run)?"
            r"\s*(?:is|of|for|=|:)?\s*(\d+(?:\.\d+)?)\s*ns\b",
            re.I,
        ),
        re.compile(r"\b(\d+(?:\.\d+)?)\s*ns\b", re.I),
    ]
    for pattern in patterns:
        match = pattern.search(text or "")
        if match:
            try:
                val = float(match.group(1))
                if val > 0:
                    return val
            except (TypeError, ValueError):
                continue
    return None


def is_donor_pdb_stem(stem: str) -> bool:
    """True when a PDB stem looks like a model/AF3 donor, not 'modelled' experimental."""
    return bool(_DONOR_STEM_RE.search(stem))


def filter_remodel_donor_pdbs(goal: str, paths: List[str]) -> List[str]:
    """
    When the goal names an experimental + model donor pair, keep only experimental PDBs
    for multi-sim enumeration. Does not run on generic 'remodelled structure' MD goals.
    """
    if len(paths) <= 1:
        return paths
    if not _REMODEL_DONOR_GOAL_RE.search(goal):
        return paths

    experimental = [p for p in paths if not is_donor_pdb_stem(Path(p).stem)]
    return experimental if experimental else [paths[0]]


def resolve_simsetup_options(
    state: Optional[Dict[str, Any]] = None,
    user_text: str = "",
    pdb_path: Optional[str] = None,
    label: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge state keys, parsed goal text, and defaults into tool-ready simsetup parameters.
    Parsed goal values override LLM plan guesses but not explicit state keys set upstream.
    """
    state = state or {}
    defaults = defaults or {}
    text = _combined_text(
        user_text,
        state.get("user_goal"),
        state.get("user_goal_original"),
        state.get("enriched_prompt"),
        state.get("master_enriched_prompt"),
        state.get("setup_instructions"),
    )

    def _pick(
        key: str,
        parser,
        default_key: Optional[str] = None,
    ) -> Optional[Any]:
        if state.get(key) is not None:
            return state.get(key)
        parsed = parser(text)
        if parsed is not None:
            return parsed
        dk = default_key or key
        return defaults.get(dk)

    resolved_pdb = pdb_path or state.get("raw_pdb") or state.get("cleaned_pdb")
    resolved_label = label or Path(state.get("working_directory", "")).name
    per_sim_pairs = extract_production_ns_pairs(text)
    per_sim_ns = (
        production_ns_for_sim(text, pdb_path=resolved_pdb, label=resolved_label)
        if per_sim_pairs
        else None
    )
    # Per-simulation mappings (e.g. 1739 ns dephospho / 2882 ns phospho) beat a single
    # global production_ns parsed from the first match in the goal.
    if per_sim_pairs and per_sim_ns is not None:
        production_ns = per_sim_ns
    elif state.get("production_ns") is not None:
        production_ns = state.get("production_ns")
    else:
        production_ns = production_ns_for_sim(
            text, pdb_path=resolved_pdb, label=resolved_label
        )
    if production_ns is None:
        production_ns = defaults.get("production_ns")

    from src.simsetup.minimization_options import should_use_extended_minimization

    extended = state.get("extended_minimization")
    if not extended:
        preprocess_dir = state.get("preprocess_dir")
        if not preprocess_dir and state.get("working_directory"):
            preprocess_dir = str(Path(state["working_directory"]) / "preprocess")
        extended = should_use_extended_minimization(
            user_text=text,
            state=state,
            preprocess_dir=preprocess_dir,
        )

    return {
        "box_type": _pick("box_type", parse_box_type_from_text),
        "box_distance": _pick("box_distance", parse_box_distance_from_text),
        "ion_concentration": _pick("ion_concentration", parse_ion_concentration_from_text),
        "temperature": _pick("temperature", parse_temperature_from_text),
        "pressure": _pick("pressure", parse_pressure_from_text),
        "production_ns": production_ns,
        "extended_minimization": bool(extended),
    }


SIMSETUP_OVERRIDE_KEYS = (
    "box_type",
    "box_distance",
    "ion_concentration",
    "temperature",
    "pressure",
    "production_ns",
    "extended_minimization",
)


def coerce_simsetup_tool_value(key: str, value: Any) -> Any:
    """Normalize override values for GROMACS tool invocation."""
    if value is None:
        return None
    if key in ("box_distance", "ion_concentration", "temperature", "pressure", "production_ns"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if key == "extended_minimization":
        return bool(value)
    return value


def summarize_override_changes(
    llm_params: Dict[str, Any],
    executed_params: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Return LLM-plan vs executed diffs for conversation logging."""
    changes: Dict[str, Dict[str, Any]] = {}
    for key in SIMSETUP_OVERRIDE_KEYS:
        llm_val = llm_params.get(key)
        exec_val = executed_params.get(key)
        if exec_val is None:
            continue
        if llm_val != exec_val:
            changes[key] = {"llm_plan": llm_val, "executed": exec_val}
    return changes


def apply_goal_simsetup_config(goal: str, config: Dict[str, Any]) -> None:
    """Populate SimAgent config dict from parsed goal text."""
    if parse_box_type_from_text(goal):
        config["box_type"] = parse_box_type_from_text(goal)
    if parse_box_distance_from_text(goal) is not None:
        config["box_distance"] = parse_box_distance_from_text(goal)
    if parse_ion_concentration_from_text(goal) is not None:
        config["ion_concentration"] = parse_ion_concentration_from_text(goal)
    if parse_temperature_from_text(goal) is not None:
        config["temperature"] = parse_temperature_from_text(goal)
    if parse_pressure_from_text(goal) is not None:
        config["pressure"] = parse_pressure_from_text(goal)
