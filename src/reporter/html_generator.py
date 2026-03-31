"""HTML report generation functionality"""
import os
import logging
import base64
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def generate_html_report(
    analysis_data: Dict[str, Any],
    literature_refs: Optional[List[Dict[str, Any]]] = None,
    report_type: str = "comprehensive",
    output_file: str = "report.html",
    working_dir: Optional[str] = None,
    system_info: Optional[Dict[str, Any]] = None,
    final_impression: Optional[str] = None,
    pdb_data: Optional[str] = None,
    enriched_prompt: Optional[str] = None
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
        pdb_data: PDB file text content for 3D structure viewer (optional)
        enriched_prompt: Supervisor-rephrased user task description (optional)
    
    Returns:
        Dict with report generation results
    """
    if working_dir is None:
        working_dir = os.getcwd()
    
    output_path = Path(working_dir) / output_file
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Auto-extract PDB for 3D viewer if not provided
    if pdb_data is None:
        pdb_data = _auto_extract_pdb(working_dir)
    
    try:
        # Build HTML content
        html_content = build_html_content(
            analysis_data=analysis_data,
            literature_refs=literature_refs or [],
            report_type=report_type,
            system_info=system_info,
            final_impression=final_impression,
            pdb_data=pdb_data,
            enriched_prompt=enriched_prompt
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


def _auto_extract_pdb(working_dir: str) -> Optional[str]:
    """Try to extract/read PDB for the 3D viewer automatically.

    Searches for an existing ``system_frame0.pdb`` first.  If not found,
    attempts to run the structure extractor on the base working directory
    (one level up from the reporter directory when appropriate).
    """
    try:
        from src.reporter.structure_extractor import extract_first_frame_pdb, read_pdb_data
    except ImportError:
        logger.debug("structure_extractor not available; skipping PDB auto-extract")
        return None

    wd = Path(working_dir).resolve()

    # Determine the base working directory (parent of reporter/ if we are inside it)
    if wd.name == "reporter":
        base_dir = wd.parent
    else:
        base_dir = wd

    # 1. Check for an already-extracted PDB in reporter/
    existing = base_dir / "reporter" / "system_frame0.pdb"
    if existing.is_file():
        pdb_text = read_pdb_data(str(existing))
        if pdb_text:
            logger.info("Auto-loaded existing PDB for 3D viewer: %s", existing)
            return pdb_text

    # 2. Extract from trajectory
    try:
        pdb_path = extract_first_frame_pdb(str(base_dir))
        if pdb_path:
            pdb_text = read_pdb_data(pdb_path)
            if pdb_text:
                logger.info("Auto-extracted PDB for 3D viewer (%d chars)", len(pdb_text))
                return pdb_text
    except Exception as exc:
        logger.warning("PDB auto-extraction failed: %s", exc)

    logger.debug("No PDB data available for 3D viewer")
    return None


def build_html_content(
    analysis_data: Dict[str, Any],
    literature_refs: List[Dict[str, Any]],
    report_type: str,
    system_info: Optional[Dict[str, Any]] = None,
    final_impression: Optional[str] = None,
    pdb_data: Optional[str] = None,
    enriched_prompt: Optional[str] = None
) -> str:
    """Build HTML content for report (not a @tool, internal helper)"""
    
    # Extract data
    entries = analysis_data.get("entries", [])
    analysis_types = analysis_data.get("analysis_types", {})
    
    # Normalize analysis_types to handle both dict and list formats
    if isinstance(analysis_types, list):
        # Convert list to dict with counts
        analysis_types = {atype: 1 for atype in analysis_types}
    elif not isinstance(analysis_types, dict):
        analysis_types = {}
    
    # Build HTML
    html_parts = []
    
    # HTML header
    html_parts.append("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Molecular Dynamics Report</title>
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
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin: 25px 0;
        }
        .stat-card {
            background: linear-gradient(135deg, #ffffff 0%, #f3f4f6 100%);
            padding: 20px;
            border-radius: 8px;
            border: 2px solid #e5e7eb;
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }
        .stat-value {
            font-size: 22px;
            font-weight: bold;
            color: #3b82f6;
            margin: 5px 0;
        }
        .stat-label {
            font-size: 14px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .highlight-stat {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
            border-color: #3b82f6;
        }
        .highlight-stat .stat-value {
            color: #1e40af;
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
""")
    
    # Title and metadata
    html_parts.append("<h1>🧬 Molecular Dynamics Report</h1>")
    html_parts.append(f'<div class="metadata">')
    html_parts.append(f'<p><strong>📊 Report Type:</strong> {report_type.title()}</p>')
    html_parts.append(f'<p><strong>📅 Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>')
    html_parts.append(f'<p><strong>🔬 Total Analyses:</strong> {len(entries)}</p>')
    html_parts.append(f'<p><strong>📈 Analysis Types:</strong> {", ".join(analysis_types.keys())}</p>')
    html_parts.append('</div>')
    
    # Task Description (enriched prompt from supervisor)
    if enriched_prompt:
        import html as html_mod
        html_parts.append('<div class="task-description">')
        html_parts.append('<h3>📝 Task Description</h3>')
        html_parts.append(f'<p>{html_mod.escape(enriched_prompt)}</p>')
        html_parts.append('</div>')
    
    # Section 1: System Information (from input validation)
    if system_info and system_info.get("success"):
        html_parts.append("<h2>🔬 System Information</h2>")
        html_parts.append('<div class="system-info">')
        
        # Summary line
        summary = system_info.get("summary", "")
        if summary:
            html_parts.append(f'<p><strong>{summary}</strong></p>')
        
        # Key metrics grid
        html_parts.append('<div class="system-info-grid">')
        html_parts.append(f'''
            <div class="system-info-card">
                <div class="info-label">Total Atoms</div>
                <div class="info-value">{system_info.get("total_atoms", "N/A"):,}</div>
            </div>
        ''')
        html_parts.append(f'''
            <div class="system-info-card">
                <div class="info-label">Total Residues</div>
                <div class="info-value">{system_info.get("total_residues", "N/A"):,}</div>
            </div>
        ''')
        
        # Trajectory info if available
        traj_info = system_info.get("trajectory", {})
        if traj_info:
            if traj_info.get("n_frames"):
                html_parts.append(f'''
                    <div class="system-info-card">
                        <div class="info-label">Frames</div>
                        <div class="info-value">{traj_info["n_frames"]:,}</div>
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
            prot = components.get("protein", {})
            if prot.get("present"):
                chains = ", ".join(prot.get("chains", [])) if prot.get("chains") else "—"
                html_parts.append(f'<tr><td>🧬 Protein</td><td>Yes</td><td>{prot.get("atom_count", 0):,}</td><td>{prot.get("residue_count", 0)} residues, Chains: {chains}</td></tr>')
            else:
                html_parts.append('<tr><td>🧬 Protein</td><td>No</td><td>—</td><td>—</td></tr>')
            
            # Water
            wat = components.get("water", {})
            if wat.get("present"):
                html_parts.append(f'<tr><td>💧 Water</td><td>Yes</td><td>{wat.get("atom_count", 0):,}</td><td>{wat.get("residue_count", 0)} molecules</td></tr>')
            else:
                html_parts.append('<tr><td>💧 Water</td><td>No</td><td>—</td><td>—</td></tr>')
            
            # Ions
            ion = components.get("ions", {})
            if ion.get("present"):
                ion_detail = ", ".join(f"{k}: {v}" for k, v in ion.get("types", {}).items())
                html_parts.append(f'<tr><td>⚡ Ions</td><td>Yes</td><td>{ion.get("atom_count", 0):,}</td><td>{ion_detail}</td></tr>')
            else:
                html_parts.append('<tr><td>⚡ Ions</td><td>No</td><td>—</td><td>—</td></tr>')
            
            # Ligand
            lig = components.get("ligand", {})
            if lig.get("present"):
                lig_names = ", ".join(lig.get("residue_names", []))
                html_parts.append(f'<tr><td>💊 Ligand</td><td>Yes</td><td>{lig.get("atom_count", 0):,}</td><td>{lig_names}</td></tr>')
            else:
                html_parts.append('<tr><td>💊 Ligand</td><td>No</td><td>—</td><td>—</td></tr>')
            
            html_parts.append('</tbody></table>')
        
        html_parts.append('</div>')  # close system-info
        html_parts.append('<div class="section-divider"></div>')
    
    # 3D Structure Viewer section (powered by 3Dmol.js)
    if pdb_data:
        html_parts.append(_build_3d_viewer_section(pdb_data))
        html_parts.append('<div class="section-divider"></div>')
    
    # Analysis sections
    html_parts.append("<h2>📊 Analysis Results</h2>")
    
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
        html_parts.append(f'<h3>{atype}</h3>')
        html_parts.append(f'<p class="timestamp">⏱️ Performed: {timestamp}</p>')
        
        # Find and display images
        image_files = _find_image_files(files)
        if image_files:
            for img_type, img_path in image_files.items():
                # Try to encode image as base64
                img_data = _encode_image_base64(img_path)
                if img_data:
                    html_parts.append(f'''
                        <div class="image-container">
                            <img src="{img_data}" alt="{img_type}" class="analysis-image">
                            <p class="image-caption">{img_type.replace("_", " ").title()}</p>
                        </div>
                    ''')
                else:
                    # Fallback to file path if encoding fails
                    html_parts.append(f'<p><em>Image: {img_path}</em></p>')
        
        # Display key statistics in cards
        if stats:
            # Identify important statistics
            key_stats = _extract_key_statistics(stats, atype)
            
            if key_stats:
                html_parts.append('<div class="key-stats">')
                for stat_name, stat_value, is_highlight in key_stats:
                    card_class = "stat-card highlight-stat" if is_highlight else "stat-card"
                    if isinstance(stat_value, float):
                        formatted_value = f"{stat_value:.3f}"
                    else:
                        formatted_value = str(stat_value)
                    
                    html_parts.append(f'''
                        <div class="{card_class}">
                            <div class="stat-label">{stat_name}</div>
                            <div class="stat-value">{formatted_value}</div>
                        </div>
                    ''')
                html_parts.append('</div>')
        
        # Additional files (non-images) in compact format
        non_image_files = {k: v for k, v in files.items() if not _is_image_file(k, v)}
        if non_image_files:
            html_parts.append('<div class="files-list">')
            html_parts.append('<p><strong>📁 Data Files:</strong></p>')
            html_parts.append('<ul>')
            for file_type, file_path in non_image_files.items():
                file_name = Path(file_path).name if isinstance(file_path, str) else str(file_path)
                html_parts.append(f'<li><strong>{file_type}:</strong> {file_name}</li>')
            html_parts.append('</ul>')
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        html_parts.append('<div class="section-divider"></div>')
    
    # Literature references
    if literature_refs:
        display_refs = literature_refs[:10]  # Max 10 references
        html_parts.append("<h2>📚 Literature</h2>")
        html_parts.append(f'<p>Found {len(literature_refs)} relevant publications (showing top {len(display_refs)}):</p>')
        
        for idx, ref in enumerate(display_refs, 1):
            import html as _html_mod
            title = _html_mod.escape(ref.get("title", "Unknown"))
            doi = ref.get("doi")
            pmid = ref.get("pmid")

            html_parts.append('<div class="reference">')

            # Title — linked to DOI if available, otherwise PubMed, otherwise url
            url = ref.get("url")
            source_tag = ref.get("source", "")
            if doi:
                html_parts.append(f'<div class="reference-title">[{idx}] <a href="https://doi.org/{_html_mod.escape(doi)}" target="_blank">{title}</a></div>')
            elif pmid:
                html_parts.append(f'<div class="reference-title">[{idx}] <a href="https://pubmed.ncbi.nlm.nih.gov/{_html_mod.escape(pmid)}/" target="_blank">{title}</a></div>')
            elif url:
                html_parts.append(f'<div class="reference-title">[{idx}] <a href="{_html_mod.escape(url)}" target="_blank">{title}</a></div>')
            else:
                html_parts.append(f'<div class="reference-title">[{idx}] {title}</div>')

            # Authors
            authors = ref.get("authors", [])
            if authors:
                author_str = ", ".join(authors[:5])
                if len(authors) > 5:
                    author_str += " et al."
                html_parts.append(f'<div class="reference-authors">{_html_mod.escape(author_str)}</div>')

            # Journal, year (single compact line)
            journal = ref.get("journal", "")
            year = ref.get("year", "")
            if journal or year or source_tag:
                meta = f'<span class="journal">{_html_mod.escape(journal)}</span>'
                if year:
                    meta += f' ({year})'
                if source_tag and source_tag not in ("PubMed", ""):
                    meta += f' <span style="background:#e0e7ff;color:#3730a3;padding:1px 6px;border-radius:4px;font-size:0.75em;margin-left:4px;">{_html_mod.escape(source_tag)}</span>'
                html_parts.append(f'<div class="reference-meta">{meta}</div>')

            # DOI and PMID on one line
            id_parts = []
            if doi:
                id_parts.append(f'DOI: <a href="https://doi.org/{_html_mod.escape(doi)}" target="_blank">{_html_mod.escape(doi)}</a>')
            if pmid:
                id_parts.append(f'PMID: <a href="https://pubmed.ncbi.nlm.nih.gov/{_html_mod.escape(pmid)}/" target="_blank">{_html_mod.escape(pmid)}</a>')
            if id_parts:
                html_parts.append(f'<div class="reference-doi">{", ".join(id_parts)}</div>')

            html_parts.append('</div>')
    
    # Final Impression section
    if final_impression:
        import re as _re_fi
        html_parts.append('<div class="section-divider"></div>')
        html_parts.append("<h2>🎯 Final Impression</h2>")
        html_parts.append('<div class="final-impression">')
        # Convert markdown-like paragraphs to HTML, with **bold** support
        for paragraph in final_impression.split('\n\n'):
            paragraph = paragraph.strip()
            if paragraph:
                # Convert **text** to <strong>text</strong>
                paragraph = _re_fi.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', paragraph)
                html_parts.append(f'<p>{paragraph}</p>')
        
        # Add cited references at the bottom of final impression
        if literature_refs:
            # Find which references are cited in the text (e.g., [1], [2])
            import re as _re
            cited_nums = set()
            for m in _re.finditer(r'\[(\d+)\]', final_impression):
                cited_nums.add(int(m.group(1)))
            
            # Show all refs if none explicitly cited, otherwise show cited ones
            refs_to_show = []
            if cited_nums:
                for num in sorted(cited_nums):
                    if 1 <= num <= len(literature_refs):
                        refs_to_show.append((num, literature_refs[num - 1]))
            else:
                # No explicit citations — show all literature refs used
                refs_to_show = [(i, ref) for i, ref in enumerate(literature_refs[:10], 1)]
            
            if refs_to_show:
                html_parts.append('<div class="ref-citations">')
                html_parts.append('<p><strong>References cited:</strong></p>')
                for num, ref in refs_to_show:
                    title = ref.get("title", "Unknown")
                    authors = ref.get("authors", [])
                    author_str = ", ".join(authors[:3])
                    if len(authors) > 3:
                        author_str += " et al."
                    year = ref.get("year", "")
                    journal = ref.get("journal", "")
                    pmid = ref.get("pmid", "")
                    cite_parts = [f"[{num}] {author_str}"]
                    if title:
                        cite_parts.append(f'"{title}"')
                    if journal:
                        cite_parts.append(f"<em>{journal}</em>")
                    if year:
                        cite_parts.append(f"({year})")
                    if pmid:
                        cite_parts.append(f'PMID: <a href="https://pubmed.ncbi.nlm.nih.gov/{pmid}/">{pmid}</a>')
                    html_parts.append(f'<p>{" ".join(cite_parts)}</p>')
                html_parts.append('</div>')
        
        html_parts.append('</div>')
    
    # Footer
    html_parts.append("""
    </div>
</body>
</html>
""")
    
    return "\n".join(html_parts)


def _build_3d_viewer_section(pdb_data: str) -> str:
    """Build interactive 3D molecular viewer section using 3Dmol.js.

    Provides controls for:
    - Representation style (cartoon, stick, line, sphere, ball-and-stick)
    - Show/hide components (protein, water, ions, ligand)
    - Color scheme (spectrum, chain, secondary structure, element)
    - Surface toggle (on/off with visual feedback)
    - Spin toggle and reset view
    - Protein sequence bar with click-to-highlight
    - PNG screenshot export
    """
    # Escape PDB data for safe embedding in JS string literal
    escaped_pdb = pdb_data.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    return f'''
<h2>🧪 3D Structure Viewer</h2>
<div class="viewer-section">
    <p>Interactive first-frame snapshot of the simulated system.
       Use mouse to rotate (left-click), zoom (scroll), and translate (right-click).</p>

    <!-- Controls -->
    <div class="viewer-controls">
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
    // ========== PDB data embedded at build time ==========
    var pdbData = `{escaped_pdb}`;

    // ========== state ==========
    var spinning   = false;
    var showSurface = false;
    var surfaceObj  = null;
    var viewer      = null;
    var seqResidues = [];    // [ {{resi, resn, chain}}, ... ]
    var seqSelStart = null;
    var seqSelEnd   = null;

    // ========== selection helpers ==========
    function selForComponent(comp) {{
        switch (comp) {{
            case "protein":
                return {{or: [{{atom: "CA"}}, {{atom: "C"}}, {{atom: "N"}}, {{atom: "O"}}, {{atom: "CB"}}],
                         not: {{resn: ["HOH","WAT","SOL","TIP3","NA","CL","K","MG","CA","ZN","FE","NA+","CL-","SOD","CLA"]}}}};
            case "water":
                return {{resn: ["HOH","WAT","SOL","TIP3"]}};
            case "ions":
                return {{resn: ["NA","CL","K","MG","CA","ZN","FE","NA+","CL-","SOD","CLA"]}};
            case "ligand":
                return {{not: {{or: [
                    {{atom: "CA"}}, {{atom: "C"}}, {{atom: "N"}}, {{atom: "O"}}, {{atom: "CB"}},
                    {{resn: ["HOH","WAT","SOL","TIP3","NA","CL","K","MG","CA","ZN","FE","NA+","CL-","SOD","CLA"]}}
                ]}}}};
            case "nowater":
                return {{not: {{resn: ["HOH","WAT","SOL","TIP3"]}}}};
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

    // ========== core render ==========
    window.updateViewer = function() {{
        if (!viewer) return;
        var style  = document.getElementById("repr-select").value;
        var color  = document.getElementById("color-select").value;
        var comp   = document.getElementById("comp-select").value;

        // Remove old surface first
        viewer.removeAllSurfaces();
        surfaceObj = null;

        // Clear all styles, then apply
        viewer.setStyle({{}}, {{}});  // hide everything

        var sel  = selForComponent(comp);
        var spec = {{}};
        spec[style] = colorSpec(color);
        viewer.setStyle(sel, spec);

        // Highlight sequence selection if any
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
        // Explicitly remove or add surface
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
        updateViewer();
    }};

    // ========== PNG export ==========
    window.savePNG = function() {{
        if (!viewer) return;
        var uri = viewer.pngURI();
        var a = document.createElement("a");
        a.href = uri;
        a.download = "structure_view.png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }};

    // ========== SEQUENCE VIEWER ==========
    function parseSequence() {{
        // Extract unique CA atoms → one per residue, ordered by resi
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
                // Skip water / ions
                if (["HOH","WAT","SOL","TIP3","NA","CL","K","MG","CA","ZN","FE"].indexOf(resName) >= 0) continue;
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

            // Add chain break marker + position every 10 residues
            if ((i + 1) % 10 === 0 && i < seqResidues.length - 1) {{
                spans.push('<span style="color:#4b5563;font-size:10px;" title="residue ' + seqResidues[i].resi + '">|</span>');
            }}
        }}
        bar.innerHTML = spans.join("");

        // Attach click handlers
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
            // Third click resets
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

        // Collect resi numbers for the selection range
        var resiList = [];
        for (var k = lo; k <= hi; k++) {{
            if (k < seqResidues.length) resiList.push(seqResidues[k].resi);
        }}
        if (!resiList.length) return;

        // Highlight with bright color
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
        viewer.addModel(pdbData, "pdb");
        viewer.setStyle({{}}, {{cartoon: {{color: "spectrum"}}}});
        viewer.zoomTo();
        viewer.render();

        // Build sequence bar
        parseSequence();
        renderSeqBar();
    }});
}})();
</script>
'''

def _find_image_files(files: Dict[str, Any]) -> Dict[str, str]:
    """Extract image files from files dictionary"""
    image_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.gif'}
    image_files = {}
    
    for file_type, file_path in files.items():
        if isinstance(file_path, str):
            path_obj = Path(file_path)
            if path_obj.suffix.lower() in image_extensions:
                image_files[file_type] = file_path
    
    return image_files


def _is_image_file(file_type: str, file_path: Any) -> bool:
    """Check if a file is an image"""
    if not isinstance(file_path, str):
        return False
    
    image_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.gif'}
    image_keywords = {'plot', 'heatmap', 'figure', 'image', 'timeseries', '3d'}
    
    path_obj = Path(file_path)
    
    # Check extension
    if path_obj.suffix.lower() in image_extensions:
        return True
    
    # Check type name
    if any(keyword in file_type.lower() for keyword in image_keywords):
        return True
    
    return False


def _encode_image_base64(image_path: str) -> Optional[str]:
    """Encode image file to base64 data URI"""
    try:
        path = Path(image_path)
        if not path.exists():
            logger.warning(f"Image file not found: {image_path}")
            return None
        
        # Determine MIME type
        ext = path.suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml'
        }
        mime_type = mime_types.get(ext, 'image/png')
        
        # Read and encode
        with open(path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
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