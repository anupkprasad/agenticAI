"""
Supervisor Helper Tools

Thin wrapper that exposes modular functions from src/supervisor/.
Provides unified input validation, component parsing, and prompt enrichment.
"""
import logging

# Import all tool implementations from src/supervisor/
from src.supervisor import (
    parse_component_selection,
    validate_feasibility,
    build_human_summary,
    extract_file_names_from_goal,
    detect_task_required_inputs,
    rephrase_with_context,
    enrich_prompt_with_context,
    validate_and_enrich_inputs,
)

# Export all functions for direct access
__all__ = [
    "parse_component_selection",
    "validate_feasibility",
    "build_human_summary",
    "extract_file_names_from_goal",
    "detect_task_required_inputs",
    "rephrase_with_context",
    "enrich_prompt_with_context",
    "validate_and_enrich_inputs",
    # Legacy names for backward compatibility
    "enrich_user_prompt",
    "enrich_analysis_prompt",
]

logger = logging.getLogger(__name__)


# Legacy wrapper functions for backward compatibility
def enrich_user_prompt(user_goal, pdb_analysis, pdb_summary, llm_client, config):
    """Legacy wrapper - use enrich_prompt_with_context instead."""
    return enrich_prompt_with_context(
        user_goal=user_goal,
        context_type="pdb",
        context_data={"pdb_analysis": pdb_analysis, "pdb_summary": pdb_summary},
        llm_client=llm_client,
        config=config
    )


def enrich_analysis_prompt(user_goal, file_info, llm_client, config):
    """Legacy wrapper - use enrich_prompt_with_context instead."""
    return enrich_prompt_with_context(
        user_goal=user_goal,
        context_type="files",
        context_data={"file_info": file_info},
        llm_client=llm_client,
        config=config
    )
