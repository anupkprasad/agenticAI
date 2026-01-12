from __future__ import annotations

from typing import Any, Dict, List

from agentic.schemas import ToolCall
from agentic.simulation_agent import SimulationAgent


class SimulationAgentWrapper:
    """Wrapper that exposes propose_plan and execute_toolcall for Supervisor.

    Delegates to the existing SimulationAgent implementation. Accepts an
    injected shared LLM client and an optional config path.
    """

    def __init__(self, llm_client=None, config_path: str | None = None, **kwargs):
        # instantiate underlying implementation
        self._impl = SimulationAgent()
        self.llm = llm_client
        self.config = {}
        if config_path:
            try:
                import yaml
                from pathlib import Path

                p = Path(config_path)
                if p.exists():
                    self.config = yaml.safe_load(p.read_text()) or {}
            except Exception:
                # ignore config load errors and keep defaults
                self.config = {}

    async def propose_plan(self, context: Dict[str, Any]) -> List[ToolCall]:
        """Return a ToolCall proposal based on context.

        If a shared LLM client is present, ask it to propose JSON tool_calls
        scoped to this agent's expertise. Otherwise fall back to a simple
        heuristic.
        """
        prompt = context.get("prompt", "")
        pdb = context.get("pdb")
        wdir = context.get("wdir")

        agent_log = ".agentic/logs/simulation_agent.log"
        try:
            import os

            os.makedirs(os.path.dirname(agent_log), exist_ok=True)
        except Exception:
            pass

        if self.llm is not None:
            sys = f"You are SimulationSetupAgent. Expertise: {self.config.get('expertise', {})}."
            sys += "\nReturn a JSON object with a top-level 'tool_calls' list where each item is {name: str, args: dict}. Only return JSON."
            user_prompt = prompt
            try:
                res = self.llm.invoke([sys, user_prompt])
                content = getattr(res, "content", "")
                tool_calls = getattr(res, "tool_calls", []) or []
            except Exception as e:
                content = f"LLM invoke error: {e}"
                tool_calls = []

            # Log the LLM interaction and proposed calls
            try:
                import json
                with open(agent_log, "a") as fh:
                    fh.write("---\n")
                    fh.write(f"prompt: {prompt}\n")
                    fh.write("llm_response:\n")
                    fh.write(content + "\n")
                    fh.write("proposed_tool_calls:\n")
                    fh.write(json.dumps(tool_calls, indent=2) + "\n")
                    fh.write("---\n")
            except Exception:
                pass

            calls: List[ToolCall] = []
            for tc in tool_calls:
                try:
                    if isinstance(tc, ToolCall):
                        calls.append(tc)
                    else:
                        calls.append(ToolCall(**tc))
                except Exception:
                    continue
            return calls

        # Fallback heuristic
        if not pdb:
            import re

            m = re.search(r"\S+\.pdb", prompt)
            if m:
                pdb = m.group(0)
        calls = []
        if pdb or wdir:
            args: Dict[str, Any] = {"pdb": pdb} if pdb else {}
            if wdir:
                args["wdir"] = wdir
            calls.append(ToolCall(name="setup_simulation", args=args))
        return calls

    async def execute_toolcall(self, toolcall: ToolCall) -> Dict[str, Any]:
        name = toolcall.name
        args = toolcall.args or {}
        agent_log = ".agentic/logs/simulation_agent.log"
        try:
            import os, json
            os.makedirs(os.path.dirname(agent_log), exist_ok=True)
            with open(agent_log, "a") as fh:
                fh.write("EXECUTE\n")
                fh.write(json.dumps(toolcall.model_dump(), indent=2) + "\n")
        except Exception:
            pass

        if name in ("setup_simulation", "run_simulation_setup"):
            pdb = args.get("pdb")
            wdir = args.get("wdir")
            res = await self._impl.plan_simulation(pdb, wdir)
            try:
                import json
                with open(agent_log, "a") as fh:
                    fh.write("RESULT\n")
                    fh.write(json.dumps(res, indent=2) + "\n")
            except Exception:
                pass
            return res
        return {"status": "unsupported_tool", "tool": name}

