"""Small CLI to exercise agents locally (dry-run).

Usage examples:
  python scripts/run_agent.py setup --pdb example.pdb
  python scripts/run_agent.py prepare-job --pdb example.pdb --out jobs/run.sh
  python scripts/run_agent.py submit --job jobs/run.sh
  python scripts/run_agent.py download --job-id MOCK-12345
  python scripts/run_agent.py analyze --data results/
"""
from __future__ import annotations

import argparse
import sys
import os


# When running this script directly (python scripts/run_agent.py), Python's
# sys.path[0] is the scripts/ directory, so sibling package `agentic` is not
# on the import path. Prepend the project root so imports work both when
# executing the script directly and when running from the project root.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agentic.agents import SimulationSetupAgent, HPCJobAgent, AnalysisAgent
from agentic.llm import LLMClient


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run agenticAI agent actions (dry-run)")
    # parent parser for global options (so they can appear before or after subcommand)
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--use-llm", action="store_true", help="Enable LLM calls for agents (uses LLMClient)")
    parent.add_argument("--llm-model", default=None, help="LLM model id (e.g. gpt-oss:120b)")
    parent.add_argument("--llm-base-url", default=None, help="LLM base URL (e.g. http://host:11434)")
    parent.add_argument("--prompt", default=None, help="Natural language instruction to run (e.g. 'setup simulation for file.pdb')")
    parent.add_argument("--llm-log", default=None, help="Path to append raw LLM responses (optional)")
    parent.add_argument("--auto-approve", action="store_true", help="Automatically approve actions that would change files or submit jobs")

    # Also allow global LLM flags at the top level (so prompt and llm flags
    # can be passed before or without a subcommand)
    parser.add_argument("--use-llm", action="store_true", help="Enable LLM calls for agents (uses LLMClient)")
    parser.add_argument("--llm-model", default=None, help="LLM model id (e.g. gpt-oss:120b)")
    parser.add_argument("--llm-base-url", default=None, help="LLM base URL (e.g. http://host:11434)")
    parser.add_argument("--prompt", default=None, help="Natural language instruction to run (e.g. 'setup simulation for file.pdb')")
    parser.add_argument("--llm-log", default=None, help="Path to append raw LLM responses (optional)")
    parser.add_argument("--auto-approve", action="store_true", help="Automatically approve actions that would change files or submit jobs")

    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("setup", parents=(parent,))
    p.add_argument("--pdb", required=True)

    p2 = sub.add_parser("prepare-job", parents=(parent,))
    p2.add_argument("--pdb", required=True)
    p2.add_argument("--out", default="jobs/run_sim.sh")

    p3 = sub.add_parser("submit", parents=(parent,))
    p3.add_argument("--job", required=True)

    p4 = sub.add_parser("download", parents=(parent,))
    p4.add_argument("--job-id", required=True)

    p5 = sub.add_parser("analyze", parents=(parent,))
    p5.add_argument("--data", required=True)
    args = parser.parse_args(argv)

    # Instantiate optional LLM client if requested, or if a prompt was provided
    llm_client = None
    if getattr(args, "use_llm", False) or getattr(args, "prompt", None):
        model = args.llm_model or "gpt-oss:120b"
        base = args.llm_base_url or None
        llm_client = LLMClient(model=model, base_url=base)

    setup = SimulationSetupAgent(llm_client=llm_client)
    hpc = HPCJobAgent()
    ana = AnalysisAgent(llm_client=llm_client)

    # If a natural-language prompt is provided, consult the LLM to decide action
    if getattr(args, "prompt", None):
        prompt_text = args.prompt
        if llm_client is None:
            print("Prompt provided but no LLM client available (pass --use-llm). Interpreting simple keywords.")
            # Fallback simple parsing
            low = prompt_text.lower()
            if "setup" in low or "prepare" in low:
                args.cmd = "setup"
                # attempt to extract pdb filename
                for tok in prompt_text.split():
                    if tok.endswith(".pdb"):
                        args.pdb = tok
                        break
            elif "submit" in low:
                args.cmd = "submit"
            elif "download" in low or "get results" in low:
                args.cmd = "download"
            elif "analyze" in low or "analysis" in low:
                args.cmd = "analyze"
        else:
            # Use invoke() which returns structured tool_calls when possible.
            # invoke() does normalization, JSON extraction, and pydantic validation
            # (if schemas are available). We'll automatically execute any
            # validated 'plan_simulation' / 'run_simulation_setup' calls.
            try:
                invoke_result = llm_client.invoke([prompt_text])
            except Exception as e:
                print("LLM invoke() failed:", e)
                invoke_result = None

            # Log raw response if requested
            try:
                raw = getattr(llm_client, "_last_raw_response", None)
            except Exception:
                raw = None
            logpath = getattr(args, "llm_log", None)
            if logpath:
                os.makedirs(os.path.dirname(logpath), exist_ok=True)
                from datetime import datetime
                with open(logpath, "a") as fh:
                    fh.write("---\n")
                    fh.write(f"timestamp: {datetime.utcnow().isoformat()}Z\n")
                    fh.write(f"prompt: {prompt_text}\n")
                    fh.write("RAW_RESPONSE:\n")
                    fh.write(raw if raw is not None else "<none>")
                    fh.write("\n")
                    try:
                        fh.write("INVOKE_RESULT:\n")
                        import json

                        fh.write(json.dumps({
                            "content": invoke_result.content if invoke_result else None,
                            "tool_calls": invoke_result.tool_calls if invoke_result else None,
                            "validation_errors": getattr(invoke_result, "validation_errors", None),
                        }, indent=2))
                        fh.write("\n")
                    except Exception:
                        pass
                    fh.write("---\n\n")

            # Print the invoke content for visibility
            if invoke_result:
                print("LLM mapped content:\n", invoke_result.content)
                if getattr(invoke_result, "validation_errors", None):
                    print("LLM validation errors:", invoke_result.validation_errors)

                # Auto-execute simulation setup tool calls only
                executed = False
                for tc in (invoke_result.tool_calls or []):
                    name = tc.get("name")
                    args_map = tc.get("args", {})
                    # Actions that change files or submit jobs should require confirmation
                    confirm_actions = {
                        "plan_simulation",
                        "run_simulation_setup",
                        "prepare_simulation",
                        "submit",
                        "submit_job",
                        "download",
                        "download_results",
                    }

                    def _confirm(action: str, params: dict) -> bool:
                        # Auto-approve short-circuit
                        if getattr(args, "auto_approve", False):
                            return True
                        # Interactive confirmation
                        print(f"About to execute action '{action}' with params: {params}")
                        resp = input("Proceed? [y/N]: ").strip().lower()
                        return resp in ("y", "yes")

                    if name in ("plan_simulation", "run_simulation_setup", "prepare_simulation"):
                        # call SimulationSetupAgent.plan_simulation
                        try:
                            do_run = True
                            if name in confirm_actions:
                                do_run = _confirm(name, args_map)
                            if not do_run:
                                print(f"Skipped execution of {name} (not approved)")
                                continue
                            # ensure setup agent has access to the same LLM client if desired
                            setup = SimulationSetupAgent(llm_client=llm_client)
                            # support either pdb or pdb_file keys
                            pdb = args_map.get("pdb") or args_map.get("pdb_file")
                            params = args_map.copy()
                            # pass only params (remove pdb/pdb_file from params)
                            params.pop("pdb", None)
                            params.pop("pdb_file", None)
                            res = setup.plan_simulation(pdb or params.get("pdb"), params=params)
                            print("Automatic simulation setup result:", res)
                            executed = True
                        except Exception as e:
                            print(f"Failed to execute simulation setup: {e}")
                if executed:
                    # we've handled the action(s); set args.cmd to setup so downstream
                    # behavior (if any) will match
                    args.cmd = "setup"
                    # mark that we've handled the action to avoid duplicate handling
                    setattr(args, "_auto_executed", True)

    # If we already auto-executed the requested action, skip duplicate work
    if getattr(args, "_auto_executed", False):
        return

    if args.cmd == "setup":
        res = setup.plan_simulation(args.pdb)
        print("Plan:", res)
    elif args.cmd == "prepare-job":
        res = setup.plan_simulation(args.pdb)
        print("Wrote job script to:", res["job_script"])
    elif args.cmd == "submit":
        res = hpc.submit_job(args.job)
        print("Submit response:", res)
    elif args.cmd == "download":
        res = hpc.download_results(args.job_id)
        print("Download response:", res)
    elif args.cmd == "analyze":
        res = ana.analyze_simulation(args.data)
        print("Analysis summary:", res)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
