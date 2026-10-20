"""Evidence-grounded literature helpers for the reporter agent.

Supports a six-step survey:
  1) MD observations needing interpretation
  2) multi-source candidate retrieval
  3) title/abstract ranking
  4) targeted OA evidence passages
  5) compare evidence vs MD results
  6) evidence-linked reporting (caller / LLM)
"""
from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence
from urllib.error import URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def extract_md_observations(
    analysis_data: Optional[Dict[str, Any]] = None,
    user_goal: str = "",
    protein_name: str = "",
) -> List[Dict[str, Any]]:
    """Step 1 — Identify MD observations that need biological interpretation."""
    observations: List[Dict[str, Any]] = []
    entries = list((analysis_data or {}).get("entries") or [])
    goal_l = (user_goal or "").lower()
    pname = (protein_name or "").strip()

    for entry in entries:
        atype = str(entry.get("analysis_type") or "Unknown")
        alow = atype.lower()
        if alow in {"pdb_input_validation", "trajectorybatch", "unknown"}:
            continue
        stats = entry.get("statistics") if isinstance(entry.get("statistics"), dict) else {}
        meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}

        if "rmsd" in alow:
            mean = stats.get("mean_rmsd_angstrom") or stats.get("mean")
            mx = stats.get("max_rmsd_angstrom") or stats.get("max")
            try:
                mean_f = float(mean) if mean is not None else None
            except (TypeError, ValueError):
                mean_f = None
            label = (
                "elevated backbone RMSD / possible instability"
                if mean_f is not None and mean_f > 3.0
                else "modest backbone RMSD / local conformational stability"
            )
            metric_bits = []
            if mean_f is not None:
                metric_bits.append(f"mean {mean_f:.2f} Å")
            try:
                if mx is not None:
                    metric_bits.append(f"max {float(mx):.2f} Å")
            except (TypeError, ValueError):
                pass
            statement = f"{pname + ': ' if pname else ''}{label}"
            if metric_bits:
                statement += f" ({', '.join(metric_bits)})"
            observations.append({
                "id": f"obs_rmsd_{len(observations)+1}",
                "kind": "rmsd_stability",
                "analysis_type": atype,
                "statement": statement,
                "metrics": {k: stats[k] for k in stats if "rmsd" in k.lower()},
                "keywords": ["rmsd", "conformational stability", "backbone", "molecular dynamics"],
            })

        if "rmsf" in alow:
            hotspots = meta.get("top_5_flexible") or []
            most = stats.get("most_flexible_residue")
            most_val = stats.get("most_flexible_rmsf")
            hotspot_bits = []
            for h in hotspots[:5]:
                if not isinstance(h, dict):
                    continue
                rid = h.get("residue_id")
                rnm = h.get("residue_name") or ""
                rv = h.get("rmsf")
                if rid is not None:
                    hotspot_bits.append(
                        f"{rnm}{rid}" + (f" ({float(rv):.2f} Å)" if rv is not None else "")
                    )
            if not hotspot_bits and most is not None:
                hotspot_bits.append(
                    f"residue {most}"
                    + (f" ({float(most_val):.2f} Å)" if most_val is not None else "")
                )
            observations.append({
                "id": f"obs_rmsf_{len(observations)+1}",
                "kind": "rmsf_hotspots",
                "analysis_type": atype,
                "statement": (
                    f"{pname + ': ' if pname else ''}RMSF hotspots / flexible sites: "
                    + (", ".join(hotspot_bits) if hotspot_bits else "see RMSF profile")
                ),
                "metrics": {
                    "mean_rmsf_angstrom": stats.get("mean_rmsf_angstrom"),
                    "most_flexible_residue": most,
                    "most_flexible_rmsf": most_val,
                    "top_flexible": hotspot_bits,
                },
                "keywords": [
                    "rmsf", "flexibility", "flexible loop",
                    "hotspot", "residue fluctuation",
                ]
                + (
                    ["activation loop"]
                    if "activation loop" in goal_l or "activation-loop" in goal_l
                    else []
                )
                + [b.split()[0] for b in hotspot_bits[:3]],
            })

        if "dccm" in alow or "correlation" in alow:
            observations.append({
                "id": f"obs_dccm_{len(observations)+1}",
                "kind": "correlated_motions",
                "analysis_type": atype,
                "statement": f"{pname + ': ' if pname else ''}correlated motions / allosteric coupling observed",
                "metrics": stats,
                "keywords": ["dccm", "correlated motion", "allosteric", "communication"],
            })

        if "gyration" in alow or alow in {"rg", "radius of gyration"} or "radius_of_gyration" in alow:
            observations.append({
                "id": f"obs_rg_{len(observations)+1}",
                "kind": "compactness",
                "analysis_type": atype,
                "statement": (
                    f"{pname + ': ' if pname else ''}radius of gyration / compactness "
                    f"(mean {stats.get('mean_rg_angstrom', stats.get('mean', 'n/a'))} Å)"
                ),
                "metrics": stats,
                "keywords": [
                    "radius of gyration", "compactness", "folding", "stability",
                    "molecular dynamics",
                ],
            })

        if "com" in alow or "distance" in alow or "residence" in alow or "ligand" in alow:
            observations.append({
                "id": f"obs_ligand_{len(observations)+1}",
                "kind": "ligand_or_pocket",
                "analysis_type": atype,
                "statement": f"{pname + ': ' if pname else ''}ligand/pocket dynamics from {atype}",
                "metrics": stats,
                "keywords": ["ligand", "binding", "pocket", "displacement", "residence"],
            })

    # Goal-driven ligand hook — skip when the goal is explicitly apo / no ligand
    apo_only = bool(
        re.search(
            r"\b(?:no|without|exclude|excluding)\s+ligand\b"
            r"|\bprotein[- ]only\b"
            r"|\bapo\b(?![^.\n]{0,60}\bholo\b)",
            goal_l,
        )
    )
    wants_ligand_lit = (
        any(t in goal_l for t in ("atp", "ligand", "holo", "binding pocket"))
        and not apo_only
    )
    if wants_ligand_lit and not any(
        o["kind"] == "ligand_or_pocket" for o in observations
    ):
        observations.append({
            "id": "obs_goal_ligand",
            "kind": "ligand_or_pocket",
            "analysis_type": "goal",
            "statement": "User objective involves apo/holo or ligand-related interpretation",
            "metrics": {},
            "keywords": ["apo", "holo", "ligand", "atp", "binding"],
        })

    if not observations:
        observations.append({
            "id": "obs_general",
            "kind": "general_dynamics",
            "analysis_type": "general",
            "statement": f"{pname or 'System'} MD dynamics require literature context",
            "metrics": {},
            "keywords": ["molecular dynamics", "conformational", "protein"],
        })
    return observations


