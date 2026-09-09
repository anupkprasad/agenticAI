"""
Domain extraction tool — trim a PDB to a residue range using Bio.PDB and MDAnalysis.
"""
import os
from typing import Dict, Any, Optional, Tuple

from langchain.tools import tool


def _atom_record_count(pdb_file: str) -> int:
    """Count ATOM/HETATM records without loading a topology library."""
    if not pdb_file or not os.path.isfile(pdb_file):
        return 0
    count = 0
    try:
        with open(pdb_file) as handle:
            for line in handle:
                if line.startswith(("ATOM", "HETATM")):
                    count += 1
    except OSError:
        return 0
    return count


def pdb_protein_residue_span(pdb_file: str) -> Optional[Tuple[int, int, int]]:
    """
    Return (min_resid, max_resid, atom_count) from ATOM records.

    None if the file is missing or has no protein ATOM rows.
    """
    if not pdb_file or not os.path.isfile(pdb_file):
        return None
    resids = []
    atom_count = 0
    try:
        with open(pdb_file) as handle:
            for line in handle:
                if not line.startswith("ATOM"):
                    continue
                atom_count += 1
                try:
                    resids.append(int(line[22:26]))
                except (ValueError, IndexError):
                    continue
    except OSError:
        return None
    if not resids or atom_count == 0:
        return None
    return min(resids), max(resids), atom_count


def classify_domain_extract(
    pdb_file: str,
    start_resid: int,
    end_resid: int,
) -> str:
    """
    Decide whether a residue-range crop should run on this PDB.

    ``already_present``: the file is already the requested domain (local
    numbering matches, or the whole construct sits inside the range).
    ``numbering_mismatch``: UniProt-style range (e.g. 875-1153) is not in a
    locally numbered domain PDB (e.g. 1-273) — do not crop.
    ``extract``: the file is larger than the requested window.
    ``empty_input``: no protein atoms to crop.
    """
    if start_resid > end_resid:
        start_resid, end_resid = end_resid, start_resid
    span = pdb_protein_residue_span(pdb_file)
    if span is None:
        return "empty_input"
    min_res, max_res, _n_atoms = span
    if end_resid < min_res or start_resid > max_res:
        return "numbering_mismatch"
    if min_res >= start_resid and max_res <= end_resid:
        return "already_present"
    return "extract"


def _remove_empty_extract(output_file: str, input_file: str) -> None:
    if not output_file or not os.path.isfile(output_file):
        return
    if os.path.abspath(output_file) == os.path.abspath(input_file):
        return
    if _atom_record_count(output_file) == 0:
        try:
            os.remove(output_file)
        except OSError:
            pass


def _extract_with_biopython(
    pdb_file: str,
    output_file: str,
    start_resid: int,
    end_resid: int,
    chain_id: Optional[str],
) -> Dict[str, Any]:
    from Bio.PDB import PDBIO, PDBParser, Select

    class DomainSelect(Select):
        def __init__(self, start: int, end: int, chain: Optional[str]):
            self.start = start
            self.end = end
            self.chain = chain

        def accept_residue(self, residue):
            if residue.id[0] != " ":
                return 0
            resid = residue.id[1]
            if resid < self.start or resid > self.end:
                return 0
            if self.chain and residue.parent.id != self.chain:
                return 0
            return 1

    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("domain", pdb_file)
    io = PDBIO()
    io.set_structure(structure)
    io.save(output_file, DomainSelect(start_resid, end_resid, chain_id))

    return {
        "method": "biopython",
        "output_file": output_file,
        "residue_range": f"{start_resid}-{end_resid}",
    }


def _extract_with_mda(
    pdb_file: str,
    output_file: str,
    start_resid: int,
    end_resid: int,
    chain_id: Optional[str],
) -> Dict[str, Any]:
    import MDAnalysis as mda

    chain_sel = f"and chainID {chain_id}" if chain_id else ""
    selection = f"protein and resid {start_resid}:{end_resid}{chain_sel}"
    u = mda.Universe(pdb_file)
    atoms = u.select_atoms(selection)
    if len(atoms) == 0:
        raise ValueError(f"No atoms matched selection: {selection}")

    with mda.Writer(output_file, atoms.n_atoms) as writer:
        writer.write(atoms)

    return {
        "method": "mdanalysis",
        "output_file": output_file,
        "residue_range": f"{start_resid}-{end_resid}",
        "atom_count": len(atoms),
        "residue_count": len(atoms.residues),
    }


