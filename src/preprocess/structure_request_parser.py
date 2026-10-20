"""
Parse structure acquisition requests from natural language goals.

Extracts UniProt IDs, protein names, domain labels, and residue ranges so the
preprocess agent can download and trim structures without an existing PDB file.

When a domain is named without explicit residues (e.g. "kinase domain"),
residue boundaries are resolved from UniProt feature annotations.

Deterministic regex extraction is the primary path. When it finds nothing but
the goal clearly asks to download / AlphaFold a structure, an optional LLM
gap-filler may propose candidates — every ID is validated before use.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .domain_sources import lookup_domain_range

logger = logging.getLogger(__name__)

# Classic 6-char (O43825, Q8NB16) and extended A0A… forms. Not gene symbols.
_VALID_UNIPROT_RE = re.compile(
    r"^(?:"
    r"[OPQABCD][0-9][A-Z0-9]{3}[0-9]"
    r"|[A-Z][0-9][A-Z0-9]{3}[0-9][A-Z0-9]{1,5}"
    r")$",
    re.IGNORECASE,
)
_VALID_PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")

_DASH_TRANSLATION = str.maketrans({
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
})


def _normalize_dashes(text: str) -> str:
    """Treat en/em dashes as ASCII hyphens in residue-range parsing."""
    return text.translate(_DASH_TRANSLATION) if text else text


def _normalize_uniprot(raw: str) -> str:
    return raw.strip().upper()


_UNIPROT_ACC_RE = re.compile(r"\b([a-z][0-9][a-z0-9]{3,8})\b", re.IGNORECASE)


def extract_uniprot_ids(text: str) -> List[str]:
    """Extract UniProt accessions from free text.

    Supports common natural-language phrasings used in goals, e.g.::

        UniProt Q8NB16
        uniprot id: Q8NB16
        which uniprot id are Q8NB16 and Q6VAB6, respectively
        Q8NB16: MLKL
    """
    if not text:
        return []

    _acc = r"[a-z][0-9][a-z0-9]{3,8}"
    patterns = [
        # UniProt Q8NB16 / uniprot id: Q8NB16 / uniprot ids = Q8NB16
        rf"\buniprot(?:\s*ids?)?\s*[:=]?\s*({_acc})\b",
        rf"\buniprotid\s+({_acc})\b",
        # q8nb16: ERBB3 / MLKL (Q8NB16) — gene map forms
        rf"\b({_acc})\s*:\s*[A-Z][A-Z0-9_]+\b",
        rf"\b({_acc})\.pdb\b",
        # Parenthetical: MLKL (Q8NB16) / (uniprot Q8NB16)
        rf"\(\s*(?:uniprot(?:\s*ids?)?\s*[:=]?\s*)?({_acc})\s*\)",
    ]
    found: List[str] = []
    lower = text.lower()
    for pattern in patterns:
        for match in re.finditer(pattern, lower, re.IGNORECASE):
            found.append(_normalize_uniprot(match.group(1)))

    # Natural language lists: "uniprot id are Q8NB16 and Q6VAB6, respectively"
    # Allow short filler (are/is/of/for/namely/…) between "uniprot id(s)" and accessions.
    for match in re.finditer(
        rf"\buniprot(?:\s*ids?)?\b(?:\s+(?:id|ids|accession|accessions|"
        rf"are|is|of|for|namely|:|=))*\s*"
        rf"((?:{_acc}(?:\s*(?:,|;|and|&|/)\s*)?)+)",
        lower,
        re.IGNORECASE,
    ):
        for acc in _UNIPROT_ACC_RE.findall(match.group(1)):
            found.append(_normalize_uniprot(acc))

    # When the goal clearly asks to download AlphaFold/UniProt structures,
    # also accept bare accession tokens (still UniProt-shaped).
    if re.search(
        r"\b(?:download|fetch|retrieve|alphafold|uniprot)\b",
        lower,
    ):
        for acc in _UNIPROT_ACC_RE.findall(lower):
            # Keep classic Swiss-Prot / TrEMBL shape: letter+digit+…
            # already enforced by _UNIPROT_ACC_RE
            found.append(_normalize_uniprot(acc))

    seen = set()
    unique = []
    for uid in found:
        if uid not in seen:
            seen.add(uid)
            unique.append(uid)
    return unique


def extract_pdb_ids(text: str) -> List[str]:
    """
    Extract RCSB PDB entry IDs (e.g. 6VC0) from free text.

    Prefers explicit PDB context to avoid false positives. Also accepts
    ``NNNN.pdb`` when the goal asks to download/fetch a structure.
    """
    if not text:
        return []

    lower = text.lower()
    found: List[str] = []
    patterns = [
        r"\bpdb(?:\s*id)?\s*[:=]?\s*([0-9][a-z0-9]{3})\b",
        r"\b(?:rcsb|protein data bank)\s+(?:entry\s+|structure\s+)?([0-9][a-z0-9]{3})\b",
        r"\b(?:download|fetch|retrieve)\s+(?:the\s+)?(?:structure\s+|pdb\s+)?([0-9][a-z0-9]{3})\b",
        r"\bstructure\s+([0-9][a-z0-9]{3})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            found.append(match.group(1).upper())

    # Bare NNNN.pdb only when download/fetch is mentioned (else treat as local path)
    if re.search(r"\b(?:download|fetch|retrieve)\b", lower):
        for match in re.finditer(r"\b([0-9][a-z0-9]{3})\.pdb\b", lower):
            found.append(match.group(1).upper())

    seen = set()
    unique: List[str] = []
    for pid in found:
        if pid not in seen:
            seen.add(pid)
            unique.append(pid)
    return unique


def extract_protein_name(text: str, uniprot_id: Optional[str] = None) -> Optional[str]:
    """Extract a human-readable protein name (e.g. ERBB3 / DCLK3) from text."""
    if not text:
        return None

    _SKIP = {
        "domain", "kinase", "loop", "region", "residue", "residues", "uniprot",
        "activation", "catalytic", "segment", "protein", "structure", "human",
        "preprocess", "preprocessing", "setup", "analysis", "reporter",
        "gyration", "radius", "rmsd", "rmsf", "download", "extract", "alphafold",
        "two", "both", "all", "each", "the", "and", "for", "from", "with",
        "please", "compare", "dynamics", "pseudokinases", "pseudokinase",
    }

    def _ok(name: str) -> bool:
        return bool(name) and name.lower() not in _SKIP

    # Prefer UniProt Q9C098 (DCLK3, human) / DCLK3 (Q9C098)
    if uniprot_id:
        m = re.search(
            rf"\b{re.escape(uniprot_id)}\s*\(\s*([A-Za-z][A-Za-z0-9_]{{2,}})\b",
            text,
            re.IGNORECASE,
        )
        if m and _ok(m.group(1)):
            return m.group(1).upper()
        m = re.search(
            rf"\b([A-Za-z][A-Za-z0-9_]{{2,}})\s*\(\s*{re.escape(uniprot_id)}\s*\)",
            text,
            re.IGNORECASE,
        )
        if m and _ok(m.group(1)):
            return m.group(1).upper()

    m = re.search(
        r"\b([A-Z][A-Za-z0-9]{2,20})\s+(?:kinase|pseudokinase)\s+domain\b",
        text,
    )
    if m and _ok(m.group(1)):
        return m.group(1).upper()

    if uniprot_id:
        for pattern in (
            rf"\b{re.escape(uniprot_id)}\s*:\s*([A-Za-z][A-Za-z0-9_]+)\b",
            rf"\b(?:protein|of)\s+([A-Za-z][A-Za-z0-9_]+)\b[^.]*\b{re.escape(uniprot_id)}\b",
            rf"\b{re.escape(uniprot_id)}\b[^.]*\b(?:protein)\s+([A-Za-z][A-Za-z0-9_]+)\b",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).upper()
                if _ok(name):
                    return name

    match = re.search(
        r"\bprotein\s+([A-Za-z][A-Za-z0-9_]{2,})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        name = match.group(1).upper()
        if _ok(name):
            return name

    return None


def extract_domain_label(text: str) -> Optional[str]:
    """Extract domain description such as 'kinase domain'."""
    if not text:
        return None

    patterns = [
        r"\b(kinase\s+domain)\b",
        r"\b(catalytic\s+domain)\b",
        r"\b(activation\s+loop)\b",
        r"\b(sh2\s+domain)\b",
        r"\b(sh3\s+domain)\b",
        r"\b([a-z][a-z0-9_\-]+\s+domain)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            label = match.group(1).strip().lower().replace(" ", "_")
            return label
    return None


def extract_residue_range(text: str) -> Optional[Tuple[int, int]]:
    """
    Extract residue range from patterns like resid 503:771 globally in text.
    """
    if not text:
        return None
    text = _normalize_dashes(text)

    patterns = [
        r"\bresid(?:ue)?s?\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidue\s+range\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidues?\s+(\d+)\s*(?:through|thru|to|-)\s*(\d+)\b",
        r"\bresid(?:ue)?s?\s+(\d+)\s+to\s+(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            return start, end
    return None


def extract_residue_range_for_domain(
    text: str,
    domain_label: Optional[str],
) -> Optional[Tuple[int, int]]:
    """
    Extract residue range scoped near the requested domain phrase.

    Avoids picking up unrelated analysis ranges (e.g. activation-loop RMSF
    resid 150-190 when the simulation target is the kinase domain).
    """
    if not text or not domain_label:
        return None
    text = _normalize_dashes(text)

    phrase = domain_label.replace("_", " ")
    match = re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE)
    if not match:
        return None

    # Window around the domain mention — stop before analysis-only clauses
    window_start = max(0, match.start() - 80)
    window_end = min(len(text), match.end() + 200)
    window = text[window_start:window_end]
    sim_parts = re.split(
        r"\b(?:for\s+analysis|during\s+analysis|analysis\s+compute|analysis:|"
        r"RMSF|DCCM|DSSP|overlay\s+plot|compare\s+dynamics|per-residue)\b",
        window,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    sim_window = sim_parts[0]

    patterns = [
        r"\bresid(?:ue)?s?\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidue\s+range\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidues?\s+(\d+)\s*(?:through|thru|to|-)\s*(\d+)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, sim_window, re.IGNORECASE)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start > end:
                start, end = end, start
            return start, end
    return None


def resolve_domain_residue_range(
    uniprot_id: str,
    domain_label: str,
    explicit_range: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    """
    Resolve residue boundaries: explicit user range > UniProt > offline fallback.
    """
    if explicit_range:
        return {
            "start_resid": explicit_range[0],
            "end_resid": explicit_range[1],
            "residue_range": f"{explicit_range[0]}-{explicit_range[1]}",
            "domain_lookup_source": "user_specified",
            "domain_lookup_description": "Residue range from user prompt",
            "domain_lookup_success": True,
        }

    lookup = lookup_domain_range(uniprot_id, domain_label)
    if lookup and lookup.get("start_resid") and lookup.get("end_resid"):
        return {
            "start_resid": lookup["start_resid"],
            "end_resid": lookup["end_resid"],
            "residue_range": f"{lookup['start_resid']}-{lookup['end_resid']}",
            "domain_lookup_source": lookup.get("source", "unknown"),
            "domain_lookup_description": lookup.get("description", ""),
            "domain_lookup_success": True,
            "domain_lookup_message": lookup.get("message", ""),
            "domain_lookup_details": lookup,
        }

    return {
        "domain_lookup_success": False,
        "domain_lookup_error": (lookup or {}).get("error", "Domain lookup failed"),
        "domain_lookup_details": lookup,
    }


def extract_structure_source(text: str) -> str:
    """Infer preferred download source from goal text."""
    if not text:
        return "auto"
    lower = text.lower()
    if "alphafold" in lower:
        return "alphafold"
    if "rcsb" in lower or "protein data bank" in lower or "pdb bank" in lower:
        return "rcsb"
    return "auto"


def parse_structure_request(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a structure acquisition request from user goal / planner instructions.

    Returns None if neither a UniProt accession nor an RCSB PDB ID is found.
    UniProt requests take precedence when both appear.
    """
    if not text:
        return None
    text = _normalize_dashes(text)

    uniprot_ids = extract_uniprot_ids(text)
    pdb_ids = extract_pdb_ids(text)

    if not uniprot_ids and not pdb_ids:
        return None

    # Direct PDB-ID download (no UniProt)
    if not uniprot_ids and pdb_ids:
        pdb_id = pdb_ids[0]
        return {
            "uniprot_id": None,
            "pdb_id": pdb_id,
            "protein_name": None,
            "domain_label": None,
            "residue_range": None,
            "start_resid": None,
            "end_resid": None,
            "needs_download": True,
            "extract_domain": False,
            "structure_source": "rcsb",
        }

    uniprot_id = uniprot_ids[0]
    protein_name = extract_protein_name(text, uniprot_id)
    domain_label = extract_domain_label(text)

    # Scope explicit ranges to the simulation domain when possible
    if domain_label:
        residue_range = extract_residue_range_for_domain(text, domain_label)
        if residue_range is None:
            residue_range = extract_residue_range(text)
    else:
        residue_range = extract_residue_range(text)

    domain_lookup: Dict[str, Any] = {}
    if domain_label and not residue_range:
        domain_lookup = resolve_domain_residue_range(uniprot_id, domain_label)
        if domain_lookup.get("domain_lookup_success"):
            residue_range = (
                domain_lookup["start_resid"],
                domain_lookup["end_resid"],
            )

    needs_download = not re.search(r"\b[\w\-]+\.pdb\b", text, re.IGNORECASE) or bool(
        re.search(r"\bdownload\b", text, re.IGNORECASE)
    )

    result = {
        "uniprot_id": uniprot_id,
        "pdb_id": pdb_ids[0] if pdb_ids else None,
        "protein_name": protein_name,
        "domain_label": domain_label,
        "residue_range": residue_range,
        "start_resid": residue_range[0] if residue_range else None,
        "end_resid": residue_range[1] if residue_range else None,
        "needs_download": needs_download,
        "extract_domain": bool(residue_range or domain_label),
        "structure_source": extract_structure_source(text),
    }
    if domain_lookup:
        result.update(domain_lookup)
    return result