def search_crossref(
    query: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search Crossref works API for scholarly metadata."""
    try:
        params = urlencode({
            "query": query,
            "rows": min(max_results, 20),
            "select": "DOI,title,author,published-print,published-online,abstract,container-title,URL",
        })
        url = f"https://api.crossref.org/works?{params}"
        logger.info("Searching Crossref: %s", query[:120])
        req = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "SimAgent/1.0 (mailto:simagent@local; literature survey)",
        })
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("message", {}).get("items") or []
        results = []
        for item in items[:max_results]:
            title = " ".join(item.get("title") or []) or "Unknown"
            authors = []
            for a in (item.get("author") or [])[:10]:
                name = " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
                if name:
                    authors.append(name)
            year = None
            for key in ("published-print", "published-online"):
                parts = (item.get(key) or {}).get("date-parts") or []
                if parts and parts[0]:
                    year = parts[0][0]
                    break
            abstract = item.get("abstract") or ""
            if abstract:
                abstract = re.sub(r"<[^>]+>", " ", abstract)
                abstract = re.sub(r"\s+", " ", abstract).strip()
            doi = item.get("DOI")
            results.append({
                "title": title,
                "authors": authors,
                "journal": " ".join(item.get("container-title") or []) or "Crossref",
                "year": year,
                "pmid": None,
                "doi": doi,
                "abstract": abstract or None,
                "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                "source": "Crossref",
            })
        return {
            "success": True,
            "query": query,
            "total_found": data.get("message", {}).get("total-results", len(results)),
            "returned": len(results),
            "results": results,
        }
    except (URLError, OSError) as e:
        logger.warning("Crossref search network error: %s", e)
        return {"success": False, "error": str(e), "results": []}
    except Exception as e:
        logger.error("Crossref search error: %s", e, exc_info=True)
        return {"success": False, "error": str(e), "results": []}


def search_arxiv(
    query: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search arXiv API (includes many q-bio / physics.bio-ph MD papers)."""
    try:
        # Prefer all: terms; fall back to AND of tokens
        tokens = [t for t in re.split(r"\s+", query.strip()) if t][:8]
        if not tokens:
            return {"success": False, "error": "empty query", "results": []}
        search_q = " AND ".join(f'all:"{t}"' if not t.startswith("all:") else t for t in tokens)
        params = urlencode({
            "search_query": search_q,
            "start": 0,
            "max_results": min(max_results, 20),
            "sortBy": "relevance",
            "sortOrder": "descending",
        })
        url = f"http://export.arxiv.org/api/query?{params}"
        logger.info("Searching arXiv: %s", search_q[:120])
        req = Request(url, headers={"User-Agent": "SimAgent/1.0"})
        with urlopen(req, timeout=20) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("a:entry", ns)[:max_results]:
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            title = re.sub(r"\s+", " ", title)
            summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
            summary = re.sub(r"\s+", " ", summary)
            authors = [
                (a.findtext("a:name", default="", namespaces=ns) or "").strip()
                for a in entry.findall("a:author", ns)
            ]
            authors = [a for a in authors if a][:10]
            link = ""
            for link_el in entry.findall("a:link", ns):
                if link_el.get("type") == "text/html" or link_el.get("rel") == "alternate":
                    link = link_el.get("href") or link
            arxiv_id = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("a:published", default="", namespaces=ns) or "")[:4]
            year = int(published) if published.isdigit() else None
            doi = None
            for el in entry.findall("{http://arxiv.org/schemas/atom}doi"):
                if el.text:
                    doi = el.text.strip()
            results.append({
                "title": title or "Unknown",
                "authors": authors,
                "journal": "arXiv",
                "year": year,
                "pmid": None,
                "doi": doi,
                "abstract": summary or None,
                "url": link or arxiv_id or None,
                "source": "arXiv",
                "arxiv_id": arxiv_id,
            })
        return {
            "success": True,
            "query": query,
            "total_found": len(results),
            "returned": len(results),
            "results": results,
        }
    except (URLError, OSError, ET.ParseError) as e:
        logger.warning("arXiv search error: %s", e)
        return {"success": False, "error": str(e), "results": []}
    except Exception as e:
        logger.error("arXiv search error: %s", e, exc_info=True)
        return {"success": False, "error": str(e), "results": []}


