from __future__ import annotations

from typing import Any, Dict, List

from agentic.schemas import ToolCall
from agentic.preprocessor.preprocessor_agent import PreprocessorAgent


class PreprocessorAgentWrapper:
    def __init__(self, llm_client=None, config_path: str | None = None, **kwargs):
        self._impl = PreprocessorAgent()
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
        # If the prompt mentions preprocessing or a pdb is provided, suggest preprocess
        prompt = context.get("prompt", "")
        pdb = context.get("pdb")
        wdir = context.get("wdir")
        agent_log = ".agentic/logs/preprocessor_agent.log"
        try:
            import os

            os.makedirs(os.path.dirname(agent_log), exist_ok=True)
        except Exception:
            pass

        # Prefer LLM-assisted local planning when available
        if self.llm is not None:
            sys = f"You are a PreprocessorAgent. Config: {self.config}.\nReturn JSON with 'tool_calls' describing preprocessing steps (name+args)."
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

        calls = []
        if pdb or ("preprocess" in prompt.lower()):
            args = {"pdb": pdb or "", "out_dir": wdir or "./out"}
            calls.append(ToolCall(name="preprocess", args=args))
        return calls

    async def execute_toolcall(self, toolcall: ToolCall) -> Dict[str, Any]:
        agent_log = ".agentic/logs/preprocessor_agent.log"
        try:
            import os, json
            os.makedirs(os.path.dirname(agent_log), exist_ok=True)
            with open(agent_log, "a") as fh:
                fh.write("EXECUTE\n")
                fh.write(json.dumps(toolcall.model_dump(), indent=2) + "\n")
        except Exception:
            pass

        if toolcall.name == "preprocess":
            args = toolcall.args or {}
            pdb = args.get("pdb")
            out = args.get("out_dir") or args.get("out") or "./out"
            res = await self._impl.preprocess(pdb, out)
            try:
                with open(agent_log, "a") as fh:
                    fh.write("RESULT\n")
                    fh.write(json.dumps(res, indent=2) + "\n")
            except Exception:
                pass
            return res
        return {"status": "unsupported_tool", "tool": toolcall.name}
