"""HTML report generation functionality"""
import os
import logging
import base64
import re
from typing import Dict, Any, List, Optional, Set, Tuple, Union
from pathlib import Path
from datetime import datetime
from langchain.tools import tool

logger = logging.getLogger(__name__)


def _figure_caption_label(analysis_type: str, img_type: str, img_path: str) -> str:
    """Human caption for a plot (without the figN. prefix)."""
    stem = Path(str(img_path)).stem.replace("_", " ").strip()
    atype = (analysis_type or "").replace("_", " ").strip()
    key = (img_type or "").replace("_", " ").strip()
    low = f"{stem} {key} {atype}".lower()
    if "rmsd" in low and "rmsf" not in low:
        return "RMSD"
    if "rmsf" in low:
        return "RMSF"
    if "gyration" in low or re.search(r"\brg\b", low) or "radius of gyration" in low:
        return "Radius of Gyration"
    if "combined metrics" in low or "multipanel" in low:
        return "Combined Metrics"
    if "sasa" in low:
        return "SASA"
    if "pca" in low:
        return "PCA"
    if "fel" in low or "free energy" in low:
        return "Free Energy Landscape"
    if atype and atype.lower() not in {"unknown", "plot"}:
        return atype
    if stem and stem.lower() not in {"plot", "figure", "image"}:
        return stem.title()
    if key and key.lower() not in {"plot", "figure", "image"}:
        return key.title()
    return "Analysis Plot"


def _format_figure_label(n: int, caption: str) -> str:
    """Canonical in-report figure label: ``fig1. RMSD``."""
    return f"fig{int(n)}. {caption}"


def _sanitize_figure_table_citations(
    text: str,
    figure_numbers: Set[int],
    table_numbers: Set[int],
) -> str:
    """Drop in-text Figure/fig/Table citations that do not correspond to report labels."""
    if not text:
        return text

    def _fig_repl(m: re.Match) -> str:
        # Supplementary-style "Figure S1" / "fig S1" is never emitted by this generator
        if m.group(1):
            return ""
        num = int(m.group(2))
        return m.group(0) if num in figure_numbers else ""

    def _tab_repl(m: re.Match) -> str:
        # "Table S1" etc. — we only label main-text Table N
        if m.group(1):
            return ""
        num = int(m.group(2))
        return m.group(0) if num in table_numbers else ""

    # Figure 1 / fig1. / Fig 1 (nbsp / narrow nbsp); optional S for supplementary-style cites
    _ws = r"[\u00a0\u202f\u2009\s]*"
    out = re.sub(
        rf"\(?{_ws}(?:Figures?|figs?\.?){_ws}([Ss]?)(\d+)\.?{_ws}\)?",
        _fig_repl,
        text,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        rf"\(?{_ws}Tables?{_ws}([Ss]?)(\d+){_ws}\)?",
        _tab_repl,
        out,
        flags=re.IGNORECASE,
    )
    # Clean leftover empty parens / double spaces from stripped citations
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([.,;:])", r"\1", out)
    return out


def _parse_gro_system_counts(gro_path: Path) -> Dict[str, Any]:
    """Extract atom / residue / component counts from a GROMACS .gro file."""
    try:
        lines = gro_path.read_text(errors="ignore").splitlines()
        if len(lines) < 3:
            return {}
        n_atoms = int(lines[1].strip())
        atom_lines = lines[2 : 2 + n_atoms]
        protein_atoms = 0
        water_atoms = 0
        ion_atoms = 0
        ligand_atoms = 0
        protein_res: Set[Tuple[str, str]] = set()
        water_res: Set[Tuple[str, str]] = set()
        ion_types: Dict[str, int] = {}
        ligand_names: Set[str] = set()
        _WATER = {"SOL", "HOH", "WAT", "TIP3", "TIP3P", "TIP4", "OPC", "SPC"}
        _IONS = {"NA", "CL", "K", "MG", "CA", "ZN", "NA+", "CL-", "MG2", "CA2"}
        _AA = {
            "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
            "HIS", "HIE", "HID", "HIP", "ILE", "LEU", "LYS", "MET",
            "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
        }
        _LIGAND = {"ATP", "ADP", "GTP", "GDP", "NAD", "HEM", "LIG", "ANP"}
        for ln in atom_lines:
            if len(ln) < 20:
                continue
            resid = ln[0:5].strip()
            resname = ln[5:10].strip().upper()
            key = (resid, resname)
            if resname in _WATER:
                water_atoms += 1
                water_res.add(key)
            elif resname in _IONS:
                ion_atoms += 1
                ion_types[resname] = ion_types.get(resname, 0) + 1
            elif resname in _LIGAND or (len(resname) <= 3 and resname not in _AA):
                ligand_atoms += 1
                ligand_names.add(resname)
            else:
                protein_atoms += 1
                protein_res.add(key)
        components: Dict[str, Any] = {
            "protein": {
                "present": protein_atoms > 0,
                "atom_count": protein_atoms,
                "residue_count": len(protein_res),
            },
            "water": {
                "present": water_atoms > 0,
                "atom_count": water_atoms,
                "residue_count": len(water_res),
            },
            "ions": {
                "present": ion_atoms > 0,
                "atom_count": ion_atoms,
                "types": ion_types,
            },
            "ligand": {
                "present": ligand_atoms > 0,
                "atom_count": ligand_atoms,
                "residue_names": sorted(ligand_names),
            },
        }
        return {
            "total_atoms": n_atoms,
            "total_residues": len(protein_res),
            "components": components,
            "summary": (
                f"{n_atoms:,} atoms · {len(protein_res):,} protein residues"
                + (f" · {len(water_res):,} waters" if water_res else "")
            ),
        }
    except Exception as exc:
        logger.debug("GRO system parse failed for %s: %s", gro_path, exc)
        return {}