def _europe_pmc_lookup(pmid: Optional[str] = None, doi: Optional[str] = None) -> Dict[str, Any]:
    """Resolve pmcid / OA flag for a paper via Europe PMC."""
    if pmid:
        q = f"EXT_ID:{pmid} AND SRC:MED"
    elif doi:
        q = f'DOI:"{doi}"'
    else:
        return {}
    params = urlencode({
        "query": q,
        "format": "json",
        "resultType": "core",
        "pageSize": 1,
    })
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    items = data.get("resultList", {}).get("result") or []
    return items[0] if items else {}


def _extract_keyword_passages(text: str, keywords: Sequence[str], max_passages: int = 3) -> List[str]:
    """Split text into sentences/paragraphs and keep those matching keywords."""
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    keys = [k.lower() for k in keywords if k and len(str(k)) > 2]
    hits: List[str] = []
    for chunk in chunks:
        c = re.sub(r"\s+", " ", chunk).strip()
        if len(c) < 40:
            continue
        cl = c.lower()
        if any(k in cl for k in keys):
            hits.append(c[:600])
        if len(hits) >= max_passages:
            break
    if not hits:
        # Fall back to leading abstract sentences
        for chunk in chunks:
            c = re.sub(r"\s+", " ", chunk).strip()
            if len(c) >= 60:
                hits.append(c[:600])
            if len(hits) >= min(2, max_passages):
                break
    return hits


