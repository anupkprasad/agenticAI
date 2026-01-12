from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agentic.llm import LLMClient

@dataclass
class PlannerAgent:
    """Agent that uses an LLM to create a plan (sequence of steps) for a
    simulation workflow. This is a thin wrapper around the project's
    `LLMClient`.
    """
    model: str = "gpt-oss:120b"
    base_url: Optional[str] = None
    llm_client: Optional[Any] = None

    def __post_init__(self):
        # Use injected LLM client if provided, otherwise instantiate one.
        if self.llm_client is not None:
            self.llm = self.llm_client
        else:
            # Instantiate LLM client lazily
            self.llm = LLMClient(model=self.model, base_url=self.base_url)

    async def plan(self, prompt: str) -> Dict[str, Any]:
        # This agent is intentionally simple; the PlannerAgent returns the
        # raw invoke() result packaged as a dictionary for post-processing.
        # Because LLMClient.invoke is synchronous, we call it in a thread if
        # used in async contexts.
        from .async_utils import run_in_thread
        # Improve planner reliability by injecting a short, explicit system
        # instruction that describes the available tools and requests a
        # JSON `tool_calls` list. This encourages the model to return a
        # structured plan the runner can validate and execute. We still
        # return the raw content and any parsed tool_calls produced by the
        # LLM client.

        # Load system instructions from config; require the file to exist so
        # the workflow is fully config-driven. If missing, raise a clear error.
        from pathlib import Path
        import yaml

        cfg = Path(__file__).parent / "configs" / "planner.yaml"
        if not cfg.exists():
            raise FileNotFoundError(f"Planner config not found: {cfg}. Please create agentic/configs/planner.yaml")
        data = yaml.safe_load(cfg.read_text()) or {}
        system_instructions = data.get("system_instructions")
        if not system_instructions:
            raise ValueError(f"planner.yaml at {cfg} does not contain 'system_instructions' key")

        # Set the system prompt on the LLM client (so it is treated as a system
        # instruction by the model rather than as user text), invoke the LLM,
        # then restore the previous system prompt.
        prev_sys = getattr(self.llm, "system_prompt", None)
        try:
            self.llm.system_prompt = system_instructions
            result = await run_in_thread(self.llm.invoke, [prompt])
        finally:
            # restore previous system prompt to avoid side-effects
            self.llm.system_prompt = prev_sys
        # The planner may return a structured `agent_calls` list (preferred)
        # or legacy `tool_calls`. If the LLM client parsed `agent_calls`,
        # prefer those and ignore any parsed `tool_calls` to avoid routing
        # low-level tools (like submit_job) when the planner intended an
        # agent-directed prompt.
        validation_errors = getattr(result, "validation_errors", None) or {}
        # prefer explicit agent_calls attribute if present
        agent_calls_attr = getattr(result, "agent_calls", None)
        if agent_calls_attr:
            tool_calls = []
            for ac in agent_calls_attr:
                name = ac.get("agent") or ac.get("name")
                prompt_text = ac.get("prompt") or (ac.get("args") or {}).get("prompt")
                if name and prompt_text:
                    tool_calls.append({"name": name, "args": {"prompt": prompt_text}})
        else:
            tool_calls = getattr(result, "tool_calls", None) or []

        if not tool_calls:
            # Try to extract a JSON substring that contains 'agent_calls' or 'tool_calls'
            import re, json

            text = result.content or ""
            compact = re.sub(r"\s+", " ", text)
            # Prefer 'agent_calls' (new format), fall back to 'tool_calls'.
            pos = compact.find('agent_calls')
            key = 'agent_calls'
            if pos == -1:
                pos = compact.find('tool_calls')
                key = 'tool_calls'
            if pos == -1:
                # tolerate tokenized splits like 'tool _calls' or 'agent _ calls'
                m = re.search(r'(agent|tool)\s*[_ ]?calls', compact, flags=re.IGNORECASE)
                pos = m.start() if m else -1
            if pos != -1:
                # find nearest opening brace before the key
                start = compact.rfind('{', 0, pos)
                if start != -1:
                    # brace matching
                    depth = 0
                    end = -1
                    for i in range(start, len(compact)):
                        if compact[i] == '{':
                            depth += 1
                        elif compact[i] == '}':
                            depth -= 1
                            if depth == 0:
                                end = i
                                break
                    if end != -1:
                        cand = compact[start:end+1]
                        # try a few tolerant loads
                        tried = [cand, cand.replace('\\"', '"')]
                        try:
                            tried.append(cand.encode('utf-8').decode('unicode_escape'))
                        except Exception:
                            pass
                        for t in tried:
                            try:
                                parsed = json.loads(t)
                                if not isinstance(parsed, dict):
                                    continue
                                # If planner produced agent_calls, convert them
                                if 'agent_calls' in parsed and isinstance(parsed['agent_calls'], list):
                                    agent_calls = parsed['agent_calls']
                                    normalized = []
                                    for ac in agent_calls:
                                        # allow either {'agent':..., 'prompt':...} or
                                        # {'name':..., 'args':{'prompt':...}}
                                        if isinstance(ac, dict):
                                            agent_name = ac.get('agent') or ac.get('name')
                                            prompt_text = ac.get('prompt') or (ac.get('args') or {}).get('prompt')
                                            if agent_name and prompt_text:
                                                normalized.append({"name": agent_name, "args": {"prompt": prompt_text}})
                                    if normalized:
                                        tool_calls = normalized
                                        break
                                if 'tool_calls' in parsed and isinstance(parsed['tool_calls'], list):
                                    tool_calls = parsed['tool_calls']
                                    break
                            except Exception:
                                continue

        return {"content": result.content, "tool_calls": tool_calls, "validation_errors": validation_errors}
