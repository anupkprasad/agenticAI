"""
Orchestrate structure download, domain extraction, and validation.

Used by the preprocessing agent when no local PDB is available but the user
describes a UniProt accession and optional domain/residue range.
"""
import os
from typing import Any, Dict, Optional

from .structure_request_parser import build_output_basename, parse_structure_request
from .structure_downloader import download_structure
from .domain_extractor import extract_domain
from .structure_validator import validate_structure


def acquire_structure_from_request(
    text: str,
    working_dir: str,
    source: str = "auto",
) -> Dict[str, Any]:
    """
    Download and optionally trim a structure based on natural language request.

    Steps:
    1. Parse UniProt / domain / residue range from text
    2. Download full structure (AlphaFold → RCSB fallback)
    3. Extract domain if range specified
    4. Validate resulting structure (gaps, broken loops)

    Returns dict with success, paths, validation, and step log.
    """
    request = parse_structure_request(text)
    if not request:
        return {
            "success": False,
            "error": "No UniProt accession found in request text",
        }

    os.makedirs(working_dir, exist_ok=True)
    uid = request["uniprot_id"]
    basename = build_output_basename(request)
    log = []

    full_pdb = os.path.join(working_dir, f"{uid.lower()}.pdb")
    log.append(f"Step 1: Download structure for {uid} (source={source})")
    dl = download_structure.func(
        uniprot_id=uid,
        output_file=full_pdb,
        source=source,
    )
    if not dl.get("success"):
        return {
            "success": False,
            "error": dl.get("error", "Download failed"),
            "structure_request": request,
            "log": log,
            "download_result": dl,
        }
    log.append(f"  Downloaded via {dl.get('source')} → {full_pdb}")

    current_pdb = full_pdb
    extract_result = None
    if request.get("extract_domain") and request.get("start_resid") and request.get("end_resid"):
        domain_pdb = os.path.join(working_dir, f"{basename}.pdb")
        log.append(
            f"Step 2: Extract domain residues "
            f"{request['start_resid']}-{request['end_resid']}"
        )
        extract_result = extract_domain.func(
            pdb_file=full_pdb,
            start_resid=request["start_resid"],
            end_resid=request["end_resid"],
            output_file=domain_pdb,
            protein_name=request.get("protein_name"),
            domain_name=request.get("domain_label") or "domain",
        )
        if not extract_result.get("success"):
            return {
                "success": False,
                "error": extract_result.get("error", "Domain extraction failed"),
                "structure_request": request,
                "log": log,
                "download_result": dl,
                "extract_result": extract_result,
            }
        current_pdb = domain_pdb
        log.append(f"  Domain PDB → {current_pdb}")

    log.append("Step 3: Validate structure")
    validation = validate_structure.func(pdb_file=current_pdb, check_domain=True)
    log.append(
        f"  Validation: issues={len(validation.get('issues', []))}, "
        f"warnings={len(validation.get('warnings', []))}"
    )

    success = validation.get("success", False)
    return {
        "success": success,
        "structure_request": request,
        "raw_download": full_pdb,
        "pdb_file": current_pdb,
        "output_file": current_pdb,
        "download_result": dl,
        "extract_result": extract_result,
        "validation": validation,
        "log": log,
        "message": f"Acquired structure: {os.path.basename(current_pdb)}",
        "issues": validation.get("issues", []),
        "warnings": validation.get("warnings", []),
    }
