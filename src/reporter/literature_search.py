"""Literature search functionality for scientific reports"""
import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, urlencode
from urllib.error import URLError
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Terms that signal dynamics / MD relevance in abstracts and titles
_DYNAMICS_TERMS = (
    "molecular dynamics", "md simulation", "conformational", "flexibility",
    "rmsd", "rmsf", "alloster", "cross-correlation", "dccm", "dynamics",
    "trajectory", "activation loop", "pseudokinase", "kinase",
)

_LIGAND_TERMS = ("atp", "ligand", "binding", "holo", "apo", "nucleotide")

_REGION_RE = re.compile(
    r"(?:resid(?:ue)?s?\s*)?(\d+)\s*(?:to|-)\s*(\d+)",
    re.IGNORECASE,
)
_PROTEIN_MAP_RE = re.compile(
    r'\b([A-Za-z0-9_\-]+)\s*:\s*([A-Za-z][A-Za-z0-9_\-]+)',
)


def extract_research_context(
    user_goal: Optional[str] = None,
    protein_name: Optional[str] = None,
    analysis_types: Optional[List[str]] = None,
    analysis_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract structured research context from the user goal and analysis outputs."""
    goal = (user_goal or "").strip()
    goal_lower = goal.lower()
    context: Dict[str, Any] = {
        "user_goal": goal,
        "protein_names": [],
        "protein_ids": [],
        "ligand_terms": [],
        "region_terms": [],
        "hypothesis_terms": [],
        "analysis_types": list(analysis_types or []),
        "finding_phrases": [],
    }

    if protein_name:
        for part in re.split(r"[,;/\s]+", protein_name):
            part = part.strip()
            if len(part) >= 2:
                context["protein_names"].append(part)

    for match in _PROTEIN_MAP_RE.finditer(goal):
        pid, pname = match.group(1).strip(), match.group(2).strip()
        if len(pid) >= 3 and pname[0].isalpha():
            context["protein_ids"].append(pid)
            if pname not in context["protein_names"]:
                context["protein_names"].append(pname)

    for term in _LIGAND_TERMS:
        if term in goal_lower:
            context["ligand_terms"].append(term)

    for match in _REGION_RE.finditer(goal):
        context["region_terms"].append(f"residues {match.group(1)}-{match.group(2)}")

    _HYP_TRIGGERS = (
        "inhibit", "bind", "interact", "affect", "role", "function", "mechanism",
        "pathway", "stability", "flexibility", "alloster", "mutation", "mutant",
        "drug", "therapeutic", "disease", "cancer", "activate", "deactivate",
        "phosphorylat", "fold", "unfold", "aggregate", "dimer", "oligomer",
        "signaling", "effect of", "compare", "versus", "apo", "holo",
    )
    for trig in _HYP_TRIGGERS:
        if trig in goal_lower:
            context["hypothesis_terms"].append(trig)

    if analysis_stats:
        for atype, stats in analysis_stats.items():
            if not isinstance(stats, dict):
                continue
            alow = str(atype).lower()
            if "rmsd" in alow:
                mean = stats.get("mean_rmsd_angstrom") or stats.get("mean")
                if mean is not None:
                    try:
                        val = float(mean)
                        phrase = (
                            "conformational instability"
                            if val > 3.0
                            else "structural stability"
                        )
                        context["finding_phrases"].append(
                            f"{phrase} (mean RMSD {val:.2f} Å)"
                        )
                    except (TypeError, ValueError):
                        pass
            if "rmsf" in alow:
                mean = stats.get("mean_rmsf_angstrom") or stats.get("mean")
                if mean is not None:
                    try:
                        val = float(mean)
                        if val > 2.0:
                            context["finding_phrases"].append(
                                f"elevated backbone flexibility (mean RMSF {val:.2f} Å)"
                            )
                    except (TypeError, ValueError):
                        pass
            if "dccm" in alow or "correlation" in alow:
                context["finding_phrases"].append("correlated residue motions / allosteric coupling")

    # Deduplicate while preserving order
    for key in ("protein_names", "protein_ids", "ligand_terms", "region_terms",
                "hypothesis_terms", "finding_phrases"):
        seen: set = set()
        deduped = []
        for item in context[key]:
            low = str(item).lower()
            if low not in seen:
                seen.add(low)
                deduped.append(item)
        context[key] = deduped

    return context


def build_analysis_summary_text(
    analysis_data: Optional[Dict[str, Any]] = None,
    analysis_stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a concise text summary of simulation analysis for LLM prompts."""
    lines: List[str] = []
    stats_map = dict(analysis_stats or {})

    if analysis_data and isinstance(analysis_data, dict):
        for entry in analysis_data.get("entries", []):
            atype = entry.get("analysis_type", "Unknown")
            stats = entry.get("statistics", {})
            if isinstance(stats, dict) and stats:
                stats_map.setdefault(atype, stats)

    for atype, stats in stats_map.items():
        if not isinstance(stats, dict):
            continue
        numeric = {
            k: v for k, v in stats.items()
            if isinstance(v, (int, float)) and not k.startswith("_")
        }
        if numeric:
            stat_line = ", ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}"
                                  for k, v in list(numeric.items())[:8])
            lines.append(f"- {atype}: {stat_line}")
        else:
            lines.append(f"- {atype}: completed")

    return "\n".join(lines) if lines else "No quantitative analysis statistics available."


