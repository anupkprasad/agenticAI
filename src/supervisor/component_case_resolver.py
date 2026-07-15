"""
Resolve multi-simulation component cases (apo, holo, protein-only, etc.) from user intent.

Heuristics use the original user goal only (not enriched/rephrased prompts) to avoid
false positives from technical details such as "1.2 nm buffer". When an LLM client is
available, the planner asks the model to confirm the simulation set before expanding PDBs.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_CASE_PROTEIN_ONLY: Dict[str, str] = {
    "case_id": "protein_only",
    "suffix": "",
    "description": "protein only",
    "directive": "Use protein-only system. Remove ATP, ligands, and non-essential ions.",
}

_CASE_DEFAULT: Dict[str, str] = {
    "case_id": "default",
    "suffix": "",
    "description": "default system from input PDB",
    "directive": "Use the full biologically relevant system present in the input PDB.",
}

_SIM_WORKSPACE_MARKERS = (
    "hpc",
    "analysis",
    "supervisor",
    "simsetup",
    "preprocess",
)


def _dir_looks_like_sim_workspace(sim_dir: Path) -> bool:
    """True when a subdirectory already holds (or held) per-simulation workflow data."""
    if not sim_dir.is_dir():
        return False
    for name in _SIM_WORKSPACE_MARKERS:
        if (sim_dir / name).is_dir():
            return True
    return False


def _has_trajectory_on_disk(sim_dir: Path) -> bool:
    hpc = sim_dir / "hpc"
    if not hpc.is_dir():
        return False
    for name in ("mdWrap.xtc", "md.xtc", "prod.xtc", "md.gro"):
        if (hpc / name).is_file():
            return True
    if (hpc / "md.tpr").is_file() and any(hpc.glob("*.xtc")):
        return True
    return False


def _is_workflow_scaffold_only(sim_dir: Path) -> bool:
    """True for agent folders only (e.g. mistaken re-run) with no MD inputs or trajectories."""
    if not sim_dir.is_dir():
        return False
    if (sim_dir / "simsetup").is_dir() or (sim_dir / "preprocess").is_dir():
        return False
    if _has_trajectory_on_disk(sim_dir):
        return False
    if (sim_dir / "hpc").is_dir():
        return False
    return any((sim_dir / name).is_dir() for name in ("supervisor", "planner", "analysis", "reporter"))


def resolve_sim_label_and_dir(
    uid: str,
    suffix: str,
    base_working_dir: str | Path,
    *,
    multi_component_cases: bool = False,
) -> tuple[str, str]:
    """
    Resolve simulation label and working directory.

    When the user already has on-disk workspaces named by UniProt ID only
    (e.g. ``o15197/``), prefer those over inferred ``{uid}_{suffix}`` names.
    Directory names without a ligand suffix do not imply apo vs holo — holo
    systems may live under plain UniProt folders.
    """
    base = Path(base_working_dir)
    plain_dir = base / uid
    suffixed_label = f"{uid}_{suffix}" if suffix else ""
    suffixed_dir = base / suffixed_label if suffixed_label else None

    if suffix:
        if suffixed_dir and _has_trajectory_on_disk(suffixed_dir):
            return suffixed_label, str(suffixed_dir.resolve())

        if (
            not multi_component_cases
            and plain_dir.is_dir()
            and _has_trajectory_on_disk(plain_dir)
            and (not suffixed_dir or not suffixed_dir.is_dir() or _is_workflow_scaffold_only(suffixed_dir))
        ):
            logger.info(
                "Sim label: using existing directory %s (not inferred %s)",
                uid,
                suffixed_label,
            )
            return uid, str(plain_dir.resolve())

        if suffixed_dir and suffixed_dir.is_dir() and _dir_looks_like_sim_workspace(suffixed_dir):
            return suffixed_label, str(suffixed_dir.resolve())

        return suffixed_label, str((base / suffixed_label).resolve())

    return uid, str(plain_dir.resolve())


def _normalize_goal_text(text: str) -> str:
    p = (text or "").lower()
    return (
        p.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _mentions_ligand_atp_positively(text: str) -> bool:
    """True when ATP/ligand is requested, not negated (e.g. 'no ATP' does not count)."""
    text = _normalize_goal_text(text)
    if not text:
        return False
    negated = bool(
        re.search(
            r"\b(?:no|not|without|exclude|drop|skip|omit|never|do\s+not)\s+"
            r"(?:create\s+)?(?:holo|ligand|ligands|atp|mg)\b",
            text,
        )
        or re.search(r"\b(?:holo|ligand|ligands|atp|mg)\s+(?:not\s+)?(?:requested|required|needed|included)\b", text)
        or re.search(
            r"\b(?:only\s+)?(?:apo|protein[\s\-]*only|apoprotein)\b.*\b(?:no|without)\s+(?:atp|holo|ligand)",
            text,
        )
        or re.search(
            r"\b(?:no|without)\s+(?:atp|holo|ligand|cofactor)",
            text,
        )
    )
    if negated and not re.search(r"\b(?:protein\s*\+\s*atp|holo\s+(?:system|simulation|form))\b", text):
        return False
    return bool(
        re.search(r"\bholo\b", text)
        or re.search(r"\bprotein\s*\+\s*atp\b", text)
        or re.search(r"protein\s*\+\s*atp\s*\+\s*mg", text)
        or re.search(
            r"\b(?:with|include|retain|keep|bound)\s+(?:atp|ligand)",
            text,
        )
        or re.search(r"\bprotein[\s\-]*(?:and|\+)\s*(?:atp|ligand)", text)
    )


def _is_apo_only_request(user_goal: str) -> bool:
    text = _normalize_goal_text(user_goal)
    if not text:
        return False
    if re.search(
        r"\b(?:do\s+not|don't|never|no)\s+(?:create|run|simulate|setup|set\s+up)\s+"
        r"(?:holo|protein\s*\+\s*atp|atp[\s\-]*bound)\b",
        text,
    ):
        return True
    if re.search(r"\b(?:only|just)\s+(?:apo|protein[\s\-]*only|apoprotein)\b", text):
        return True
    if re.search(r"\b(?:apo|protein[\s\-]*only)\s+(?:systems?|simulations?|forms?|states?|proteins?)\b", text):
        return True
    if re.search(r"\bprotein[\s\-]*only\b", text) and re.search(
        r"\b(?:no|without)\s+(?:atp|holo|ligand|cofactor)",
        text,
    ):
        return True
    if re.search(r"\b(?:twelve|eleven|ten|nine|eight|seven|six|five|four|three|\d+)\s+apo\b", text):
        if not re.search(r"\bapo\s*(?:/|vs|versus|and)\s*holo\b", text):
            return True
    return False


def _is_explicit_apo_holo_comparison(user_goal: str) -> bool:
    text = _normalize_goal_text(user_goal)
    return bool(
        re.search(r"\bapo\s*(?:/|vs|versus|and)\s*holo\b", text)
        or re.search(
            r"\btwo\s+(?:different\s+)?(?:cases?|simulation\s+systems?|systems?\s+per\s+(?:file|pdb))\b",
            text,
        )
        or re.search(r"\btwo\s+systems\s+per\s+file\b", text)
        or (
            re.search(r"\bcase\s*1\b", text)
            and re.search(r"\bcase\s*2\b", text)
            and re.search(r"\bprotein[\s\-]*(only|alone)\b", text)
            and _mentions_ligand_atp_positively(text)
        )
        or (
            re.search(r"\(\s*1\s*\)", text)
            and re.search(r"\(\s*2\s*\)", text)
            and re.search(r"\bprotein[\s\-]*(only|alone)\b", text)
            and _mentions_ligand_atp_positively(text)
        )
    )


def _simulation_count_implies_two_cases(user_goal: str, pdb_count: int) -> bool:
    if pdb_count <= 0:
        return False
    text = _normalize_goal_text(user_goal)
    target = pdb_count * 2
    for match in re.finditer(
        r"(?:total\s+)?(\d+)\s+(?:resulting\s+)?(?:simulations?|jobs?|runs?)\b",
        text,
    ):
        try:
            if int(match.group(1)) == target:
                return True
        except ValueError:
            continue
    word_to_count = {
        "two": 2,
        "four": 4,
        "six": 6,
        "eight": 8,
        "ten": 10,
        "twelve": 12,
        "sixteen": 16,
        "twenty": 20,
        "twenty-four": 24,
    }
    for word, count in word_to_count.items():
        if count == target and re.search(
            rf"\b{word}\s+(?:resulting\s+)?(?:simulations?|jobs?|runs?)\b",
            text,
        ):
            return True
    return False


def _holo_case_templates(user_goal: str) -> List[Dict[str, str]]:
    text = _normalize_goal_text(user_goal)
    has_mg = bool(re.search(r"\bmg(?:2\+?|\u00b2\+?)?\b", text))
    full_suffix = "ATP_MG" if has_mg else "ATP"
    full_desc = "protein + ATP + MG" if has_mg else "protein + ATP"
    full_directive = (
        "Keep protein with ATP ligand and Mg ions from the source PDB."
        if has_mg
        else "Keep protein with ATP ligand from the source PDB."
    )
    return [
        dict(_CASE_PROTEIN_ONLY),
        {
            "case_id": "protein_with_ligand",
            "suffix": full_suffix,
            "description": full_desc,
            "directive": full_directive,
        },
    ]


def heuristic_component_cases(
    user_goal: str,
    *,
    pdb_count: int = 0,
) -> List[Dict[str, str]]:
    """
    Conservative component-case detection from the original user goal only.
    """
    text = _normalize_goal_text(user_goal)

    if _is_apo_only_request(user_goal):
        logger.info("Component cases: apo-only request detected — single protein-only case")
        return [dict(_CASE_PROTEIN_ONLY)]

    has_protein_only = bool(
        re.search(r"\bprotein[\s\-]*(only|alone)\b", text)
        or re.search(r"\bonly\s+the\s+protein\b", text)
        or re.search(r"\bapo\s+(?:system|simulation|state|form|protein)\b", text)
        or "apoprotein" in text
    )
    wants_holo = _mentions_ligand_atp_positively(user_goal)
    explicit_multi = _is_explicit_apo_holo_comparison(user_goal)
    if pdb_count > 0:
        explicit_multi = explicit_multi or _simulation_count_implies_two_cases(user_goal, pdb_count)

    if explicit_multi and has_protein_only and wants_holo:
        logger.info("Component cases: explicit apo+holo multi-case request")
        return _holo_case_templates(user_goal)

    if wants_holo and not has_protein_only and re.search(r"\bholo\b", text):
        suffix = "ATP_MG" if re.search(r"\bmg(?:2\+?|\u00b2\+?)?\b", text) else "ATP"
        desc = "protein + ATP + MG" if suffix == "ATP_MG" else "protein + ATP"
        directive = (
            "Keep protein with ATP ligand and Mg ions from the source PDB."
            if suffix == "ATP_MG"
            else "Keep protein with ATP ligand from the source PDB."
        )
        return [
            {
                "case_id": "protein_with_ligand",
                "suffix": suffix,
                "description": desc,
                "directive": directive,
            }
        ]

    return [dict(_CASE_DEFAULT)]


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_resolved_cases(raw_cases: Sequence[Any]) -> List[Dict[str, str]]:
    allowed_ids = {
        "protein_only",
        "default",
        "protein_with_ligand",
    }
    normalized: List[Dict[str, str]] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or "default").strip()
        if case_id not in allowed_ids:
            case_id = "default"
        suffix = str(item.get("suffix") or "").strip()
        if suffix.upper() in ("ATP", "ATP_MG"):
            suffix = suffix.upper()
        description = str(item.get("description") or case_id).strip()
        directive = str(item.get("directive") or _CASE_DEFAULT["directive"]).strip()
        normalized.append(
            {
                "case_id": case_id,
                "suffix": suffix,
                "description": description,
                "directive": directive,
            }
        )
    return normalized or [dict(_CASE_DEFAULT)]


def _collapse_redundant_component_cases(
    cases: Sequence[Dict[str, str]],
    pdb_count: int,
) -> List[Dict[str, str]]:
    """
    Collapse LLM case lists that incorrectly expand one entry per PDB.

    ``cases`` must be the *set* of component systems applied to *each* PDB
    (typically 1, or 2 for apo+holo). LLMs often return N near-identical copies
    when there are many source structures; those must not be cartesian-producted
    with the PDB list (38 × 37 ≈ 1406 bogus simulations).
    """
    if len(cases) <= 1:
        return list(cases)

    # Exact duplicate rows (all fields).
    keys = [
        (
            c.get("case_id", ""),
            c.get("suffix", ""),
            c.get("description", ""),
            c.get("directive", ""),
        )
        for c in cases
    ]
    if len(set(keys)) == 1:
        logger.info(
            "Component cases: collapsing %d identical LLM cases to one shared case",
            len(cases),
        )
        return [dict(cases[0])]

    # Deduplicate by (case_id, suffix) — ignore wording drift in description/directive.
    by_id_suffix: Dict[tuple, Dict[str, str]] = {}
    for c in cases:
        key = (c.get("case_id", ""), c.get("suffix", ""))
        if key not in by_id_suffix:
            by_id_suffix[key] = dict(c)
    unique = list(by_id_suffix.values())

    if len(unique) < len(cases):
        logger.info(
            "Component cases: collapsing %d LLM cases → %d unique (case_id, suffix)",
            len(cases),
            len(unique),
        )
        cases = unique

    # Near-PDB-count dumps that share one case type (e.g. 37 of 38 PDBs).
    if pdb_count > 1 and len(cases) >= max(3, pdb_count - 1):
        id_suffix = {(c.get("case_id", ""), c.get("suffix", "")) for c in cases}
        if len(id_suffix) == 1:
            logger.info(
                "Component cases: collapsing %d near-per-PDB LLM cases "
                "(pdb_count=%d) to one shared case",
                len(cases),
                pdb_count,
            )
            return [dict(cases[0])]

    # Hard safety: never keep more case templates than a few real system variants.
    max_templates = 4
    if len(cases) > max_templates:
        logger.warning(
            "Component cases: truncating %d templates to first %d unique "
            "(case_id, suffix) entries — LLM likely echoed one case per PDB",
            len(cases),
            max_templates,
        )
        return cases[:max_templates]

    return list(cases)


def llm_component_cases(
    user_goal: str,
    *,
    pdb_count: int,
    pdb_summaries: Optional[Sequence[str]] = None,
    llm_client: Any,
    is_error_response: Optional[Callable[[str], bool]] = None,
) -> Optional[List[Dict[str, str]]]:
    """Ask the LLM which component cases the user requested."""
    if llm_client is None or pdb_count <= 0:
        return None

    pdb_block = ""
    if pdb_summaries:
        pdb_block = "SOURCE STRUCTURES:\n" + "\n".join(pdb_summaries) + "\n\n"

    prompt = (
        "You are an MD workflow planner. Read the USER GOAL and decide which simulation "
        "component cases to run for EACH listed PDB.\n\n"
        f"USER GOAL:\n{user_goal}\n\n"
        f"{pdb_block}"
        f"NUMBER OF PDB FILES: {pdb_count}\n\n"
        "Return ONLY valid JSON with this shape:\n"
        '{"cases": [{"case_id": "...", "suffix": "...", "description": "...", "directive": "..."}]}\n\n'
        "Rules:\n"
        "- `cases` is the SHARED set of component systems applied to EVERY PDB "
        f"(length is usually 1, or 2 for apo+holo). NEVER return one array entry per PDB "
        f"(do NOT return ~{pdb_count} nearly identical objects).\n"
        "- Use ONE case unless the user explicitly requests multiple component systems "
        "(e.g. apo vs holo, protein-only vs protein+ATP+MG).\n"
        "- If all PDBs are the same system type (e.g. all protein–ATP holo), return exactly "
        "ONE case object.\n"
        "- If the user requests apo / protein-only / no ATP / no holo, return a SINGLE "
        'protein_only case with empty suffix.\n'
        "- Do NOT invent holo or protein+ATP cases when the user asked for apo-only systems.\n"
        "- Ignore technical setup details (box size, force field, 1.2 nm buffer) — they are "
        "NOT separate simulation cases.\n"
        "- Allowed case_id values: protein_only, default, protein_with_ligand.\n"
        "- suffix: empty string for apo/default; ATP or ATP_MG for holo variants.\n"
        f"- Expected |cases| is small (1–2). Total simulations ≈ |cases| × {pdb_count}.\n"
    )

    try:
        response = llm_client.prompt_raw(prompt, temperature=0.1, max_tokens=800, format="json")
    except Exception as exc:
        logger.warning("LLM component-case resolution failed: %s", exc)
        return None

    if is_error_response and is_error_response(response):
        return None

    parsed = _extract_json_object(response)
    if not parsed or "cases" not in parsed:
        return None

    cases = _normalize_resolved_cases(parsed.get("cases") or [])
    if not cases:
        return None

    cases = _collapse_redundant_component_cases(cases, pdb_count)

    logger.info(
        "LLM component cases: %s",
        [c.get("description") for c in cases],
    )
    return cases


def resolve_component_cases(
    user_goal: str,
    enriched_prompt: str = "",
    *,
    pdb_count: int = 0,
    pdb_summaries: Optional[Sequence[str]] = None,
    llm_client: Any = None,
    is_error_response: Optional[Callable[[str], bool]] = None,
    prefer_llm: bool = True,
) -> List[Dict[str, str]]:
    """
    Resolve simulation component cases from user intent.

    Priority:
    1. LLM interpretation of the original user goal (when available)
    2. Conservative heuristics on the original user goal only
    """
    _ = enriched_prompt  # intentionally ignored — enriched text causes false positives

    heuristic = heuristic_component_cases(user_goal, pdb_count=pdb_count)

    if prefer_llm and llm_client is not None:
        llm_cases = llm_component_cases(
            user_goal,
            pdb_count=pdb_count,
            pdb_summaries=pdb_summaries,
            llm_client=llm_client,
            is_error_response=is_error_response,
        )
        if llm_cases is not None:
            # If heuristics say apo-only but LLM returned holo, trust apo-only heuristic.
            if (
                len(heuristic) == 1
                and heuristic[0].get("case_id") == "protein_only"
                and len(llm_cases) > 1
            ):
                logger.warning(
                    "LLM returned multiple cases for apo-only goal; using heuristic apo-only"
                )
                return heuristic
            # Single clear heuristic case (e.g. holo-only) outweighs an LLM dump of
            # many near-duplicate templates for a multi-PDB campaign.
            if (
                len(heuristic) == 1
                and len(llm_cases) > 1
                and pdb_count > 1
            ):
                h = heuristic[0]
                same_family = all(
                    (c.get("case_id") == h.get("case_id")
                     or (c.get("case_id") == "protein_with_ligand"
                         and h.get("case_id") == "protein_with_ligand"))
                    and (c.get("suffix") or "") == (h.get("suffix") or "")
                    for c in llm_cases
                )
                if same_family or len(llm_cases) >= max(3, pdb_count - 1):
                    logger.warning(
                        "LLM returned %d cases for a single-case multi-PDB goal; "
                        "using heuristic case %s",
                        len(llm_cases),
                        h.get("description"),
                    )
                    return heuristic
            return llm_cases

    return heuristic
