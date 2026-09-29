"""Compile a CampaignSpec once from the master goal + planned systems."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agentic.campaign.family_recipe import (
    REQUIRED_CALCULATIONS,
    build_shared_analysis_protocol,
    family_contract,
)
from agentic.campaign.pre_combined import (
    REQUIRED_SHARED_SETUP,
    build_shared_setup_protocol,
)
from agentic.campaign.spec import AnalysisRecipe, ArtifactContract, CampaignSpec, spec_from_state

logger = logging.getLogger(__name__)


def compile_campaign_spec(state: Optional[Dict[str, Any]] = None) -> CampaignSpec:
    """Build (or refresh) the campaign program from workflow state.

    Family-modular goals get the shared analysis protocol and a hard artifact
    contract. Generic goals leave the protocol empty so LLM/retrieval planning
    still applies.
    """
    state = state or {}
    original = (
        state.get("user_goal_original")
        or state.get("user_goal")
        or ""
    )
    sim_prompts = state.get("sim_prompts") or []
    labels: List[str] = [
        str(sp.get("label") or "") for sp in sim_prompts if sp.get("label")
    ]
    if not labels:
        labels = [
            str(p).rsplit("/", 1)[-1].replace(".pdb", "")
            for p in (state.get("pdb_list") or [])
        ]

    family = False
    try:
        from agentic.planner.planning_guidelines import (
            detect_family_modular_dynamics_requested,
        )

        family = bool(detect_family_modular_dynamics_requested(original))
    except Exception:
        family = False

    allow_partial = bool(state.get("allow_partial_combined"))
    existing = spec_from_state(state)
    try:
        from agentic.campaign.config import settings_from_state

        settings = settings_from_state(state)
        settings_dict = settings.to_dict()
        gold = list(settings.gold_columns or [])
    except Exception:
        settings = None
        settings_dict = {}
        gold = []
    if family:
        spec = CampaignSpec(
            mode="family_modular",
            n_systems=len(labels),
            labels=labels,
            family_modular=True,
            analysis_recipe=build_shared_analysis_protocol(gold_columns=gold or None),
            pre_combined_recipe=build_shared_setup_protocol(settings=settings),
            contract=family_contract(),
            pin_tools=list(REQUIRED_CALCULATIONS),
            pin_pre_tools=list(REQUIRED_SHARED_SETUP),
            allow_partial_combined=allow_partial,
            original_goal=str(original),
            settings=settings_dict,
        )
    else:
        spec = CampaignSpec(
            mode="generic",
            n_systems=len(labels),
            labels=labels,
            family_modular=False,
            analysis_recipe=AnalysisRecipe(),
            pre_combined_recipe=AnalysisRecipe(),
            contract=ArtifactContract(),
            pin_tools=[],
            pin_pre_tools=[],
            allow_partial_combined=True,
            original_goal=str(original),
            settings=settings_dict,
        )
    # Keep an LLM-compiled pre_combined recipe across spec refreshes.
    if existing and existing.pre_combined_compiled and existing.pre_combined_recipe.steps:
        spec.pre_combined_recipe = existing.pre_combined_recipe
        spec.pre_combined_compiled = True
        spec.pin_pre_tools = list(existing.pin_pre_tools or spec.pin_pre_tools)
    logger.info(
        "CampaignSpec compiled: mode=%s n=%d family=%s required_calculations=%s",
        spec.mode,
        spec.n_systems,
        spec.family_modular,
        spec.pin_tools,
    )
    return spec
