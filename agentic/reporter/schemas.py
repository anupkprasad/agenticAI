"""
Pydantic schemas for Reporter Agent.

Defines input/output models for report generation, literature search,
and workflow coordination.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ReportType(str, Enum):
    """Types of reports that can be generated"""
    COMPREHENSIVE = "comprehensive"  # Detailed report with all analyses
    EXECUTIVE = "executive"  # Brief overview with key findings
    CUSTOM = "custom"  # User-defined format


class LiteratureSource(str, Enum):
    """Source for literature search"""
    PUBMED = "pubmed"
    ARXIV = "arxiv"
    BOTH = "both"


# ========== Input Schemas ==========

class ReporterAgentInput(BaseModel):
    """Input to reporter agent from workflow"""
    working_directory: str = Field(description="Root working directory")
    analysis_summary_file: str = Field(
        description="Path to analysis_summary.jsonl file"
    )
    user_goal: Optional[str] = Field(
        default=None,
        description="Original user's analysis goal/question"
    )
    report_type: ReportType = Field(
        default=ReportType.COMPREHENSIVE,
        description="Type of report to generate"
    )
    planner_instructions: Optional[str] = Field(
        default=None,
        description="Instructions from planner about what to highlight"
    )
    literature_search: bool = Field(
        default=True,
        description="Whether to search scientific literature"
    )
    literature_keywords: Optional[List[str]] = Field(
        default=None,
        description="Manual keywords for literature search (if None, auto-generate)"
    )
    literature_source: LiteratureSource = Field(
        default=LiteratureSource.PUBMED,
        description="Source for literature search"
    )
    include_visualizations: bool = Field(
        default=True,
        description="Whether to embed analysis plots in report"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (force field, MD engine, etc.)"
    )


# ========== Planning Schemas ==========

class ReporterStep(BaseModel):
    """Single step in reporter execution plan"""
    name: str = Field(description="Step name")
    description: str = Field(description="What this step does")
    tool_name: str = Field(description="Tool to invoke")
    tool_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for tool"
    )
    reason: str = Field(description="Why this step is needed")
    dependencies: List[str] = Field(
        default_factory=list,
        description="Steps that must complete first"
    )


class ReporterPlan(BaseModel):
    """Plan for generating report"""
    reasoning: str = Field(description="Why this approach was chosen")
    overview: str = Field(description="High-level summary of the plan")
    steps: List[ReporterStep] = Field(description="Ordered steps to execute")
    report_focus: List[str] = Field(
        default_factory=list,
        description="Key topics to emphasize in report"
    )
    literature_queries: List[str] = Field(
        default_factory=list,
        description="Literature search queries to execute"
    )
    estimated_complexity: Literal["low", "medium", "high"] = Field(
        description="Complexity estimate"
    )
    potential_issues: List[str] = Field(
        default_factory=list,
        description="Potential problems to watch for"
    )


# ========== Result Schemas ==========

class AnalysisSummaryEntry(BaseModel):
    """Parsed entry from analysis_summary.jsonl"""
    timestamp: str = Field(description="When analysis was run")
    analysis_type: str = Field(description="Type of analysis (e.g., RMSD, RMSF)")
    statistics: Dict[str, Any] = Field(description="Statistical results")
    files: Dict[str, str] = Field(description="Generated files")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class LiteratureReference(BaseModel):
    """Scientific literature reference"""
    title: str = Field(description="Paper title")
    authors: List[str] = Field(description="Author list")
    journal: Optional[str] = Field(None, description="Journal name")
    year: Optional[int] = Field(None, description="Publication year")
    doi: Optional[str] = Field(None, description="DOI")
    pmid: Optional[str] = Field(None, description="PubMed ID")
    abstract: Optional[str] = Field(None, description="Abstract text")
    relevance_score: Optional[float] = Field(
        None,
        description="Relevance score (0-1)"
    )
    url: Optional[str] = Field(None, description="URL to full text")


class ReportSection(BaseModel):
    """Section of generated report"""
    title: str = Field(description="Section title")
    content: str = Field(description="Section content (HTML)")
    subsections: List["ReportSection"] = Field(
        default_factory=list,
        description="Nested subsections"
    )
    figures: List[str] = Field(
        default_factory=list,
        description="Paths to figure files"
    )
    references: List[int] = Field(
        default_factory=list,
        description="Indices into literature references list"
    )


class ReporterResult(BaseModel):
    """Result of report generation execution"""
    success: bool = Field(description="Whether execution succeeded")
    completed_steps: int = Field(description="Number of steps completed")
    total_steps: int = Field(description="Total number of steps in plan")
    report_file: Optional[str] = Field(
        None,
        description="Path to generated HTML report"
    )
    analysis_summaries: List[AnalysisSummaryEntry] = Field(
        default_factory=list,
        description="Parsed analysis summary entries"
    )
    literature_references: List[LiteratureReference] = Field(
        default_factory=list,
        description="Found literature references"
    )
    report_sections: List[ReportSection] = Field(
        default_factory=list,
        description="Generated report sections"
    )
    key_findings: List[str] = Field(
        default_factory=list,
        description="LLM-extracted key findings"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="LLM-generated recommendations"
    )
    issues: List[str] = Field(
        default_factory=list,
        description="Issues encountered"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings"
    )
    report: str = Field(description="Execution report summary")
    generated_files: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of file types to paths"
    )
    step_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Results from each step"
    )


# ========== Output Schemas ==========

class ReporterAgentOutput(BaseModel):
    """Output from reporter agent"""
    success: bool = Field(description="Whether reporter succeeded")
    result: ReporterResult = Field(description="Detailed results")
    next_actions: List[str] = Field(
        default_factory=list,
        description="Recommended next steps"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Errors encountered"
    )
    report_path: Optional[str] = Field(
        None,
        description="Path to generated HTML report"
    )
    pdf_path: Optional[str] = Field(
        None,
        description="Path to PDF report (if converted)"
    )


# Enable forward references for nested models
ReportSection.model_rebuild()