def build_domain_context_for_agents(request: Dict[str, Any]) -> str:
    """Human-readable domain annotation block for planner/agent prompts."""
    if not request or not request.get("domain_label"):
        return ""

    lines = [
        f"**Domain target:** {request['domain_label'].replace('_', ' ')}",
        f"**UniProt:** {request.get('uniprot_id', 'unknown')}",
    ]
    if request.get("protein_name"):
        lines.append(f"**Protein:** {request['protein_name']}")

    if request.get("start_resid") and request.get("end_resid"):
        source = request.get("domain_lookup_source", "unknown")
        desc = request.get("domain_lookup_description", "")
        lines.append(
            f"**Residue range (UniProt numbering):** "
            f"{request['start_resid']}-{request['end_resid']} "
            f"(source: {source})"
        )
        if desc:
            lines.append(f"**Annotation:** {desc}")
        lines.append(
            "**Action:** extract_domain on downloaded/full PDB before preprocessing "
            f"→ output e.g. {build_output_basename(request)}.pdb"
        )
    elif request.get("domain_label"):
        lines.append(
            "**Warning:** domain requested but residue range could not be resolved. "
            "Run lookup_domain_range_tool or provide explicit resid range."
        )
    return "\n".join(lines)


def build_output_basename(request: Dict[str, Any]) -> str:
    """Build output filename stem, e.g. ERBB3_kinase_domain."""
    _BAD = {
        "protein", "domain", "kinase", "gyration", "preprocess", "structure",
        "radius", "rmsd", "rmsf", "unknown", "none", "null",
    }
    raw = (request.get("protein_name") or "").strip()
    if raw and raw.lower() not in _BAD and not raw.lower().startswith("gyration"):
        name = raw
    else:
        name = (
            request.get("uniprot_id")
            or request.get("pdb_id")
            or "protein"
        )
    domain = request.get("domain_label")
    if domain:
        return f"{name}_{domain}"
    if request.get("extract_domain"):
        return f"{name}_domain"
    return str(name)


