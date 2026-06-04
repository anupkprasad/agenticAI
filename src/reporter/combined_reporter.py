"""
Combined Reporter - Multi-simulation comparison HTML report generator

Reads per-simulation analysis summaries and overlay plots produced by the
combined_analysis phase, then builds a rich single-page comparison HTML report
with: task description, per-sim overview, 3D structure viewer (up to 5 PDBs),
overlay plots, statistics comparison table, aggregated literature, and a final
combined impression.

Designed to be imported by agentic/reporter/tools.py and exposed as an
@tool for the Reporter Agent.
"""
import html as _html_mod
import json
import logging
import re
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from langchain.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_image(path: str) -> Optional[str]:
    """Return a base64-encoded data-URI for PNG/JPEG, or None on failure."""
    try:
        data = Path(path).read_bytes()
        ext = Path(path).suffix.lstrip(".").lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception as exc:
        logger.warning(f"Could not encode image {path}: {exc}")
        return None


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read an analysis_summary.jsonl file."""
    try:
        from src.analysis.summary_logger import read_summary_file
        records = read_summary_file(str(Path(path).parent))
        return [r for r in records if r.get("analysis_type")]
    except Exception:
        pass

    records = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("---"):
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        logger.warning(f"Could not read {path}: {exc}")
    return [r for r in records if r.get("analysis_type")]


def _parse_label_name_map(text: str) -> Dict[str, str]:
    """Extract a {label: protein_name} mapping from free text.

    Handles patterns like:
      "p17612: KAPCA, p24941: CDK2"
      "p17612:KAPCA_HUMAN  p24941:CDK2_HUMAN"

    Keys are lowercased labels; values are the protein names exactly as given.
    Silently returns {} if nothing is found.
    """
    mapping: Dict[str, str] = {}
    if not text:
        return mapping
    # Pattern: <word_id><optional_space>:<optional_space><protein_name>
    # Both the id and name may contain letters, digits, underscores, hyphens.
    for m in re.finditer(
        r'\b([A-Za-z0-9_\-]+)\s*:\s*([A-Za-z][A-Za-z0-9_\-]+)',
        text
    ):
        key, val = m.group(1).strip(), m.group(2).strip()
        # Skip overly generic pairs that aren't ID→name mappings
        # (e.g. "RMSD: 2.5" — value must start with a letter)
        if val[0].isalpha() and len(key) >= 3 and len(val) >= 2:
            mapping[key.lower()] = val
    return mapping


def _collect_sim_summaries(
    sim_dirs: List[str],
    labels: List[str],
    label_name_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Read analysis_summary.jsonl from each per-sim analysis directory.

    Returns a list of dicts, one per simulation, with keys:
        label, analysis_dir, records (list of JSONL records)

    If *label_name_map* is provided it is used to replace raw labels (e.g.
    UniProt IDs) with human-readable protein names.
    """
    _lmap = {k.lower(): v for k, v in (label_name_map or {}).items()}
    sims = []
    for sim_dir, label in zip(sim_dirs, labels):
        display_label = _lmap.get(label.lower(), label)
        analysis_dir = Path(sim_dir) / "analysis"
        jsonl = analysis_dir / "analysis_summary.jsonl"
        records: List[Dict[str, Any]] = []
        if jsonl.exists():
            records = _read_jsonl(str(jsonl))
        else:
            logger.warning(f"No analysis_summary.jsonl in {analysis_dir}")
        sims.append({
            "label": display_label,
            "analysis_dir": str(analysis_dir),
            "records": records,
        })
    return sims


