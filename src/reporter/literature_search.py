"""Literature search functionality for scientific reports"""
import logging
import json
from typing import Dict, Any, List, Optional
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, urlencode
from urllib.error import URLError
from langchain.tools import tool

logger = logging.getLogger(__name__)


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
    protein_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate PubMed search queries prioritising the protein and its
    functional context, then the analysis methods used.

    Query priority order:
      1. Protein name + functional context (structure, function, dynamics)
      2. Protein name + specific analysis method
      3. Generic analysis method queries (fallback)

    Args:
        analysis_types: List of analysis types performed (e.g., ["RMSD", "RMSF"])
        user_goal: User's original goal/question (helps extract protein context)
        protein_name: Explicit protein / system name (e.g. "pseudokinase")

    Returns:
        Dict with generated queries keyed by priority label
    """
    # --- 1. Resolve protein name and functional keywords -----------------
    _raw_name = (protein_name or "").strip()

    # Known functional-context keywords that commonly appear next to a
    # protein name in the user goal (case-insensitive matching).
    # These are ALSO valid PubMed search terms (correctly spelled).
    _FUNC_KEYWORDS = [
        "kinase", "pseudokinase", "protease", "receptor", "channel",
        "transporter", "enzyme", "inhibitor", "ligand", "antibody",
        "chaperone", "transferase", "synthase", "reductase", "oxidase",
        "dehydrogenase", "hydrolase", "lyase", "isomerase", "polymerase",
    ]

    # Scan user_goal for functional keywords (these are reliable, correctly spelled)
    func_context = []
    goal_lower = (user_goal or "").lower()
    for kw in _FUNC_KEYWORDS:
        if kw in goal_lower:
            func_context.append(kw)
    # Also check _raw_name for functional keywords
    name_lower = _raw_name.lower()
    for kw in _FUNC_KEYWORDS:
        if kw in name_lower and kw not in func_context:
            func_context.append(kw)
    func_context = list(dict.fromkeys(func_context))

    # Build the primary search name:
    # Prefer the most specific functional keyword found (correctly spelled)
    # over the raw system_name which may contain typos.
    if func_context:
        # Use the most specific (longest) keyword as the primary name
        _name = max(func_context, key=len)
    elif _raw_name:
        _name = _raw_name
    elif user_goal:
        # Fallback: extract first domain word from user_goal
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

    # --- 2. Build queries in priority order ------------------------------
    queries = {}  # Ordered dict (Python 3.7+)

    if _name:
        # Priority 1a: protein + structure/function
        queries["protein_dynamics"] = f"{_name} molecular dynamics simulation"
        queries["protein_function"] = f"{_name} structure function"
        if func_context:
            fc = " ".join(func_context[:2])
            queries["protein_context"] = f"{_name} {fc} molecular dynamics"

    # Priority 2: protein + analysis methods
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

        # Method queries stay broad (no protein name) so they return results
        queries[f"method_{atype}"] = f"protein {method_terms}"

    # Priority 3: generic fallbacks (only used if everything above fails)
    queries["_fallback_general"] = "molecular dynamics protein stability review"

    logger.info("Generated %d literature queries (protein=%s)", len(queries), _name or "unknown")

    return {
        "success": True,
        "queries": queries,
        "total": len(queries),
        "protein_name": _name or None,
    }
