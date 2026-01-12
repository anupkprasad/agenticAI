from __future__ import annotations

from typing import Any
import asyncio

from .agents import (
    SimulationAgentWrapper,
    PreprocessorAgentWrapper,
    HPCAgentWrapper,
    AnalysisAgentWrapper,
)
from .planner_agent import PlannerAgent


async def agent_from_name(name: str, **kwargs) -> Any:
    """Async factory returning agent instances by name.

    Example:
        agent = await agent_from_name("simulation")
        await agent.plan_simulation("0.pdb", "/tmp/run")
    """
    name = (name or "").lower()
    if name in ("simulation", "simulation_agent"):
        return SimulationAgentWrapper(**kwargs)
    if name in ("preprocessor", "preprocessor_agent"):
        return PreprocessorAgentWrapper(**kwargs)
    if name in ("hpc", "hpc_agent"):
        return HPCAgentWrapper(**kwargs)
    if name in ("analysis", "analysis_agent"):
        return AnalysisAgentWrapper(**kwargs)
    if name in ("planner", "planner_agent"):
        return PlannerAgent(**kwargs)
    if name in ("agent_creator", "creator"):
        # return a lightweight meta-agent that can orchestrate others
        return AgentCreator(**kwargs)
    raise ValueError(f"Unknown agent name: {name}")


class AgentCreator:
    """A simple meta-agent that composes the other agents.

    This is intentionally small: it demonstrates how you might orchestrate
    fetching/preparing/scheduling/analysis in a single high-level agent.
    """
    def __init__(self, **kwargs):
        self.sim = SimulationAgentWrapper()
        self.ana = AnalysisAgentWrapper()
        self.pre = PreprocessorAgentWrapper()
        self.hpc = HPCAgentWrapper()
        self.planner = PlannerAgent()

    async def run_simulation_workflow(self, pdb: str, wdir: str) -> dict:
        # 1) Plan via planner (optional)
        plan = await self.planner.plan(f"Prepare simulation for {pdb} in {wdir}")
        # 1.5) Preprocess inputs (if available)
        try:
            preproc = await self.pre.preprocess(pdb, wdir)
        except Exception:
            preproc = {"status": "skipped"}

        # 2) Run simulation setup
        setup = await self.sim.plan_simulation(pdb, wdir)
        # 3) (mock) submit to HPC and wait for results - left as placeholder
        # 4) Analyze
        analysis = await self.ana.analyze(wdir)
        return {"plan": plan, "setup": setup, "analysis": analysis}