@tool
def extract_domain(
    pdb_file: str,
    start_resid: int,
    end_resid: int,
    output_file: Optional[str] = None,
    chain_id: Optional[str] = None,
    protein_name: Optional[str] = None,
    domain_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract a protein domain by UniProt/PDB residue numbering.

    Writes a trimmed PDB containing only the requested residue range.
    Uses Bio.PDB when available, with MDAnalysis as fallback.

    Example: extract kinase domain of ERBB3 (P21860) with resid 503-771
    → ERBB3_kinase_domain.pdb

    Args:
        pdb_file: Input full-length or partial PDB
        start_resid: First residue (inclusive)
        end_resid: Last residue (inclusive)
        output_file: Output PDB path (auto-generated if omitted)
        chain_id: Optional chain ID filter
        protein_name: Used for auto naming (e.g. ERBB3)
        domain_name: Used for auto naming (e.g. kinase_domain)

    Returns:
        Dict with success, output_file, statistics, and message
    """
    if not os.path.exists(pdb_file):
        return {"success": False, "error": f"File not found: {pdb_file}"}

    if start_resid > end_resid:
        start_resid, end_resid = end_resid, start_resid

    decision = classify_domain_extract(pdb_file, start_resid, end_resid)
    if decision in ("already_present", "numbering_mismatch"):
        span = pdb_protein_residue_span(pdb_file)
        span_txt = f"{span[0]}-{span[1]}" if span else "unknown"
        reason = (
            f"PDB already covers residues {span_txt}; requested "
            f"{start_resid}-{end_resid} needs no crop"
            if decision == "already_present"
            else (
                f"Requested residues {start_resid}-{end_resid} are not in this PDB "
                f"(span {span_txt}). Keeping the local file; it is already a "
                "domain-sized construct with different numbering."
            )
        )
        return {
            "success": True,
            "skipped": True,
            "skip_reason": decision,
            "output_file": pdb_file,
            "pdb_file": pdb_file,
            "start_resid": start_resid,
            "end_resid": end_resid,
            "statistics": {
                "atom_count": span[2] if span else 0,
                "residue_range": span_txt,
            },
            "message": reason,
        }
    if decision == "empty_input":
        return {
            "success": False,
            "error": f"No protein ATOM records in {pdb_file}",
        }

    if not output_file:
        base = protein_name or os.path.splitext(os.path.basename(pdb_file))[0]
        suffix = domain_name or "domain"
        output_file = f"{base}_{suffix}.pdb"

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    details = None
    errors = []

    try:
        details = _extract_with_biopython(
            pdb_file, output_file, start_resid, end_resid, chain_id
        )
        if _atom_record_count(output_file) == 0:
            errors.append("Bio.PDB wrote no ATOM records for the requested range")
            _remove_empty_extract(output_file, pdb_file)
            details = None
    except ImportError:
        errors.append("Bio.PDB not available (install biopython)")
    except Exception as exc:
        errors.append(f"Bio.PDB extraction failed: {exc}")

    if details is None:
        try:
            details = _extract_with_mda(
                pdb_file, output_file, start_resid, end_resid, chain_id
            )
        except ImportError:
            return {
                "success": False,
                "error": "Neither biopython nor MDAnalysis is installed",
                "details": errors,
            }
        except Exception as exc:
            _remove_empty_extract(output_file, pdb_file)
            return {
                "success": False,
                "error": f"Domain extraction failed: {exc}",
                "details": errors,
            }

    if _atom_record_count(output_file) == 0:
        _remove_empty_extract(output_file, pdb_file)
        return {
            "success": False,
            "error": (
                f"Domain extract of residues {start_resid}-{end_resid} produced "
                f"an empty PDB from {os.path.basename(pdb_file)}"
            ),
            "details": errors,
        }

    # Gather quick stats with MDAnalysis when possible
    stats = {}
    try:
        import MDAnalysis as mda

        u = mda.Universe(output_file)
        stats = {
            "atom_count": len(u.atoms),
            "residue_count": len(u.residues),
            "residue_range": f"{u.residues[0].resid}-{u.residues[-1].resid}"
            if len(u.residues) else "empty",
        }
    except Exception:
        stats = {"atom_count": _atom_record_count(output_file)}

    return {
        "success": True,
        "output_file": output_file,
        "pdb_file": output_file,
        "start_resid": start_resid,
        "end_resid": end_resid,
        "statistics": stats,
        "extraction": details,
        "message": (
            f"Extracted domain residues {start_resid}-{end_resid} "
            f"to {os.path.basename(output_file)}"
        ),
    }
