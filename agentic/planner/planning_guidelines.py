"""
Shared planning guidelines for the MD planner and downstream field agents.

Keeps intent preservation and standard output naming in one place so master-plan,
per-simulation, and combined planning stay consistent.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Set, Any, List

# Canonical per-simulation output basenames (no label prefix).
# Combined analysis collects these from {base}/{label}/analysis/.
STANDARD_OUTPUT_FILES: Dict[str, Dict[str, str]] = {
    "rmsd": {"data": "rmsd.dat", "plot": "rmsd.png"},
    "rmsf": {"data": "rmsf.dat", "plot": "rmsf.png"},
    "rg": {"data": "gyration.dat", "plot": "gyration.png"},
    "gyration": {"data": "gyration.dat", "plot": "gyration.png"},
    "sasa": {"data": "sasa.dat", "plot": "sasa.png"},
    "energy": {"data": "energy.dat", "plot": "energy.png"},
    "dccm": {"data_prefix": "dccm", "plot": "dccm_heatmap.png"},
    "dssp": {"data_prefix": "dssp", "plot": "dssp.png"},
    "com": {"data": "ligand_pocket_distance.csv", "plot": "ligand_pocket_distance.png"},
}

_METRIC_PATTERNS: Dict[str, tuple[str, ...]] = {
    "rmsd": (r"\brmsd\b", r"root mean square deviation"),
    "rmsf": (r"\brmsf\b", r"root mean square fluctuation"),
    "rg": (r"\brg\b", r"radius of gyration", r"\bgyration\b"),
    "sasa": (r"\bsasa\b", r"solvent accessible surface"),
    "dccm": (r"\bdccm\b", r"cross[-\s]?correlation", r"correlated motion"),
    "dssp": (r"\bdssp\b", r"secondary[-\s]?structure"),
    "com": (
        r"\bcom\b",
        r"center[-\s]?of[-\s]?mass",
        r"centre[-\s]?of[-\s]?mass",
        r"ligand[-\s]?pocket[-\s]?distance",
        r"pocket[-\s]?distance",
        r"atp[-\s]?(?:to[-\s]?)?(?:protein[-\s]?)?(?:pocket[-\s]?)?distance",
    ),
    "energy": (r"\benergy\b", r"\bedr\b"),
}

_EXCLUSIVE_PATTERNS = (
    r"\b(?:only|just|specifically|exclusively)\b[^.\n]{0,80}\b(rmsd|rmsf|rg|gyration|sasa|dccm|dssp|energy)\b",
    r"\b(rmsd|rmsf|rg|gyration|sasa|dccm|dssp|energy)\b[^.\n]{0,40}\b(?:only|just)\b",
)

_BROAD_DYNAMICS_PATTERNS = (
    "protein dynamics",
    "dynamic behavior",
    "dynamic behaviour",
    "conformational dynamics",
    "molecular dynamics analysis",
    "comprehensive analysis",
    "full analysis",
)


def collect_goal_texts_for_intent(
    state: Optional[Dict[str, Any]] = None,
    agent_input: Optional[Any] = None,
) -> tuple[str, ...]:
    """
    Gather all user-facing goal strings that may define analysis scope.

    In multisim runs, ``user_goal_original`` holds the CLI --goal text while
    ``user_goal`` holds the per-simulation prompt (which may add sim-specific
    analyses such as ATP COM distance). All non-empty sources are returned.
    """
    texts: list[str] = []
    seen: set[str] = set()
    if state:
        for key in ("user_goal", "user_goal_original"):
            value = (state.get(key) or "").strip()
            if value and value not in seen:
                texts.append(value)
                seen.add(value)
    if agent_input is not None:
        value = (getattr(agent_input, "user_goal", None) or "").strip()
        if value and value not in seen:
            texts.append(value)
            seen.add(value)
    return tuple(texts)


def detect_requested_metrics_union(*goal_texts: str) -> Optional[FrozenSet[str]]:
    """
    Union metrics detected across multiple goal strings.

    Used when master --goal and per-simulation prompts disagree in scope
    (e.g. master says "RMSF for all sims" while a holo sim prompt adds ATP COM).
    """
    merged: Set[str] = set()
    saw_broad = False
    for text in goal_texts:
        if not (text or "").strip():
            continue
        metrics = detect_requested_metrics(text)
        if metrics is None:
            saw_broad = True
        else:
            merged.update(metrics)
    if merged:
        return frozenset(merged)
    return None if saw_broad else None


def detect_requested_metrics(goal: str) -> Optional[FrozenSet[str]]:
    """
    Return the set of metrics explicitly requested in *goal*.

    Returns None when the goal is broad (e.g. "protein dynamics") and the planner
    may choose a small justified dynamics bundle. Returns a frozen set when the
    user names specific metrics or uses exclusive language ("RMSF only").
    """
    text = (goal or "").lower()
    text = (
        text.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )

    found = {
        metric
        for metric, patterns in _METRIC_PATTERNS.items()
        if any(re.search(pattern, text) for pattern in patterns)
    }
    # Normalise rg/gyration
    if "rg" in found or "gyration" in found:
        found.discard("gyration")
        found.add("rg")

    for pattern in _EXCLUSIVE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            token = match.group(1)
            if token == "gyration":
                token = "rg"
            # "specifically RMSF … and COM distance" must keep both metrics.
            if found - {token}:
                return frozenset(found)
            return frozenset({token})

    if found and not any(phrase in text for phrase in _BROAD_DYNAMICS_PATTERNS):
        return frozenset(found)

    if any(phrase in text for phrase in _BROAD_DYNAMICS_PATTERNS):
        return None

    return frozenset(found) if found else None


def detect_requested_metrics_for_sim(
    state: Optional[Dict[str, Any]] = None,
    agent_input: Optional[Any] = None,
) -> Optional[FrozenSet[str]]:
    """
    Metrics requested for the *current* simulation.

    Per-simulation ``user_goal`` text (from the multisim master plan) overrides
    the global CLI goal so e.g. DCCM requested only for JAK1/TYK2 does not
    run on STRAA/ULK4.
    """
    per_sim_texts: list[str] = []
    if state:
        text = (state.get("user_goal") or "").strip()
        if text:
            per_sim_texts.append(text)
    if agent_input is not None:
        text = (getattr(agent_input, "user_goal", None) or "").strip()
        if text and text not in per_sim_texts:
            per_sim_texts.append(text)

    for text in per_sim_texts:
        metrics = detect_requested_metrics(text)
        if metrics is not None:
            return metrics

    return detect_requested_metrics_union(
        *collect_goal_texts_for_intent(state, agent_input)
    )


def get_intent_preservation_block(user_goal: str = "") -> str:
    """Prompt block: user goal defines which analyses to run."""
    metrics = detect_requested_metrics(user_goal)
    metric_hint = ""
    if metrics:
        names = ", ".join(sorted(metrics))
        metric_hint = (
            f"\nDetected explicit analysis scope from USER GOAL: {names}. "
            "Do NOT add other metrics unless the goal also names them.\n"
        )

    return f"""**USER INTENT IS MANDATORY (HIGHEST PRIORITY):**
