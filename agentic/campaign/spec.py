"""Typed campaign program: systems, shared analysis protocol, and artifact contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RecipeStep:
    """One deterministic analysis tool invocation."""

    name: str
    tool_name: str
    description: str = ""
    tool_params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisRecipe:
    """Shared analysis protocol cloned onto every system (same tools and output dirs)."""

    steps: List[RecipeStep] = field(default_factory=list)
    required_feature_columns: List[str] = field(default_factory=list)
    metric_groups: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "required_feature_columns": list(self.required_feature_columns),
            "metric_groups": list(self.metric_groups),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "AnalysisRecipe":
        data = data or {}
        steps = [
            RecipeStep(
                name=str(s.get("name") or s.get("tool_name") or "step"),
                tool_name=str(s.get("tool_name") or ""),
                description=str(s.get("description") or ""),
                tool_params=dict(s.get("tool_params") or {}),
                reason=str(s.get("reason") or ""),
            )
            for s in (data.get("steps") or [])
            if s
        ]
        return cls(
            steps=steps,
            required_feature_columns=list(data.get("required_feature_columns") or []),
            metric_groups=list(data.get("metric_groups") or []),
        )


@dataclass
class ArtifactContract:
    """On-disk files that must exist before a stage is considered done."""

    modular_dirs: List[str] = field(default_factory=list)
    analysis_markers: List[str] = field(default_factory=list)
    min_features_present: int = 1
    min_complete_fraction: float = 0.85

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ArtifactContract":
        data = data or {}
        return cls(
            modular_dirs=list(data.get("modular_dirs") or []),
            analysis_markers=list(data.get("analysis_markers") or []),
            min_features_present=int(data.get("min_features_present") or 1),
            min_complete_fraction=float(data.get("min_complete_fraction") or 0.85),
        )


@dataclass
class CampaignSpec:
    """Single source of truth compiled once from the natural-language goal."""

    mode: str = "generic"
    n_systems: int = 0
    labels: List[str] = field(default_factory=list)
    family_modular: bool = False
    analysis_recipe: AnalysisRecipe = field(default_factory=AnalysisRecipe)
    pre_combined_recipe: AnalysisRecipe = field(default_factory=AnalysisRecipe)
    contract: ArtifactContract = field(default_factory=ArtifactContract)
    pin_tools: List[str] = field(default_factory=list)  # required calculations (every protein)
    pin_pre_tools: List[str] = field(default_factory=list)  # required shared setup (MSA/pocket)
    pre_combined_compiled: bool = False
    allow_partial_combined: bool = False
    original_goal: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "n_systems": self.n_systems,
            "labels": list(self.labels),
            "family_modular": self.family_modular,
            "analysis_recipe": self.analysis_recipe.to_dict(),
            "pre_combined_recipe": self.pre_combined_recipe.to_dict(),
            "contract": self.contract.to_dict(),
            "pin_tools": list(self.pin_tools),
            "required_calculations": list(self.pin_tools),
            "pin_pre_tools": list(self.pin_pre_tools),
            "required_shared_setup": list(self.pin_pre_tools),
            "pre_combined_compiled": self.pre_combined_compiled,
            "allow_partial_combined": self.allow_partial_combined,
            "original_goal": self.original_goal,
            "settings": dict(self.settings or {}),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CampaignSpec":
        data = data or {}
        return cls(
            mode=str(data.get("mode") or "generic"),
            n_systems=int(data.get("n_systems") or 0),
            labels=list(data.get("labels") or []),
            family_modular=bool(data.get("family_modular")),
            analysis_recipe=AnalysisRecipe.from_dict(
                data.get("analysis_recipe") or data.get("shared_analysis_protocol")
            ),
            pre_combined_recipe=AnalysisRecipe.from_dict(
                data.get("pre_combined_recipe") or data.get("shared_setup_protocol")
            ),
            contract=ArtifactContract.from_dict(data.get("contract")),
            pin_tools=list(data.get("pin_tools") or data.get("required_calculations") or []),
            pin_pre_tools=list(data.get("pin_pre_tools") or data.get("required_shared_setup") or []),
            pre_combined_compiled=bool(data.get("pre_combined_compiled")),
            allow_partial_combined=bool(data.get("allow_partial_combined")),
            original_goal=str(data.get("original_goal") or ""),
            settings=dict(data.get("settings") or {}),
        )

    @property
    def required_calculations(self) -> List[str]:
        """Measurements that must run for every protein."""
        return list(self.pin_tools)

    @property
    def required_shared_setup(self) -> List[str]:
        """Structure-only calculations every simulation will consume (MSA, pocket, maps)."""
        return list(self.pin_pre_tools)

    @property
    def shared_analysis_protocol(self) -> AnalysisRecipe:
        """Same analysis protocol applied to every protein."""
        return self.analysis_recipe


def spec_from_state(state: Optional[Dict[str, Any]]) -> Optional[CampaignSpec]:
    """Load a CampaignSpec from workflow state if present."""
    if not state:
        return None
    raw = state.get("campaign_spec")
    if isinstance(raw, CampaignSpec):
        return raw
    if isinstance(raw, dict) and raw:
        return CampaignSpec.from_dict(raw)
    return None
