"""Repo-root runner for agenticAI.
This is a minimal script that runs the SupervisorAgent
"""
from __future__ import annotations

import argparse
import sys
import os
import asyncio
from agentic import agent_from_name
from agentic.llm import LLMClient
from agentic.log_utils import reconstruct_assistant_text
from agentic.supervisor_agent import SupervisorAgent


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Minimal agenticAI runner: always driven by a natural-language --prompt"
    )
    parser.add_argument("--prompt", required=True, help="Natural language instruction to run (e.g. 'setup simulation for file.pdb')")
    parser.add_argument("--use-llm", action="store_true", help="Enable LLM calls for agents (uses LLMClient)")
    parser.add_argument("--llm-model", default=None, help="LLM model id (e.g. gpt-oss:120b)")
    parser.add_argument("--llm-base-url", default=None, help="LLM base URL (e.g. http://host:11434)")
    parser.add_argument("--llm-log", default=None, help="Path to append raw LLM responses (optional)")
    parser.add_argument("--auto-approve", action="store_true", help="Automatically approve actions that would change files or submit jobs")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without executing them")

    args = parser.parse_args(argv)
    # hand off most work to an async main so we can use the new async agents
    return asyncio.run(async_main(args))


async def async_main(args):
    # Instantiate optional LLM client
    model = args.llm_model or "gpt-oss:120b"
    base = args.llm_base_url or None
    llm_client = LLMClient(model=model, base_url=base) if args.use_llm else None

    # instantiate a shared LLM client and pass it to all agents so they
    # share the same model/endpoint. This centralizes model configuration
    # and ensures consistent behavior across agents.
    shared_llm = LLMClient(model=model, base_url=base) if args.use_llm else None

    # instantiate agents via the async factory and wire them into the Supervisor
    sim = await agent_from_name("simulation", llm_client=shared_llm, config_path="agentic/configs/simulation.yaml")
    pre = await agent_from_name("preprocessor", llm_client=shared_llm, config_path="agentic/configs/preprocessor.yaml")
    hpc = await agent_from_name("hpc", llm_client=shared_llm, config_path="agentic/configs/hpc.yaml")
    ana = await agent_from_name("analysis", llm_client=shared_llm, config_path="agentic/configs/analysis.yaml")

    # forward shared LLM client to the planner agent so it uses the same model
    planner = await agent_from_name("planner", llm_client=shared_llm, model=model, base_url=base if args.use_llm else None)

    supervisor = SupervisorAgent(planner=planner, agents={"simulation": sim, "preprocessor": pre, "hpc": hpc, "analysis": ana})

    prompt_text = args.prompt

    # Ask the Supervisor to run the workflow (it will call the planner and
    # coordinate field agents). If it fails, surface the error and exit.
    try:
        result = await supervisor.run(prompt_text, {})
    except Exception as e:
        print("Supervisor run failed:", e)
        return

    # Log raw planner response (if any) for audit
    try:
        raw = getattr(planner.llm, "_last_raw_response", None)
    except Exception:
        raw = None
    logpath = getattr(args, "llm_log", None)
    if logpath:
        os.makedirs(os.path.dirname(logpath), exist_ok=True)
        from datetime import datetime
        import json

        assistant_paragraph = reconstruct_assistant_text(raw)

        with open(logpath, "a") as fh:
            fh.write("---\n")
            fh.write(f"timestamp: {datetime.utcnow().isoformat()}Z\n")
            fh.write(f"prompt: {prompt_text}\n\n")
            fh.write("Assistant message:\n")
            # write multi-line assistant message for readability
            for line in assistant_paragraph.splitlines():
                fh.write(line + "\n")
            fh.write("\n")
            try:
                fh.write("SUPERVISOR_RESULT:\n")
                fh.write(json.dumps(result, indent=2))
                fh.write("\n")
            except Exception:
                pass
            fh.write("---\n\n")

    # Print supervisor/plan content for visibility
    print("Supervisor result summary:")
    print(result)

    # Supervisor already dispatched approved calls. Show a brief summary.
    print("Supervisor dispatched results (see SUPERVISOR_RESULT in log for full details).")

    # Done. The script is prompt-driven; any actions were executed above.
    return


if __name__ == "__main__":
    main()