def is_valid_uniprot_accession(uid: Optional[str]) -> bool:
    """True for Swiss-Prot / TrEMBL accession shapes (not gene symbols)."""
    return bool(uid and _VALID_UNIPROT_RE.match(str(uid).strip()))


def is_valid_pdb_id(pid: Optional[str]) -> bool:
    """True for 4-character RCSB PDB entry IDs."""
    return bool(pid and _VALID_PDB_ID_RE.match(str(pid).strip()))


def goal_requests_structure_download(text: str) -> bool:
    """True when the goal likely needs AlphaFold/RCSB acquisition (no local PDB)."""
    if not text:
        return False
    lower = text.lower()
    if re.search(r"\b[\w./\-]+\.pdb\b", lower) and not re.search(
        r"\b(?:download|fetch|retrieve|alphafold)\b", lower
    ):
        # Local path mentioned, no download intent
        return False
    return bool(
        re.search(
            r"\b(?:download|fetch|retrieve|alphafold|uniprot|rcsb|"
            r"alpha\s*fold|structure\s+for)\b",
            lower,
        )
    )


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON object extraction from an LLM response."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def validate_structure_targets(
    targets: List[Dict[str, Any]],
    *,
    default_source: str = "auto",
) -> List[Dict[str, Any]]:
    """Keep only targets with a valid UniProt accession and/or PDB ID."""
    validated: List[Dict[str, Any]] = []
    seen: set = set()
    for raw in targets or []:
        if not isinstance(raw, dict):
            continue
        uid = (raw.get("uniprot_id") or raw.get("uniprot") or "").strip().upper() or None
        pid = (raw.get("pdb_id") or raw.get("pdb") or "").strip().upper() or None
        if uid and not is_valid_uniprot_accession(uid):
            logger.info("Rejecting LLM UniProt candidate (bad shape): %r", uid)
            uid = None
        if pid and not is_valid_pdb_id(pid):
            logger.info("Rejecting LLM PDB candidate (bad shape): %r", pid)
            pid = None
        if not uid and not pid:
            continue
        key = uid or pid
        if key in seen:
            continue
        seen.add(key)
        source = str(raw.get("structure_source") or default_source or "auto").lower()
        if source not in {"auto", "alphafold", "rcsb"}:
            source = "alphafold" if uid else "rcsb"
        if pid and not uid:
            source = "rcsb"
        domain = raw.get("domain_label") or raw.get("domain")
        if isinstance(domain, str):
            domain = domain.strip().lower().replace(" ", "_") or None
        else:
            domain = None
        name = raw.get("protein_name") or raw.get("gene_name") or raw.get("name")
        if isinstance(name, str):
            name = name.strip() or None
        else:
            name = None
        validated.append(
            {
                "uniprot_id": uid,
                "pdb_id": pid if not uid else None,
                "protein_name": name,
                "domain_label": domain,
                "structure_source": source,
                "extract_domain": bool(domain or raw.get("extract_domain")),
                "start_resid": raw.get("start_resid"),
                "end_resid": raw.get("end_resid"),
            }
        )
    return validated


