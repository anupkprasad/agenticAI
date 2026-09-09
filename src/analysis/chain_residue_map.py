"""
Map PDB chain ID + residue numbers onto GROMACS trajectory residue indices.

GROMACS ``.gro`` / ``.tpr`` / ``.xtc`` files do not store PDB chain IDs, and
``pdb2gmx -merge all`` concatenates chains into one molecule. User-facing
selections such as ``chainID B and resid 50:75`` are translated to unique
``resindex`` selections using a JSON map built from the input PDB (chain
vocabulary) and the processed protein topology (trajectory residue order).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

CHAIN_MAP_FILENAME = "chain_residue_map.json"
CHAIN_MAP_VERSION = 1

SELECTION_PARAM_KEYS = (
    "selection",
    "selection1",
    "selection2",
    "align_selection",
    "ligand_selection",
    "protein_selection",
    "query_selection",
    "neighbor_selection",
)

# Prompt snippet for the analysis LLM — keep chainID in planned selections.
CHAIN_SELECTION_LLM_NOTE = """
**CHAIN / RESID SELECTIONS (multi-chain complexes):**
GROMACS trajectories (md.tpr / .gro / .xtc) have no chain IDs. Still write
MDAnalysis selections in PDB chain language, for example:
  "chainID B and resid 50:75"
  "chainID A and resid 1:10 and name CA"
  "protein and chainID C"
  "chainID A and name CA and around 10 (chainID B and resid 1:34)"
