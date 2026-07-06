"""
Resolve human-readable protein names for reports and literature search.

Falls back through master-plan metadata, id:name maps in goals, inline
gene names (e.g. 'IRAK2 holo system (o43187)'), and UniProt lookup when
only an accession is available.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_UNIPROT_RE = re.compile(r"^[A-Za-z][0-9][0-9A-Za-z]{3,}[0-9A-Za-z]*$")
_ID_NAME_MAP_RE = re.compile(
    r"\b([A-Za-z0-9_\-]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})"
)

_SKIP_NAMES = frozenset({
    "ATP", "ADP", "MD", "PDB", "HPC", "COM", "FEL", "PCA", "DSSP", "DCCM",
    "RMSD", "RMSF", "SASA", "HTML", "B5R1", "SYSTEM", "PROTEIN", "LIGAND",
    "HOLO", "APO", "FOR", "THE", "AND", "WITH", "USING", "BASED",
    "ANALYZE", "ANALYSE", "COMPUTE", "CALCULATE", "GENERATE", "PREPARE",
    "RUN", "WRITE", "CREATE", "BUILD", "PERFORM", "EXECUTE", "REPORT",
})


def _looks_like_uniprot(name: str) -> bool:
    return bool(name and _UNIPROT_RE.match(name.strip()))


def _parse_id_name_map(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in _ID_NAME_MAP_RE.finditer(text or ""):
        uid, pname = m.group(1).strip().lower(), m.group(2).strip()
        if any(c.isdigit() for c in uid) and pname[0].isalpha():
            out[uid] = pname
    return out

def _gene_from_goal(label: str, *texts: Optional[str]) -> Optional[str]:
    combined = " ".join(t for t in texts if t)
    if not combined or not label:
        return None
    patterns = [
        rf"\b([A-Z][A-Za-z0-9]{{2,20}})\s+(?:holo|apo)\s+(?:simulation|system)\s*\(\s*{re.escape(label)}\s*\)",
        rf"of the\s+([A-Z][A-Za-z0-9]{{2,20}})\s+holo\s+system\s*\(\s*{re.escape(label)}\s*\)",
        rf"\b([A-Z][A-Za-z0-9]{{2,20}})\s+(?:holo|apo)\s+(?:simulation|system)[^.\n]{{0,40}}\b{re.escape(label)}\b",
        rf"for the\s+([A-Z][A-Za-z0-9]{{2,20}})\s+(?:holo|apo|kinase|pseudokinase|protein|system)",
        rf"\b([A-Z][A-Za-z0-9]{{2,20}})\b[^.\n]{{0,80}}\(\s*{re.escape(label)}\s*\)",
    ]
    for pat in patterns:
        hit = re.search(pat, combined, re.IGNORECASE)
        if hit:
            candidate = hit.group(1).strip()
            if candidate.upper() not in _SKIP_NAMES and not _looks_like_uniprot(candidate):
                return candidate.upper() if candidate.isupper() or re.search(r"\d", candidate) else candidate
    return None


def _lookup_uniprot_gene(accession: str) -> Optional[Dict[str, str]]:
    try:
        from src.reporter.literature_search import search_uniprot
        result = search_uniprot.invoke({"query": accession, "max_results": 1})
        if not isinstance(result, dict) or not result.get("success"):
            return None
        entries = result.get("entries") or []
        if not entries:
            return None
        entry = entries[0]
        gene = (entry.get("gene_name") or "").strip()
        pname = (entry.get("protein_name") or "").strip()
        organism = (entry.get("organism") or "").strip()
        func = (entry.get("function") or "").strip()
        display = gene or pname.split()[0] if pname else accession
        if display and not _looks_like_uniprot(display):
            return {
                "gene_name": gene or display,
                "protein_name": pname or display,
                "display_name": display,
                "organism": organism,
                "function": func,
                "uniprot_id": accession,
            }
    except Exception as exc:
        logger.debug("UniProt lookup failed for %s: %s", accession, exc)
    return None


def _sim_prompt_protein_name(state: Dict[str, Any], sim_label: str) -> Optional[str]:
    for sp in state.get("sim_prompts") or []:
        if (sp.get("label") or "").lower() == sim_label.lower():
            pname = (sp.get("protein_name") or "").strip()
            if pname and not _looks_like_uniprot(pname):
                return pname
            prompt = sp.get("prompt") or sp.get("goal") or ""
            gene = _gene_from_goal(sim_label, prompt)
            if gene:
                return gene
    return None


def resolve_protein_identity(
    state: Optional[Dict[str, Any]] = None,
    user_goal: str = "",
    sim_label: str = "",
) -> Dict[str, Any]:
    """
    Return resolved identity fields for reporting and literature.

    Keys: display_name, gene_name, protein_name, uniprot_id, organism,
    protein_family, related_terms, source
    """
    state = state or {}
    goal_text = " ".join(
        t for t in (
            state.get("user_goal_original"),
            state.get("master_enriched_prompt"),
            state.get("enriched_prompt"),
            state.get("user_goal"),
            user_goal,
        )
        if t
    )

    workdir = state.get("working_directory") or ""
    if not sim_label and workdir:
        sim_label = Path(workdir).name

    uniprot_id: Optional[str] = None
    gene_name: Optional[str] = None
    display_name: Optional[str] = None
    source = "unknown"

    id_map = _parse_id_name_map(goal_text)
    if sim_label and sim_label.lower() in id_map:
        gene_name = id_map[sim_label.lower()]
        display_name = gene_name
        source = "goal_id_map"

    if not display_name:
        from_sim = _sim_prompt_protein_name(state, sim_label)
        if from_sim:
            gene_name = from_sim
            display_name = from_sim
            source = "master_plan"

    if not display_name:
        gene = _gene_from_goal(sim_label, goal_text)
        if gene:
            gene_name = gene
            display_name = gene
            source = "goal_text"

    sys_info = state.get("system_info") if isinstance(state.get("system_info"), dict) else {}
    if not display_name and sys_info:
        candidate = (
            sys_info.get("protein_name")
            or sys_info.get("system_name")
            or sys_info.get("gene_name")
        )
        if candidate and not _looks_like_uniprot(str(candidate)):
            display_name = str(candidate)
            gene_name = display_name
            source = "system_info"

    if not uniprot_id:
        uniprot_id = (
            state.get("uniprot_id")
            or (sys_info.get("uniprot_id") if sys_info else None)
            or (sim_label if _looks_like_uniprot(sim_label) else None)
        )

    if not display_name or _looks_like_uniprot(display_name):
        acc = uniprot_id or sim_label
        if acc and _looks_like_uniprot(acc):
            uni = _lookup_uniprot_gene(acc)
            if uni:
                gene_name = uni.get("gene_name") or gene_name
                display_name = uni.get("display_name") or display_name
                source = "uniprot_lookup"
                if not uniprot_id:
                    uniprot_id = uni.get("uniprot_id")

    if not display_name:
        display_name = gene_name or sim_label or "Protein"
    if not gene_name:
        gene_name = display_name

    related_terms: List[str] = []
    lower = goal_text.lower()
    for term in ("pseudokinase", "kinase", "receptor", "transferase", "phosphatase"):
        if term in lower:
            related_terms.append(term)

    protein_family = related_terms[0] if related_terms else ""
    if not protein_family and display_name:
        uni = _lookup_uniprot_gene(uniprot_id) if uniprot_id and _looks_like_uniprot(uniprot_id) else None
        if uni and uni.get("function"):
            func_low = uni["function"].lower()
            for term in ("pseudokinase", "kinase", "receptor"):
                if term in func_low:
                    protein_family = term
                    break

    return {
        "display_name": display_name,
        "gene_name": gene_name,
        "protein_name": display_name,
        "uniprot_id": (uniprot_id or sim_label or "").lower() if uniprot_id or _looks_like_uniprot(sim_label) else sim_label,
        "organism": (sys_info or {}).get("organism", ""),
        "protein_family": protein_family,
        "related_terms": related_terms,
        "source": source,
    }