def enrich_system_info_for_report(
    system_info: Optional[Dict[str, Any]],
    analysis_data: Optional[Dict[str, Any]] = None,
    analysis_dir: Optional[str] = None,
    protein_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fill missing system_info fields from analysis stats and nearby .gro files."""
    info: Dict[str, Any] = dict(system_info) if isinstance(system_info, dict) else {}
    entries = []
    if isinstance(analysis_data, dict):
        entries = list(analysis_data.get("entries") or [])

    # Analysis-derived trajectory / residue counts
    traj: Dict[str, Any] = dict(info.get("trajectory") or {}) if isinstance(info.get("trajectory"), dict) else {}
    for entry in entries:
        atype = str(entry.get("analysis_type") or "")
        stats = entry.get("statistics") or {}
        if not isinstance(stats, dict):
            continue
        if atype == "RMSD" and stats.get("n_frames") and not traj.get("n_frames"):
            traj["n_frames"] = stats["n_frames"]
        if atype == "RMSF" and stats.get("n_residues"):
            if not info.get("total_residues"):
                info["total_residues"] = stats["n_residues"]
        if atype == "PDB_Input_Validation":
            for key in ("total_atoms", "total_residues"):
                val = stats.get(key)
                if val not in (None, "", 0) and not info.get(key):
                    info[key] = val
            meta = entry.get("metadata") or {}
            if isinstance(meta, dict):
                summary = meta.get("human_readable_summary")
                if summary and summary != "N/A" and not info.get("summary"):
                    info["summary"] = summary

    if traj:
        info["trajectory"] = traj

    # Prefer production / analysis GRO over empty validation zeros
    search_roots: List[Path] = []
    if analysis_dir:
        ad = Path(analysis_dir)
        search_roots.extend([ad, ad.parent, ad.parent / "hpc", ad.parent / "simsetup"])
    for root in search_roots:
        if not root.is_dir():
            continue
        for name in ("md.gro", "complex.gro", "boxed.gro", "system.gro"):
            cand = root / name
            if cand.is_file():
                parsed = _parse_gro_system_counts(cand)
                if parsed.get("total_atoms"):
                    for k, v in parsed.items():
                        if k == "components":
                            if not info.get("components"):
                                info["components"] = v
                        elif k == "summary":
                            if not info.get("summary") or info.get("summary") == "N/A":
                                info["summary"] = v
                        elif not info.get(k) or info.get(k) in (0, "0", "N/A"):
                            info[k] = v
                    info.setdefault("_source_gro", str(cand))
                    break
        if info.get("_source_gro"):
            break

    if protein_name and not info.get("protein_name"):
        info["protein_name"] = protein_name

    # Only mark success when we have something useful to show
    has_counts = any(
        info.get(k) not in (None, "", 0, "0", "N/A")
        for k in ("total_atoms", "total_residues")
    )
    has_traj = isinstance(info.get("trajectory"), dict) and bool(info.get("trajectory"))
    has_comps = isinstance(info.get("components"), dict) and bool(info.get("components"))
    if has_counts or has_traj or has_comps or info.get("summary"):
        info["success"] = True
        return info
    if info.get("success"):
        return info
    return system_info if system_info else None


@tool
def generate_html_report(
    analysis_data: Dict[str, Any],
    literature_refs: Optional[List[Dict[str, Any]]] = None,
    report_type: str = "comprehensive",
    output_file: str = "report.html",
    working_dir: Optional[str] = None,
    system_info: Optional[Dict[str, Any]] = None,
    final_impression: Optional[str] = None,
    pdb_data: Optional[Any] = None,
    enriched_prompt: Optional[str] = None,
    literature_review: Optional[str] = None,
    protein_name: Optional[str] = None,
    sim_label: Optional[str] = None,
    analysis_dir: Optional[str] = None,
    user_goal: Optional[str] = None,
    report_focus: Optional[str] = None,
    max_figures_per_section: Optional[int] = None,
    include_visualizations: bool = True,
) -> Dict[str, Any]:
    """
    Generate HTML report from analysis data and literature.
    
    Creates a professional scientific report with analysis results,
    visualizations, literature context, and final impressions.
    
    Args:
        analysis_data: Parsed analysis summary data
        literature_refs: List of literature references (optional)
        report_type: Type of report ("comprehensive" or "executive")
        output_file: Output HTML filename (saved in working_dir)
        working_dir: Working directory for output
        system_info: Molecular system metadata from input validation (optional)
        final_impression: LLM-generated final impression correlating analysis with literature (optional)
        pdb_data: PDB data — either a single PDB string or Dict[str, str] mapping labels to PDB text (optional)
        enriched_prompt: Supervisor-rephrased user task description (optional)
    
    Returns:
        Dict with report generation results
    """
    if working_dir is None:
        working_dir = os.getcwd()
    
    output_path = Path(working_dir) / output_file
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Auto-extract PDB(s) for 3D viewer if not provided
    pdb_frames: Dict[str, str] = {}
    if isinstance(pdb_data, dict):
        # Caller passed a dict of label → PDB text (multi-timepoint)
        pdb_frames = pdb_data
    elif isinstance(pdb_data, str):
        # Caller passed a single PDB string — wrap as single-frame dict
        pdb_frames = {"0 ns": pdb_data}
    else:
        pdb_frames = _auto_extract_pdbs(working_dir)

    system_info = enrich_system_info_for_report(
        system_info,
        analysis_data=analysis_data if isinstance(analysis_data, dict) else None,
        analysis_dir=analysis_dir,
        protein_name=protein_name,
    )
    
    try:
        # Build HTML content
        html_content = build_html_content(
            analysis_data=analysis_data,
            literature_refs=literature_refs or [],
            report_type=report_type,
            system_info=system_info,
            final_impression=final_impression,
            pdb_data=pdb_frames,
            enriched_prompt=enriched_prompt,
            literature_review=literature_review,
            protein_name=protein_name,
            sim_label=sim_label,
            analysis_dir=analysis_dir,
            user_goal=user_goal,
            report_focus=report_focus,
            max_figures_per_section=max_figures_per_section,
            include_visualizations=include_visualizations,
        )
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Generated HTML report: {output_path}")
        
        return {
            "success": True,
            "report_file": str(output_path),
            "report_type": report_type,
            "file_size_kb": output_path.stat().st_size / 1024
        }
        
    except Exception as e:
        logger.error(f"Error generating HTML report: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def _auto_extract_pdbs(working_dir: str) -> Dict[str, str]:
    """Extract PDB frames at multiple time points for the 3D viewer.

    Returns a dict mapping ``"<time> ns"`` labels to PDB text.
    Falls back to a single first-frame if multi-frame extraction fails.
    """
    try:
        from src.reporter.structure_extractor import (
            extract_multi_frame_pdb,
            extract_first_frame_pdb,
            read_pdb_data,
        )
    except ImportError:
        logger.debug("structure_extractor not available; skipping PDB auto-extract")
        return {}

    wd = Path(working_dir).resolve()
    base_dir = wd.parent if wd.name == "reporter" else wd

    # Try multi-frame extraction first
    try:
        frames = extract_multi_frame_pdb(str(base_dir))
        if frames:
            logger.info("Auto-extracted %d PDB frames for 3D viewer", len(frames))
            return frames
    except Exception as exc:
        logger.warning("Multi-frame PDB extraction failed: %s", exc)

    # Fall back to single frame
    existing = base_dir / "reporter" / "system_frame0.pdb"
    if existing.is_file():
        txt = read_pdb_data(str(existing))
        if txt:
            return {"0 ns": txt}

    try:
        pdb_path = extract_first_frame_pdb(str(base_dir))
        if pdb_path:
            txt = read_pdb_data(pdb_path)
            if txt:
                return {"0 ns": txt}
    except Exception as exc:
        logger.warning("PDB auto-extraction failed: %s", exc)

    return {}


def build_html_content(
    analysis_data: Dict[str, Any],
    literature_refs: List[Dict[str, Any]],
    report_type: str,
    system_info: Optional[Dict[str, Any]] = None,
    final_impression: Optional[str] = None,
    pdb_data: Optional[Union[str, Dict[str, str]]] = None,
    enriched_prompt: Optional[str] = None,
    literature_review: Optional[str] = None,
    protein_name: Optional[str] = None,
    sim_label: Optional[str] = None,
    analysis_dir: Optional[str] = None,
    user_goal: Optional[str] = None,
    report_focus: Optional[str] = None,
    max_figures_per_section: Optional[int] = None,
    include_visualizations: bool = True,
) -> str:
    """Build HTML content for report (not a @tool, internal helper)"""

    from src.reporter.figure_selector import (
        ReportFigurePolicy,
        select_analysis_entries,
        select_images_from_entry,
    )

    policy = ReportFigurePolicy(
        max_figures_per_section=max_figures_per_section or 5,
        include_visualizations=include_visualizations,
    )

    # Normalise pdb_data to dict
    pdb_frames: Dict[str, str] = {}
    if isinstance(pdb_data, str):
        pdb_frames = {"0 ns": pdb_data}
    elif isinstance(pdb_data, dict):
        pdb_frames = pdb_data
    
    # Extract data — keep latest entry per analysis_type (re-runs append duplicates)
    raw_entries = analysis_data.get("entries", [])
    seen_types: Dict[str, Dict[str, Any]] = {}
    for entry in raw_entries:
        atype = entry.get("analysis_type", "Unknown")
        seen_types[atype] = entry
    entries = select_analysis_entries(
        list(seen_types.values()),
        user_goal=user_goal or "",
        report_focus=report_focus or "",
        enriched_prompt=enriched_prompt or "",
        policy=policy,
    )
    if not entries:
        entries = list(seen_types.values())[: policy.max_total_per_sim_figures]
    analysis_types = analysis_data.get("analysis_types", {})
    
    # Resolve asset search directories for plots and data files
    search_dirs: List[Path] = []
    if analysis_dir:
        search_dirs.append(Path(analysis_dir))
    for entry in entries:
        for fval in (entry.get("files") or {}).values():
            if isinstance(fval, str) and Path(fval).is_file():
                search_dirs.append(Path(fval).parent)
    if analysis_dir:
        parent = Path(analysis_dir).parent
        search_dirs.extend([parent / "analysis", parent])
    # dedupe while preserving order
    seen_dir: set = set()
    unique_dirs: List[Path] = []
    for d in search_dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key not in seen_dir:
            seen_dir.add(key)
            unique_dirs.append(d)
    search_dirs = unique_dirs
    
    # Normalize analysis_types to handle both dict and list formats
    if isinstance(analysis_types, list):
        # Convert list to dict with counts
        analysis_types = {atype: 1 for atype in analysis_types}
    elif not isinstance(analysis_types, dict):
        analysis_types = {}
    
    # Build HTML
    html_parts = []
    
    # Precompute title so <title> and <h1> stay consistent
    _title_parts = []
    if protein_name:
        _title_parts.append(protein_name)
    if sim_label and sim_label.lower() != (protein_name or "").lower():
        _title_parts.append(f"({sim_label})")
    _report_title = " — ".join(_title_parts) if _title_parts else "Molecular Dynamics"

    # HTML header (not an f-string — CSS uses curly braces)
    import html as _html_esc
    _safe_title = _html_esc.escape(_report_title)
    html_parts.append("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__REPORT_TITLE__ MD Report</title>
    <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
    <style>
        body {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            line-height: 1.7;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            font-size: 16px;
            background: linear-gradient(135deg, #f5f7fa 0%, #e3e6eb 100%);
        }
        .container {
            background-color: white;
            padding: 40px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            border-radius: 12px;
        }
        h1 {
            color: #1e3a8a;
            border-bottom: 4px solid #3b82f6;
            padding-bottom: 15px;
            margin-bottom: 30px;
            font-size: 32px;
        }
        h2 {
            color: #1e40af;
            margin-top: 40px;
            border-bottom: 2px solid #93c5fd;
            padding-bottom: 10px;
            font-size: 24px;
        }
        h3 {
            color: #1e40af;
            font-size: 20px;
            margin-top: 20px;
        }
        .metadata {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #3b82f6;
        }
        .metadata p {
            margin: 8px 0;
            font-size: 15px;
        }
        .system-info {
            margin: 30px 0;
            padding: 25px;
            border-radius: 10px;
            background-color: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-left: 4px solid #22c55e;
        }
        .system-info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .system-info-card {
            background: white;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #d1fae5;
            text-align: center;
        }
        .system-info-card .info-label {
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .system-info-card .info-value {
            font-size: 22px;
            font-weight: bold;
            color: #166534;
            margin: 5px 0;
        }
        .component-table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        .component-table th, .component-table td {
            padding: 10px 15px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        .component-table th {
            background-color: #f0fdf4;
            color: #166534;
            font-weight: 600;
            font-size: 13px;
            text-transform: uppercase;
        }
        .component-table td {
            color: #374151;
        }
        .analysis-section {
            margin: 40px 0;
            padding: 30px;
            border-radius: 10px;
            background-color: #f9fafb;
            border: 1px solid #e5e7eb;
        }
        .image-container {
            text-align: center;
            margin: 30px 0;
            padding: 20px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .analysis-image {
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }
        .image-caption {
            font-size: 14px;
            color: #6b7280;
            margin-top: 10px;
            font-style: italic;
        }
        .key-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
            margin: 25px 0;
        }
        .key-stats .tile-observations-row {
            grid-column: 1 / -1;
        }
        .info-tile {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            padding: 22px 24px;
            border-radius: 10px;
            border: 2px solid #e5e7eb;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .info-tile:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(59, 130, 246, 0.2);
        }
        .info-tile.tile-stats { border-left: 5px solid #3b82f6; }
        .info-tile.tile-files { border-left: 5px solid #10b981; }
        .info-tile.tile-meta  { border-left: 5px solid #8b5cf6; }
        .tile-header {
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 14px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e5e7eb;
        }
        .tile-stats .tile-header { color: #2563eb; }
        .tile-files .tile-header { color: #059669; }
        .tile-meta  .tile-header { color: #7c3aed; }
        .tile-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            padding: 4px 0;
            font-size: 14px;
            line-height: 1.6;
        }
        .tile-row:not(:last-child) {
            border-bottom: 1px dashed #f0f0f0;
        }
        .tile-key {
            color: #6b7280;
            font-weight: 600;
            margin-right: 12px;
            white-space: nowrap;
        }
        .tile-val {
            color: #1f2937;
            font-weight: 500;
            text-align: right;
            word-break: break-all;
        }
        .tile-val.highlight {
            color: #2563eb;
            font-weight: 700;
            font-size: 15px;
        }
        .timestamp {
            color: #9ca3af;
            font-size: 14px;
            margin: 10px 0;
        }
        .reference {
            margin: 18px 0;
            padding: 18px 20px;
            background-color: #f9fafb;
            border-left: 4px solid #6b7280;
            border-radius: 6px;
        }
        .literature-review {
            background: #f0fdf4;
            border-left: 4px solid #22c55e;
            padding: 18px 22px;
            border-radius: 8px;
            margin: 12px 0 20px;
            line-height: 1.75;
        }
        .literature-review sup { color: #15803d; font-weight: 700; }
        .reference-abstract {
            font-size: 0.9em;
            color: #4b5563;
            margin-top: 6px;
            line-height: 1.5;
            font-style: italic;
        }
        .reference-title {
            font-weight: 700;
            color: #1f2937;
            font-size: 16px;
            margin-bottom: 6px;
        }
        .reference-title a {
            color: #1e40af;
            text-decoration: none;
        }
        .reference-title a:hover {
            text-decoration: underline;
        }
        .reference-meta {
            font-size: 14px;
            color: #4b5563;
            margin: 4px 0;
        }
        .reference-meta .journal {
            font-style: italic;
        }
        .reference-doi {
            font-size: 13px;
            color: #6b7280;
            margin-top: 4px;
        }
        .reference-doi a {
            color: #2563eb;
        }
        .reference-authors {
            color: #4b5563;
            font-size: 14px;
        }
        .section-divider {
            height: 2px;
            background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
            margin: 40px 0;
        }
        .files-list {
            background-color: #f3f4f6;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
        }
        .files-list ul {
            margin: 10px 0;
            padding-left: 20px;
        }
        .files-list li {
            margin: 5px 0;
            color: #4b5563;
        }
        .final-impression {
            margin: 40px 0;
            padding: 30px;
            border-radius: 10px;
            background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
            border: 1px solid #fde68a;
            border-left: 4px solid #f59e0b;
        }
        .final-impression p {
            margin: 12px 0;
            line-height: 1.85;
            font-size: 17px;
        }
        .final-impression strong {
            color: #92400e;
        }
        .final-impression .ref-citations {
            font-size: 14px;
            color: #92400e;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #fde68a;
        }
        .final-impression .ref-citations p {
            font-size: 14px;
            line-height: 1.6;
        }
        /* 3D Structure Viewer */
        .viewer-section {
            margin: 30px 0;
            padding: 25px;
            border-radius: 10px;
            background-color: #f0f4ff;
            border: 1px solid #c7d2fe;
            border-left: 4px solid #6366f1;
        }
        .viewer-container {
            position: relative;
            width: 100%;
            height: 550px;
            border-radius: 8px;
            overflow: hidden;
            background: #1a1a2e;
            box-shadow: 0 2px 12px rgba(0,0,0,0.15);
        }
        .viewer-controls {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 15px 0;
            align-items: center;
        }
        .viewer-controls label {
            font-size: 13px;
            font-weight: 600;
            color: #4338ca;
            margin-right: 4px;
        }
        .viewer-controls select, .viewer-controls button {
            padding: 6px 14px;
            border: 1px solid #c7d2fe;
            border-radius: 6px;
            background: white;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .viewer-controls button {
            background: #6366f1;
            color: white;
            border: none;
            font-weight: 600;
        }
        .viewer-controls button:hover { background: #4f46e5; }
        .viewer-controls select:focus { outline: 2px solid #6366f1; }
        /* Task Description */
        .task-description {
            margin: 25px 0;
            padding: 20px 25px;
            border-radius: 10px;
            background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
            border: 1px solid #c4b5fd;
            border-left: 4px solid #7c3aed;
        }
        .task-description h3 {
            margin: 0 0 10px 0;
            color: #5b21b6;
            font-size: 16px;
        }
        .task-description p {
            margin: 0;
            color: #4c1d95;
            font-size: 15px;
            line-height: 1.7;
        }
    </style>
</head>
<body>
    <div class="container">
""".replace("__REPORT_TITLE__", _safe_title))
    
    # Title and metadata — story arc: Question → System → Results → Interpretation
    report_title = _report_title
    html_parts.append(f"<h1>🧬 {report_title} MD Report</h1>")
    html_parts.append(f'<div class="metadata">')
    if protein_name:
        html_parts.append(f'<p><strong>🧫 Protein:</strong> {protein_name}</p>')
    if sim_label:
        html_parts.append(f'<p><strong>🏷️ Simulation:</strong> {sim_label}</p>')
    html_parts.append(f'<p><strong>📊 Report Type:</strong> {report_type.title()}</p>')
    html_parts.append(f'<p><strong>📅 Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>')
    html_parts.append(f'<p><strong>🔬 Analyses in Report:</strong> {len(entries)} '
                      f'(of {len(seen_types)} available)</p>')
    html_parts.append(
        f'<p><strong>📈 Selected analyses:</strong> '
        f'{", ".join(e.get("analysis_type", "?") for e in entries)}</p>'
    )
    html_parts.append('</div>')
    
    # Task Description = research question
    if enriched_prompt or user_goal:
        import html as html_mod
        html_parts.append('<div class="task-description">')
        html_parts.append('<h2>1. Research Question</h2>')
        html_parts.append(
            f'<p>{html_mod.escape(enriched_prompt or user_goal or "")}</p>'
        )
        html_parts.append('</div>')
    
    # Section 2: System Information (from input validation)
    if system_info and system_info.get("success"):
        html_parts.append("<h2>2. System Information</h2>")
        html_parts.append('<div class="system-info">')
        
        # Summary line
        summary = system_info.get("summary", "")
        if summary:
            html_parts.append(f'<p><strong>{summary}</strong></p>')
        
        # Key metrics grid
        def _fmt_int(val: Any, default: str = "N/A") -> str:
            try:
                if val is None or val == "":
                    return default
                return f"{int(val):,}"
            except (TypeError, ValueError):
                return str(val) if val not in (None, "") else default

        html_parts.append('<div class="system-info-grid">')
        atoms_s = _fmt_int(system_info.get("total_atoms"), "")
        residues_s = _fmt_int(system_info.get("total_residues"), "")
        if atoms_s:
            html_parts.append(f'''
            <div class="system-info-card">
                <div class="info-label">Total Atoms</div>
                <div class="info-value">{atoms_s}</div>
            </div>
        ''')
        if residues_s:
            html_parts.append(f'''
            <div class="system-info-card">
                <div class="info-label">Total Residues</div>
                <div class="info-value">{residues_s}</div>
            </div>
        ''')
        
        # Trajectory info if available
        traj_info = system_info.get("trajectory", {})
        if isinstance(traj_info, dict) and traj_info:
            if traj_info.get("n_frames"):
                html_parts.append(f'''
                    <div class="system-info-card">
                        <div class="info-label">Frames</div>
                        <div class="info-value">{_fmt_int(traj_info.get("n_frames"))}</div>
                    </div>
                ''')
            if traj_info.get("total_time_ns"):
                html_parts.append(f'''
                    <div class="system-info-card">
                        <div class="info-label">Simulation Time</div>
                        <div class="info-value">{traj_info["total_time_ns"]} ns</div>
                    </div>
                ''')
            if traj_info.get("dt_ps"):
                html_parts.append(f'''
                    <div class="system-info-card">
                        <div class="info-label">Timestep</div>
                        <div class="info-value">{traj_info["dt_ps"]} ps</div>
                    </div>
                ''')
        
        html_parts.append('</div>')  # close system-info-grid
        
        # Components table
        components = system_info.get("components", {})
        if components:
            html_parts.append('<h3>System Components</h3>')
            html_parts.append('<table class="component-table">')
            html_parts.append('<thead><tr><th>Component</th><th>Present</th><th>Atoms</th><th>Details</th></tr></thead>')
            html_parts.append('<tbody>')
            
            # Protein
            prot = components.get("protein", {}) if isinstance(components.get("protein"), dict) else {}
            if prot.get("present"):
                chains = ", ".join(prot.get("chains", [])) if prot.get("chains") else "—"
                html_parts.append(
                    f'<tr><td>🧬 Protein</td><td>Yes</td><td>{_fmt_int(prot.get("atom_count"), "0")}</td>'
                    f'<td>{_fmt_int(prot.get("residue_count"), "0")} residues, Chains: {chains}</td></tr>'
                )
            else:
                html_parts.append('<tr><td>🧬 Protein</td><td>No</td><td>—</td><td>—</td></tr>')
            
            # Water
            wat = components.get("water", {}) if isinstance(components.get("water"), dict) else {}
            if wat.get("present"):
                html_parts.append(
                    f'<tr><td>💧 Water</td><td>Yes</td><td>{_fmt_int(wat.get("atom_count"), "0")}</td>'
                    f'<td>{_fmt_int(wat.get("residue_count"), "0")} molecules</td></tr>'
                )
            else:
                html_parts.append('<tr><td>💧 Water</td><td>No</td><td>—</td><td>—</td></tr>')
            
            # Ions
            ion = components.get("ions", {}) if isinstance(components.get("ions"), dict) else {}
            if ion.get("present"):
                ion_types = ion.get("types", {}) if isinstance(ion.get("types"), dict) else {}
                ion_detail = ", ".join(f"{k}: {v}" for k, v in ion_types.items())
                html_parts.append(
                    f'<tr><td>⚡ Ions</td><td>Yes</td><td>{_fmt_int(ion.get("atom_count"), "0")}</td>'
                    f'<td>{ion_detail}</td></tr>'
                )
            else:
                html_parts.append('<tr><td>⚡ Ions</td><td>No</td><td>—</td><td>—</td></tr>')
            
            # Ligand
            lig = components.get("ligand", {}) if isinstance(components.get("ligand"), dict) else {}
            if lig.get("present"):
                lig_names = ", ".join(lig.get("residue_names", []) or [])
                html_parts.append(
                    f'<tr><td>💊 Ligand</td><td>Yes</td><td>{_fmt_int(lig.get("atom_count"), "0")}</td>'
                    f'<td>{lig_names}</td></tr>'
                )
            else:
                html_parts.append('<tr><td>💊 Ligand</td><td>No</td><td>—</td><td>—</td></tr>')
            
            html_parts.append('</tbody></table>')
        
        html_parts.append('</div>')  # close system-info
        html_parts.append('<div class="section-divider"></div>')
    
    # 3D Structure Viewer section (powered by 3Dmol.js)
    if pdb_frames:
        html_parts.append(_build_3d_viewer_section(pdb_frames))
        html_parts.append('<div class="section-divider"></div>')
    
    # Analysis sections — key figures + stats
    html_parts.append("<h2>3. Key Results</h2>")
    figure_counter = 0
    table_counter = 0
    figure_numbers: Set[int] = set()
    table_numbers: Set[int] = set()
    figure_catalog: List[str] = []  # e.g. "fig1. RMSD"
    
    for entry in entries:
        atype = entry.get("analysis_type", "Unknown")
        stats = entry.get("statistics", {})
        if not isinstance(stats, dict):
            stats = {}
        files = entry.get("files", {})
        if not isinstance(files, dict):
            files = {}
        metadata = entry.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        timestamp = entry.get("timestamp", "")
        
        html_parts.append(f'<div class="analysis-section">')
        html_parts.append(f'<h3>{atype.replace("_", " ")}</h3>')
        html_parts.append(f'<p class="timestamp">⏱️ Performed: {timestamp}</p>')
        
        # Find and display images (goal-aware subset)
        image_files = _collect_image_paths(files, metadata, search_dirs)
        image_files = select_images_from_entry(
            image_files,
            user_goal=user_goal or "",
            report_focus=report_focus or "",
            enriched_prompt=enriched_prompt or "",
            analysis_type=atype,
            policy=policy,
        )
        if image_files:
            for img_type, img_path in image_files.items():
                img_data = _encode_image_base64(img_path, search_dirs)
                if img_data:
                    figure_counter += 1
                    figure_numbers.add(figure_counter)
                    caption = _figure_caption_label(atype, str(img_type), str(img_path))
                    fig_label = _format_figure_label(figure_counter, caption)
                    figure_catalog.append(fig_label)
                    safe_alt = _html_esc.escape(fig_label)
                    html_parts.append(f'''
                        <div class="image-container" id="figure-{figure_counter}">
                            <img src="{img_data}" alt="{safe_alt}" class="analysis-image">
                            <p class="image-caption"><strong>{safe_alt}</strong></p>
                        </div>
                    ''')
                else:
                    # Fallback to file path if encoding fails
                    html_parts.append(f'<p><em>Image: {img_path}</em></p>')
        
        # Three-tile display: Statistics + Files (side-by-side), Key Observations (full-width below)
        has_stats = bool(stats)
        non_image_files = {k: v for k, v in files.items() if not _is_image_file(k, v)}
        has_files = bool(non_image_files)
        has_meta = bool(metadata)

        if has_stats or has_files or has_meta:
            html_parts.append('<div class="key-stats">')

            # --- Statistics tile (left) ---
            if has_stats:
                table_counter += 1
                table_numbers.add(table_counter)
                html_parts.append('<div class="info-tile tile-stats">')
                html_parts.append(
                    f'<div class="tile-header" id="table-{table_counter}">'
                    f'Table {table_counter}: {atype.replace("_", " ")} Statistics</div>'
                )
                for k, v in stats.items():
                    if isinstance(v, float):
                        fv = f"{v:.4f}"
                    else:
                        fv = str(v)
                    label = k.replace("_", " ").title()
                    html_parts.append(f'<div class="tile-row"><span class="tile-key">{label}</span><span class="tile-val highlight">{fv}</span></div>')
                html_parts.append('</div>')

            # --- Files tile (collapsed; raw paths are secondary to figures/stats) ---
            if has_files:
                html_parts.append('<div class="info-tile tile-files">')
                html_parts.append(
                    '<details><summary class="tile-header" style="cursor:pointer;">'
                    f'📁 Data files ({len(non_image_files)})</summary>'
                )
                for k, v in non_image_files.items():
                    fname = Path(v).name if isinstance(v, str) else str(v)
                    label = k.replace("_", " ").title()
                    html_parts.append(
                        f'<div class="tile-row"><span class="tile-key">{label}</span>'
                        f'<span class="tile-val">{fname}</span></div>'
                    )
                html_parts.append('</details></div>')

            # --- Key Observations tile (full-width row below) ---
            if has_meta:
                html_parts.append('<div class="tile-observations-row">')
                html_parts.append('<div class="info-tile tile-meta">')
                html_parts.append('<div class="tile-header">🔬 Key Observations</div>')
                for k, v in metadata.items():
                    label = k.replace("_", " ").title()
                    if isinstance(v, dict):
                        fv = "; ".join(f"{sk}: {sv}" for sk, sv in list(v.items())[:8])
                    elif isinstance(v, list):
                        if len(v) > 5:
                            fv = ", ".join(str(x) for x in v[:5]) + f" … (+{len(v)-5})"
                        else:
                            fv = ", ".join(str(x) for x in v)
                    elif isinstance(v, float):
                        fv = f"{v:.4f}"
                    else:
                        fv = str(v)
                    html_parts.append(f'<div class="tile-row"><span class="tile-key">{label}</span><span class="tile-val">{fv}</span></div>')
                html_parts.append('</div>')
                html_parts.append('</div>')

            html_parts.append('</div>')
        
        html_parts.append('</div>')
        html_parts.append('<div class="section-divider"></div>')
    
    # Literature Review (prose only) → Final Impression → References (end)
    import html as _html_mod

    # Keep prose citations consistent with figures/tables actually in this report
    lit_review_text = _sanitize_figure_table_citations(
        literature_review or "", figure_numbers, table_numbers
    )
    impression_text = _sanitize_figure_table_citations(
        final_impression or "", figure_numbers, table_numbers
    )

    if lit_review_text:
        html_parts.append("<h2>4. Literature Context</h2>")
        html_parts.append('<div class="literature-review">')
        for paragraph in lit_review_text.split("\n\n"):
            paragraph = paragraph.strip()
            if paragraph:
                paragraph = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", paragraph)
                paragraph = re.sub(
                    r"\[(\d+)\]",
                    r'<sup>[\1]</sup>',
                    paragraph,
                )
                html_parts.append(f"<p>{paragraph}</p>")
        html_parts.append("</div>")

    if impression_text:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append("<h2>5. Final Impression</h2>")
        html_parts.append('<div class="final-impression">')
        for paragraph in impression_text.split('\n\n'):
            paragraph = paragraph.strip()
            if paragraph:
                paragraph = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', paragraph)
                html_parts.append(f'<p>{paragraph}</p>')
        html_parts.append('</div>')

    if literature_refs:
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append("<h2>6. References</h2>")
        for idx, ref in enumerate(literature_refs, 1):
            title = _html_mod.escape(ref.get("title", "Unknown"))
            doi = ref.get("doi")
            pmid = ref.get("pmid")
            url = ref.get("url")
            source_tag = ref.get("source", "")

            html_parts.append('<div class="reference">')
            if doi:
                html_parts.append(
                    f'<div class="reference-title">[{idx}] '
                    f'<a href="https://doi.org/{_html_mod.escape(doi)}" '
                    f'target="_blank">{title}</a></div>'
                )
            elif pmid:
                html_parts.append(
                    f'<div class="reference-title">[{idx}] '
                    f'<a href="https://pubmed.ncbi.nlm.nih.gov/{_html_mod.escape(pmid)}/" '
                    f'target="_blank">{title}</a></div>'
                )
            elif url:
                html_parts.append(
                    f'<div class="reference-title">[{idx}] '
                    f'<a href="{_html_mod.escape(url)}" target="_blank">{title}</a></div>'
                )
            else:
                html_parts.append(f'<div class="reference-title">[{idx}] {title}</div>')

            authors = ref.get("authors", [])
            if authors:
                author_str = ", ".join(authors[:5])
                if len(authors) > 5:
                    author_str += " et al."
                html_parts.append(
                    f'<div class="reference-authors">{_html_mod.escape(author_str)}</div>'
                )

            journal = ref.get("journal", "")
            year = ref.get("year", "")
            if journal or year or source_tag:
                meta = f'<span class="journal">{_html_mod.escape(journal)}</span>'
                if year:
                    meta += f' ({year})'
                if source_tag and source_tag not in ("PubMed", ""):
                    meta += (
                        f' <span style="background:#e0e7ff;color:#3730a3;'
                        f'padding:1px 6px;border-radius:4px;font-size:0.75em;'
                        f'margin-left:4px;">{_html_mod.escape(source_tag)}</span>'
                    )
                html_parts.append(f'<div class="reference-meta">{meta}</div>')

            id_parts = []
            if doi:
                id_parts.append(
                    f'DOI: <a href="https://doi.org/{_html_mod.escape(doi)}" '
                    f'target="_blank">{_html_mod.escape(doi)}</a>'
                )
            if pmid:
                id_parts.append(
                    f'PMID: <a href="https://pubmed.ncbi.nlm.nih.gov/'
                    f'{_html_mod.escape(pmid)}/" target="_blank">'
                    f'{_html_mod.escape(pmid)}</a>'
                )
            if id_parts:
                html_parts.append(f'<div class="reference-doi">{", ".join(id_parts)}</div>')

            abstract = ref.get("abstract") or ""
            if abstract:
                snippet = abstract[:500] + ("…" if len(abstract) > 500 else "")
                html_parts.append(
                    f'<div class="reference-abstract">{_html_mod.escape(snippet)}</div>'
                )
            html_parts.append('</div>')

    # Footer
    html_parts.append("""
    </div>
</body>
</html>
""")
    
    return "\n".join(html_parts)


