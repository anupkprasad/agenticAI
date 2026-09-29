"""Campaign compile / contract layer for family-scale SimAgent runs."""

from agentic.campaign.spec import (
    AnalysisRecipe,
    ArtifactContract,
    CampaignSpec,
    RecipeStep,
)
from agentic.campaign.config import (
    CampaignSettings,
    load_campaign_settings,
    settings_from_state,
)
from agentic.campaign.family_recipe import REQUIRED_CALCULATIONS
from agentic.campaign.compile import compile_campaign_spec
from agentic.campaign.memory import (
    remember_from_state,
    retrieve_episodes,
    retrieve_memory_for_prompt,
)
from agentic.campaign.prompt_quality import llm_sim_prompts_lose_shared_intent
from agentic.campaign.pre_combined import (
    FAMILY_PRE_PIN_TOOLS,
    REQUIRED_SHARED_SETUP,
    merge_pre_combined_steps,
    pre_combined_tool_allowed,
)
from agentic.campaign.contracts import (
    campaign_science_report,
    clustering_table_usable,
    decide_analysis_success,
    family_feature_matrix_ready,
    family_tool_already_done,
    is_noncritical_analysis_tool,
    per_sim_science_complete,
)
from agentic.campaign.snapshots import (
    persist_state_snapshots,
    spec_hash,
)

__all__ = [
    "AnalysisRecipe",
    "ArtifactContract",
    "CampaignSpec",
    "CampaignSettings",
    "RecipeStep",
    "compile_campaign_spec",
    "load_campaign_settings",
    "settings_from_state",
    "remember_from_state",
    "retrieve_episodes",
    "retrieve_memory_for_prompt",
    "llm_sim_prompts_lose_shared_intent",
    "REQUIRED_CALCULATIONS",
    "REQUIRED_SHARED_SETUP",
    "FAMILY_PRE_PIN_TOOLS",
    "merge_pre_combined_steps",
    "pre_combined_tool_allowed",
    "campaign_science_report",
    "clustering_table_usable",
    "decide_analysis_success",
    "family_feature_matrix_ready",
    "family_tool_already_done",
    "is_noncritical_analysis_tool",
    "per_sim_science_complete",
    "persist_state_snapshots",
    "spec_hash",
]