def interpret_fuzzy_structure_goal(
    goal: str,
    llm: Any,
    *,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Ask an LLM to interpret a fuzzy structure-download goal.

    Deterministic parsing should be tried first. This helper only proposes
    candidates; callers must use :func:`validate_structure_targets` (already
    applied here) before fetching.

    Returns
    -------
    dict
        ``success``, ``targets`` (validated), ``raw_response``, ``error``.
    """
    if not goal or not llm:
        return {
            "success": False,
            "targets": [],
            "raw_response": "",
            "error": "missing goal or llm",
        }

    system = (
        "You extract structure-download targets from MD simulation goals. "
        "Return ONLY valid JSON (no markdown, no prose). "
        "Never invent UniProt accessions or PDB IDs you are unsure of — "
        "omit a target rather than guess. Prefer UniProt accessions when "
        "AlphaFold download is requested."
    )
    prompt = f"""Extract structure acquisition targets from this user goal.

Goal:
\"\"\"{goal}\"\"\"

Return JSON with this schema:
{{
  "targets": [
    {{
      "uniprot_id": "Q8NB16 or null",
      "pdb_id": "6VC0 or null",
      "protein_name": "MLKL or null",
      "domain_label": "pseudokinase_domain or kinase_domain or null",
      "structure_source": "alphafold|rcsb|auto",
      "extract_domain": true
    }}
  ]
}}

Rules:
- Include one object per protein/structure to download.
- uniprot_id must be a real UniProt accession (e.g. Q8NB16, O43825, A0A0B4J2F0).
- pdb_id must be a 4-character RCSB ID when an experimental PDB is requested.
- If the goal names genes (MLKL, KSR2) with UniProt IDs nearby, pair them.
- domain_label: snake_case when a domain extract is requested; else null.
- If nothing can be extracted confidently, return {{"targets": []}}.
"""

    try:
        call = getattr(llm, "prompt_raw", None) or getattr(llm, "prompt")
        raw = call(
            prompt,
            system=system,
            temperature=temperature,
            agent="structure_goal_parser",
        )
    except Exception as exc:
        logger.warning("LLM structure-goal interpret failed: %s", exc)
        return {
            "success": False,
            "targets": [],
            "raw_response": "",
            "error": str(exc),
        }

    parsed = _extract_json_object(str(raw or ""))
    if not parsed:
        return {
            "success": False,
            "targets": [],
            "raw_response": str(raw or "")[:2000],
            "error": "could not parse JSON from LLM response",
        }

    default_source = extract_structure_source(goal)
    targets = validate_structure_targets(
        list(parsed.get("targets") or []),
        default_source=default_source,
    )
    return {
        "success": bool(targets),
        "targets": targets,
        "raw_response": str(raw or "")[:2000],
        "error": None if targets else "LLM returned no valid UniProt/PDB IDs",
    }