- The USER GOAL defines which analyses to run. Do not expand beyond it.
- If the goal says "RMSF only" (or similar), plan ONLY RMSF plus the directly
  required plot/CSV outputs and reporter documentation for those results.
- Do NOT add RMSD, Rg, SASA, hydrogen bonds, DCCM, DSSP, energy, wrap_trajectory,
  or run_complete_analysis unless the USER GOAL explicitly requests them.
- If the goal asks broadly for "protein dynamics" without naming metrics, choose a
  small justified dynamics set (typically RMSD + RMSF + Rg, optionally DCCM when relevant).
- When both Analysis and Reporter agents are in the workflow, the Reporter section
  must document only what the Analysis section produces — no extra calculations.
{metric_hint}"""


def get_standard_output_filenames_block() -> str:
    """Prompt block: consistent basenames across simulations for combined overlay."""
    lines = [
        "**STANDARD PER-SIMULATION OUTPUT FILENAMES (CRITICAL for multi-sim):**",
        "Use the SAME basename in every simulation directory so combined analysis can",
        "collect and overlay results. Write outputs under {working_dir}/analysis/.",
        "Do NOT prefix filenames with simulation labels (no p29597_rmsf.dat).",
        "",
    ]
    for metric, files in STANDARD_OUTPUT_FILES.items():
        if "data" in files:
            lines.append(f"- {metric.upper()}: data={files['data']}, plot={files.get('plot', 'N/A')}")
        elif "data_prefix" in files:
            lines.append(
                f"- {metric.upper()}: prefix={files['data_prefix']}, plot={files.get('plot', 'N/A')}"
            )
    lines.append(
        "\nWhen the same metric is requested for every simulation, every sim must use "
        "these exact basenames."
    )
    return "\n".join(lines)


def get_master_plan_tools_note(agent_list: list[str]) -> str:
    """Short note explaining how tool sections map to workflow agents."""
    agents = ", ".join(agent_list) if agent_list else "workflow agents"
    return (
        "Tool sections below match the workflow agents in --subtask. "
        f"Per-simulation tools are for: {agents}. "
        "Cross-simulation tools run once at the project base after all per-sim runs."
    )


def metric_mentioned_in_goal(metric: str, goal_text: str) -> bool:
    """True when *goal_text* explicitly names a metric (incl. rg / radius of gyration)."""
    text = (goal_text or "").lower()
    if not text:
        return False
    metric = metric.lower()
    patterns = _METRIC_PATTERNS.get(metric)
    if patterns:
        return any(re.search(p, text) for p in patterns)
    return metric in text


def get_metric_collect_pattern(metric: str) -> str:
    """
    Filename stem used by combined analysis to locate per-sim data files.

    Matches STANDARD_OUTPUT_FILES basenames (e.g. rg → ``gyration`` not ``rg``).
    """
    metric = metric.lower()
    if metric in STANDARD_OUTPUT_FILES:
        spec = STANDARD_OUTPUT_FILES[metric]
        if "data" in spec:
            return Path(spec["data"]).stem
        if "data_prefix" in spec:
            return spec["data_prefix"]
    return metric


def detect_com_distance_mode(goal: str) -> str:
    """
    Which COM-distance tool(s) the user wants.

    Returns ``pocket``, ``protein_com``, or ``both``.
    """
    text = (goal or "").lower()
    pocket_markers = (
        "pocket",
        "binding site",
        "catalytic pocket",
        "catalytic site",
        "active site",
        "ligand_pocket",
        "ligand pocket",
        "within 5",
        "within 5 å",
        "within 5 a",
        "nearby atoms",
        "surrounding atoms",
    )
    protein_com_markers = (
        "whole protein",
        "entire protein",
        "protein com",
        "protein center of mass",
        "protein centre of mass",
        "com of protein",
        "protein-to-ligand com",
        "protein to ligand com",
    )
    wants_pocket = any(m in text for m in pocket_markers)
    wants_protein_com = any(m in text for m in protein_com_markers)
    if wants_pocket and wants_protein_com:
        return "both"
    if wants_protein_com:
        return "protein_com"
    if wants_pocket:
        return "pocket"
    # Generic "COM distance … ATP … protein" in holo kinase studies → pocket tracking
    if any(k in text for k in ("atp", "ligand", "inhibitor", "adp", "gtp")) and (
        "com" in text or "center of mass" in text or "centre of mass" in text
    ):
        return "pocket"
    return "protein_com" if "com" in text else "pocket"


def get_com_distance_tool_guide() -> str:
    """Prompt block: choose ligand-pocket vs generic COM distance tools."""
    return """**COM DISTANCE TOOLS — choose exactly one unless the user asks for both:**

