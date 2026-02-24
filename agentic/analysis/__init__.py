"""
Analysis module for AgenticAI

Provides MD trajectory analysis capabilities including:
- RMSD (Root Mean Square Deviation) - structural stability
- RMSF (Root Mean Square Fluctuation) - residue flexibility
- Radius of gyration - protein compactness
- Energy analysis - thermodynamic properties
- Trajectory metrics - basic statistics

Components:
- MDAnalysisAgent: Main agent class with LLM-powered planning
- Tools: Wrapper functions for src/analysis/ implementations
- Schemas: Workflow orchestration and result models

Note: Tool-level input validation is handled by LangChain's @tool decorator.
"""

from .analysis_agent import MDAnalysisAgent
from .tools import (
    calculate_rmsd,
    calculate_rmsf,
    calculate_radius_of_gyration,
    analyze_energy,
    extract_trajectory_metrics,
    AnalysisToolExecutor,
    run_complete_analysis
)
from .schemas import (
    AnalysisResult,
    RMSDResult,
    RMSFResult,
    GyrationResult,
    EnergyResult,
    AnalysisWorkflowInput,
    AnalysisWorkflowOutput
)

__all__ = [
    # Agent
    "MDAnalysisAgent",
    
    # Tools
    "calculate_rmsd",
    "calculate_rmsf",
    "calculate_radius_of_gyration",
    "analyze_energy",
    "extract_trajectory_metrics",
    "AnalysisToolExecutor",
    "run_complete_analysis",
    
    # Schemas (workflow and results only)
    "AnalysisResult",
    "RMSDResult",
    "RMSFResult",
    "GyrationResult",
    "EnergyResult",
    "AnalysisWorkflowInput",
    "AnalysisWorkflowOutput",
]


