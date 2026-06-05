"""
PDB Structure Validation Tool

Validates PDB integrity including domain-specific checks:
- Missing residues (sequence gaps)
- Broken loops (large CA-CA distances)
"""
import os
from typing import Dict, Any, List, Optional, Tuple

from langchain.tools import tool

# CA-CA distance above this suggests a broken loop or missing segment
BROKEN_LOOP_CA_THRESHOLD = 4.5


def _validate_with_mda(pdb_file: str, check_domain: bool) -> Dict[str, Any]:
    import MDAnalysis as mda
    import numpy as np

    issues: List[str] = []
    warnings: List[str] = []

    u = mda.Universe(pdb_file)
    protein = u.select_atoms("protein")
    if len(protein) == 0:
        issues.append("No protein atoms found in PDB file")
        return {
            "issues": issues,
            "warnings": warnings,
            "atoms": len(u.atoms),
            "heteroatoms": len(u.select_atoms("not protein")),
        }

    ca_atoms = protein.select_atoms("name CA")
    missing_residues: List[str] = []
    broken_loops: List[str] = []

    for chain_id in sorted(set(ca_atoms.chainIDs)):
        chain_ca = ca_atoms.select_atoms(f"chainID {chain_id}")
        if len(chain_ca) == 0:
            continue

        resids = [int(r.resid) for r in chain_ca.residues]
        resids_sorted = sorted(resids)

        # Missing residues within observed range
        if resids_sorted:
            expected = set(range(resids_sorted[0], resids_sorted[-1] + 1))
            missing = sorted(expected - set(resids_sorted))
            if missing:
                gaps = _format_gaps(missing)
                missing_residues.append(f"Chain {chain_id}: gaps at {gaps}")
                if check_domain:
                    issues.append(
                        f"Missing residues in chain {chain_id}: {gaps}"
                    )
                else:
                    warnings.append(
                        f"Missing residues in chain {chain_id}: {gaps}"
                    )

        # Broken loops via consecutive CA distances
        ordered = sorted(chain_ca.residues, key=lambda r: r.resid)
        for i in range(len(ordered) - 1):
            r1, r2 = ordered[i], ordered[i + 1]
            if r2.resid - r1.resid != 1:
                continue  # already flagged as gap
            a1 = r1.atoms.select_atoms("name CA")
            a2 = r2.atoms.select_atoms("name CA")
            if len(a1) == 0 or len(a2) == 0:
                continue
            dist = np.linalg.norm(a1.positions[0] - a2.positions[0])
            if dist > BROKEN_LOOP_CA_THRESHOLD:
                msg = (
                    f"Chain {chain_id} resid {r1.resid}-{r2.resid}: "
                    f"CA-CA distance {dist:.2f} Å"
                )
                broken_loops.append(msg)
                if check_domain:
                    issues.append(f"Broken loop / discontinuity: {msg}")
                else:
                    warnings.append(f"Possible broken loop: {msg}")

    hetatm = u.select_atoms("not protein")
    stats = {
        "total_atoms": len(u.atoms),
        "protein_atoms": len(protein),
        "heteroatoms": len(hetatm),
        "residue_count": len(protein.residues),
        "chains": sorted(set(protein.chainIDs)),
        "missing_residues": missing_residues,
        "broken_loops": broken_loops,
    }

    if len(u.atoms) == 0:
        issues.append("PDB file contains no atoms")

    if hetatm and len(hetatm) > 100 and not check_domain:
        warnings.append(f"Large number of heteroatoms ({len(hetatm)}) detected")

    return {
        "issues": issues,
        "warnings": warnings,
        "statistics": stats,
        "atoms": len(u.atoms),
        "heteroatoms": len(hetatm),
    }


def _format_gaps(resids: List[int]) -> str:
    """Collapse residue IDs into compact ranges."""
    if not resids:
        return ""
    ranges: List[str] = []
    start = prev = resids[0]
    for resid in resids[1:]:
        if resid == prev + 1:
            prev = resid
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = resid
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def _validate_basic(pdb_file: str) -> Dict[str, Any]:
    issues: List[str] = []
    warnings: List[str] = []
    atom_count = 0
    hetatm_count = 0

    with open(pdb_file, "r") as fh:
        for line in fh:
            if line.startswith("ATOM"):
                atom_count += 1
            elif line.startswith("HETATM"):
                hetatm_count += 1

    if atom_count == 0:
        issues.append("No ATOM records found in PDB file")
    if hetatm_count > 100:
        warnings.append(f"Large number of heteroatoms ({hetatm_count}) detected")

    return {
        "issues": issues,
        "warnings": warnings,
        "atoms": atom_count,
        "heteroatoms": hetatm_count,
    }


@tool
def validate_structure(
    pdb_file: str,
    check_domain: bool = False,
) -> Dict[str, Any]:
    """
    Validate PDB file structure and integrity.

    Checks atom records, missing residues (sequence gaps), and broken loops
    (CA-CA distances > 4.5 Å). Set check_domain=True after domain extraction
    to treat gaps and discontinuities as errors rather than warnings.

    Args:
        pdb_file: PDB file path to validate
        check_domain: Stricter validation for extracted domains

    Returns:
        Dict with validation results, issues, warnings, and statistics
    """
    try:
        if not os.path.exists(pdb_file):
            return {
                "success": False,
                "error": f"File not found: {pdb_file}",
            }

        try:
            result = _validate_with_mda(pdb_file, check_domain)
        except ImportError:
            result = _validate_basic(pdb_file)
            result["warnings"].append(
                "MDAnalysis not installed — limited validation only"
            )
        except Exception as exc:
            result = _validate_basic(pdb_file)
            result["warnings"].append(f"Advanced validation failed: {exc}")

        issues = result.get("issues", [])
        warnings = result.get("warnings", [])

        return {
            "success": len(issues) == 0,
            "pdb_file": pdb_file,
            "issues": issues,
            "warnings": warnings,
            "statistics": result.get("statistics", {}),
            "atoms": result.get("atoms", 0),
            "heteroatoms": result.get("heteroatoms", 0),
            "check_domain": check_domain,
            "message": (
                f"Validation complete: {result.get('atoms', 0)} atoms, "
                f"{len(issues)} issues, {len(warnings)} warnings"
            ),
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Validation failed: {e}",
        }