| User intent | Tool | Output files | When to use |
|-------------|------|--------------|-------------|
| Ligand **binding-pocket** stability (atoms within ~5 Å of ligand at frame 0) | `calculate_ligand_pocket_distance` | `ligand_pocket_distance.csv`, `.png` | "ligand pocket distance", "catalytic pocket", "binding site", "ATP in the pocket", "nearby pocket atoms" |
| **Whole-protein** COM to ligand COM (or any two explicit selections) | `calculate_com_distance` | `com_distance.csv`, `.png` | "COM distance between the whole protein and ATP", "protein COM to ligand COM", domain–domain COM |

Rules:
- Do **NOT** run both tools unless the user explicitly requests pocket distance **and** whole-protein COM distance.
- For holo kinase goals like "COM distance of ATP from protein" without further detail, prefer **`calculate_ligand_pocket_distance`** (biologically meaningful pocket tracking).
- `calculate_com_distance` requires `selection1` and `selection2` (NOT `ligand_selection`).
- Example pocket: `ligand_selection="resname ATP"`, `cutoff=5.0`, `output_file="ligand_pocket_distance.csv"`.
- Example protein COM: `selection1="protein"`, `selection2="resname ATP"`, `output_file="com_distance.csv"`."""


def _metric_clause_pattern(metric: str) -> str:
    """Regex fragment for metric name in ``… for JAK1 and TYK2`` clauses."""
    if metric == "rg":
        return r"(?:rg|radius[-\s]of[-\s]gyration|\bgyration\b)"
    if metric == "com":
        return r"(?:com|center[-\s]?of[-\s]?mass|ligand[-\s]?pocket|ligand[-\s]?pocket[-\s]?distance)"
    return re.escape(metric)


def _resolve_token_to_label(
    token: str,
    labels: List[str],
    label_name_map: Dict[str, str],
) -> Optional[str]:
    """Map a protein name, UniProt id, or label token to a simulation label."""
    raw = token.strip().strip("*_\"'")
    if not raw:
        return None
    low = raw.lower()
    if low.endswith(".pdb"):
        low = low[:-4]

    for label in labels:
        if label.lower() == low or low == label.lower().split("_")[0]:
            return label

    for uid, pname in label_name_map.items():
        uid_low = uid.lower()
        pname_low = pname.lower()
        if low in (uid_low, pname_low):
            for label in labels:
                if label.lower() == uid_low or label.lower().startswith(f"{uid_low}_"):
                    return label
    return None


def parse_metric_target_labels(
    goal_text: str,
    metric: str,
    labels: List[str],
    label_name_map: Optional[Dict[str, str]] = None,
) -> Optional[FrozenSet[str]]:
    """
    When the user names specific proteins/systems for one metric (e.g. DCCM for
    JAK1 and TYK2), return the matching simulation labels.
    """
    if not goal_text or not labels:
        return None
    text = goal_text.lower()
    metric = metric.lower()
    if not metric_mentioned_in_goal(metric, text):
        return None

    name_map = {k.lower(): v for k, v in (label_name_map or {}).items()}
    matched: Set[str] = set()

    metric_pat = _metric_clause_pattern(metric)

    clause_patterns = (
        rf"\b{metric_pat}\b\s+for\s+([^.\n;]+?)(?:\.\s|$|\bto compare\b|\bto\b|\bacross\b|\bonly\b|\bfrom\b|\bwith\b|\bin\b)",
        rf"\b{metric_pat}\b[^.\n]{{0,40}}\bbetween\s+([^.\n;]+?)(?:\.\s|$|\bto\b|\bwith\b)",
    )
    for pattern in clause_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            clause = match.group(1)
            clause = re.split(r"\bto compare\b|\bcompare\b|\bacross\b", clause)[0]
            for part in re.split(r"\band\b|,|/|&", clause):
                part = part.strip()
                if not part or part in {"all", "each", "every", "all simulations", "four proteins"}:
                    continue
                label = _resolve_token_to_label(part, labels, name_map)
                if label:
                    matched.add(label)

    return frozenset(matched) if matched else None


def resolve_sims_for_combined_metric(
    metric: str,
    sim_dirs: List[str],
    labels: List[str],
    *,
    master_goal: str = "",
    combined_plan: str = "",
    completed_sim_states: Optional[List[Dict[str, Any]]] = None,
    label_name_map: Optional[Dict[str, str]] = None,
) -> tuple[List[str], List[str]]:
    """
    Select which simulations participate in one combined-metric analysis.

    Combined overlays do NOT always use every simulation:
    - RMSF for all four proteins → all labels
    - DCCM only for JAK1 and TYK2 → subset ``p23458``, ``p29597``

    Priority:
    1. Per-simulation goals from completed runs (authoritative per sim)
    2. Master goal / combined plan naming specific targets for this metric
    3. Global metric request with no named subset → all simulations
    """
    completed = completed_sim_states or []
    by_label = {s.get("label"): s for s in completed if s.get("label")}
    name_map = {k.lower(): v for k, v in (label_name_map or {}).items()}

    included_dirs: List[str] = []
    included_labels: List[str] = []
    saw_explicit_per_sim = False

    for sim_dir, label in zip(sim_dirs, labels):
        goal = (by_label.get(label) or {}).get("user_goal", "").strip()
        if not goal:
            continue
        per_sim_metrics = detect_requested_metrics(goal)
        if per_sim_metrics is None:
            continue
        saw_explicit_per_sim = True
        if metric in per_sim_metrics:
            included_dirs.append(sim_dir)
            included_labels.append(label)

    if included_dirs:
        return included_dirs, included_labels

    if saw_explicit_per_sim:
        # Per-sim goals exist and none request this metric.
        return [], []

    goal_text = f"{master_goal}\n{combined_plan}"
    subset = parse_metric_target_labels(goal_text, metric, labels, name_map)
    if subset:
        dirs = [d for d, l in zip(sim_dirs, labels) if l in subset]
        labs = [l for l in labels if l in subset]
        return dirs, labs

    global_metrics = detect_requested_metrics_union(master_goal, combined_plan)
    if global_metrics and metric in global_metrics:
        return list(sim_dirs), list(labels)

    return [], []