The analysis layer maps these to trajectory ``resindex`` using
``chain_residue_map.json`` (built from the input PDB at setup, or rebuilt
from preprocess PDB + topology). Always include ``chainID`` when residue
numbers overlap across chains. Do not use bare ``resid 50:75`` on a
multi-chain complex. Prefer ``identify_nearby_residues`` when the user asks
to list residues within a cutoff, then pass that JSON via ``selection_from_file``.
"""

_NONPROTEIN_RESNAMES = frozenset({
    "HOH", "WAT", "SOL", "TIP3", "TIP", "SPC", "H2O",
    "NA", "CL", "K", "MG", "CA", "ZN", "FE", "MN", "CU", "NI", "CO",
    "NA+", "CL-", "MG2", "CA2", "ZN2",
    "ATP", "ADP", "GTP", "GDP", "AMP", "ANP", "CNP", "LIG",
})

# Force-field / tautomer names that still represent the same amino acid.
# Values are stable keys (standard PDB name, or phospho base SEP/TPO/PTR).
_RESNAME_TO_GROUP: Dict[str, str] = {
    "HIS": "HIS", "HID": "HIS", "HIE": "HIS", "HIP": "HIS",
    "HSD": "HIS", "HSE": "HIS", "HSP": "HIS",
    "CYS": "CYS", "CYX": "CYS", "CYM": "CYS",
    "ASP": "ASP", "ASH": "ASP",
    "GLU": "GLU", "GLH": "GLU",
    "LYS": "LYS", "LYN": "LYS",
    "SER": "SER",
    "SEP": "SEP", "SP1": "SEP", "SP2": "SEP",
    "THR": "THR",
    "TPO": "TPO", "THP": "TPO", "THP1": "TPO", "THP2": "TPO",
    "TYR": "TYR",
    "PTR": "PTR", "TP1": "PTR", "TP2": "PTR", "TP1A": "PTR", "TP2A": "PTR",
}

_AA_ONE_LETTER = {
    "ALA": "A", "CYS": "C", "ASP": "D", "GLU": "E", "PHE": "F",
    "GLY": "G", "HIS": "H", "ILE": "I", "LYS": "K", "LEU": "L",
    "MET": "M", "ASN": "N", "PRO": "P", "GLN": "Q", "ARG": "R",
    "SER": "S", "THR": "T", "VAL": "V", "TRP": "W", "TYR": "Y",
    "SEP": "S", "TPO": "T", "PTR": "Y",
}

_CHAIN_TOKEN_RE = re.compile(
    r"(?:chainID|chainid|chain|segid)\s+['\"]?([A-Za-z0-9]{1,4})['\"]?",
    re.IGNORECASE,
)
_RESID_RANGE_RE = re.compile(
    r"(?:resid|resnum|resi)\s+(\d+)\s*(?:[:\-]|to)\s*(\d+)",
    re.IGNORECASE,
)
_RESID_LIST_RE = re.compile(
    r"(?:resid|resnum|resi)\s+((?:\d+\s*)+)",
    re.IGNORECASE,
)
_NOT_CHAIN_RE = re.compile(r"\bnot\s+(?:chainID|chainid|chain|segid)\b", re.IGNORECASE)


class ChainSelectionError(ValueError):
    """User chain/resid selection cannot be mapped onto the trajectory."""


def canonical_resname(resname: str) -> str:
    """Collapse tautomer / phospho names onto a stable matching key."""
    raw = (resname or "").strip().upper()
    if not raw:
        return ""
    stripped = re.sub(r"^\d+", "", raw)
    key = stripped or raw
    return _RESNAME_TO_GROUP.get(key, key)


def resname_one_letter(resname: str) -> str:
    canon = canonical_resname(resname)
    return _AA_ONE_LETTER.get(canon, "X")


def same_residue(name_a: str, name_b: str) -> bool:
    return canonical_resname(name_a) == canonical_resname(name_b)


def _norm_chain_id(chain_id: str) -> str:
    text = (chain_id or "").strip()
    return text if text else "A"


def _is_protein_resname(resname: str) -> bool:
    key = (resname or "").strip().upper()
    stripped = re.sub(r"^\d+", "", key) or key
    if stripped in _NONPROTEIN_RESNAMES or key in _NONPROTEIN_RESNAMES:
        return False
    if canonical_resname(stripped) in _AA_ONE_LETTER:
        return True
    if stripped in _RESNAME_TO_GROUP:
        return True
    try:
        from src.preprocess.phospho_residues import is_phospho_protein_resname

        return is_phospho_protein_resname(stripped)
    except Exception:
        return stripped in {"SEP", "TPO", "PTR", "SP1", "SP2", "THP", "THP1", "THP2", "TP1", "TP2"}


# ---------------------------------------------------------------------------
# Residue extraction
# ---------------------------------------------------------------------------


def _residues_from_pdb_lines(pdb_file: str) -> List[Dict[str, Any]]:
    """Parse unique protein residues from a PDB, preserving first-seen order."""
    residues: List[Dict[str, Any]] = []
    seen = set()
    with open(pdb_file) as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")) or len(line) < 26:
                continue
            try:
                from src.preprocess.phospho_residues import resname_from_pdb_line

                resname = resname_from_pdb_line(line)
            except Exception:
                resname = line[17:20].strip()
            if not _is_protein_resname(resname):
                continue
            chain = _norm_chain_id(line[21] if len(line) > 21 else "")
            try:
                resid = int(line[22:26].strip())
            except ValueError:
                continue
            icode = line[26].strip() if len(line) > 26 else ""
            key = (chain, resid, icode)
            if key in seen:
                continue
            seen.add(key)
            residues.append({
                "chain_id": chain,
                "pdb_resid": resid,
                "resname": resname.strip().upper(),
                "icode": icode,
            })
    return residues


def _residues_from_universe(universe, *, from_pdb: bool) -> List[Dict[str, Any]]:
    """Ordered protein (+ phospho) residues from an MDAnalysis Universe."""
    try:
        from src.preprocess.phospho_residues import select_phospho_protein_atoms

        atoms = universe.select_atoms("protein") + select_phospho_protein_atoms(universe)
    except Exception:
        atoms = universe.select_atoms("protein")
    if len(atoms) == 0:
        atoms = universe.select_atoms("not resname HOH WAT SOL TIP3 NA CL MG")

    ordered = []
    seen = set()
    for residue in atoms.residues:
        idx = int(residue.resindex)
        if idx in seen:
            continue
        seen.add(idx)
        resname = str(residue.resname).strip().upper()
        if not _is_protein_resname(resname):
            continue
        chain = ""
        if from_pdb:
            try:
                chain = _norm_chain_id(str(residue.atoms[0].chainID))
            except Exception:
                chain = "A"
        ordered.append({
            "chain_id": chain,
            "pdb_resid": int(residue.resid),
            "resname": resname,
            "traj_resindex": idx,
            "traj_resid": int(residue.resid),
        })
    return ordered


def extract_pdb_chain_residues(pdb_file: str) -> List[Dict[str, Any]]:
    """Protein residues from a PDB, with chain IDs, in file order."""
    try:
        import MDAnalysis as mda

        universe = mda.Universe(pdb_file)
        residues = _residues_from_universe(universe, from_pdb=True)
        if residues:
            return residues
    except Exception as exc:
        logger.debug("MDAnalysis PDB residue extract failed, using line parser: %s", exc)
    return _residues_from_pdb_lines(pdb_file)


def extract_traj_protein_residues(topology_file: str) -> List[Dict[str, Any]]:
    """Protein residues from GRO/TPR/PDB topology, in trajectory order."""
    import MDAnalysis as mda

    universe = mda.Universe(topology_file)
    return _residues_from_universe(universe, from_pdb=False)


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


def _needleman_wunsch(
    pdb_letters: Sequence[str],
    traj_letters: Sequence[str],
) -> List[Tuple[Optional[int], Optional[int]]]:
    """Global alignment; returns (pdb_index, traj_index) pairs including gaps."""
    n, m = len(pdb_letters), len(traj_letters)
    gap = -1
    score = [[0] * (m + 1) for _ in range(n + 1)]
    ptr = [[0] * (m + 1) for _ in range(n + 1)]  # 1=diag, 2=up, 3=left
    for i in range(1, n + 1):
        score[i][0] = i * gap
        ptr[i][0] = 2
    for j in range(1, m + 1):
        score[0][j] = j * gap
        ptr[0][j] = 3
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match = 1 if pdb_letters[i - 1] == traj_letters[j - 1] else -1
            diag = score[i - 1][j - 1] + match
            up = score[i - 1][j] + gap
            left = score[i][j - 1] + gap
            best = max(diag, up, left)
            score[i][j] = best
            ptr[i][j] = 1 if best == diag else (2 if best == up else 3)
    pairs: List[Tuple[Optional[int], Optional[int]]] = []
    i, j = n, m
    while i > 0 or j > 0:
        direction = ptr[i][j] if i >= 0 and j >= 0 else (2 if i > 0 else 3)
        if direction == 1:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif direction == 2:
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    pairs.reverse()
    return pairs


def _pair_residues(
    pdb_residues: Sequence[Dict[str, Any]],
    traj_residues: Sequence[Dict[str, Any]],
) -> Tuple[List[Tuple[Dict[str, Any], Dict[str, Any]]], List[str]]:
    warnings: List[str] = []
    n_pdb, n_traj = len(pdb_residues), len(traj_residues)

    if n_pdb == n_traj and n_pdb > 0:
        pairs = list(zip(pdb_residues, traj_residues))
        mismatches = [
            f"{p['chain_id']}:{p['pdb_resid']} {p['resname']} vs traj {t['resname']} (resindex {t['traj_resindex']})"
            for p, t in pairs
            if not same_residue(p["resname"], t["resname"])
        ]
        if mismatches and len(mismatches) / n_pdb > 0.2:
            warnings.append(
                f"1:1 residue map has {len(mismatches)}/{n_pdb} resname mismatches; "
                "check chain order. Examples: " + "; ".join(mismatches[:5])
            )
        elif mismatches:
            warnings.append(
                f"{len(mismatches)} residue-name differences after tautomer/phospho canonicalization"
            )
        return pairs, warnings

    warnings.append(
        f"Residue-count mismatch: PDB protein={n_pdb}, trajectory protein={n_traj}; "
        "using sequence alignment"
    )
    aligned = _needleman_wunsch(
        [resname_one_letter(r["resname"]) for r in pdb_residues],
        [resname_one_letter(r["resname"]) for r in traj_residues],
    )
    pairs = []
    for pdb_i, traj_i in aligned:
        if pdb_i is None or traj_i is None:
            continue
        pairs.append((pdb_residues[pdb_i], traj_residues[traj_i]))
    if not pairs:
        raise ChainSelectionError(
            "Could not align PDB protein residues to trajectory topology residues"
        )
    return pairs, warnings


def build_chain_residue_map(
    pdb_file: str,
    topology_file: str,
) -> Dict[str, Any]:
    """
    Build chain_id → PDB resid → trajectory resindex mapping.

    ``pdb_file`` must contain chain IDs (preprocess protein PDB).
    ``topology_file`` should be ``protein_processed.gro`` or ``md.tpr`` —
    protein residue order matches the production trajectory.
    """
    pdb_path = Path(pdb_file)
    topo_path = Path(topology_file)
    if not pdb_path.is_file():
        raise FileNotFoundError(f"PDB not found: {pdb_file}")
    if not topo_path.is_file():
        raise FileNotFoundError(f"Topology not found: {topology_file}")

    pdb_residues = extract_pdb_chain_residues(str(pdb_path))
    if not pdb_residues:
        raise ChainSelectionError(f"No protein residues found in PDB: {pdb_file}")
    traj_residues = extract_traj_protein_residues(str(topo_path))
    if not traj_residues:
        raise ChainSelectionError(f"No protein residues found in topology: {topology_file}")

    paired, warnings = _pair_residues(pdb_residues, traj_residues)

    chains: Dict[str, Dict[str, List[Any]]] = {}
    chain_order: List[str] = []
    for pdb_res, traj_res in paired:
        cid = pdb_res["chain_id"]
        if cid not in chains:
            chains[cid] = {
                "pdb_resids": [],
                "pdb_resnames": [],
                "traj_resindices": [],
                "traj_resids": [],
            }
            chain_order.append(cid)
        chains[cid]["pdb_resids"].append(int(pdb_res["pdb_resid"]))
        chains[cid]["pdb_resnames"].append(str(pdb_res["resname"]))
        chains[cid]["traj_resindices"].append(int(traj_res["traj_resindex"]))
        chains[cid]["traj_resids"].append(int(traj_res["traj_resid"]))

    payload = {
        "version": CHAIN_MAP_VERSION,
        "source_pdb": str(pdb_path.resolve()),
        "trajectory_topology": str(topo_path.resolve()),
        "n_chains": len(chains),
        "n_mapped_residues": sum(len(c["pdb_resids"]) for c in chains.values()),
        "n_pdb_residues": len(pdb_residues),
        "n_traj_residues": len(traj_residues),
        "chain_order": chain_order,
        "warnings": warnings,
        "chains": chains,
    }
    logger.info(
        "Chain residue map: %d chain(s) %s, %d mapped residues (PDB %d, traj %d)",
        payload["n_chains"],
        chain_order,
        payload["n_mapped_residues"],
        payload["n_pdb_residues"],
        payload["n_traj_residues"],
    )
    for warning in warnings:
        logger.warning("Chain residue map: %s", warning)
    return payload


_CHAIN_ARRAY_KEYS = ("pdb_resids", "pdb_resnames", "traj_resindices", "traj_resids")
_TOP_KEY_ORDER = (
    "version",
    "source_pdb",
    "trajectory_topology",
    "n_chains",
    "n_mapped_residues",
    "n_pdb_residues",
    "n_traj_residues",
    "chain_order",
    "warnings",
)


def _int_field_width(entry: Dict[str, Any]) -> int:
    nums: List[int] = []
    for key in ("pdb_resids", "traj_resindices", "traj_resids"):
        nums.extend(int(x) for x in (entry.get(key) or []))
    if not nums:
        return 1
    return max(len(str(n)) for n in nums)


def _format_int_array(values: Sequence[Any], width: int) -> str:
    return "[" + ", ".join(f"{int(v):{width}d}" for v in values) + "]"


def _format_str_array(values: Sequence[Any]) -> str:
    return "[" + ", ".join(json.dumps(str(v)) for v in values) + "]"


def format_chain_residue_map(payload: Dict[str, Any]) -> str:
    """
    JSON with each residue array on one line, integers padded so columns line up.

    ``pdb_resids``, ``traj_resindices``, and ``traj_resids`` share a field width
    per chain so the i-th residue can be checked down the page.
    """
    indent = "  "
    chain_indent = indent * 2
    field_indent = indent * 3
    key_header_width = max(len(f'"{k}":') for k in _CHAIN_ARRAY_KEYS)

    lines = ["{"]
    top_keys = [k for k in _TOP_KEY_ORDER if k in payload]
    top_keys.extend(k for k in payload if k not in _TOP_KEY_ORDER and k != "chains")
    for key in top_keys:
        lines.append(f"{indent}{json.dumps(key)}: {json.dumps(payload[key], ensure_ascii=False)},")

    chains = payload.get("chains") or {}
    chain_ids = list(payload.get("chain_order") or chains.keys())
    for cid in chains:
        if cid not in chain_ids:
            chain_ids.append(cid)

    lines.append(f'{indent}"chains": {{')
    for i, cid in enumerate(chain_ids):
        entry = chains[cid]
        comma = "," if i < len(chain_ids) - 1 else ""
        lines.append(f"{chain_indent}{json.dumps(str(cid))}: {{")
        width = _int_field_width(entry)
        for j, key in enumerate(_CHAIN_ARRAY_KEYS):
            values = entry.get(key) or []
            header = f'"{key}":'.ljust(key_header_width)
            if key == "pdb_resnames":
                rendered = _format_str_array(values)
            else:
                rendered = _format_int_array(values, width)
            field_comma = "," if j < len(_CHAIN_ARRAY_KEYS) - 1 else ""
            extra = [k for k in entry if k not in _CHAIN_ARRAY_KEYS]
            if extra:
                field_comma = ","
            lines.append(f"{field_indent}{header} {rendered}{field_comma}")
        extras = [k for k in entry if k not in _CHAIN_ARRAY_KEYS]
        for k, extra_key in enumerate(extras):
            extra_comma = "," if k < len(extras) - 1 else ""
            lines.append(
                f"{field_indent}{json.dumps(extra_key)}: "
                f"{json.dumps(entry[extra_key], ensure_ascii=False)}{extra_comma}"
            )
        lines.append(f"{chain_indent}}}{comma}")
    lines.append(f"{indent}}}")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def save_chain_residue_map(payload: Dict[str, Any], output_file: str) -> str:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_chain_residue_map(payload), encoding="utf-8")
    return str(path.resolve())


def load_chain_residue_map(path: str) -> Optional[Dict[str, Any]]:
    map_path = Path(path)
    if not map_path.is_file():
        return None
    try:
        with map_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load chain residue map %s: %s", path, exc)
        return None
    if not isinstance(data, dict) or not data.get("chains"):
        return None
    return data


def build_and_save_chain_residue_map(
    pdb_file: str,
    topology_file: str,
    output_file: str,
) -> Dict[str, Any]:
    """Build the map and write JSON. Returns a result dict (never raises to caller)."""
    try:
        payload = build_chain_residue_map(pdb_file, topology_file)
        saved = save_chain_residue_map(payload, output_file)
        return {
            "success": True,
            "output_file": saved,
            "n_chains": payload["n_chains"],
            "n_mapped_residues": payload["n_mapped_residues"],
            "chain_order": payload["chain_order"],
            "warnings": payload.get("warnings") or [],
        }
    except Exception as exc:
        logger.warning("Failed to build chain residue map: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Discovery / ensure
# ---------------------------------------------------------------------------

_SIM_LEAF_DIRS = frozenset({"analysis", "simsetup", "hpc", "preprocess", "reporter", "programmer"})


def sim_root_from_path(path: Optional[str]) -> Optional[Path]:
    """Return the simulation directory given analysis/simsetup/hpc/working_dir."""
    if not path:
        return None
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    if current.name in _SIM_LEAF_DIRS:
        return current.parent
    return current


def find_chain_residue_map(
    *search_roots: Optional[str],
) -> Optional[str]:
    """Locate an existing ``chain_residue_map.json`` under typical sim folders."""
    seen = set()
    candidates: List[Path] = []
    for root in search_roots:
        if not root:
            continue
        base = Path(root)
        try:
            base = base.resolve()
        except OSError:
            continue
        if base.is_file():
            if base.name == CHAIN_MAP_FILENAME:
                return str(base)
            base = base.parent
        sim = sim_root_from_path(str(base))
        folders = [base]
        if sim is not None:
            folders.append(sim)
            for leaf in ("simsetup", "hpc", "analysis"):
                folders.append(sim / leaf)
        for folder in folders:
            key = str(folder)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(folder / CHAIN_MAP_FILENAME)
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _find_source_pdb(sim_root: Path) -> Optional[str]:
    preprocess = sim_root / "preprocess"
    for name in (
        "protein_h.pdb",
        "protein.pdb",
        "protein_phospho_mapped.pdb",
        "raw.pdb",
    ):
        candidate = preprocess / name
        if candidate.is_file():
            return str(candidate)
    return None


def _find_map_topology(sim_root: Path, topology_file: Optional[str]) -> Optional[str]:
    preferred = [
        sim_root / "simsetup" / "protein_processed.gro",
        sim_root / "simsetup" / "processed.gro",
    ]
    for path in preferred:
        if path.is_file():
            return str(path)
    if topology_file and Path(topology_file).is_file():
        suffix = Path(topology_file).suffix.lower()
        if suffix in {".gro", ".tpr", ".pdb"}:
            return str(Path(topology_file).resolve())
    for name in ("md.tpr", "md.gro", "system.gro"):
        for folder in ("hpc", "simsetup"):
            candidate = sim_root / folder / name
            if candidate.is_file():
                return str(candidate)
    return None


def ensure_chain_residue_map(
    *,
    working_dir: Optional[str] = None,
    topology_file: Optional[str] = None,
    pdb_file: Optional[str] = None,
    map_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load ``chain_residue_map.json``, or rebuild it from the preprocess PDB.

    Returns the map dict, or None when the simulation is single-file / unmapped
    and no PDB+topology pair is available.
    """
    if map_path:
        loaded = load_chain_residue_map(map_path)
        if loaded:
            return loaded

    found = find_chain_residue_map(map_path, working_dir, topology_file)
    if found:
        loaded = load_chain_residue_map(found)
        if loaded:
            return loaded

    sim = sim_root_from_path(working_dir) or sim_root_from_path(topology_file)
    pdb = pdb_file
    if not pdb and sim:
        pdb = _find_source_pdb(sim)
    topo = None
    if sim:
        topo = _find_map_topology(sim, topology_file)
    elif topology_file and Path(topology_file).is_file():
        topo = topology_file
    if not pdb or not topo:
        return None

    out_dir = (sim / "simsetup") if sim else Path(working_dir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / CHAIN_MAP_FILENAME
    result = build_and_save_chain_residue_map(pdb, topo, str(out_path))
    if not result.get("success"):
        return None
    return load_chain_residue_map(result["output_file"])


# ---------------------------------------------------------------------------
# Lookup + selection translation
# ---------------------------------------------------------------------------


def available_chains(chain_map: Optional[Dict[str, Any]]) -> List[str]:
    if not chain_map:
        return []
    order = chain_map.get("chain_order")
    if order:
        return [str(c) for c in order]
    return sorted(str(c) for c in (chain_map.get("chains") or {}))


def _chain_entry(chain_map: Dict[str, Any], chain_id: str) -> Dict[str, List[Any]]:
    chains = chain_map.get("chains") or {}
    key = _norm_chain_id(chain_id)
    if key in chains:
        return chains[key]
    upper = key.upper()
    for cid, entry in chains.items():
        if str(cid).upper() == upper:
            return entry
    available = ", ".join(available_chains(chain_map)) or "(none)"
    raise ChainSelectionError(
        f"Chain '{chain_id}' is not in the residue map. Available chains: {available}"
    )


def lookup_resindices(
    chain_map: Dict[str, Any],
    chain_id: str,
    *,
    resid_start: Optional[int] = None,
    resid_end: Optional[int] = None,
    resids: Optional[Iterable[int]] = None,
) -> List[int]:
    """Return trajectory resindices for a PDB chain, optionally filtered by PDB resid."""
    entry = _chain_entry(chain_map, chain_id)
    pdb_resids = [int(x) for x in entry.get("pdb_resids") or []]
    traj_idx = [int(x) for x in entry.get("traj_resindices") or []]
    if len(pdb_resids) != len(traj_idx):
        raise ChainSelectionError(
            f"Corrupt chain map for chain {chain_id}: resid/resindex length mismatch"
        )

    if resids is not None:
        wanted = {int(r) for r in resids}
    elif resid_start is not None or resid_end is not None:
        lo = int(resid_start if resid_start is not None else resid_end)
        hi = int(resid_end if resid_end is not None else resid_start)
        if lo > hi:
            lo, hi = hi, lo
        wanted = set(range(lo, hi + 1))
    else:
        return list(traj_idx)

    matched = [idx for resid, idx in zip(pdb_resids, traj_idx) if resid in wanted]
    if not matched:
        raise ChainSelectionError(
            f"No mapped residues for chain {chain_id} with PDB resid(s) "
            f"{sorted(wanted)[:12]}{'...' if len(wanted) > 12 else ''}"
        )
    missing = sorted(wanted - set(pdb_resids))
    if missing:
        logger.warning(
            "Chain %s: %d requested PDB resid(s) are not in the map (e.g. %s)",
            chain_id,
            len(missing),
            missing[:8],
        )
    return matched


def format_resindex_selection(indices: Sequence[int]) -> str:
    """Compress 0-based resindices into an MDAnalysis ``resindex`` clause."""
    unique = sorted({int(i) for i in indices})
    if not unique:
        raise ChainSelectionError("No trajectory residue indices to select")
    runs: List[Tuple[int, int]] = []
    start = prev = unique[0]
    for value in unique[1:]:
        if value == prev + 1:
            prev = value
            continue
        runs.append((start, prev))
        start = prev = value
    runs.append((start, prev))
    parts = [str(a) if a == b else f"{a}:{b}" for a, b in runs]
    return "resindex " + " ".join(parts)


def selection_has_chain_token(selection: str) -> bool:
    return bool(selection) and _CHAIN_TOKEN_RE.search(selection) is not None


def _cleanup_selection(text: str) -> str:
    sel = re.sub(r"\s+", " ", text).strip()
    sel = re.sub(r"\(\s*and\s+", "(", sel, flags=re.IGNORECASE)
    sel = re.sub(r"\s+and\s+\)", ")", sel, flags=re.IGNORECASE)
    sel = re.sub(r"^\s*and\s+", "", sel, flags=re.IGNORECASE)
    sel = re.sub(r"\s+and\s+$", "", sel, flags=re.IGNORECASE)
    sel = re.sub(r"\(\s*\)", "", sel)
    sel = re.sub(r"\band\s+and\b", "and", sel, flags=re.IGNORECASE)
    sel = re.sub(r"\s+", " ", sel).strip(" \t")
    return sel.strip()


def _split_top_level_or(selection: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    lower = selection.lower()
    i = 0
    while i < len(selection):
        char = selection[i]
        if char == "(":
            depth += 1
            i += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and lower.startswith(" or ", i):
            parts.append(selection[start:i])
            start = i + 4
            i += 4
            continue
        i += 1
    parts.append(selection[start:])
    return parts


def _parse_resid_filter(clause: str) -> Tuple[Optional[int], Optional[int], Optional[List[int]], str]:
    """Return (start, end, explicit_list, clause_without_resid)."""
    range_match = _RESID_RANGE_RE.search(clause)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        rest = _RESID_RANGE_RE.sub("", clause, count=1)
        return start, end, None, rest
    list_match = _RESID_LIST_RE.search(clause)
    if list_match:
        numbers = [int(x) for x in list_match.group(1).split() if x.strip().isdigit()]
        rest = _RESID_LIST_RE.sub("", clause, count=1)
        if len(numbers) == 1:
            return numbers[0], numbers[0], None, rest
        return None, None, numbers, rest
    return None, None, None, clause


def _translate_flat_clause(clause: str, chain_map: Dict[str, Any]) -> str:
    if _NOT_CHAIN_RE.search(clause):
        return clause
    chain_ids = [_norm_chain_id(m.group(1)) for m in _CHAIN_TOKEN_RE.finditer(clause)]
    resid_start, resid_end, resid_list, without_resid = _parse_resid_filter(clause)

    if not chain_ids:
        n_chains = int(chain_map.get("n_chains") or len(chain_map.get("chains") or {}))
        if n_chains == 1 and (resid_start is not None or resid_list is not None):
            only = available_chains(chain_map)[0]
            indices = lookup_resindices(
                chain_map, only,
                resid_start=resid_start, resid_end=resid_end, resids=resid_list,
            )
            rest = _cleanup_selection(_CHAIN_TOKEN_RE.sub("", without_resid))
            resindex = format_resindex_selection(indices)
            return _cleanup_selection(f"{rest} and {resindex}" if rest else resindex)
        if n_chains > 1 and (resid_start is not None or resid_list is not None):
            logger.warning(
                "Selection %r uses resid without chainID on a %d-chain system; "
                "leaving unchanged (ambiguous)",
                clause.strip(),
                n_chains,
            )
        return clause

    unique_chains = []
    for cid in chain_ids:
        if cid not in unique_chains:
            unique_chains.append(cid)
    if len(unique_chains) > 1:
        raise ChainSelectionError(
            f"Clause contains multiple chain IDs without OR: {unique_chains}. "
            "Use 'chainID A or chainID B', or separate AND groups."
        )

    indices = lookup_resindices(
        chain_map, unique_chains[0],
        resid_start=resid_start, resid_end=resid_end, resids=resid_list,
    )
    rest = _CHAIN_TOKEN_RE.sub("", without_resid)
    rest = _cleanup_selection(rest)
    resindex = format_resindex_selection(indices)
    if not rest:
        return resindex
    return _cleanup_selection(f"{rest} and {resindex}")


def _needs_translation(selection: str, chain_map: Dict[str, Any]) -> bool:
    if not selection or not chain_map:
        return False
    if selection_has_chain_token(selection):
        return True
    n_chains = int(chain_map.get("n_chains") or 0)
    return n_chains == 1 and bool(_RESID_RANGE_RE.search(selection) or _RESID_LIST_RE.search(selection))


def translate_selection(
    selection: str,
    chain_map: Optional[Dict[str, Any]],
) -> str:
    """
    Rewrite PDB-vocabulary selections into trajectory ``resindex`` selections.

    Selections without chain tokens are returned unchanged (except a single-chain
    map, where a bare resid range is still mapped).
    """
    if not selection or not isinstance(selection, str):
        return selection
    if not chain_map or not chain_map.get("chains"):
        if selection_has_chain_token(selection):
            logger.warning(
                "Selection %r uses chainID but no chain_residue_map.json was found; "
                "GROMACS topologies typically match 0 atoms for chainID",
                selection,
            )
        return selection
    if not _needs_translation(selection, chain_map):
        return selection

    rewritten = selection
    changed = True
    while changed:
        changed = False
        for match in re.finditer(r"\(([^()]*)\)", rewritten):
            inner = match.group(1)
            if not _needs_translation(inner, chain_map):
                continue
            new_inner = " or ".join(
                _translate_flat_clause(part, chain_map) for part in _split_top_level_or(inner)
            )
            rewritten = rewritten[: match.start()] + "(" + new_inner + ")" + rewritten[match.end() :]
            changed = True
            break

    parts = [_translate_flat_clause(part, chain_map) for part in _split_top_level_or(rewritten)]
    result = " or ".join(parts)
    cleaned = _cleanup_selection(result)
    if cleaned != selection.strip():
        logger.info("Translated selection %r → %r", selection, cleaned)
    return cleaned


def params_need_chain_map(params: Dict[str, Any]) -> bool:
    """True when any selection-like parameter uses chainID or a resid range."""
    for key in SELECTION_PARAM_KEYS:
        value = params.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        if selection_has_chain_token(value):
            return True
        if _RESID_RANGE_RE.search(value) or _RESID_LIST_RE.search(value):
            return True
    return False


def translate_selection_params(
    params: Dict[str, Any],
    chain_map: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a copy of *params* with selection-like strings translated."""
    out = dict(params)
    for key in SELECTION_PARAM_KEYS:
        value = out.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = translate_selection(value, chain_map)
    return out
