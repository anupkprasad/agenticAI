"""SupervisorAgent scaffold.

Responsible for high-level orchestration: receives a user prompt, asks
field-specific agents for proposed plans, validates them, and approves/dispatches
tool_calls. Uses a centralized LLM configuration and a shared LLM client.

This module is intentionally lightweight: it defines the orchestration APIs
and a simple example flow. Later we can plug in LangGraph flows and richer
policies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import asyncio
import logging

from .schemas import ToolCall
from .state_graph import StateGraph


@dataclass
class SupervisorAgent:
    """A simple Supervisor that coordinates field agents.

    For now it expects field agents to be passed in as keyword args to the
    constructor (dependency injection). Agents should implement two methods:
      - propose_plan(context) -> List[ToolCall]
      - execute_toolcall(toolcall) -> Dict (execution result)
    """

    planner: Any = None
    agents: Dict[str, Any] = None
    state: StateGraph = None

    def __init__(self, planner: Any = None, agents: Optional[Dict[str, Any]] = None):
        self.planner = planner
        self.agents = agents or {}
        self.state = StateGraph()

    def _select_agents_from_prompt(self, prompt: str) -> List[str]:
        """Return a list of agent keys we should contact for this prompt.

        This is a small heuristic used to avoid contacting every field agent
        for every prompt. It can be replaced later with an LLM-based intent
        classifier or a planner-derived routing decision.
        """
        p = prompt.lower()
        # If the user explicitly asks for simulation setup, only contact the
        # simulation agent (do not submit jobs or run analysis unless asked).
        if "setup" in p and "simulation" in p:
            return ["simulation"]
        # Fallback: contact all agents
        return list(self.agents.keys())

    def _make_field_prompt(self, user_prompt: str, agent_name: str) -> str:
        """Create a short, clear field-agent prompt derived from the user prompt.

        This ensures the field agent receives a focused instruction instead of
        the raw user prompt (which the supervisor may parse or enrich).
        """
        if agent_name == "simulation":
            return (
                f"You are the SimulationSetupAgent. The user asked: {user_prompt}\n"
                "Your job: produce a detailed plan (sequence of tool_calls) to set up the simulation only. "
                "Do NOT submit jobs to HPC or run post-run analysis. Include required fields (e.g. pdb, wdir, engine) in each tool_call. "
                "Return a JSON-list of tool_calls with their arguments."
            )
        # Generic fallback prompt
        return f"You are the {agent_name} agent. The user asked: {user_prompt}\nPlease propose a detailed plan (tool_calls) relevant to your role." 

    async def run(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Top-level entrypoint. Returns consolidated result and state snapshot.

        Steps (simplified):
          1) Ask planner for global plan (optional)
          2) Query relevant field agents for local plans
          3) Validate and approve plans
          4) Dispatch approved tool_calls and collect results
        """
        context = context or {}
        root_id = self.state.add_node("prompt", {"prompt": prompt, "context": context})

        # 1) global planning (if available)
        global_plan = None
        if self.planner is not None:
            try:
                if asyncio.iscoroutinefunction(self.planner.plan):
                    global_plan = await self.planner.plan(prompt)
                else:
                    # run in thread if blocking
                    loop = asyncio.get_running_loop()
                    global_plan = await loop.run_in_executor(None, self.planner.plan, prompt)
            except Exception as e:
                logging.getLogger(__name__).exception("Planner failed: %s", e)
                global_plan = None

        gp_id = self.state.add_node("global_plan", {"plan": global_plan})
        self.state.add_edge(root_id, gp_id, "planned")

        # 2) ask agents for proposals. Prefer planner-provided agent_calls
        # (normalized into global_plan['tool_calls']) if available; otherwise
        # fall back to the heuristic router that builds field prompts.
        proposals: Dict[str, List[ToolCall]] = {}
        planner_calls = None
        if isinstance(global_plan, dict):
            # Prefer planner-produced agent_calls (high-level prompts for
            # field agents). Fall back to legacy tool_calls only when
            # agent_calls are not provided.
            planner_calls = global_plan.get("agent_calls") or global_plan.get("tool_calls")

        if planner_calls:
            # planner_calls is expected to be a list of dicts with 'name' and 'args'
            for call in planner_calls:
                name = call.get("name")
                args = call.get("args", {}) or {}
                agent = self.agents.get(name)
                if agent is None:
                    logging.getLogger(__name__).warning("Planner requested agent '%s' not available", name)
                    continue
                # use planner-provided prompt when available, otherwise generate one
                field_prompt = args.get("prompt") or self._make_field_prompt(prompt, name)
                try:
                    if asyncio.iscoroutinefunction(agent.propose_plan):
                        p = await agent.propose_plan({"prompt": field_prompt, **context})
                    else:
                        loop = asyncio.get_running_loop()
                        p = await loop.run_in_executor(None, agent.propose_plan, {"prompt": field_prompt, **context})
                    calls = []
                    for item in (p or []):
                        if isinstance(item, ToolCall):
                            calls.append(item)
                        else:
                            try:
                                calls.append(ToolCall(**item))
                            except Exception:
                                logging.getLogger(__name__).warning("Agent %s returned invalid plan item: %s", name, item)
                    # append/merge multiple planner calls to same agent
                    proposals.setdefault(name, []).extend(calls)
                    self.state.add_node("proposal", {"agent": name, "tool_calls": [c.model_dump() for c in calls]})
                except Exception as e:
                    logging.getLogger(__name__).exception("Agent %s propose_plan failed: %s", name, e)
        else:
            target_agents = self._select_agents_from_prompt(prompt)
            for name in target_agents:
                agent = self.agents.get(name)
                if agent is None:
                    logging.getLogger(__name__).warning("Requested agent '%s' not available", name)
                    continue
                field_prompt = self._make_field_prompt(prompt, name)
                try:
                    if asyncio.iscoroutinefunction(agent.propose_plan):
                        p = await agent.propose_plan({"prompt": field_prompt, **context})
                    else:
                        loop = asyncio.get_running_loop()
                        p = await loop.run_in_executor(None, agent.propose_plan, {"prompt": field_prompt, **context})
                    # coerce to ToolCall instances when possible
                    calls = []
                    for item in (p or []):
                        if isinstance(item, ToolCall):
                            calls.append(item)
                        else:
                            try:
                                calls.append(ToolCall(**item))
                            except Exception:
                                logging.getLogger(__name__).warning("Agent %s returned invalid plan item: %s", name, item)
                    proposals[name] = calls
                    self.state.add_node("proposal", {"agent": name, "tool_calls": [c.model_dump() for c in calls]})
                except Exception as e:
                    logging.getLogger(__name__).exception("Agent %s propose_plan failed: %s", name, e)

        # 3) simple validation: ensure required fields exist for known tools
        approved: List[ToolCall] = []
        for agent_name, calls in proposals.items():
            for c in calls:
                err = c.validate_args() if hasattr(c, "validate_args") else None
                if err:
                    logging.getLogger(__name__).warning("Validation failed for %s: %s", c.name, err)
                    # attach validation error to state
                    self.state.add_node("validation_error", {"agent": agent_name, "tool_call": c.model_dump(), "error": str(err)})
                else:
                    # honor suggested agent if present, otherwise use owner
                    c.agent = c.agent or agent_name
                    approved.append(c)

        # 4) dispatch: execute approved tool_calls sequentially (async)
        results: List[Dict[str, Any]] = []
        for c in approved:
            agent_name = c.agent
            agent = self.agents.get(agent_name)
            self.state.add_node("approved_call", {"tool_call": c.model_dump(), "agent": agent_name})
            if agent is None:
                results.append({"tool_call": c.model_dump(), "status": "no_agent"})
                continue
            try:
                if asyncio.iscoroutinefunction(agent.execute_toolcall):
                    r = await agent.execute_toolcall(c)
                else:
                    loop = asyncio.get_running_loop()
                    r = await loop.run_in_executor(None, agent.execute_toolcall, c)
                results.append({"tool_call": c.model_dump(), "result": r})
                self.state.add_node("execution_result", {"tool_call": c.model_dump(), "result": r})
            except Exception as e:
                logging.getLogger(__name__).exception("Execution failed for %s: %s", c.name, e)
                results.append({"tool_call": c.model_dump(), "status": "error", "error": str(e)})

        # snapshot state for audit (write to .agentic/state_graph.json)
        try:
            self.state.snapshot('.agentic/state_graph.json')
        except Exception:
            pass

        return {"prompt": prompt, "global_plan": global_plan, "proposals": {k: [x.model_dump() for x in v] for k, v in proposals.items()}, "results": results}