def fetch_oa_evidence_passages(
    refs: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    max_refs: int = 5,
    max_passages_per_ref: int = 3,
) -> List[Dict[str, Any]]:
    """Step 4 — Retrieve targeted OA evidence passages (Europe PMC full text when available)."""
    keywords: List[str] = []
    for obs in observations:
        keywords.extend(obs.get("keywords") or [])
    keywords = list(dict.fromkeys(keywords))[:20]

    evidence: List[Dict[str, Any]] = []
    for ref in refs[:max_refs]:
        title = ref.get("title") or "Unknown"
        pmid = ref.get("pmid")
        doi = ref.get("doi")
        abstract = ref.get("abstract") or ""
        passages: List[str] = []
        source_kind = "abstract"
        pmcid = ref.get("pmcid")
        try:
            meta = {}
            if pmid or doi:
                meta = _europe_pmc_lookup(pmid=str(pmid) if pmid else None, doi=doi)
            pmcid = pmcid or meta.get("pmcid")
            is_oa = str(meta.get("isOpenAccess", "")).upper() == "Y" or bool(pmcid)
            if pmcid and is_oa:
                ft_url = (
                    f"https://www.ebi.ac.uk/europepmc/webservices/rest/"
                    f"{quote_plus(str(pmcid))}/fullTextXML"
                )
                req = Request(ft_url, headers={"Accept": "application/xml"})
                with urlopen(req, timeout=20) as resp:
                    xml_text = resp.read().decode("utf-8", errors="replace")
                # Strip tags → plain text
                text = re.sub(r"<[^>]+>", " ", xml_text)
                text = re.sub(r"\s+", " ", text).strip()
                passages = _extract_keyword_passages(text, keywords, max_passages_per_ref)
                if passages:
                    source_kind = "europe_pmc_fulltext"
            if not passages and abstract:
                passages = _extract_keyword_passages(abstract, keywords, max_passages_per_ref)
                source_kind = "abstract"
        except Exception as exc:
            logger.debug("OA evidence fetch failed for %s: %s", title[:60], exc)
            if abstract:
                passages = _extract_keyword_passages(abstract, keywords, max_passages_per_ref)
                source_kind = "abstract"

        if not passages and abstract:
            passages = [abstract[:500]]
            source_kind = "abstract"

        evidence.append({
            "title": title,
            "pmid": pmid,
            "doi": doi,
            "pmcid": pmcid,
            "source": ref.get("source"),
            "evidence_source": source_kind,
            "passages": passages,
            "relevance_note": ref.get("relevance_note"),
        })
    return evidence


def classify_evidence_vs_observations(
    observations: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Step 5 (heuristic) — Compare evidence passages with MD observations.

    Returns one record per observation with categories:
    supported / plausible / conflicting / not_addressed.
    """
    comparisons: List[Dict[str, Any]] = []
    for obs in observations:
        keys = [k.lower() for k in (obs.get("keywords") or []) if k]
        stmt = (obs.get("statement") or "").lower()
        supporting: List[Dict[str, Any]] = []
        conflicting: List[Dict[str, Any]] = []
        for ev in evidence:
            blob = " ".join(ev.get("passages") or []).lower()
            if not blob:
                continue
            hit = any(k in blob for k in keys if len(k) > 3)
            if not hit:
                continue
            neg = any(
                neg_w in blob
                for neg_w in ("however", "in contrast", "not observed", "contradict", "unlike")
            )
            item = {
                "title": ev.get("title"),
                "pmid": ev.get("pmid"),
                "doi": ev.get("doi"),
                "evidence_source": ev.get("evidence_source"),
                "passage": (ev.get("passages") or [""])[0][:300],
            }
            # Soft conflict signal only when negation co-occurs with opposite stability language
            if neg and (
                ("instability" in stmt and "stable" in blob)
                or ("stability" in stmt and "unfold" in blob)
            ):
                conflicting.append(item)
            else:
                supporting.append(item)

        if supporting:
            category = "supported" if len(supporting) >= 2 else "plausible"
        elif conflicting:
            category = "conflicting"
        else:
            category = "not_addressed"

        comparisons.append({
            "observation_id": obs.get("id"),
            "observation": obs.get("statement"),
            "kind": obs.get("kind"),
            "category": category,
            "supporting": supporting[:3],
            "conflicting": conflicting[:2],
        })
    return comparisons


def compact_ref(ref: Dict[str, Any], include_score: bool = True) -> Dict[str, Any]:
    """Compact reference dict for provenance logs."""
    out = {
        "title": (ref.get("title") or "")[:180],
        "year": ref.get("year"),
        "pmid": ref.get("pmid"),
        "doi": ref.get("doi"),
        "source": ref.get("source"),
        "url": ref.get("url"),
    }
    if include_score and ref.get("relevance_note"):
        out["relevance_note"] = ref.get("relevance_note")
    if ref.get("_relevance_score") is not None:
        out["score"] = ref.get("_relevance_score")
    if ref.get("query_key"):
        out["query_key"] = ref.get("query_key")
    return out


def write_literature_provenance(
    path: str,
    provenance: Dict[str, Any],
) -> None:
    """Write machine-readable provenance JSON beside the report."""
    try:
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")
        logger.info("Wrote literature provenance → %s", p)
    except Exception as exc:
        logger.warning("Could not write literature provenance: %s", exc)
