"""Literature search functionality for scientific reports"""
import logging
from typing import Dict, Any, List, Optional
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
            
            articles = []
            for article in records.get("PubmedArticle", []):
                try:
                    medline = article.get("MedlineCitation", {})
                    article_data = medline.get("Article", {})
                    
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


@tool
def generate_literature_queries(
    analysis_types: List[str],
    user_goal: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate PubMed search queries based on analysis types.
    
    Creates optimized search queries for each analysis type to find
    relevant literature automatically.
    
    Args:
        analysis_types: List of analysis types performed (e.g., ["RMSD", "RMSF"])
        user_goal: User's original goal/question (optional, helps refine queries)
    
    Returns:
        Dict with generated queries for each analysis type
    """
    # Default query templates
    query_templates = {
        "RMSD": "root mean square deviation molecular dynamics protein stability",
        "RMSF": "root mean square fluctuation residue flexibility protein dynamics",
        "Radius_of_Gyration": "radius of gyration protein compactness folding",
        "Energy": "molecular dynamics energy stability thermodynamic analysis",
        "SASA": "solvent accessible surface area protein binding interface",
        "Secondary_Structure": "secondary structure DSSP molecular dynamics",
        "COM_Analysis": "center of mass protein motion trajectory analysis"
    }
    
    queries = {}
    for atype in analysis_types:
        # Match analysis type (case-insensitive, flexible matching)
        matched = False
        for template_key in query_templates:
            if template_key.lower() in atype.lower() or atype.lower() in template_key.lower():
                queries[atype] = query_templates[template_key]
                matched = True
                break
        
        if not matched:
            # Generic query for unknown analysis types
            queries[atype] = f"{atype} molecular dynamics simulation analysis"
    
    # Add user goal context if provided
    if user_goal:
        # Extract key terms from user goal (simplified)
        user_terms = [word for word in user_goal.lower().split() 
                      if len(word) > 4 and word not in ["analysis", "please", "could", "would"]]
        if user_terms:
            context = " ".join(user_terms[:3])  # Max 3 terms
            for atype in queries:
                queries[atype] += f" {context}"
    
    logger.info(f"Generated {len(queries)} literature queries")
    
    return {
        "success": True,
        "queries": queries,
        "total": len(queries)
    }