def _extract_stats(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build a dict mapping analysis_type → statistics from JSONL records.
    Only records that have a "statistics" key are included.
    """
    stats: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        atype = rec.get("analysis_type", "")
        if atype and rec.get("statistics"):
            stats[atype] = rec["statistics"]
    return stats


def _parse_timepoint(filename: str) -> str:
    """Extract simulation timepoint (e.g. '36 ns') from a PDB filename."""
    # Match patterns like system_frame_36ns.pdb, frame_36ns, frame36ns
    m = re.search(r'[_\-](\d+)\s*ns', filename, re.IGNORECASE)
    if m:
        return f"{m.group(1)} ns"
    # Fallback: match bare frame number, e.g. system_frame0.pdb
    m2 = re.search(r'frame(\d+)', filename, re.IGNORECASE)
    if m2:
        return f"{m2.group(1)} ns"
    return "0 ns"


def _collect_per_sim_resources(
    sim_dirs: List[str],
    labels: List[str],
    label_name_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Read comprehensive_summary.json and execution_plan.json for each sim."""
    _lmap = {k.lower(): v for k, v in (label_name_map or {}).items()}
    resources = []
    for sim_dir, label in zip(sim_dirs, labels):
        display_label = _lmap.get(label.lower(), label)
        res: Dict[str, Any] = {
            "label": display_label,
            "sim_dir": sim_dir,
            "report_focus": "",
            "reasoning": "",
            "literature_queries": [],
            "html_report_path": None,
            "analysis_types": [],
        }
        reporter_dir = Path(sim_dir) / "reporter"

        # Read comprehensive_summary.json (analysis data + report_focus)
        summary_path = reporter_dir / "comprehensive_summary.json"
        if summary_path.exists():
            try:
                with open(summary_path, encoding="utf-8") as f:
                    d = json.load(f)
                lp = d.get("llm_plan", {})
                res["report_focus"] = lp.get("report_focus", "")
                res["literature_queries"] = lp.get("literature_queries", [])
                # Collect analysis types actually performed
                ads = d.get("analysis_data_summary", {})
                if isinstance(ads, dict):
                    res["analysis_types"] = ads.get("analysis_types", [])
                elif isinstance(ads, list):
                    res["analysis_types"] = [r.get("analysis_type", "") for r in ads if r.get("analysis_type")]
                for step in d.get("step_results", []):
                    if step.get("tool") == "generate_html_report":
                        res["html_report_path"] = step.get("result", {}).get("report_file")
            except Exception as exc:
                logger.warning(f"Could not read comprehensive_summary.json for {label}: {exc}")

        # Read execution_plan.json for the supervisor-assigned reasoning / report focus
        plan_path = reporter_dir / "execution_plan.json"
        if plan_path.exists():
            try:
                with open(plan_path, encoding="utf-8") as f:
                    ep = json.load(f)
                res["reasoning"] = ep.get("reasoning", "")
                if not res["report_focus"]:
                    res["report_focus"] = ep.get("report_focus", "")
                if not res["literature_queries"]:
                    res["literature_queries"] = ep.get("literature_queries", [])
            except Exception as exc:
                logger.warning(f"Could not read execution_plan.json for {label}: {exc}")

        if not res["html_report_path"] and reporter_dir.exists():
            html_files = sorted(reporter_dir.glob("*.html"))
            if html_files:
                res["html_report_path"] = str(html_files[0])

        resources.append(res)
    return resources


def _select_representative_pdbs(
    sim_dirs: List[str], labels: List[str], max_pdbs: int = 5
) -> Dict[str, str]:
    """Pick one representative PDB per simulation, labelled with sim type + timepoint.

    Label format: ``"1A (0 ns)"`` — simulation label + actual time from filename.
    Capped at *max_pdbs* total.
    """
    pdb_frames: Dict[str, str] = {}
    for sim_dir, label in zip(sim_dirs, labels):
        if len(pdb_frames) >= max_pdbs:
            break
        reporter_dir = Path(sim_dir) / "reporter"
        if not reporter_dir.exists():
            continue
        pdb_files = sorted(reporter_dir.glob("*.pdb"))
        if not pdb_files:
            continue

        # Prefer earliest timepoint: *_0ns.pdb, frame0, then first alphabetically
        chosen = pdb_files[0]
        for pf in pdb_files:
            name = pf.name.lower()
            if "_0ns" in name or "frame0" in name or name.endswith("_0.pdb"):
                chosen = pf
                break

        try:
            pdb_text = chosen.read_text(encoding="utf-8", errors="replace")
            timepoint = _parse_timepoint(chosen.name)
            viewer_label = f"{label} ({timepoint})"
            pdb_frames[viewer_label] = pdb_text
        except Exception as exc:
            logger.warning(f"Could not read PDB {chosen}: {exc}")

    return pdb_frames


def _parse_refs_from_html(html_path: Optional[str]) -> List[Dict[str, Any]]:
    """Extract literature references from a per-sim HTML report (class='reference' divs)."""
    if not html_path or not Path(html_path).exists():
        return []
    try:
        html_text = Path(html_path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning(f"Could not read HTML {html_path}: {exc}")
        return []

    refs: List[Dict[str, Any]] = []
    ref_blocks = re.findall(r'<div class="reference">(.*?)</div>\s*\n\s*</div>', html_text, re.DOTALL)
    for block in ref_blocks:
        ref: Dict[str, Any] = {}

        # Title + URL from reference-title
        title_link_m = re.search(
            r'<div class="reference-title">[^<]*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block, re.DOTALL
        )
        if title_link_m:
            raw_url = title_link_m.group(1)
            ref["title"] = _html_mod.unescape(re.sub(r"<[^>]+>", "", title_link_m.group(2))).strip()
            if "doi.org/" in raw_url:
                ref["doi"] = raw_url.replace("https://doi.org/", "").replace("http://doi.org/", "")
            elif "pubmed" in raw_url:
                m = re.search(r"/(\d+)/?$", raw_url)
                if m:
                    ref["pmid"] = m.group(1)
        else:
            title_plain = re.search(r'<div class="reference-title">(.*?)</div>', block, re.DOTALL)
            if title_plain:
                raw = _html_mod.unescape(re.sub(r"<[^>]+>", "", title_plain.group(1))).strip()
                ref["title"] = re.sub(r"^\[\d+\]\s*", "", raw)

        # Authors
        auth_m = re.search(r'<div class="reference-authors">(.*?)</div>', block, re.DOTALL)
        if auth_m:
            authors_raw = _html_mod.unescape(re.sub(r"<[^>]+>", "", auth_m.group(1)))
            ref["authors"] = [a.strip() for a in authors_raw.split(",") if a.strip()]

        # Journal + year
        meta_m = re.search(r'<span class="journal">(.*?)</span>\s*\((\d{4})\)', block, re.DOTALL)
        if meta_m:
            ref["journal"] = _html_mod.unescape(re.sub(r"<[^>]+>", "", meta_m.group(1))).strip()
            ref["year"] = meta_m.group(2)

        # Explicit DOI
        doi_m = re.search(r'DOI: <a href="https://doi\.org/([^"]+)"', block)
        if doi_m and not ref.get("doi"):
            ref["doi"] = doi_m.group(1)

        # Explicit PMID
        pmid_m = re.search(r'PMID: <a href="https://pubmed[^"]*/(\d+)/"', block)
        if pmid_m and not ref.get("pmid"):
            ref["pmid"] = pmid_m.group(1)

        if ref.get("title"):
            refs.append(ref)

    return refs


def _score_ref_relevance(
    ref: Dict[str, Any],
    protein_terms: List[str],
    analysis_terms: List[str],
) -> int:
    """Score a reference for relevance. Higher = more relevant."""
    haystack = " ".join([
        ref.get("title", ""),
        ref.get("journal", ""),
        " ".join(ref.get("authors", [])),
    ]).lower()

    score = 0
    for term in protein_terms:
        if term.lower() in haystack:
            score += 3
    for term in analysis_terms:
        if term.lower() in haystack:
            score += 1
    return score


def _aggregate_literature(
    sim_resources: List[Dict[str, Any]],
    max_refs: int = 10,
    hypothesis_text: Optional[str] = None,
    protein_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Collect, deduplicate, and rank literature refs from all per-sim HTML reports.

    Refs are ranked by relevance to:
      (a) protein/system names derived from simulation labels
      (b) analysis method terms (RMSD, RMSF, etc.)
      (c) hypothesis / objective keywords from the user goal

    Returns at most *max_refs* references.

    Args:
        sim_resources: Per-simulation resource dicts with "label", "html_report_path", etc.
        max_refs: Maximum references to return.
        hypothesis_text: Optional free-text goal/hypothesis from the user to boost
                         papers that match the research objective.
    """
    # ── Build protein/system term list ───────────────────────────────────
    # Sim labels are the most reliable protein identifiers (derived from PDB stems).
    protein_terms: List[str] = []
    _GENERIC = {"rmsd", "rmsf", "protein", "simulation", "analysis",
                "molecular", "dynamics", "with", "without", "versus", "and"}
    for res in sim_resources:
        lbl = res.get("label", "")
        if lbl:
            # Split on underscores, hyphens, spaces — each part may be meaningful
            for part in re.split(r"[_\-\s]+", lbl):
                if len(part) >= 3 and part.lower() not in _GENERIC:
                    protein_terms.append(part)

        # Also harvest words from existing query strings
        for q in res.get("literature_queries", []):
            words = [w for w in re.split(r"\s+", q) if len(w) > 3
                     and w.lower() not in _GENERIC]
            protein_terms.extend(words)

        foci = res.get("report_focus", [])
        if isinstance(foci, list):
            for f in foci:
                protein_terms.extend(w for w in re.split(r"\s+", str(f)) if len(w) > 4)
        elif isinstance(foci, str) and foci:
            protein_terms.extend(w for w in re.split(r"\s+", foci) if len(w) > 4)

    # ── Build hypothesis/objective terms ─────────────────────────────────
    hyp_terms: List[str] = []
    _HYP_TRIGGERS = {
        "inhibit", "bind", "interact", "affect", "role", "function",
        "mechanism", "pathway", "stability", "flexibility", "alloster",
        "mutation", "mutant", "drug", "therapeutic", "disease", "cancer",
        "activate", "deactivate", "phosphorylat", "fold", "unfold",
        "aggregate", "dimer", "oligomer",
    }
    if hypothesis_text:
        htl = hypothesis_text.lower()
        for trig in _HYP_TRIGGERS:
            if trig in htl:
                hyp_terms.append(trig)
        # Also include meaningful non-stop words from the goal
        _STOP = {"please", "could", "would", "should", "compute", "calculate",
                 "trajectory", "simulation", "report", "generate", "agent"}
        for w in re.split(r"\W+", htl):
            if len(w) > 4 and w not in _STOP and w not in hyp_terms:
                hyp_terms.append(w)

    # ── Inject explicit protein name with boosted weight ─────────────────
    # Repeat the protein_name 3× so that any ref mentioning it scores high.
    if protein_name:
        for _part in re.split(r"[_\-\s]+", protein_name):
            if len(_part) >= 2:
                protein_terms.extend([_part] * 3)

    analysis_terms = ["RMSD", "RMSF", "radius of gyration", "molecular dynamics",
                      "MD simulation", "protein", "trajectory", "secondary structure"]

    all_refs: List[Dict[str, Any]] = []
    seen_dois: set = set()
    seen_pmids: set = set()
    seen_titles: set = set()

    for res in sim_resources:
        refs = _parse_refs_from_html(res.get("html_report_path"))
        for ref in refs:
            doi = ref.get("doi", "")
            pmid = ref.get("pmid", "")
            title_key = re.sub(r"\W+", "", ref.get("title", "").lower())[:60]

            if doi and doi in seen_dois:
                continue
            if pmid and pmid in seen_pmids:
                continue
            if title_key and title_key in seen_titles:
                continue

            if doi:
                seen_dois.add(doi)
            if pmid:
                seen_pmids.add(pmid)
            if title_key:
                seen_titles.add(title_key)

            ref["source"] = res["label"]
            # Combine protein, analysis, and hypothesis terms for scoring
            all_score_terms = protein_terms + analysis_terms + hyp_terms
            ref["_relevance"] = _score_ref_relevance(ref, all_score_terms, [])
            all_refs.append(ref)

    # Sort by relevance descending, then cap
    all_refs.sort(key=lambda r: r.get("_relevance", 0), reverse=True)
    for ref in all_refs:
        ref.pop("_relevance", None)

    return all_refs[:max_refs]


def _extract_mean_value(stats: Dict[str, Any], atype_lower: str) -> Optional[float]:
    """Extract the relevant mean value from a stats dict based on analysis type."""
    # Type-specific keys have priority (these are the actual keys produced by MD analysis tools)
    if "rmsd" in atype_lower:
        candidates = ("mean_rmsd_angstrom", "mean_rmsd_nm", "mean", "average")
    elif "rmsf" in atype_lower:
        candidates = ("mean_rmsf_angstrom", "mean_rmsf_nm", "mean", "average")
    elif "radius" in atype_lower or "gyration" in atype_lower or atype_lower == "rg":
        candidates = ("mean_rg_angstrom", "mean_rg_nm", "mean", "average")
    else:
        candidates = ("mean", "mean_angstrom", "mean_nm", "average")

    for key in candidates:
        v = stats.get(key)
        if isinstance(v, (int, float)) and v != 0.0:
            return float(v)
    # Allow zero only as last resort
    for key in candidates:
        v = stats.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _build_combined_final_impression(
    sims_summary: List[Dict[str, Any]],
    sim_resources: List[Dict[str, Any]],
) -> str:
    """Generate a synthesis paragraph comparing dynamics across simulations."""
    sim_rmsd: Dict[str, float] = {}
    sim_rmsf: Dict[str, float] = {}
    sim_rg: Dict[str, float] = {}

    for s in sims_summary:
        label = s["label"]
        st = _extract_stats(s["records"])
        for atype, vals in st.items():
            alow = atype.lower()
            val = _extract_mean_value(vals, alow)
            if val is None:
                continue
            if "rmsd" in alow:
                sim_rmsd[label] = val
            elif "rmsf" in alow:
                sim_rmsf[label] = val
            elif "radius" in alow or "gyration" in alow or alow == "rg":
                sim_rg[label] = val

    resource_map = {r["label"]: r for r in sim_resources}
    parts: List[str] = []

    labels_str = ", ".join(s["label"] for s in sims_summary)
    n_sims = len(sims_summary)
    parts.append(
        f"This combined analysis compared {n_sims} molecular dynamics "
        f"simulation{'s' if n_sims != 1 else ''} ({labels_str}). "
        "The cross-simulation comparison reveals both shared trends and notable "
        "differences in structural dynamics."
    )

    if sim_rmsd:
        rmsd_sorted = sorted(sim_rmsd.items(), key=lambda x: x[1])
        most_stable = rmsd_sorted[0]
        least_stable = rmsd_sorted[-1]
        vals_str = "; ".join(f"{lbl}: {v:.3f}" for lbl, v in rmsd_sorted)
        parts.append(
            f"**Structural stability (RMSD):** {vals_str} Å. "
            f"Simulation **{most_stable[0]}** shows the greatest structural stability "
            f"(lowest average RMSD = {most_stable[1]:.3f} Å), while **{least_stable[0]}** "
            f"exhibits the largest conformational deviations from the reference structure."
        )

    if sim_rmsf:
        rmsf_sorted = sorted(sim_rmsf.items(), key=lambda x: x[1])
        most_rigid = rmsf_sorted[0]
        most_flexible = rmsf_sorted[-1]
        vals_str = "; ".join(f"{lbl}: {v:.3f}" for lbl, v in rmsf_sorted)
        parts.append(
            f"**Backbone flexibility (RMSF):** {vals_str} Å. "
            f"Simulation **{most_rigid[0]}** has the most rigid backbone, whereas "
            f"**{most_flexible[0]}** shows higher per-residue fluctuations, "
            "suggesting increased local flexibility."
        )

    if sim_rg:
        rg_sorted = sorted(sim_rg.items(), key=lambda x: x[1])
        most_compact = rg_sorted[0]
        least_compact = rg_sorted[-1]
        vals_str = "; ".join(f"{lbl}: {v:.3f}" for lbl, v in rg_sorted)
        parts.append(
            f"**Structural compactness (Rg):** {vals_str} Å. "
            f"Simulation **{most_compact[0]}** maintains the most compact fold "
            f"(Rg = {most_compact[1]:.3f} Å), while **{least_compact[0]}** displays "
            f"a somewhat expanded conformation (Rg = {least_compact[1]:.3f} Å)."
        )

    for res in sim_resources:
        focus = res.get("report_focus", "")
        if focus and len(focus) > 20:
            parts.append(f"**{res['label']} key observations:** {focus}")

    if sim_rmsd or sim_rmsf or sim_rg:
        if sim_rmsd:
            stable = min(sim_rmsd, key=lambda k: sim_rmsd[k])
            parts.append(
                f"Overall, simulation **{stable}** demonstrates the most consistent "
                f"structural behavior across the trajectory. These results highlight "
                "the influence of system composition and simulation conditions on "
                "the dynamic properties of the molecular system."
            )
    else:
        parts.append(
            "Detailed quantitative comparison was limited by available analysis data. "
            "Refer to individual simulation reports for system-specific findings."
        )

    return "\n\n".join(parts)


def _build_task_description_html(
    enriched_prompt: str,
    sim_resources: Optional[List[Dict[str, Any]]] = None,
    user_goal: Optional[str] = None,
    protein_name: Optional[str] = None,
) -> str:
    """Render a structured task description card.

    Layout:
      - Protein / System badge (if protein_name provided)
      - Overall Goal: the original user_goal text (clean, concise)
      - Detailed Technical Objectives: collapsible block with enriched_prompt
      - Per-Simulation Analysis Objectives: table from per-sim reasoning / report_focus
    """
    if not enriched_prompt and not user_goal and not sim_resources:
        return ""

    parts: List[str] = []
    parts.append('<div class="task-box">')
    parts.append('<div class="task-box-header">&#128203; Study Objectives &amp; Task Description</div>')
    parts.append('<div class="task-box-body">')

    # ── Protein / System badge ────────────────────────────────────────────
    if protein_name:
        parts.append(
            f'<div style="display:inline-block;background:#ede9fe;color:#5b21b6;'
            f'border:1px solid #c4b5fd;border-radius:16px;padding:4px 14px;'
            f'font-size:13px;font-weight:700;margin-bottom:12px;">'
            f'&#129516; Protein / System:&nbsp;<span style="color:#7c3aed;">'
            f'{_html_mod.escape(protein_name)}</span></div>'
        )

    # ── Overall Goal — supervisor's enriched/rephrased goal ──────────────
    # Show enriched_prompt as the primary authoritative goal statement.
    # If no enriched prompt, fall back to user_goal.
    primary_goal = (enriched_prompt or user_goal or "").strip()
    if primary_goal:
        parts.append('<div style="margin-bottom:14px;">')
        parts.append('<strong style="color:#5b21b6;">&#128269; Overall Goal</strong><br>')
        parts.append(
            f'<p style="margin:6px 0 0 0;line-height:1.6;color:#1e1b4b;">'
            f'{_html_mod.escape(primary_goal)}</p>'
        )
        parts.append('</div>')

    # ── Original User Request (collapsible) ──────────────────────────────
    # Show the raw user_goal in a collapsible so it's accessible but not
    # dominant.  Only render when it differs from the enriched version.
    if user_goal and user_goal.strip() != primary_goal:
        parts.append(
            '<details style="margin-bottom:14px;">'
            '<summary style="cursor:pointer;color:#7c3aed;font-weight:600;'
            'list-style:none;user-select:none;">&#128221; Original User Request '
            '<span style="font-size:11px;font-weight:400;color:#9ca3af;">'
            '(click to expand)</span></summary>'
        )
        parts.append('<div style="margin-top:8px;padding:10px 14px;background:#faf9ff;'
                     'border-left:3px solid #c4b5fd;border-radius:4px;">')
        parts.append(
            f'<p style="margin:0;line-height:1.6;color:#374151;font-size:13px;">'
            f'{_html_mod.escape(user_goal.strip())}</p>'
        )
        parts.append('</div></details>')

    # ── Per-simulation analysis objectives (from execution_plan / reasoning) ──
    if sim_resources:
        parts.append('<hr style="border:none;border-top:1px dashed #c4b5fd;margin:10px 0;">')
        parts.append(
            '<strong style="color:#5b21b6;">&#128296; Per-Simulation Analysis Objectives</strong>'
        )
        parts.append('<table style="width:100%;border-collapse:collapse;margin-top:10px;font-size:13.5px;">')
        parts.append('<tr style="background:#ede9fe;">')
        parts.append('<th style="padding:6px 10px;text-align:left;color:#5b21b6;">Simulation</th>')
        parts.append('<th style="padding:6px 10px;text-align:left;color:#5b21b6;">Analysis Goals</th>')
        parts.append('</tr>')

        for idx, res in enumerate(sim_resources):
            label = res.get("label", "?")
            foci = res.get("report_focus", [])
            reasoning = res.get("reasoning", "")

            if isinstance(foci, list) and foci:
                focus_items = foci[:4]
            elif isinstance(foci, str) and foci:
                focus_items = [foci]
            elif reasoning:
                focus_items = [s.strip() for s in re.split(r"(?<=[.!?])\s+", reasoning.strip())
                               if len(s.strip()) > 20][:2]
            else:
                focus_items = []

            if focus_items:
                cell_html = "<ul style='margin:2px 0 2px 18px;padding:0;'>" + \
                    "".join(f"<li style='margin:2px 0'>{_html_mod.escape(str(f))}</li>"
                             for f in focus_items) + "</ul>"
            else:
                cell_html = "<em style='color:#9ca3af;'>No objectives recorded</em>"

            row_bg = "background:#faf9ff;" if idx % 2 == 0 else "background:#f5f3ff;"
            parts.append(f'<tr style="{row_bg}">')
            parts.append(f'<td style="padding:7px 10px;font-weight:700;color:#7c3aed;white-space:nowrap;">{_html_mod.escape(label)}</td>')
            parts.append(f'<td style="padding:7px 10px;">{cell_html}</td>')
            parts.append('</tr>')

        parts.append('</table>')

    parts.append('</div>')  # task-box-body
    parts.append('</div>')  # task-box
    parts.append('')
    return "\n".join(parts)


def _build_3d_viewer_html(pdb_frames: Dict[str, str]) -> str:
    """Build interactive 3Dmol.js viewer section for multiple simulations."""
    try:
        from src.reporter.html_generator import _build_3d_viewer_section
        return _build_3d_viewer_section(pdb_frames)
    except Exception as exc:
        logger.warning(f"Could not import _build_3d_viewer_section: {exc}")
        return ""


def _build_literature_html(refs: List[Dict[str, Any]]) -> str:
    """Render aggregated literature references."""
    if not refs:
        return ""
    display = refs  # already capped at max_refs by _aggregate_literature

    parts = ["<h2>&#128218; Literature References</h2>"]
    parts.append(
        f"<p>Top {len(display)} most relevant {'reference' if len(display) == 1 else 'references'} "
        f"aggregated and ranked from individual simulation reports:</p>"
    )

    for idx, ref in enumerate(display, 1):
        title = _html_mod.escape(ref.get("title", "Unknown"))
        doi = ref.get("doi", "")
        pmid = ref.get("pmid", "")
        source = ref.get("source", "")
        source_badge = (
            f'<span class="sim-badge">{_html_mod.escape(source)}</span>' if source else ""
        )

        parts.append('<div class="reference">')

        # Title with link
        if doi:
            parts.append(
                f'<div class="reference-title">[{idx}] '
                f'<a href="https://doi.org/{_html_mod.escape(doi)}" target="_blank">'
                f'{title}</a>{source_badge}</div>'
            )
        elif pmid:
            parts.append(
                f'<div class="reference-title">[{idx}] '
                f'<a href="https://pubmed.ncbi.nlm.nih.gov/{_html_mod.escape(pmid)}/" target="_blank">'
                f'{title}</a>{source_badge}</div>'
            )
        else:
            parts.append(f'<div class="reference-title">[{idx}] {title}{source_badge}</div>')

        # Authors
        authors = ref.get("authors", [])
        if authors:
            author_str = ", ".join(authors[:5])
            if len(authors) > 5:
                author_str += " et al."
            parts.append(f'<div class="reference-authors">{_html_mod.escape(author_str)}</div>')

        # Journal + year
        journal = ref.get("journal", "")
        year = ref.get("year", "")
        if journal or year:
            meta = ""
            if journal:
                meta += f'<span class="journal">{_html_mod.escape(journal)}</span>'
            if year:
                meta += f" ({year})"
            parts.append(f'<div class="reference-meta">{meta}</div>')

        # DOI / PMID links
        id_parts = []
        if doi:
            id_parts.append(
                f'DOI: <a href="https://doi.org/{_html_mod.escape(doi)}" target="_blank">'
                f'{_html_mod.escape(doi)}</a>'
            )
        if pmid:
            id_parts.append(
                f'PMID: <a href="https://pubmed.ncbi.nlm.nih.gov/{_html_mod.escape(pmid)}/" target="_blank">'
                f'{_html_mod.escape(pmid)}</a>'
            )
        if id_parts:
            parts.append(f'<div class="reference-doi">{", ".join(id_parts)}</div>')

        parts.append("</div>")

    return "\n".join(parts)


def _build_final_impression_html(text: str, refs: List[Dict[str, Any]]) -> str:
    """Render the combined final impression paragraph with bold/citation support."""
    if not text:
        return ""

    parts = [
        "<h2>&#127919; Combined Final Impression</h2>",
        '<div class="final-impression">',
    ]

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            paragraph = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", paragraph)
            parts.append(f"<p>{paragraph}</p>")

    parts.append("</div>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML building helpers (statistics & overlay plots)
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    margin: 0; padding: 0;
    background: linear-gradient(135deg, #f0f4ff 0%, #e8f4f8 100%);
    color: #1f2937; min-height: 100vh;
}
.container {
    max-width: 1200px; margin: 20px auto 40px; padding: 30px 28px 60px;
    background: white;
    box-shadow: 0 4px 24px rgba(0,0,0,0.10);
    border-radius: 12px;
}
h1 {
    color: #1e3a8a; border-bottom: 4px solid #3b82f6;
    padding-bottom: 15px; margin-bottom: 30px; font-size: 2em;
}
h2 {
    color: #1e40af; margin-top: 40px; border-bottom: 2px solid #93c5fd;
    padding-bottom: 10px; font-size: 1.5em;
}
h3 { color: #1e40af; font-size: 1.15em; margin-top: 18px; }
.header-meta {
    background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
    padding: 18px 22px; border-radius: 8px; margin: 20px 0;
    border-left: 4px solid #3b82f6;
}
.header-meta p { margin: 6px 0; font-size: 15px; }
/* ---- Task description card ---- */
.task-box {
    margin: 24px 0; border-radius: 10px;
    border: 1px solid #c4b5fd; border-left: 5px solid #7c3aed; overflow: hidden;
}
.task-box-header {
    background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
    padding: 12px 20px; color: #5b21b6; font-weight: 700; font-size: 1em;
}
.task-box-body {
    padding: 16px 24px; background: #faf9ff; color: #3b0764;
    font-size: 14.5px; line-height: 1.75;
}
.task-box-body ul { margin: 6px 0; padding-left: 22px; }
.task-box-body li { margin: 5px 0; }
/* ---- Tables ---- */
table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14px; }
th { background: #1e3a8a; color: white; padding: 10px 14px; text-align: left; }
td { border: 1px solid #e5e7eb; padding: 9px 14px; }
tr:nth-child(even) td { background: #f3f8ff; }
tr:hover td { background: #dbeafe; transition: background 0.15s; }
/* ---- Overlay plot grid ---- */
.plot-grid { display: flex; flex-wrap: wrap; gap: 18px; margin: 20px 0; }
.plot-card {
    background: white; border: 1px solid #d1d5db; border-radius: 8px;
    padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    flex: 1 1 420px; text-align: center;
}
.plot-card img { width: 100%; height: auto; border-radius: 5px; }
.plot-card p { margin: 8px 0 0; font-size: 13px; color: #6b7280; font-style: italic; }
/* ---- Section divider ---- */
.section-divider {
    height: 2px;
    background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
    margin: 40px 0;
}
/* ---- 3D Viewer (copied from html_generator) ---- */
.viewer-section {
    margin: 30px 0; padding: 25px; border-radius: 10px;
    background: #f0f4ff; border: 1px solid #c7d2fe; border-left: 5px solid #6366f1;
}
.viewer-container {
    position: relative; width: 100%; height: 550px; border-radius: 8px;
    overflow: hidden; background: #1a1a2e; box-shadow: 0 2px 12px rgba(0,0,0,0.15);
}
.viewer-controls {
    display: flex; flex-wrap: wrap; gap: 8px; margin: 15px 0; align-items: center;
}
.viewer-controls label { font-size: 13px; font-weight: 600; color: #4338ca; margin-right: 4px; }
.viewer-controls select, .viewer-controls button {
    padding: 6px 14px; border: 1px solid #c7d2fe; border-radius: 6px;
    background: white; font-size: 13px; cursor: pointer;
}
.viewer-controls button { background: #6366f1; color: white; border: none; font-weight: 600; }
.viewer-controls button:hover { background: #4f46e5; }
/* ---- Literature ---- */
.reference {
    margin: 15px 0; padding: 16px 20px; background: #f9fafb;
    border-left: 4px solid #6b7280; border-radius: 6px;
}
.reference-title { font-weight: 700; color: #1f2937; font-size: 15px; margin-bottom: 5px; }
.reference-title a { color: #1e40af; text-decoration: none; }
.reference-title a:hover { text-decoration: underline; }
.reference-authors { color: #4b5563; font-size: 13px; margin: 3px 0; }
.reference-meta { font-size: 13px; color: #4b5563; margin: 3px 0; }
.reference-meta .journal { font-style: italic; }
.reference-doi { font-size: 12px; color: #6b7280; margin-top: 4px; }
.reference-doi a { color: #2563eb; }
.sim-badge {
    display: inline-block; padding: 1px 7px; border-radius: 5px;
    font-size: 11px; font-weight: 600; margin-left: 6px;
    background: #dbeafe; color: #1e40af;
}
/* ---- Final impression ---- */
.final-impression {
    margin: 20px 0; padding: 28px 30px; border-radius: 10px;
    background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
    border: 1px solid #fde68a; border-left: 5px solid #f59e0b;
}
.final-impression p { margin: 10px 0; line-height: 1.85; font-size: 16px; }
.final-impression strong { color: #92400e; }
/* ---- Stats section ---- */
.stats-section {
    margin: 20px 0; padding: 20px; background: #f9fafb;
    border-radius: 8px; border: 1px solid #e5e7eb;
}
/* ---- Footer ---- */
footer {
    text-align: center; padding: 20px; font-size: 13px; color: #9ca3af;
    margin-top: 40px; border-top: 1px solid #e5e7eb;
}
/* ---- Comparative Dynamics Summary panels ---- */
.dyn-panel-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin: 20px 0;
}
.dyn-panel {
    border: 1px solid #e0e7ff;
    border-top: 4px solid #6366f1;
    border-radius: 8px;
    overflow: hidden;
    background: white;
    box-shadow: 0 2px 8px rgba(99,102,241,0.07);
}
.dyn-panel.panel-full {
    grid-column: 1 / -1;
}
.panel-header {
    background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.panel-badge {
    background: #6366f1;
    color: white;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 9px;
    border-radius: 10px;
    white-space: nowrap;
}
.panel-title {
    font-weight: 700;
    color: #312e81;
    font-size: 14px;
}
.panel-subtitle {
    font-size: 12px;
    color: #6b7280;
    padding: 4px 16px 6px;
    background: #fafaff;
    border-bottom: 1px solid #e0e7ff;
    font-style: italic;
}
.panel-body {
    padding: 14px 16px;
    min-height: 80px;
}
.panel-missing {
    text-align: center;
    color: #9ca3af;
    font-size: 13px;
    padding: 30px 20px;
    font-style: italic;
}
"""


def _build_stats_section(sims_summary: List[Dict[str, Any]]) -> str:
    """Generate an HTML comparison table of per-sim statistics for every analysis type."""
    all_types: List[str] = []
    for s in sims_summary:
        for t in _extract_stats(s["records"]):
            if t not in all_types:
                all_types.append(t)

    if not all_types:
        return "<p><em>No per-simulation statistics available.</em></p>\n"

    html_parts: List[str] = []
    for atype in all_types:
        stat_keys: List[str] = []
        for s in sims_summary:
            st = _extract_stats(s["records"]).get(atype, {})
            if st:
                stat_keys = [k for k in st if isinstance(st[k], (int, float, str))]
                break
        if not stat_keys:
            continue

        html_parts.append(f"<h3>{_html_mod.escape(atype)}</h3>\n<table>\n")
        header_cols = "".join(
            f"<th>{_html_mod.escape(k.replace('_', ' ').title())}</th>" for k in stat_keys
        )
        html_parts.append(f"<tr><th>Simulation</th>{header_cols}</tr>\n")

        for s in sims_summary:
            st = _extract_stats(s["records"]).get(atype, {})
            cells = "".join(
                f"<td>{st.get(k, 'N/A')}</td>" for k in stat_keys
            )
            html_parts.append(f"<tr><td><b>{_html_mod.escape(s['label'])}</b></td>{cells}</tr>\n")

        html_parts.append("</table>\n")

    return "".join(html_parts)


def _build_plots_section(overlay_plots: List[str]) -> str:
    """Embed overlay images as base64 data-URIs in a responsive grid."""
    if not overlay_plots:
        return "<p><em>No overlay plots found.</em></p>\n"

    cards: List[str] = []
    for fpath in overlay_plots:
        uri = _encode_image(fpath)
        if uri is None:
            continue
        fname = Path(fpath).name
        metric = fname.replace("_overlay.png", "").replace("_", " ").upper()
        cards.append(
            f'<div class="plot-card">'
            f'<img src="{uri}" alt="{metric} overlay" loading="lazy">'
            f'<p>{metric} Overlay — all simulations</p>'
            f'</div>\n'
        )

    if not cards:
        return "<p><em>Could not encode overlay plots.</em></p>\n"

    return '<div class="plot-grid">\n' + "".join(cards) + "</div>\n"


# ---------------------------------------------------------------------------
# Comparative Dynamics Summary — multi-panel helpers
# ---------------------------------------------------------------------------

def _find_overlay_by_type(overlay_plots: List[str], keyword: str) -> Optional[str]:
    """Return the first overlay plot path whose filename contains *keyword*."""
    kl = keyword.lower()
    for p in overlay_plots:
        if kl in Path(p).name.lower():
            return p
    return None


def _find_per_sim_plots(
    sim_dirs: List[str],
    labels: List[str],
    keyword: str,
) -> List[Tuple[str, str]]:
    """Search each sim's analysis directory for a plot matching *keyword*.

    Returns a list of (label, filepath) pairs, at most one per simulation.
    """
    kl = keyword.lower()
    results: List[Tuple[str, str]] = []
    for sim_dir, label in zip(sim_dirs, labels):
        analysis_dir = Path(sim_dir) / "analysis"
        if not analysis_dir.exists():
            continue
        for png in sorted(analysis_dir.glob("*.png")):
            if kl in png.name.lower():
                results.append((label, str(png)))
                break
    return results


def _build_summary_bar_chart_svg(sims_summary: List[Dict[str, Any]]) -> str:
    """Generate an inline SVG grouped bar chart for stability/flexibility ranking (Panel F)."""
    # Collect per-sim metric means
    sim_data: List[Dict[str, Any]] = []
    for s in sims_summary:
        st = _extract_stats(s["records"])
        rmsd_val = rmsf_val = rg_val = None
        for atype, vals in st.items():
            alow = atype.lower()
            v = _extract_mean_value(vals, alow)
            if v is None:
                continue
            if "rmsd" in alow and rmsd_val is None:
                rmsd_val = v
            elif "rmsf" in alow and rmsf_val is None:
                rmsf_val = v
            elif ("radius" in alow or "gyration" in alow or alow == "rg") and rg_val is None:
                rg_val = v
        sim_data.append({"label": s["label"], "rmsd": rmsd_val, "rmsf": rmsf_val, "rg": rg_val})

    metrics = []
    if any(d["rmsd"] is not None for d in sim_data):
        metrics.append(("RMSD (\u00c5)", "rmsd", "#3b82f6", "Stability"))
    if any(d["rmsf"] is not None for d in sim_data):
        metrics.append(("RMSF (\u00c5)", "rmsf", "#ef4444", "Flexibility"))
    if any(d["rg"] is not None for d in sim_data):
        metrics.append(("Rg (\u00c5)", "rg", "#10b981", "Compactness"))

    if not metrics:
        return ""

    n_sims = len(sim_data)
    n_metrics = len(metrics)

    # SVG layout constants
    svgw = 760
    ml, mr, mt, mb = 72, 20, 50, 90
    pw = svgw - ml - mr
    ph = 230

    svgh = mt + ph + mb
    group_w = pw / max(n_sims, 1)
    bar_pad = 8
    bar_total = group_w - bar_pad * 2
    bw = max((bar_total / max(n_metrics, 1)) - 4, 4)

    # Y-axis scale
    all_vals = [d[k] for d in sim_data for _, k, _, _ in metrics if d.get(k) is not None]
    ymax = (max(all_vals) * 1.18) if all_vals else 1.0
    if ymax == 0:
        ymax = 1.0

    def val_to_y(v: float) -> float:
        return ph - (v / ymax) * ph + mt

    def val_to_h(v: float) -> float:
        return (v / ymax) * ph

    lines: List[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svgw} {svgh}" '
        f'style="width:100%;max-width:{svgw}px;height:auto;display:block;margin:auto;">'
    )
    lines.append(f'<rect width="{svgw}" height="{svgh}" fill="white" rx="4"/>')
    lines.append(
        f'<text x="{svgw // 2}" y="22" text-anchor="middle" font-size="13" '
        f'font-weight="700" fill="#1e3a8a" font-family="Segoe UI,Arial,sans-serif">'
        f'Panel F \u2014 Stability &amp; Flexibility Summary Ranking</text>'
    )

    # Y-axis gridlines + labels
    for i in range(6):
        yval = ymax * i / 5
        ypos = val_to_y(yval)
        lines.append(
            f'<line x1="{ml}" y1="{ypos:.1f}" x2="{ml + pw}" y2="{ypos:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
        )
        lines.append(
            f'<text x="{ml - 6}" y="{ypos + 4:.1f}" text-anchor="end" font-size="10" '
            f'fill="#6b7280" font-family="Segoe UI,Arial,sans-serif">{yval:.2f}</text>'
        )

    # Axes
    lines.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="#9ca3af" stroke-width="1.5"/>')
    lines.append(f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="#9ca3af" stroke-width="1.5"/>')

    # Y-axis unit label
    mid_y = mt + ph // 2
    lines.append(
        f'<text x="14" y="{mid_y}" text-anchor="middle" '
        f'transform="rotate(-90,14,{mid_y})" font-size="11" fill="#374151" '
        f'font-family="Segoe UI,Arial,sans-serif">Value (\u00c5)</text>'
    )

    # Bars
    for si, d in enumerate(sim_data):
        gx = ml + si * group_w + bar_pad
        for mi, (metric_label, key, color, _role) in enumerate(metrics):
            v = d.get(key)
            if v is None or v < 0:
                continue
            bx = gx + mi * (bw + 4)
            by = val_to_y(v)
            bh = val_to_h(v)
            safe_lbl = _html_mod.escape(d["label"])
            safe_metric = _html_mod.escape(metric_label)
            lines.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                f'fill="{color}" rx="2" opacity="0.85">'
                f'<title>{safe_lbl} {safe_metric}: {v:.3f}</title></rect>'
            )
            label_y = by - 3
            if label_y < mt + 12:
                label_y = by + 12
            lines.append(
                f'<text x="{bx + bw / 2:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                f'font-size="8" fill="{color}" font-weight="600" '
                f'font-family="Segoe UI,Arial,sans-serif">{v:.2f}</text>'
            )

        # X-axis sim label (rotated)
        lx = ml + si * group_w + group_w / 2
        ly = mt + ph + 14
        safe_sim = _html_mod.escape(d["label"])
        lines.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="end" '
            f'transform="rotate(-40,{lx:.1f},{ly:.1f})" font-size="11" '
            f'fill="#1f2937" font-weight="600" '
            f'font-family="Segoe UI,Arial,sans-serif">{safe_sim}</text>'
        )

    # Legend
    legend_y = mt + ph + 64
    for mi, (metric_label, _key, color, role) in enumerate(metrics):
        lx = ml + mi * 170
        lines.append(f'<rect x="{lx}" y="{legend_y}" width="14" height="14" fill="{color}" rx="2"/>')
        lines.append(
            f'<text x="{lx + 18}" y="{legend_y + 11}" font-size="11" fill="#374151" '
            f'font-family="Segoe UI,Arial,sans-serif">'
            f'{_html_mod.escape(metric_label)} ({role})</text>'
        )

    lines.append('</svg>')
    return "\n".join(lines)


def _build_ranking_summary_table(sims_summary: List[Dict[str, Any]]) -> str:
    """Generate a concise dynamics ranking summary table below the panel grid."""
    rows_data: List[Dict[str, Any]] = []
    for s in sims_summary:
        st = _extract_stats(s["records"])
        rmsd_val = rmsf_val = rg_val = None
        for atype, vals in st.items():
            alow = atype.lower()
            v = _extract_mean_value(vals, alow)
            if v is None:
                continue
            if "rmsd" in alow and rmsd_val is None:
                rmsd_val = v
            elif "rmsf" in alow and rmsf_val is None:
                rmsf_val = v
            elif ("radius" in alow or "gyration" in alow or alow == "rg") and rg_val is None:
                rg_val = v
        rows_data.append({"label": s["label"], "rmsd": rmsd_val, "rmsf": rmsf_val, "rg": rg_val})

    if not any(r["rmsd"] is not None or r["rmsf"] is not None for r in rows_data):
        return ""

    def rank_asc(key: str) -> Dict[str, int]:
        """Rank simulations by *key* ascending (lower = rank 1)."""
        valid = sorted(
            [(r["label"], r[key]) for r in rows_data if r.get(key) is not None],
            key=lambda x: x[1],
        )
        return {lbl: i + 1 for i, (lbl, _) in enumerate(valid)}

    def rank_desc(key: str) -> Dict[str, int]:
        """Rank simulations by *key* descending (higher = rank 1)."""
        valid = sorted(
            [(r["label"], r[key]) for r in rows_data if r.get(key) is not None],
            key=lambda x: x[1],
            reverse=True,
        )
        return {lbl: i + 1 for i, (lbl, _) in enumerate(valid)}

    rmsd_rank = rank_asc("rmsd")    # lower RMSD → more stable
    rmsf_rank = rank_desc("rmsf")   # higher RMSF → more flexible
    rg_rank = rank_asc("rg")        # lower Rg → more compact

    medals: Dict[int, str] = {1: "&#129351;", 2: "&#129352;", 3: "&#129353;"}

    def medal(r: int) -> str:
        return medals.get(r, f"&nbsp;#{r}")

    table_rows = ""
    for r in rows_data:
        lbl = r["label"]
        rmsd_c = (
            f'{r["rmsd"]:.3f}&thinsp;\u00c5 <small style="color:#6b7280;">'
            f'{medal(rmsd_rank.get(lbl, 99))}</small>'
            if r["rmsd"] is not None else "\u2014"
        )
        rmsf_c = (
            f'{r["rmsf"]:.3f}&thinsp;\u00c5 <small style="color:#6b7280;">'
            f'{medal(rmsf_rank.get(lbl, 99))}</small>'
            if r["rmsf"] is not None else "\u2014"
        )
        rg_c = (
            f'{r["rg"]:.3f}&thinsp;\u00c5 <small style="color:#6b7280;">'
            f'{medal(rg_rank.get(lbl, 99))}</small>'
            if r["rg"] is not None else "\u2014"
        )
        if r["rmsd"] is not None and rmsd_rank.get(lbl) == 1:
            verdict = '<span style="color:#059669;font-weight:700;">Most Stable</span>'
        elif r["rmsf"] is not None and rmsf_rank.get(lbl) == 1:
            verdict = '<span style="color:#f59e0b;font-weight:700;">Most Flexible</span>'
        elif r["rg"] is not None and rg_rank.get(lbl) == 1:
            verdict = '<span style="color:#6366f1;font-weight:700;">Most Compact</span>'
        else:
            verdict = "\u2014"
        table_rows += (
            f"<tr>"
            f"<td><strong>{_html_mod.escape(lbl)}</strong></td>"
            f"<td>{rmsd_c}</td>"
            f"<td>{rmsf_c}</td>"
            f"<td>{rg_c}</td>"
            f"<td>{verdict}</td>"
            f"</tr>\n"
        )

    return (
        '<h3>&#127942; Dynamics Ranking Summary</h3>\n'
        '<table style="font-size:13.5px;">\n'
        '<tr><th>Simulation</th>'
        '<th>Mean RMSD&nbsp;&#8595; (stability)</th>'
        '<th>Mean RMSF&nbsp;&#8593; (flexibility)</th>'
        '<th>Mean Rg&nbsp;&#8595; (compactness)</th>'
        '<th>Verdict</th></tr>\n'
        + table_rows
        + '</table>\n'
    )


def _build_comparative_dynamics_section(
    overlay_plots: List[str],
    sims_summary: List[Dict[str, Any]],
    sim_dirs: List[str],
    labels: List[str],
) -> str:
    """Build the Comparative Dynamics Summary multi-panel HTML section.

    Panel A — RMSD overlay (structural stability over time)
    Panel B — RMSF overlay (per-residue backbone flexibility)
    Panel C — Rg comparison (structural compactness over time)
    Panel D — ATP/ligand pocket distance (active-site geometry)
    Panel E — DCCM representative heatmaps (collective motions, one per sim)
    Panel F — Summary bar chart generated from per-sim statistics
    """

    def _panel(
        panel_id: str,
        title: str,
        subtitle: str,
        body: str,
        full_width: bool = False,
    ) -> str:
        cls = ' class="dyn-panel panel-full"' if full_width else ' class="dyn-panel"'
        return (
            f'<div{cls}>'
            f'<div class="panel-header">'
            f'<span class="panel-badge">Panel {_html_mod.escape(panel_id)}</span>'
            f'<span class="panel-title">{_html_mod.escape(title)}</span>'
            f'</div>'
            f'<div class="panel-subtitle">{subtitle}</div>'
            f'<div class="panel-body">{body}</div>'
            f'</div>'
        )

    def _img(fpath: str, alt: str) -> str:
        uri = _encode_image(fpath)
        if uri is None:
            return f'<p class="panel-missing">Image not available: {_html_mod.escape(Path(fpath).name)}</p>'
        return (
            f'<img src="{uri}" alt="{_html_mod.escape(alt)}" loading="lazy" '
            f'style="width:100%;height:auto;border-radius:4px;">'
        )

    def _missing(msg: str = "No data available") -> str:
        return f'<div class="panel-missing"><span>&#128202;</span><br>{_html_mod.escape(msg)}</div>'

    # ── Panel A: RMSD overlay ────────────────────────────────────────────
    rmsd_path = _find_overlay_by_type(overlay_plots, "rmsd")
    panel_a = _panel(
        "A", "RMSD Overlay",
        "Root-mean-square deviation from reference structure across all simulations",
        _img(rmsd_path, "RMSD overlay") if rmsd_path else _missing("No RMSD overlay found"),
    )

    # ── Panel B: RMSF overlay ────────────────────────────────────────────
    rmsf_path = _find_overlay_by_type(overlay_plots, "rmsf")
    panel_b = _panel(
        "B", "RMSF Overlay",
        "Per-residue C\u03b1 backbone flexibility across all simulations",
        _img(rmsf_path, "RMSF overlay") if rmsf_path else _missing("No RMSF overlay found"),
    )

    # ── Panel C: Rg comparison ───────────────────────────────────────────
    rg_path = _find_overlay_by_type(overlay_plots, "rg")
    if not rg_path:
        rg_path = _find_overlay_by_type(overlay_plots, "gyration")
    panel_c = _panel(
        "C", "Radius of Gyration (Rg)",
        "Structural compactness over simulation time — all simulations",
        _img(rg_path, "Rg overlay") if rg_path else _missing("No Rg overlay found"),
    )

    # ── Panel D: ATP/ligand pocket distance ──────────────────────────────
    pocket_plots = _find_per_sim_plots(sim_dirs, labels, "pocket_distance")
    if not pocket_plots:
        pocket_plots = _find_per_sim_plots(sim_dirs, labels, "ligand_pocket")
    if not pocket_plots:
        pocket_plots = _find_per_sim_plots(sim_dirs, labels, "atp_distance")
    if not pocket_plots:
        pocket_plots = _find_per_sim_plots(sim_dirs, labels, "distance")

    if pocket_plots:
        rep_label, rep_path = pocket_plots[0]
        pocket_body = (
            f'<p style="font-size:12px;color:#6b7280;margin:0 0 6px 0;">'
            f'Representative: <strong>{_html_mod.escape(rep_label)}</strong></p>'
            + _img(rep_path, f"Pocket distance {rep_label}")
        )
        if len(pocket_plots) > 1:
            pocket_body += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">'
            for lbl, pth in pocket_plots[1:]:
                uri = _encode_image(pth)
                if uri:
                    pocket_body += (
                        f'<div style="flex:1 1 110px;text-align:center;">'
                        f'<img src="{uri}" alt="{_html_mod.escape(lbl)}" '
                        f'style="width:100%;border-radius:3px;">'
                        f'<p style="font-size:10px;color:#6b7280;margin:2px 0;">'
                        f'{_html_mod.escape(lbl)}</p></div>'
                    )
            pocket_body += '</div>'
    else:
        pocket_body = _missing("No pocket distance data found")

    panel_d = _panel(
        "D", "ATP Pocket / Active Site Distance",
        "Key inter-residue distances in the nucleotide or ligand binding pocket",
        pocket_body,
    )

    # ── Panel E: DCCM heatmaps (per-sim) + comparison/difference (combined) ─
    dccm_per_sim = _find_per_sim_plots(sim_dirs, labels, "dccm_heatmap")
    if not dccm_per_sim:
        dccm_per_sim = _find_per_sim_plots(sim_dirs, labels, "dccm")

    # Separate combined DCCM plots (comparison / difference) from overlay list
    _dccm_combined_plots = [
        p for p in overlay_plots
        if "dccm" in Path(p).name.lower()
        and Path(p).name not in {Path(pp).name for _, pp in dccm_per_sim}
    ]

    if not dccm_per_sim and not _dccm_combined_plots:
        # Last fallback: any dccm overlay
        dccm_ov = _find_overlay_by_type(overlay_plots, "dccm")
        dccm_body = _img(dccm_ov, "DCCM heatmap") if dccm_ov else _missing("No DCCM heatmaps found")
    else:
        dccm_body = ""
        # Per-sim individual heatmaps
        if dccm_per_sim:
            dccm_body += (
                '<p style="font-weight:700;color:#1e40af;margin:0 0 8px;">Individual Simulations</p>'
                '<div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;">'
            )
            for lbl, dpath in dccm_per_sim:
                uri = _encode_image(dpath)
                if uri:
                    dccm_body += (
                        f'<div style="flex:1 1 180px;max-width:260px;text-align:center;">'
                        f'<img src="{uri}" alt="DCCM {_html_mod.escape(lbl)}" '
                        f'style="width:100%;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,0.12);">'
                        f'<p style="font-size:11px;font-weight:700;color:#1e40af;margin:5px 0 0;">'
                        f'{_html_mod.escape(lbl)}</p></div>'
                    )
            dccm_body += '</div>'
        # Combined DCCM comparison / difference plots
        if _dccm_combined_plots:
            if dccm_per_sim:
                dccm_body += '<hr style="border:none;border-top:1px dashed #bfdbfe;margin:14px 0 10px;">'
            dccm_body += (
                '<p style="font-weight:700;color:#1e40af;margin:0 0 8px;">'
                'Comparison &amp; Difference (Apo vs Holo)</p>'
                '<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;">'
            )
            for _cp in _dccm_combined_plots:
                uri = _encode_image(_cp)
                if uri:
                    _fname = Path(_cp).stem.replace("_", " ").title()
                    dccm_body += (
                        f'<div style="flex:1 1 320px;text-align:center;">'
                        f'<img src="{uri}" alt="{_html_mod.escape(_fname)}" '
                        f'style="width:100%;border-radius:4px;box-shadow:0 1px 6px rgba(0,0,0,0.15);">'
                        f'<p style="font-size:11px;color:#6b7280;margin:5px 0 0;">'
                        f'{_html_mod.escape(_fname)}</p></div>'
                    )
            dccm_body += '</div>'

    panel_e = _panel(
        "E", "DCCM Heatmaps & Difference",
        "Dynamic cross-correlation matrix \u2014 per-simulation heatmaps and apo\u2013holo \u0394DCCM",
        dccm_body,
        full_width=True,
    )

    # ── Panel F: Summary bar chart ────────────────────────────────────────
    bar_svg = _build_summary_bar_chart_svg(sims_summary)
    panel_f = _panel(
        "F", "Summary Bar Chart",
        "Stability (RMSD \u2193), flexibility (RMSF \u2191), and compactness (Rg \u2193) rankings",
        bar_svg if bar_svg else _missing("Insufficient statistics for bar chart"),
        full_width=True,
    )

    # ── Ranking table ─────────────────────────────────────────────────────
    ranking_table = _build_ranking_summary_table(sims_summary)

    return (
        '<h2>&#128202; Comparative Dynamics Summary</h2>\n'
        '<p>Multi-panel comparison of structural dynamics across all simulations. '
        'Each panel highlights a distinct aspect of molecular behaviour.</p>\n'
        '<div class="dyn-panel-grid">\n'
        + panel_a + "\n"
        + panel_b + "\n"
        + panel_c + "\n"
        + panel_d + "\n"
        + panel_e + "\n"
        + panel_f + "\n"
        + '</div>\n'
        + ranking_table
    )


# ---------------------------------------------------------------------------
# Public @tool
# ---------------------------------------------------------------------------

@tool
def generate_combined_html_report(
    sim_dirs: List[str],
    labels: List[str],
    overlay_plots: List[str],
    working_dir: str,
    output_file: str = "combined_report.html",
    title: str = "Multi-Simulation Comparison Report",
    enriched_prompt: Optional[str] = None,
    user_goal: Optional[str] = None,
    protein_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a rich comparison HTML report spanning multiple MD simulations.

    Reads ``analysis_summary.jsonl`` from each simulation's analysis directory,
    embeds all overlay plots, harvests 3D PDB structures and literature
    references from per-sim reporter artefacts, and writes a self-contained
    HTML report with visualisation, literature, and a final combined impression.

    Args:
        sim_dirs: List of per-simulation root directories in the same order
            as *labels* (e.g. ``["multi_run/1A", "multi_run/2B", ...]``).
        labels: Human-readable simulation labels (e.g. ``["1A", "2B", "3C"]``).
        overlay_plots: Absolute or relative paths to overlay plot images
            produced by ``run_combined_analysis`` (or any PNG/JPEG files).
        working_dir: Directory where the HTML report is written.
        output_file: Output filename (default ``"combined_report.html"``).
        title: Report title shown in the browser tab and header.
        enriched_prompt: LLM-enriched technical task description used as
            detailed objectives (shown in a collapsible panel).
        user_goal: Original user goal text — shown prominently as the
            high-level Overall Goal in the objectives section.
        protein_name: Protein / system name (e.g. "CDK2") used in the
            report header, objectives section, and literature relevance ranking.

    Returns:
        Dict with ``success`` and ``output_path``.
    """
    Path(working_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(working_dir) / output_file)

    # ---- Build label → protein name map from user_goal + protein_name ------
    # Merge: explicit protein_name overrides nothing; user_goal text has the
    # full "uniprotId: ProteinName" table the user typed.
    _combined_text = " ".join(filter(None, [user_goal, enriched_prompt, protein_name]))
    label_name_map = _parse_label_name_map(_combined_text)
    # Also fold in any "(label) ProteinName" style from enriched_prompt if we
    # didn't already find the label there.
    if label_name_map:
        logger.info("Label → protein name map: %s", label_name_map)

    # ---- Collect data -------------------------------------------------------
    sims_summary = _collect_sim_summaries(sim_dirs, labels, label_name_map)
    sim_resources = _collect_per_sim_resources(sim_dirs, labels, label_name_map)

    stats_html = _build_stats_section(sims_summary)
    plots_html = _build_plots_section(overlay_plots)

    # Comparative Dynamics Summary — multi-panel figure (Panels A–F)
    comparative_html = _build_comparative_dynamics_section(
        overlay_plots, sims_summary, sim_dirs, labels
    )

    # 3D viewer: pick one representative PDB per sim (max 5)
    pdb_frames = _select_representative_pdbs(sim_dirs, labels, max_pdbs=5)
    viewer_html = _build_3d_viewer_html(pdb_frames) if pdb_frames else ""

    # Literature: aggregate from per-sim HTML reports (deduplicated)
    agg_refs = _aggregate_literature(
        sim_resources,
        max_refs=10,
        hypothesis_text=enriched_prompt,
        protein_name=protein_name,
    )
    literature_html = _build_literature_html(agg_refs)

    # Final impression: synthesise cross-sim stats
    final_text = _build_combined_final_impression(sims_summary, sim_resources)
    final_html = _build_final_impression_html(final_text, agg_refs)

    # Task description (original prompt + per-sim objectives)
    task_html = _build_task_description_html(
        enriched_prompt=enriched_prompt or "",
        sim_resources=sim_resources,
        user_goal=user_goal,
        protein_name=protein_name,
    )

    # ---- Metadata header ----------------------------------------------------
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    sims_list_html = ", ".join(f"<b>{_html_mod.escape(s['label'])}</b>" for s in sims_summary)
    # Build a protein name display: use unique labels (already resolved to names)
    _unique_names = list(dict.fromkeys(s["label"] for s in sims_summary))
    _names_display = ", ".join(_html_mod.escape(n) for n in _unique_names)
    protein_meta_html = (
        f'\n  <p><strong>&#129516; Protein / System:</strong> '
        f'<span style="font-weight:700;color:#7c3aed;">{_names_display}</span></p>'
        if _unique_names else ""
    )

    # ---- Simulations overview table (enhanced) ------------------------------
    sim_overview_rows = ""
    for s in sims_summary:
        n_records = len(s["records"])
        atypes = ", ".join(
            _html_mod.escape(r.get("analysis_type", "")) for r in s["records"]
            if r.get("analysis_type")
        ) or "—"
        sim_dir_display = _html_mod.escape(Path(s["analysis_dir"]).parent.name)
        sim_overview_rows += (
            f"<tr>"
            f"<td><b>{_html_mod.escape(s['label'])}</b></td>"
            f"<td>{sim_dir_display}</td>"
            f"<td>{n_records}</td>"
            f"<td>{atypes}</td>"
            f"</tr>\n"
        )

    sim_overview_html = (
        "<table>"
        "<tr><th>Label</th><th>Directory</th><th>Analysis Records</th><th>Types</th></tr>\n"
        + sim_overview_rows
        + "</table>\n"
    )

    # ---- 3Dmol.js CDN script tag (always inject when viewer section present) -------
    viewer_script = (
        '<script src="https://3Dmol.org/build/3Dmol-min.js"></script>\n'
        if viewer_html
        else ""
    )

    # ---- Assemble HTML ------------------------------------------------------
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html_mod.escape(title)}</title>
<style>{_CSS}</style>
{viewer_script}</head>
<body>
<div class="container">

<h1>&#129516; {_html_mod.escape(title)}</h1>
<div class="header-meta">
  <p><strong>&#128197; Generated:</strong> {now}</p>
  <p><strong>&#128202; Simulations:</strong> {sims_list_html}</p>{protein_meta_html}
  <p><strong>&#128296; Total analyses:</strong> {sum(len(s['records']) for s in sims_summary)}</p>
  <p><strong>&#129366; PDB structures in viewer:</strong> {len(pdb_frames)}</p>
  <p><strong>&#128218; Literature references:</strong> {len(agg_refs)}</p>
</div>

{task_html}

<div class="section-divider"></div>

<h2>&#128202; Simulations Overview</h2>
{sim_overview_html}

<div class="section-divider"></div>

{viewer_html}

{"<div class='section-divider'></div>" if viewer_html else ""}

{comparative_html}

<div class="section-divider"></div>

<h2>&#128293; Statistics Comparison</h2>
<div class="stats-section">
{stats_html}
</div>

<div class="section-divider"></div>

{literature_html}

{"<div class='section-divider'></div>" if literature_html else ""}

{final_html}

</div>
<footer>Generated by AgenticAI Multi-Simulation Reporter &nbsp;|&nbsp; {now}</footer>
</body>
</html>
"""

    try:
        Path(output_path).write_text(html, encoding="utf-8")
        logger.info(f"Combined HTML report saved → {output_path}")
        return {
            "success": True,
            "output_path": output_path,
            "output_file": output_file,
            "pdb_structures": len(pdb_frames),
            "literature_count": len(agg_refs),
        }
    except Exception as exc:
        logger.error(f"Failed to write combined report: {exc}")
        return {"success": False, "error": str(exc)}