def _build_3d_viewer_section(pdb_frames: Dict[str, str]) -> str:
    """Build interactive 3D molecular viewer section using 3Dmol.js.

    *pdb_frames* maps ``"<time> ns"`` labels to PDB text.  When only one
    frame is provided the timepoint dropdown is hidden.
    """
    import json as _json

    # Escape each PDB string for safe JS template-literal embedding
    def _esc(txt: str) -> str:
        return txt.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    # Build a JS object literal:  { "0 ns": `...`, "50 ns": `...`, ... }
    # We construct the raw JS source string ourselves (no json.dumps for
    # the backtick-delimited values).
    labels = list(pdb_frames.keys())
    js_entries = []
    for label in labels:
        escaped = _esc(pdb_frames[label])
        js_entries.append(f'"{label}": `{escaped}`')
    js_frames_obj = "{\n        " + ",\n        ".join(js_entries) + "\n    }"

    # Build <option> tags for timepoint dropdown
    time_options = "\n".join(
        f'            <option value="{lbl}">{lbl}</option>' for lbl in labels
    )
    # Hide the dropdown when there is only a single frame
    time_display = "none" if len(labels) <= 1 else "inline"

    return f'''
<h2>🧪 3D Structure Viewer</h2>
<div class="viewer-section">
    <p>Interactive snapshot of the simulated system.
       Rotate (left-drag), zoom (scroll), translate (right-drag).
       {"Select a simulation timepoint to compare conformations." if len(labels) > 1 else ""}</p>

    <!-- Controls -->
    <div class="viewer-controls">
        <label for="time-select" style="display:{time_display}">Time:</label>
        <select id="time-select" onchange="switchTimepoint()" style="display:{time_display}">
{time_options}
        </select>

        <label for="repr-select">Style:</label>
        <select id="repr-select" onchange="updateViewer()">
            <option value="cartoon">Cartoon</option>
            <option value="stick">Stick (Licorice)</option>
            <option value="line">Line</option>
            <option value="sphere">Sphere</option>
            <option value="cross">Ball &amp; Stick</option>
        </select>

        <label for="color-select">Color:</label>
        <select id="color-select" onchange="updateViewer()">
            <option value="spectrum">Spectrum (rainbow)</option>
            <option value="chain">By Chain</option>
            <option value="ss">Secondary Structure</option>
            <option value="elem">By Element</option>
            <option value="residue">By Residue</option>
        </select>

        <label for="comp-select">Show:</label>
        <select id="comp-select" onchange="updateViewer()">
            <option value="all">All Components</option>
            <option value="protein">Protein Only</option>
            <option value="water">Water Only</option>
            <option value="ions">Ions Only</option>
            <option value="ligand">Ligand / Non-protein</option>
            <option value="nowater">Protein + Ions (no water)</option>
        </select>

        <button id="btn-spin" onclick="toggleSpin()">⟳ Spin</button>
        <button id="btn-surface" onclick="toggleSurface()">◉ Surface</button>
        <button onclick="resetView()">↺ Reset</button>
        <button onclick="savePNG()" title="Save current view as PNG image">📷 Save PNG</button>
    </div>

    <!-- Viewer canvas -->
    <div id="viewer3d" class="viewer-container"></div>

    <!-- Sequence viewer -->
    <div id="seq-viewer-wrap" style="margin-top:12px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <label style="font-size:13px;font-weight:600;color:#4338ca;">Sequence:</label>
            <span id="seq-info" style="font-size:12px;color:#6b7280;"></span>
            <button onclick="clearSeqSelection()" style="margin-left:auto;padding:3px 10px;border:1px solid #c7d2fe;border-radius:5px;background:#fff;font-size:12px;cursor:pointer;">Clear selection</button>
        </div>
        <div id="seq-bar" style="
            font-family:'Courier New',monospace;font-size:12px;line-height:1.15;
            background:#1e1e2e;color:#a5b4fc;padding:10px 12px;border-radius:8px;
            overflow-x:auto;white-space:nowrap;cursor:pointer;user-select:none;
            max-height:80px;letter-spacing:1px;
        "></div>
    </div>
</div>

<script>
(function() {{
    // ========== PDB data for each timepoint ==========
    var pdbFrames = {js_frames_obj};
    var frameLabels = {_json.dumps(labels)};
    var currentLabel = frameLabels[0];
    var pdbData = pdbFrames[currentLabel];

    // ========== state ==========
    var spinning   = false;
    var showSurface = false;
    var surfaceObj  = null;
    var viewer      = null;
    var seqResidues = [];
    var seqSelStart = null;
    var seqSelEnd   = null;

    // ========== selection helpers ==========
    function selForComponent(comp) {{
        var proteinResn = [
            "ALA","ARG","ASN","ASP","CYS","GLN","GLU","GLY","HIS","ILE","LEU","LYS","MET","PHE","PRO","SER","THR","TRP","TYR","VAL",
            "SEC","PYL","ASX","GLX","XLE","UNK"
        ];
        var waterResn = ["HOH","WAT","SOL","TIP3"];
        var ionResn = [
            "NA","CL","K","MG","CA","ZN","FE","MN","CU","CO","CD","NI","SR","BA","CS","LI","RB","PB","AL","CR","V","TI","AG","AU","HG",
            "NA+","CL-","SOD","CLA","POT","IOD","BR","F"
        ];
        switch (comp) {{
            case "protein":
                return {{resn: proteinResn}};
            case "water":
                return {{resn: waterResn}};
            case "ions":
                return {{resn: ionResn}};
            case "ligand":
                return {{not: {{or: [
                    {{resn: proteinResn}},
                    {{resn: waterResn}},
                    {{resn: ionResn}}
                ]}}}};
            case "nowater":
                return {{not: {{resn: waterResn}}}};
            default:
                return {{}};
        }}
    }}

    function colorSpec(scheme) {{
        switch (scheme) {{
            case "spectrum":  return {{color: "spectrum"}};
            case "chain":     return {{colorscheme: "chain"}};
            case "ss":        return {{colorscheme: "ssJmol"}};
            case "elem":      return {{colorscheme: "default"}};
            case "residue":   return {{colorscheme: "amino"}};
            default:          return {{color: "spectrum"}};
        }}
    }}

    // ========== load a model into the viewer ==========
    function loadModel(pdbText) {{
        viewer.removeAllModels();
        viewer.removeAllSurfaces();
        surfaceObj = null;
        viewer.addModel(pdbText, "pdb");
        // Multi-component default styling
        viewer.setStyle(selForComponent("protein"), {{cartoon: {{color: "spectrum"}}}});
        viewer.setStyle(selForComponent("ligand"), {{stick: {{colorscheme: "default", radius: 0.15}}}});
        viewer.setStyle(selForComponent("ions"), {{sphere: {{colorscheme: "Jmol", scale: 0.5}}}});
        viewer.zoomTo();
        viewer.render();
    }}

    // ========== switch timepoint ==========
    window.switchTimepoint = function() {{
        var sel = document.getElementById("time-select");
        if (!sel) return;
        currentLabel = sel.value;
        pdbData = pdbFrames[currentLabel];
        loadModel(pdbData);
        parseSequence();
        renderSeqBar();
    }};

    // ========== core render ==========
    window.updateViewer = function() {{
        if (!viewer) return;
        var style  = document.getElementById("repr-select").value;
        var color  = document.getElementById("color-select").value;
        var comp   = document.getElementById("comp-select").value;

        viewer.removeAllSurfaces();
        surfaceObj = null;

        viewer.setStyle({{}}, {{}});

        var sel  = selForComponent(comp);
        var spec = {{}};
        spec[style] = colorSpec(color);
        viewer.setStyle(sel, spec);

        if (comp === "all" || comp === "nowater") {{
            viewer.setStyle(selForComponent("ligand"), {{stick: {{colorscheme: "default", radius: 0.15}}}});
            viewer.setStyle(selForComponent("ions"), {{sphere: {{colorscheme: "Jmol", scale: 0.5}}}});
        }}

        applySeqHighlight(style, color);

        if (showSurface) {{
            surfaceObj = viewer.addSurface($3Dmol.SurfaceType.VDW,
                {{opacity: 0.7, color: "white"}}, sel);
        }}
        viewer.zoomTo(sel);
        viewer.render();
    }};

    // ========== surface toggle ==========
    window.toggleSurface = function() {{
        if (!viewer) return;
        showSurface = !showSurface;
        var btn = document.getElementById("btn-surface");
        if (showSurface) {{
            btn.style.background = "#dc2626";
            btn.textContent = "◉ Surface ON";
        }} else {{
            btn.style.background = "#6366f1";
            btn.textContent = "◉ Surface";
        }}
        viewer.removeAllSurfaces();
        surfaceObj = null;
        if (showSurface) {{
            var comp = document.getElementById("comp-select").value;
            var sel  = selForComponent(comp);
            surfaceObj = viewer.addSurface($3Dmol.SurfaceType.VDW,
                {{opacity: 0.7, color: "white"}}, sel);
        }}
        viewer.render();
    }};

    // ========== spin ==========
    window.toggleSpin = function() {{
        if (!viewer) return;
        spinning = !spinning;
        viewer.spin(spinning);
        var btn = document.getElementById("btn-spin");
        btn.style.background = spinning ? "#dc2626" : "#6366f1";
    }};

    // ========== reset ==========
    window.resetView = function() {{
        if (!viewer) return;
        spinning = false;
        showSurface = false;
        viewer.spin(false);
        viewer.removeAllSurfaces();
        surfaceObj = null;
        seqSelStart = null;
        seqSelEnd = null;
        document.getElementById("repr-select").value  = "cartoon";
        document.getElementById("color-select").value  = "spectrum";
        document.getElementById("comp-select").value   = "all";
        document.getElementById("btn-spin").style.background    = "#6366f1";
        document.getElementById("btn-surface").style.background = "#6366f1";
        document.getElementById("btn-surface").textContent      = "◉ Surface";
        renderSeqBar();
        loadModel(pdbData);
    }};

    // ========== PNG export ==========
    window.savePNG = function() {{
        if (!viewer) return;
        var uri = viewer.pngURI();
        var a = document.createElement("a");
        a.href = uri;
        a.download = "structure_" + currentLabel.replace(" ", "_") + ".png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }};

    // ========== SEQUENCE VIEWER ==========
    function parseSequence() {{
        seqResidues = [];
        var seen = {{}};
        var lines = pdbData.split("\\n");
        for (var i = 0; i < lines.length; i++) {{
            var line = lines[i];
            if ((line.substring(0,6).trim() === "ATOM" || line.substring(0,6).trim() === "HETATM")) {{
                var atomName = line.substring(12,16).trim();
                var resName  = line.substring(17,20).trim();
                var chain    = line.substring(21,22).trim() || "A";
                var resi     = parseInt(line.substring(22,26).trim(), 10);
                if (["HOH","WAT","SOL","TIP3","NA","CL","K","MG","CA","ZN","FE","NA+","CL-","SOD","CLA"].indexOf(resName) >= 0) continue;
                var key = chain + "_" + resi;
                if (atomName === "CA" && !seen[key]) {{
                    seen[key] = true;
                    seqResidues.push({{resi: resi, resn: resName, chain: chain}});
                }}
            }}
        }}
    }}

    var _AA_MAP = {{
        "ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E",
        "GLY":"G","HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F",
        "PRO":"P","SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V",
        "SEC":"U","PYL":"O","ASX":"B","GLX":"Z","XLE":"J","UNK":"X"
    }};

    function renderSeqBar() {{
        var bar = document.getElementById("seq-bar");
        var info = document.getElementById("seq-info");
        if (!seqResidues.length) {{
            bar.innerHTML = "<em style='color:#6b7280'>No protein residues found in PDB</em>";
            return;
        }}
        info.textContent = seqResidues.length + " residues  |  Click to select start, click again for end";

        var spans = [];
        for (var i = 0; i < seqResidues.length; i++) {{
            var r = seqResidues[i];
            var letter = _AA_MAP[r.resn] || "X";
            var highlighted = false;
            if (seqSelStart !== null && seqSelEnd !== null) {{
                var lo = Math.min(seqSelStart, seqSelEnd);
                var hi = Math.max(seqSelStart, seqSelEnd);
                if (i >= lo && i <= hi) highlighted = true;
            }} else if (seqSelStart !== null && i === seqSelStart) {{
                highlighted = true;
            }}

            var bg = highlighted ? "background:#fbbf24;color:#1e1e2e;border-radius:2px;" : "";
            spans.push('<span data-idx="' + i + '" title="' + r.resn + ' ' + r.resi + ' (chain ' + r.chain + ')" ' +
                       'style="cursor:pointer;padding:0 1px;' + bg + '">' + letter + '</span>');

            if ((i + 1) % 10 === 0 && i < seqResidues.length - 1) {{
                spans.push('<span style="color:#4b5563;font-size:10px;" title="residue ' + seqResidues[i].resi + '">|</span>');
            }}
        }}
        bar.innerHTML = spans.join("");

        var charSpans = bar.querySelectorAll("span[data-idx]");
        for (var j = 0; j < charSpans.length; j++) {{
            charSpans[j].addEventListener("click", onSeqClick);
        }}
    }}

    function onSeqClick(e) {{
        var idx = parseInt(e.target.getAttribute("data-idx"), 10);
        if (isNaN(idx)) return;

        if (seqSelStart === null) {{
            seqSelStart = idx;
            seqSelEnd = null;
        }} else if (seqSelEnd === null) {{
            seqSelEnd = idx;
        }} else {{
            seqSelStart = idx;
            seqSelEnd = null;
        }}
        renderSeqBar();
        updateViewer();
    }}

    window.clearSeqSelection = function() {{
        seqSelStart = null;
        seqSelEnd = null;
        renderSeqBar();
        updateViewer();
    }};

    function applySeqHighlight(style, color) {{
        if (seqSelStart === null) return;
        var lo = seqSelStart;
        var hi = (seqSelEnd !== null) ? seqSelEnd : seqSelStart;
        if (lo > hi) {{ var t = lo; lo = hi; hi = t; }}

        var resiList = [];
        for (var k = lo; k <= hi; k++) {{
            if (k < seqResidues.length) resiList.push(seqResidues[k].resi);
        }}
        if (!resiList.length) return;

        var hlSpec = {{}};
        hlSpec[style] = {{color: "#fbbf24"}};
        viewer.setStyle({{resi: resiList}}, hlSpec);
    }}

    // ========== initialise ==========
    document.addEventListener("DOMContentLoaded", function() {{
        var element = document.getElementById("viewer3d");
        viewer = $3Dmol.createViewer(element, {{
            backgroundColor: "#1a1a2e"
        }});
        loadModel(pdbData);
        parseSequence();
        renderSeqBar();
    }});
}})();
</script>
'''

