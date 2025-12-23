"""Pydantic schemas for validated tool-call objects returned by the LLM.

These models are intentionally small and permissive: we validate the
presence and basic types for common actions (plan_simulation / run_simulation_setup)
and provide a general `ToolCall` model for unknown actions.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ValidationError, validator


class PlanSimulationParams(BaseModel):
    pdb: str = Field(..., description="Path to the input PDB file")
    wdir: str = Field(..., description="Working directory for the simulation")
    engine: Optional[str] = Field(None, description="MD engine name (gromacs, namd, etc)")
    steps: Optional[int] = Field(None, description="Number of MD steps / frames to run")

    @validator("pdb", "wdir")
    def not_empty(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("must be a non-empty string")
        return v.strip()


class ToolCall(BaseModel):
    name: str = Field(..., description="Tool/action name e.g. plan_simulation")
    args: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None

    def validate_args(self) -> Optional[ValidationError]:
        """Validate args for known tool names and coerce where possible.

        Returns a ValidationError if validation fails, otherwise None.
        """
        if self.name in ("plan_simulation", "run_simulation_setup"):
            try:
                params = PlanSimulationParams(**self.args)
                # replace with validated / coerced values
                self.args = params.model_dump()
                return None
            except ValidationError as e:
                return e
        # Unknown tool: no strict validation
        return None
