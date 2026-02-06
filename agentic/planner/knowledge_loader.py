"""
Knowledge Base Loader

Loads and manages knowledge documents (research papers, manuals, protocols) 
for the planner agent to access during execution planning.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class KnowledgeLoader:
    """
    Loads and manages knowledge documents for planner context.
    
    Supports:
    - Markdown files (.md)
    - Text files (.txt)
    - JSON files (.json) for structured knowledge
    - PDF files (.pdf) - basic text extraction
    """
    
    def __init__(self, knowledge_base_path: Optional[str] = None):
        """
        Initialize knowledge loader.
        
        Args:
            knowledge_base_path: Path to knowledge directory (defaults to planner/knowledge)
        """
        if knowledge_base_path is None:
            # Default to knowledge directory in planner
            current_dir = Path(__file__).parent
            knowledge_base_path = str(current_dir / "knowledge")
        
        self.knowledge_path = Path(knowledge_base_path)
        self.knowledge_docs = {}
        self.knowledge_by_category = {}
        
        # Create knowledge directory if it doesn't exist
        self.knowledge_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized KnowledgeLoader with path: {self.knowledge_path}")
    
    def load_all_knowledge(self) -> Dict[str, Any]:
        """
        Load all knowledge documents from the knowledge base.
        
        Returns:
            Dict mapping document names to their content and metadata
        """
        logger.info("Loading knowledge base...")
        
        if not self.knowledge_path.exists():
            logger.warning(f"Knowledge path does not exist: {self.knowledge_path}")
            return {}
        
        # Scan all subdirectories
        for root, dirs, files in os.walk(self.knowledge_path):
            root_path = Path(root)
            category = root_path.relative_to(self.knowledge_path).parts[0] if root_path != self.knowledge_path else "general"
            
            for filename in files:
                file_path = root_path / filename
                
                # Skip hidden files and non-document files
                if filename.startswith(".") or filename.startswith("_"):
                    continue
                
                # Load based on file extension
                if filename.endswith((".md", ".txt", ".json", ".pdf")):
                    self._load_document(file_path, category)
        
        logger.info(f"Loaded {len(self.knowledge_docs)} knowledge documents across {len(self.knowledge_by_category)} categories")
        return self.knowledge_docs
    
    def _load_document(self, file_path: Path, category: str):
        """
        Load a single knowledge document.
        
        Args:
            file_path: Path to document file
            category: Document category (subdirectory name)
        """
        try:
            doc_name = file_path.stem
            doc_key = f"{category}.{doc_name}"
            
            # Read content based on extension
            if file_path.suffix == ".json":
                with open(file_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                doc_type = "json"
            elif file_path.suffix == ".pdf":
                content = self._extract_pdf_text(file_path)
                doc_type = "pdf"
            else:  # .md or .txt
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                doc_type = "text"
            
            # Store document
            self.knowledge_docs[doc_key] = {
                "name": doc_name,
                "category": category,
                "file_path": str(file_path),
                "type": doc_type,
                "content": content,
                "size": len(str(content))
            }
            
            # Group by category
            if category not in self.knowledge_by_category:
                self.knowledge_by_category[category] = []
            self.knowledge_by_category[category].append(doc_key)
            
            logger.debug(f"Loaded document: {doc_key} ({len(str(content))} characters)")
            
        except Exception as e:
            logger.error(f"Error loading document {file_path}: {e}", exc_info=True)
    
    def _extract_pdf_text(self, file_path: Path) -> str:
        """
        Extract text from PDF file.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text content
        """
        try:
            import PyPDF2
            
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                text = []
                for page in pdf_reader.pages:
                    text.append(page.extract_text())
                return "\n".join(text)
        except ImportError:
            logger.warning("PyPDF2 not installed. Cannot extract PDF text. Install with: pip install PyPDF2")
            return f"[PDF content not extracted - PyPDF2 not available: {file_path.name}]"
        except Exception as e:
            logger.error(f"Error extracting PDF text from {file_path}: {e}")
            return f"[Error extracting PDF: {file_path.name}]"
    
    def get_knowledge_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get all knowledge documents in a specific category.
        
        Args:
            category: Category name (subdirectory name)
            
        Returns:
            List of document metadata dicts
        """
        doc_keys = self.knowledge_by_category.get(category, [])
        return [self.knowledge_docs[key] for key in doc_keys]
    
    def get_document(self, doc_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific knowledge document.
        
        Args:
            doc_key: Document key (category.name)
            
        Returns:
            Document metadata dict or None
        """
        return self.knowledge_docs.get(doc_key)
    
    def search_knowledge(self, query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search knowledge base for documents matching query.
        
        Args:
            query: Search query string
            category: Optional category filter
            
        Returns:
            List of matching documents
        """
        query_lower = query.lower()
        matches = []
        
        docs_to_search = self.knowledge_docs.values()
        if category:
            doc_keys = self.knowledge_by_category.get(category, [])
            docs_to_search = [self.knowledge_docs[key] for key in doc_keys]
        
        for doc in docs_to_search:
            # Search in name and content
            content_str = str(doc["content"]).lower()
            if query_lower in doc["name"].lower() or query_lower in content_str:
                matches.append(doc)
        
        logger.debug(f"Found {len(matches)} documents matching query: {query}")
        return matches
    
    def get_knowledge_summary(self) -> str:
        """
        Generate a human-readable summary of the knowledge base.
        
        Returns:
            Formatted string with knowledge base overview
        """
        summary = ["=" * 80, "KNOWLEDGE BASE SUMMARY", "=" * 80, ""]
        
        summary.append(f"Total Documents: {len(self.knowledge_docs)}")
        summary.append(f"Categories: {len(self.knowledge_by_category)}\n")
        
        for category, doc_keys in sorted(self.knowledge_by_category.items()):
            summary.append(f"\n### {category.upper()} ###")
            summary.append("-" * 60)
            
            for doc_key in doc_keys:
                doc = self.knowledge_docs[doc_key]
                summary.append(f"📄 {doc['name']}")
                summary.append(f"   Type: {doc['type']} | Size: {doc['size']} chars")
                
                # Show first 200 chars of content as preview
                content_preview = str(doc['content'])[:200].replace("\n", " ")
                summary.append(f"   Preview: {content_preview}...")
                summary.append("")
        
        summary.append("=" * 80)
        return "\n".join(summary)
    
    def get_knowledge_for_planner(self, 
                                   category: Optional[str] = None,
                                   max_chars: int = 10000) -> str:
        """
        Get formatted knowledge content for planner LLM context.
        
        Args:
            category: If specified, only include this category
            max_chars: Maximum characters to include (to fit in LLM context)
            
        Returns:
            Formatted knowledge string suitable for LLM prompts
        """
        formatted = ["**Available Knowledge:**\n"]
        total_chars = 0
        
        categories_to_include = [category] if category else sorted(self.knowledge_by_category.keys())
        
        for cat in categories_to_include:
            if cat not in self.knowledge_by_category:
                continue
            
            formatted.append(f"\n### {cat.upper()} ###")
            
            for doc_key in self.knowledge_by_category[cat]:
                doc = self.knowledge_docs[doc_key]
                
                # Add document header
                doc_header = f"\n**{doc['name']}** ({doc['type']})"
                formatted.append(doc_header)
                
                # Add content (truncated if needed)
                content = str(doc['content'])
                remaining_chars = max_chars - total_chars - len(doc_header)
                
                if remaining_chars <= 0:
                    formatted.append("...[Content truncated to fit context limit]...")
                    break
                
                if len(content) > remaining_chars:
                    content = content[:remaining_chars] + "...[truncated]"
                
                formatted.append(content)
                total_chars += len(content) + len(doc_header)
                
                if total_chars >= max_chars:
                    break
            
            if total_chars >= max_chars:
                break
        
        return "\n".join(formatted)
    
    def get_knowledge_files_summary(self, category: Optional[str] = None) -> str:
        """
        Get a summary of available knowledge files (for logging, not LLM context).
        
        Args:
            category: If specified, only include this category
            
        Returns:
            Formatted list of knowledge files without full content
        """
        formatted = []
        
        categories_to_include = [category] if category else sorted(self.knowledge_by_category.keys())
        
        for cat in categories_to_include:
            if cat not in self.knowledge_by_category:
                continue
            
            formatted.append(f"\n### {cat.upper()} ###")
            
            for doc_key in self.knowledge_by_category[cat]:
                doc = self.knowledge_docs[doc_key]
                size_kb = doc['size'] / 1024
                formatted.append(f"  - {doc['name']} ({doc['type']}, {size_kb:.1f} KB)")
        
        return "\n".join(formatted)
    
    def get_categories(self) -> List[str]:
        """
        Get list of all knowledge categories.
        
        Returns:
            List of category names
        """
        return list(self.knowledge_by_category.keys())


# Global knowledge loader instance
_global_loader = None


def get_knowledge_loader(knowledge_path: Optional[str] = None, refresh: bool = False) -> KnowledgeLoader:
    """
    Get or create the global knowledge loader.
    
    Args:
        knowledge_path: Path to knowledge directory (optional)
        refresh: If True, reload all knowledge
        
    Returns:
        KnowledgeLoader instance
    """
    global _global_loader
    
    if _global_loader is None or refresh:
        _global_loader = KnowledgeLoader(knowledge_path)
        _global_loader.load_all_knowledge()
    
    return _global_loader