def _resolve_asset_path(path: str, search_dirs: Optional[List[Path]] = None) -> Optional[Path]:
    """Resolve a relative or absolute asset path against known analysis directories."""
    if not path or not isinstance(path, str):
        return None
    path = path.strip()
    if path.startswith("[") and path.endswith("]"):
        return None
    p = Path(path)
    if p.is_file():
        return p
    for d in search_dirs or []:
        for candidate in (d / p.name, d / path, d / Path(path).name):
            if candidate.is_file():
                return candidate
    return None


def _dedupe_fel_plot_images(image_files: Dict[str, str]) -> Dict[str, str]:
    """Prefer annotated ``fel_basins.png`` over the plain ``fel_pc1_pc2.png`` FEL."""
    has_basins = any(Path(v).name == "fel_basins.png" for v in image_files.values())
    if not has_basins:
        return image_files
    return {
        key: path
        for key, path in image_files.items()
        if Path(path).name != "fel_pc1_pc2.png"
    }


def _collect_image_paths(
    files: Dict[str, Any],
    metadata: Dict[str, Any],
    search_dirs: Optional[List[Path]] = None,
) -> Dict[str, str]:
    """Collect all image paths from an analysis entry (files + metadata).

    Also discovers sibling ``stem.png`` next to metric ``.dat``/``.csv`` files
    when plot tools ran but the summary was not updated with a plot path.
    """
    image_extensions = {".png", ".jpg", ".jpeg", ".svg", ".gif"}
    image_files: Dict[str, str] = {}

    def _maybe_add(key: str, val: Any) -> None:
        if not isinstance(val, str):
            return
        if Path(val).suffix.lower() not in image_extensions and not _is_image_file(key, val):
            return
        resolved = _resolve_asset_path(val, search_dirs)
        if resolved:
            image_files[key] = str(resolved)

    for src_name, src in (("files", files), ("metadata", metadata)):
        for key, val in (src or {}).items():
            if isinstance(val, list):
                for i, item in enumerate(val):
                    _maybe_add(f"{key}_{i}", item)
            else:
                _maybe_add(key, val)

    # Sibling PNGs for metric data files (rmsd.dat → rmsd.png)
    for key, val in (files or {}).items():
        if not isinstance(val, str):
            continue
        stem_path = Path(val)
        if stem_path.suffix.lower() not in {".dat", ".csv"}:
            continue
        sibling_name = f"{stem_path.stem}.png"
        if any(Path(p).name == sibling_name for p in image_files.values()):
            continue
        resolved = _resolve_asset_path(sibling_name, search_dirs)
        if resolved and resolved.is_file():
            image_files.setdefault("plot", str(resolved))

    return _dedupe_fel_plot_images(image_files)


