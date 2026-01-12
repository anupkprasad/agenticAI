from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentic.schemas import ToolCall
from agentic.hpc.hpc_agent import AsyncHPCJobAgent


class HPCAgentWrapper:
    def __init__(self, llm_client=None, config_path: str | None = None, **kwargs):
        # Use the async HPC wrapper implementation
        self._impl = AsyncHPCJobAgent()
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
                self.config = {}

    async def propose_plan(self, context: Dict[str, Any]) -> List[ToolCall]:
        # Prefer LLM-assisted planning when available: HPC agent can suggest submission params
        prompt = context.get("prompt", "")
        agent_log = ".agentic/logs/hpc_agent.log"
        try:
            import os

            os.makedirs(os.path.dirname(agent_log), exist_ok=True)
        except Exception:
            pass

        if self.llm is not None:
            sys = f"You are an HPCJobAgent. Config: {self.config}.\nReturn JSON with 'tool_calls' for submit_job or download_results as appropriate."
            try:
                res = self.llm.invoke([sys, prompt])
                content = getattr(res, "content", "")
                tool_calls = getattr(res, "tool_calls", []) or []
            except Exception as e:
                content = f"LLM invoke error: {e}"
                tool_calls = []
            try:
                import json
                with open(agent_log, "a") as fh:
                    fh.write("---\n")
                    fh.write(f"prompt: {prompt}\n")
                    fh.write(content + "\n")
                    fh.write(json.dumps(tool_calls, indent=2) + "\n")
                    fh.write("---\n")
            except Exception:
                pass
            calls: List[ToolCall] = []
            for tc in tool_calls:
                try:
                    calls.append(ToolCall(**tc) if not isinstance(tc, ToolCall) else tc)
                except Exception:
                    continue
            return calls

        return []

    async def execute_toolcall(self, toolcall: ToolCall) -> Dict[str, Any]:
        name = toolcall.name
        args = toolcall.args or {}
        agent_log = ".agentic/logs/hpc_agent.log"
        try:
            import os, json
            os.makedirs(os.path.dirname(agent_log), exist_ok=True)
            with open(agent_log, "a") as fh:
                fh.write("EXECUTE\n")
                fh.write(json.dumps(toolcall.model_dump(), indent=2) + "\n")
        except Exception:
            pass

        if name == "submit_job":
            job_script = args.get("job_script")
            # submit_job returns a dict-like result
            res = await self._impl.submit_job(job_script)
            try:
                with open(agent_log, "a") as fh:
                    fh.write("RESULT\n")
                    fh.write(json.dumps(res, indent=2) + "\n")
            except Exception:
                pass
            return res
        if name == "download_results":
            job_id = args.get("job_id")
            res = await self._impl.download_results(job_id, args.get("remote_path"), args.get("local_dir"))
            try:
                with open(agent_log, "a") as fh:
                    fh.write("RESULT\n")
                    fh.write(json.dumps(res, indent=2) + "\n")
            except Exception:
                pass
            return res
        return {"status": "unsupported_tool", "tool": name}