def rank_literature_refs(
    refs: List[Dict[str, Any]],
    context: Dict[str, Any],
    max_refs: int = 15,
) -> List[Dict[str, Any]]:
    """Re-rank literature by relevance to protein, user goal, and simulation findings."""
    protein_names = context.get("protein_names") or []
    hypothesis_terms = context.get("hypothesis_terms") or []
    ligand_terms = context.get("ligand_terms") or []
    region_terms = context.get("region_terms") or []
    finding_phrases = context.get("finding_phrases") or []
    analysis_types = [str(a).lower() for a in (context.get("analysis_types") or [])]

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for ref in refs:
        haystack = " ".join(filter(None, [
            ref.get("title", ""),
            ref.get("abstract", "") or "",
            ref.get("journal", ""),
            " ".join(ref.get("authors") or []),
        ])).lower()

        score = 0
        for name in protein_names:
            if name.lower() in haystack:
                score += 8

        for term in hypothesis_terms + ligand_terms:
            if term.lower() in haystack:
                score += 4

        for term in _DYNAMICS_TERMS:
            if term in haystack:
                score += 2

        for atype in analysis_types:
            if atype and atype in haystack:
                score += 2

        for region in region_terms:
            if region.lower() in haystack:
                score += 3

        for finding in finding_phrases:
            for word in finding.lower().split():
                if len(word) > 5 and word in haystack:
                    score += 1
                    break

        if ref.get("abstract"):
            score += 2  # prefer papers where we have abstract text for review

        ref_copy = dict(ref)
        ref_copy["_relevance_score"] = score
        scored.append((score, ref_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [r for _, r in scored[:max_refs]]
    for r in ranked:
        r.pop("_relevance_score", None)
    return ranked


def extract_analysis_stats_from_entries(
    analysis_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Pull analysis_type → statistics mapping from analysis_summary entries."""
    stats_map: Dict[str, Any] = {}
    if not isinstance(analysis_data, dict):
        return stats_map
    for entry in analysis_data.get("entries", []):
        atype = entry.get("analysis_type")
        stats = entry.get("statistics")
        if atype and isinstance(stats, dict) and stats:
            stats_map[atype] = stats
    return stats_map


@tool
def search_pubmed(
    query: str,
    max_results: int = 10,
    include_abstracts: bool = True,
    max_age_years: Optional[int] = 10
) -> Dict[str, Any]:
    """
    Search PubMed for scientific literature.
    
    Uses the NCBI E-utilities API to search PubMed and retrieve
    article metadata, abstracts, and citations.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        include_abstracts: Whether to fetch full abstracts
        max_age_years: Limit to papers from last N years (None for no limit)
    
    Returns:
        Dict with search results and metadata
    """
    try:
        from Bio import Entrez
        Entrez.email = "anupkprasad121@gmail.com"  # Required by NCBI
        
        # Build search term with date filter
        search_term = query
        if max_age_years:
            from datetime import datetime
            current_year = datetime.now().year
            min_year = current_year - max_age_years
            search_term += f" AND {min_year}[PDAT]:{current_year}[PDAT]"
        
        logger.info(f"Searching PubMed: {search_term}")
        
        # Search PubMed
        handle = Entrez.esearch(
            db="pubmed",
            term=search_term,
            retmax=max_results,
            sort="relevance"
        )
        search_results = Entrez.read(handle)
        handle.close()
        
        pmids = search_results.get("IdList", [])
        logger.info(f"Found {len(pmids)} results")
        
        if not pmids:
            return {
                "success": True,
                "query": query,
                "total_found": 0,
                "results": []
            }
        
        # Fetch article details
        if include_abstracts:
            handle = Entrez.efetch(
                db="pubmed",
                id=pmids,
                rettype="medline",
                retmode="xml"
            )
            records = Entrez.read(handle)
            handle.close()
            
            # Article types to skip (not research papers)
            _SKIP_TYPES = {
                "highlights", "reply", "editorial", "comment",
                "erratum", "retraction", "letter", "news",
                "correction", "special issue",
            }

            articles = []
            for article in records.get("PubmedArticle", []):
                try:
                    medline = article.get("MedlineCitation", {})
                    article_data = medline.get("Article", {})

                    # Skip non-research article types
                    raw_title = str(article_data.get("ArticleTitle", "")).strip().rstrip(".")
                    if raw_title.lower() in _SKIP_TYPES:
                        logger.debug("Skipping non-research article: %s", raw_title)
                        continue
                    pub_types = article_data.get("PublicationTypeList", [])
                    pub_type_strs = {str(pt).lower() for pt in pub_types}
                    if pub_type_strs & {"editorial", "comment", "letter", "published erratum", "retraction of publication", "news"}:
                        logger.debug("Skipping by pub-type: %s", pub_type_strs)
                        continue
                    
                    # Extract authors
                    author_list = article_data.get("AuthorList", [])
                    authors = []
                    for author in author_list[:10]:  # Max 10 authors
                        if "LastName" in author and "Initials" in author:
                            authors.append(f"{author['LastName']} {author['Initials']}")
                    
                    # Extract abstract
                    abstract_data = article_data.get("Abstract", {})
                    abstract_texts = abstract_data.get("AbstractText", [])
                    abstract = " ".join([str(text) for text in abstract_texts]) if abstract_texts else None
                    
                    # Extract journal info
                    journal = article_data.get("Journal", {})
                    journal_title = journal.get("Title", "Unknown")
                    pub_date = journal.get("JournalIssue", {}).get("PubDate", {})
                    year = pub_date.get("Year", None)
                    
                    # Extract IDs
                    pmid = medline.get("PMID", None)
                    article_ids = article.get("PubmedData", {}).get("ArticleIdList", [])
                    doi = None
                    for aid in article_ids:
                        if aid.attributes.get("IdType") == "doi":
                            doi = str(aid)
                            break
                    
                    articles.append({
                        "title": article_data.get("ArticleTitle", "Unknown"),
                        "authors": authors,
                        "journal": journal_title,
                        "year": int(year) if year else None,
                        "pmid": str(pmid) if pmid else None,
                        "doi": doi,
                        "abstract": abstract,
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
                    })
                    
                except Exception as e:
                    logger.warning(f"Error parsing article: {e}")
                    continue
            
            return {
                "success": True,
                "query": query,
                "total_found": len(pmids),
                "returned": len(articles),
                "results": articles
            }
        else:
            # Just return PMIDs without abstracts
            return {
                "success": True,
                "query": query,
                "total_found": len(pmids),
                "pmids": [str(pmid) for pmid in pmids],
                "results": []
            }
            
    except ImportError:
        logger.error("Biopython not installed - PubMed search unavailable")
        return {
            "success": False,
            "error": "Biopython not installed. Install with: pip install biopython",
            "results": []
        }
    except Exception as e:
        logger.error(f"PubMed search error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "results": []
        }


# ---------------------------------------------------------------------------
# bioRxiv / medRxiv preprint search  (via Europe PMC REST API)
# ---------------------------------------------------------------------------

@tool
def search_biorxiv(
    query: str,
    max_results: int = 5,
    max_age_years: Optional[int] = 5
) -> Dict[str, Any]:
    """
    Search bioRxiv/medRxiv preprints via the Europe PMC REST API.

    Args:
        query: Search query string
        max_results: Maximum number of results to return
        max_age_years: Limit to preprints from last N years (None for no limit)

    Returns:
        Dict with search results and metadata
    """
    try:
        search_q = query
        if max_age_years:
            from datetime import datetime
            min_year = datetime.now().year - max_age_years
            search_q += f" FIRST_PDATE:[{min_year} TO *]"
        # SRC:PPR restricts to preprints (bioRxiv + medRxiv)
        search_q += " SRC:PPR"

        params = urlencode({
            "query": search_q,
            "format": "json",
            "resultType": "lite",
            "pageSize": min(max_results, 25),
        })
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
        logger.info("Searching bioRxiv (Europe PMC): %s", search_q[:120])

        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())

        articles = []
        for item in data.get("resultList", {}).get("result", []):
            doi = item.get("doi")
            articles.append({
                "title": item.get("title", "Unknown"),
                "authors": [a.strip() for a in (item.get("authorString") or "").split(",")][:10],
                "journal": (item.get("bookOrReportDetails") or {}).get("publisher", "bioRxiv"),
                "year": int(item["pubYear"]) if item.get("pubYear") else None,
                "pmid": item.get("pmid"),
                "doi": doi,
                "abstract": item.get("abstractText"),
                "url": f"https://doi.org/{doi}" if doi else None,
                "source": "bioRxiv",
            })

        return {
            "success": True,
            "query": query,
            "total_found": data.get("hitCount", 0),
            "returned": len(articles),
            "results": articles,
        }
    except (URLError, OSError) as e:
        logger.warning("bioRxiv search network error: %s", e)
        return {"success": False, "error": str(e), "results": []}
    except Exception as e:
        logger.error("bioRxiv search error: %s", e, exc_info=True)
        return {"success": False, "error": str(e), "results": []}


# ---------------------------------------------------------------------------
# UniProt protein entry search
# ---------------------------------------------------------------------------

@tool
def search_uniprot(
    query: str,
    max_results: int = 3
) -> Dict[str, Any]:
    """
    Search UniProt for reviewed protein entries matching a query.
    Returns functional annotations and key literature references
    associated with each protein entry.

    Args:
        query: Protein name or keyword to search (e.g. "pseudokinase")
        max_results: Maximum number of UniProt entries to return

    Returns:
        Dict with protein entries containing function, references, and links
    """
    try:
        params = urlencode({
            "query": f"({query}) AND reviewed:true",
            "format": "json",
            "size": min(max_results, 10),
            "fields": "accession,protein_name,organism_name,cc_function,lit_pubmed_id",
        })
        url = f"https://rest.uniprot.org/uniprotkb/search?{params}"
        logger.info("Searching UniProt: %s", query[:100])

        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())

        entries = []
        for item in data.get("results", []):
            accession = item.get("primaryAccession", "")
            # Protein name
            prot_desc = item.get("proteinDescription", {})
            rec_name = prot_desc.get("recommendedName", {})
            pname = (rec_name.get("fullName") or {}).get("value", accession)

            # Organism
            organism = (item.get("organism") or {}).get("scientificName", "")

            # Function text
            func_text = ""
            for comment in item.get("comments", []):
                if comment.get("commentType") == "FUNCTION":
                    for txt in comment.get("texts", []):
                        func_text += txt.get("value", "") + " "
            func_text = func_text.strip()

            # Collect PubMed IDs and DOIs from references
            ref_pmids = []
            ref_details = []
            for ref in item.get("references", []):
                cit = ref.get("citation", {})
                pmid = None
                doi = None
                for xref in cit.get("citationCrossReferences", []):
                    if xref.get("database") == "PubMed":
                        pmid = xref.get("id")
                    elif xref.get("database") == "DOI":
                        doi = xref.get("id")
                if pmid and pmid not in ref_pmids:
                    ref_pmids.append(pmid)
                    ref_details.append({
                        "pmid": pmid,
                        "doi": doi,
                        "title": cit.get("title", ""),
                        "journal": cit.get("journal", ""),
                        "year": int(cit["publicationDate"][:4]) if cit.get("publicationDate") else None,
                    })

            entries.append({
                "accession": accession,
                "protein_name": pname,
                "organism": organism,
                "function": func_text[:500] if func_text else None,
                "url": f"https://www.uniprot.org/uniprot/{accession}",
                "reference_count": len(ref_pmids),
                "key_references": ref_details[:5],  # top 5 refs per entry
            })

        return {
            "success": True,
            "query": query,
            "total_entries": len(entries),
            "entries": entries,
        }
    except (URLError, OSError) as e:
        logger.warning("UniProt search network error: %s", e)
        return {"success": False, "error": str(e), "entries": []}
    except Exception as e:
        logger.error("UniProt search error: %s", e, exc_info=True)
        return {"success": False, "error": str(e), "entries": []}


@tool
def generate_literature_queries(
    analysis_types: List[str],
    user_goal: Optional[str] = None,
    protein_name: Optional[str] = None,
    analysis_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate PubMed search queries prioritising the protein and its
    functional context, then the analysis methods, then the user hypothesis.

    Query priority order:
      1. Protein name + MD simulation / structure-function
      2. Protein name + specific analysis method
      3. Protein name + analysis results (e.g. "high RMSD", "flexible loop")
      4. Protein name + user hypothesis / objective extracted from user_goal
      5. Generic analysis method queries (last resort fallback)

    Args:
        analysis_types: List of analysis types performed (e.g., ["RMSD", "RMSF"])
        user_goal: User's original goal/question (hypothesis extraction)
        protein_name: Explicit protein / system name (e.g. "CDK2", "TP53").
                      Must be the actual protein name, NOT a UniProt accession.
        analysis_stats: Optional dict mapping analysis_type → {"mean": ..., "max": ...}
                        Used to build context-aware result queries.

    Returns:
        Dict with generated queries keyed by priority label
    """
    context = extract_research_context(
        user_goal=user_goal,
        protein_name=protein_name,
        analysis_types=analysis_types,
        analysis_stats=analysis_stats,
    )

    # ── 1. Resolve protein name ───────────────────────────────────────────
    _raw_name = (protein_name or "").strip()
    if not _raw_name and context["protein_names"]:
        _raw_name = context["protein_names"][0]

    # Known functional-context keywords that add biological specificity
    _FUNC_KEYWORDS = [
        "kinase", "pseudokinase", "protease", "receptor", "channel",
        "transporter", "enzyme", "inhibitor", "ligand", "antibody",
        "chaperone", "transferase", "synthase", "reductase", "oxidase",
        "dehydrogenase", "hydrolase", "lyase", "isomerase", "polymerase",
    ]

    # Collect functional context words from both protein_name and goal
    goal_lower = (user_goal or "").lower()
    name_lower = _raw_name.lower()
    func_context = []
    for kw in _FUNC_KEYWORDS:
        if kw in name_lower or kw in goal_lower:
            func_context.append(kw)
    func_context = list(dict.fromkeys(func_context))

    # Decide the primary search name: prefer the given protein_name.
    if _raw_name:
        _name = _raw_name
    elif func_context:
        _name = max(func_context, key=len)
    elif user_goal:
        _STOP = {
            "analysis", "please", "could", "would", "should", "compute",
            "calculate", "analyse", "analyze", "trajectory", "simulation",
            "dynamics", "molecular", "protein", "report", "working",
            "generate", "plots", "values", "steps", "required",
            "additional", "preprocessing", "given", "initial", "structure",
            "already", "finished", "trajectory", "finised", "reporter",
            "agent", "scientific", "based", "comments", "result",
            "those", "data", "secondary", "calculate", "only",
        }
        goal_words = [
            w for w in goal_lower.replace(",", " ").replace(".", " ").split()
            if len(w) > 3 and w not in _STOP
        ]
        _name = goal_words[0] if goal_words else ""
    else:
        _name = ""

    # ── 2. Build queries in priority order ───────────────────────────────
    queries = {}  # Ordered dict (Python 3.7+)

    # Multi-protein names from user goal (e.g. ERBB3, VRK3)
    for idx, pname in enumerate(context["protein_names"][:4]):
        queries[f"protein_{idx}_dynamics"] = f"{pname} protein dynamics molecular dynamics"
        if func_context:
            queries[f"protein_{idx}_function"] = (
                f"{pname} {' '.join(func_context[:2])} structure dynamics"
            )

    if _name:
        # Priority 1a: protein name + MD simulation
        queries["protein_dynamics"] = f"{_name} molecular dynamics simulation"
        # Priority 1b: protein name + structure/function
        queries["protein_function"] = f"{_name} structure function"
        # Priority 1c: protein name + functional context (if available)
        if func_context:
            fc = " ".join(func_context[:2])
            queries["protein_context"] = f"{_name} {fc} molecular dynamics"

    # Ligand / ATP effect queries from user goal
    if context["ligand_terms"] and _name:
        lig = context["ligand_terms"][0]
        queries["ligand_effect"] = f"{_name} {lig} binding protein dynamics simulation"

    # Region-specific queries (e.g. activation loop residues 150-190)
    if context["region_terms"] and _name:
        region = context["region_terms"][0]
        queries["region_dynamics"] = f"{_name} {region} flexibility dynamics"

    # DCCM / allosteric when requested or computed
    if any("dccm" in a.lower() or "correlation" in a.lower()
           for a in (analysis_types or [])) or "dccm" in goal_lower:
        if _name:
            queries["allosteric_dccm"] = (
                f"{_name} allosteric communication correlated motion molecular dynamics"
            )

    # ── 3. Protein + analysis method queries ─────────────────────────────
    _METHOD_TEMPLATES = {
        "RMSD": "RMSD stability molecular dynamics",
        "RMSF": "RMSF residue flexibility dynamics",
        "Radius_of_Gyration": "radius of gyration compactness",
        "Energy": "energy stability thermodynamic",
        "SASA": "solvent accessible surface area",
        "Secondary_Structure": "secondary structure DSSP",
        "COM_Analysis": "center of mass trajectory",
    }

    for atype in analysis_types:
        method_terms = None
        for tkey, tval in _METHOD_TEMPLATES.items():
            if tkey.lower() in atype.lower() or atype.lower() in tkey.lower():
                method_terms = tval
                break
        if method_terms is None:
            method_terms = f"{atype} molecular dynamics"

        if _name:
            # Protein-specific method query (most relevant)
            queries[f"method_{atype}"] = f"{_name} {method_terms}"
        else:
            queries[f"method_{atype}"] = f"protein {method_terms}"

    # ── 4. Analysis-result–driven queries ────────────────────────────────
    stats = analysis_stats or {}
    if stats and _name:

        # RMSD: high values → instability; low → stable
        for key in stats:
            if "rmsd" in key.lower():
                mean_rmsd = stats[key].get("mean_rmsd_angstrom") or stats[key].get("mean", 0)
                if mean_rmsd and float(mean_rmsd) > 3.0:
                    queries["result_rmsd_instability"] = (
                        f"{_name} conformational instability RMSD molecular dynamics"
                    )
                else:
                    queries["result_rmsd_stability"] = (
                        f"{_name} conformational stability RMSD molecular dynamics"
                    )
                break

        # RMSF: high values → flexible regions / loops
        for key in stats:
            if "rmsf" in key.lower():
                mean_rmsf = stats[key].get("mean_rmsf_angstrom") or stats[key].get("mean", 0)
                if mean_rmsf and float(mean_rmsf) > 2.0:
                    queries["result_rmsf_flexibility"] = (
                        f"{_name} flexible loop region dynamics"
                    )
                break

        # Rg: high → expanded; low → compact
        for key in stats:
            if "rg" in key.lower() or "gyration" in key.lower():
                mean_rg = stats[key].get("mean_rg_angstrom") or stats[key].get("mean", 0)
                if mean_rg and float(mean_rg) > 25.0:
                    queries["result_rg_expanded"] = (
                        f"{_name} expanded conformation unfolding molecular dynamics"
                    )
                elif mean_rg and float(mean_rg) < 15.0:
                    queries["result_rg_compact"] = (
                        f"{_name} compact folded structure dynamics"
                    )
                break

    # ── 5. Hypothesis / objective queries from user goal ─────────────────
    if user_goal and _name:
        hyp_terms = context.get("hypothesis_terms") or []
        if hyp_terms:
            hyp_str = " ".join(hyp_terms[:3])
            queries["hypothesis_objective"] = f"{_name} {hyp_str} molecular dynamics"

    # ── 6. Generic fallback ───────────────────────────────────────────────
    queries["_fallback_general"] = "molecular dynamics protein stability review"

    logger.info(
        "Generated %d literature queries (protein=%r, func_context=%s)",
        len(queries), _name or "unknown", func_context,
    )

    return {
        "success": True,
        "queries": queries,
        "total": len(queries),
        "protein_name": _name or None,
        "research_context": context,
    }