def _find_image_files(files: Dict[str, Any]) -> Dict[str, str]:
    """Extract image files from files dictionary (legacy helper)."""
    return _collect_image_paths(files, {}, None)


def _is_image_file(file_type: str, file_path: Any) -> bool:
    """Check if a file is an image."""
    if not isinstance(file_path, str):
        return False

    image_extensions = {".png", ".jpg", ".jpeg", ".svg", ".gif"}
    image_keywords = {"plot", "heatmap", "figure", "image", "timeseries", "3d"}

    path_obj = Path(file_path)

    if path_obj.suffix.lower() in image_extensions:
        return True

    if any(keyword in file_type.lower() for keyword in image_keywords):
        return True

    return False


def _encode_image_base64(
    image_path: str,
    search_dirs: Optional[List[Path]] = None,
) -> Optional[str]:
    """Encode image file to base64 data URI."""
    try:
        path = _resolve_asset_path(image_path, search_dirs) or Path(image_path)
        if not path.is_file():
            logger.warning(f"Image file not found: {image_path}")
            return None

        ext = path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
        }
        mime_type = mime_types.get(ext, "image/png")

        with open(path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return f"data:{mime_type};base64,{image_data}"

    except Exception as e:
        logger.error(f"Error encoding image {image_path}: {e}")
        return None


def _extract_key_statistics(stats: Dict[str, Any], analysis_type: str) -> List[tuple]:
    """
    Extract key statistics to display prominently.
    
    Returns:
        List of tuples: (stat_name, stat_value, is_highlight)
    """
    key_stats = []
    
    # Define priority statistics for each analysis type
    priority_stats = {
        'RMSD': ['mean_rmsd', 'std_rmsd', 'min_rmsd', 'max_rmsd'],
        'RMSF': ['mean_rmsf', 'std_rmsf', 'min_rmsf', 'max_rmsf'],
        'Gyration': ['mean_rg', 'std_rg', 'min_rg', 'max_rg'],
        'RadiusOfGyration': ['mean_rg', 'std_rg', 'min_rg', 'max_rg'],
        'DSSP': ['avg_helix_percent', 'avg_sheet_percent', 'avg_coil_percent'],
        'DSSP_SecondaryStructure': ['avg_helix_percent', 'avg_sheet_percent', 'avg_coil_percent'],
        'Energy': ['Potential_mean', 'Kinetic-En._mean', 'Temperature_mean'],
        'SASA': ['mean_sasa', 'std_sasa', 'min_sasa', 'max_sasa'],
    }
    
    # Get priority stats for this analysis type
    priority_list = []
    for key in priority_stats:
        if key.lower() in analysis_type.lower() or analysis_type.lower() in key.lower():
            priority_list = priority_stats[key]
            break
    
    # If no specific priority, show common stats
    if not priority_list:
        common_stats = ['mean', 'std', 'min', 'max', 'average', 'avg']
        priority_list = [k for k in stats.keys() if any(cs in k.lower() for cs in common_stats)]
    
    # Extract priority stats first
    for stat_key in priority_list:
        if stat_key in stats:
            value = stats[stat_key]
            if isinstance(value, (int, float)):
                # Highlight mean/average values
                is_highlight = 'mean' in stat_key.lower() or 'avg' in stat_key.lower()
                display_name = stat_key.replace('_', ' ').title()
                # Simplify names
                display_name = display_name.replace('Rmsd', 'RMSD')
                display_name = display_name.replace('Rmsf', 'RMSF')
                display_name = display_name.replace('Rg', 'Rg')
                display_name = display_name.replace('Sasa', 'SASA')
                key_stats.append((display_name, value, is_highlight))
    
    # Add other numeric stats if we don't have enough
    if len(key_stats) < 4:
        for stat_key, value in stats.items():
            if stat_key not in priority_list and isinstance(value, (int, float)):
                display_name = stat_key.replace('_', ' ').title()
                key_stats.append((display_name, value, False))
                if len(key_stats) >= 6:  # Limit to 6 stats per analysis
                    break
    
    return key_stats