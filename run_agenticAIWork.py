"""Enhanced LangGraph-based MD Runner with LLM-Powered Supervisor"""
import argparse
import sys
import os
import asyncio
import logging
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from agentic.workflow import MDWorkflow
from agentic.llm import LLMClient
from agentic.utils import (
    get_conversation_logger, log_user_prompt, log_workflow_completion, set_log_file
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ---------------------------------------------------------------------------
# Action keywords that end the interactive session and return a decision
# ---------------------------------------------------------------------------
_ACTION_KEYWORDS = {
    "approved", "continue", "retry", "redo", "exit", "quit", "stop"
}

# Friendly display names for agents
_AGENT_DISPLAY_NAMES = {
    "preprocess": "Preprocessing Agent",
    "setup": "Simulation Setup Agent",
    "hpc": "HPC Agent",
    "analysis": "Analysis Agent",
    "reporter": "Reporter Agent",
}

def _is_action(text: str) -> bool:
    """Return True if the user input is a workflow action (not a question)."""
    lower = text.lower().strip()
    # Exact match
    if lower in _ACTION_KEYWORDS:
        return True
    # "modify: ..." or "recommend: ..." prefix
    if lower.startswith("modify") or lower.startswith("recommend"):
        return True
    return False


def _build_qa_context(summary: Dict[str, Any]) -> str:
    """Build a textual context block from the checkpoint summary for LLM Q&A."""
    parts = [f"Checkpoint: {summary['checkpoint_type']}"]
    
    if summary.get("error_triggered"):
        parts.append("STATUS: Error — agent needs human guidance")
    
    parts.append("\nCurrent state:")
    for k, v in summary.get("current_state", {}).items():
        parts.append(f"  {k}: {v}")
    
    issues = summary.get("issues_found", [])
    if issues:
        parts.append("\nIssues:")
        for i in issues:
            parts.append(f"  - {i}")
    
    recs = summary.get("recommendations", [])
    if recs:
        parts.append("\nRecommendations:")
        for r in recs:
            parts.append(f"  - {r}")
    
    return "\n".join(parts)


def _read_file_snippet(path_str: str, max_lines: int = 60) -> str:
    """Read the first max_lines of a file, return content or error message."""
    p = Path(path_str)
    if not p.exists():
        return f"(file not found: {path_str})"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return "\n".join(lines)
    except Exception as e:
        return f"(error reading file: {e})"


def _resolve_path(filename: str, working_dir: str, agent_dirs: Dict[str, str]) -> Optional[Path]:
    """Resolve a filename to an absolute path within the working directory tree.
    
    Security: only allows access under working_dir.
    """
    # Try absolute first (but must be under working_dir)
    candidate = Path(filename)
    if candidate.is_absolute():
        try:
            candidate.resolve().relative_to(Path(working_dir).resolve())
            if candidate.exists():
                return candidate
        except ValueError:
            return None  # outside working_dir
        return None
    
    # Try agent dirs, supervisor dir, then working_dir root
    search_dirs = list(agent_dirs.values()) + [
        str(Path(working_dir) / "supervisor"),
        str(Path(working_dir) / "reporter"),
        working_dir,
    ]
    for d in search_dirs:
        if not d:
            continue
        p = Path(d) / filename
        if p.exists():
            return p
    return None


def _list_dir_safe(dir_path: str, working_dir: str) -> str:
    """List directory contents, restricted to working_dir tree."""
    p = Path(dir_path)
    if not p.is_absolute():
        p = Path(working_dir) / dir_path
    try:
        p.resolve().relative_to(Path(working_dir).resolve())
    except ValueError:
        return f"(access denied: {dir_path} is outside the working directory)"
    if not p.is_dir():
        return f"(not a directory: {dir_path})"
    entries = sorted(p.iterdir())
    lines = []
    for e in entries:
        suffix = "/" if e.is_dir() else f"  ({e.stat().st_size} bytes)"
        lines.append(f"  {e.name}{suffix}")
    return "\n".join(lines) if lines else "(empty directory)"


def _write_file_safe(filepath: str, content: str, working_dir: str) -> str:
    """Write content to a file, restricted to working_dir tree. No deletion."""
    p = Path(filepath)
    if not p.is_absolute():
        p = Path(working_dir) / filepath
    try:
        p.resolve().relative_to(Path(working_dir).resolve())
    except ValueError:
        return f"ERROR: {filepath} is outside the working directory"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} chars to {p}"


def _load_last_state_snapshot(working_dir: str) -> str:
    """Load the last state snapshot from state.jsonl for LLM context."""
    state_path = Path(working_dir) / "supervisor" / "state.jsonl"
    if not state_path.exists():
        return ""
    try:
        content = state_path.read_text(encoding="utf-8")
        blocks = content.split("--- snapshot ---")
        for block in reversed(blocks):
            block = block.strip()
            if block:
                # Parse and re-format with key fields only
                entry = json.loads(block)
                st = entry.get("state", {})
                # Extract the most useful fields
                useful_keys = [
                    "user_goal", "force_field", "water_model",
                    "raw_pdb", "cleaned_pdb", "preprocessing_report",
                    "ligand_resnames", "ion_resnames",
                    "topology", "coordinates", "mdp_files", "setup_report",
                    "job_script", "job_id", "job_status", "hpc_report",
                    "analysis_results", "figures", "conclusions",
                    "errors", "warnings", "execution_path",
                    "working_directory", "preprocess_dir", "simsetup_dir",
                    "hpc_dir", "analysis_dir",
                ]
                filtered = {k: st[k] for k in useful_keys if k in st and st[k]}
                return json.dumps(filtered, indent=2, default=str)
        return ""
    except Exception:
        return ""


def _load_execution_report(working_dir: str) -> str:
    """Load execution_report.md for LLM context."""
    report_path = Path(working_dir) / "supervisor" / "execution_report.md"
    if not report_path.exists():
        return ""
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
        # Truncate if very long
        if len(text) > 3000:
            text = text[:3000] + "\n... (truncated)"
        return text
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# LLM tool-calling loop for interactive Q&A
# ---------------------------------------------------------------------------
# Use >>CALL format to avoid triggering Ollama's native tool-call parser
# which chokes on "TOOL:" prefix in model output.
# ---------------------------------------------------------------------------
_TOOL_PATTERN = re.compile(
    r"^>>CALL:\s*(read_file|list_dir|write_file)\s*\|\s*(.+)$",
    re.MULTILINE
)

_TOOL_INSTRUCTIONS = """
You have access to tools for inspecting files in the working directory.
To use a tool, output EXACTLY one line in this format (no other text on that line):

  >>CALL: read_file | <filepath>
  >>CALL: list_dir | <directory_path>
  >>CALL: write_file | <filepath> | <content>

Rules:
- Paths are relative to the working directory unless absolute.
- read_file: returns file content (max 80 lines). Use to inspect topology, MDP, logs, etc.
- list_dir: lists files in a directory. Use "." for the working directory root.
- write_file: creates or overwrites a file. Use ONLY if the user asks to write/edit.
- You may call ONE tool per response. After calling a tool, wait for the result.
- When you have enough information, give a FINAL ANSWER (no tool call).
- NEVER call a tool just to be thorough — only when needed to answer the question.
""".strip()

_MAX_TOOL_ROUNDS = 4


def _execute_tool_call(line: str, working_dir: str, agent_dirs: Dict[str, str]) -> str:
    """Parse and execute a single tool call line. Returns result text."""
    m = _TOOL_PATTERN.match(line.strip())
    if not m:
        return "(invalid tool call format)"
    
    tool_name = m.group(1)
    args_str = m.group(2).strip()
    
    if tool_name == "read_file":
        resolved = _resolve_path(args_str, working_dir, agent_dirs)
        if resolved is None:
            return f"(file not found: {args_str})"
        return _read_file_snippet(str(resolved), max_lines=80)
    
    elif tool_name == "list_dir":
        return _list_dir_safe(args_str, working_dir)
    
    elif tool_name == "write_file":
        parts = args_str.split("|", 1)
        if len(parts) < 2:
            return "(write_file requires: filepath | content)"
        filepath = parts[0].strip()
        content = parts[1].strip()
        return _write_file_safe(filepath, content, working_dir)
    
    return "(unknown tool)"


def _llm_qa_with_tools(
    llm,
    user_question: str,
    qa_context: str,
    conversation_history: List[Dict[str, str]],
    working_dir: str,
    agent_dirs: Dict[str, str],
) -> Optional[str]:
    """Run LLM Q&A with tool-calling loop.
    
    Uses prompt_raw() (/api/generate) to bypass Ollama's chat-endpoint
    tool-call parser which would choke on our text-based tool format.
    """
    
    # Pre-load key context files
    state_snapshot = _load_last_state_snapshot(working_dir)
    exec_report = _load_execution_report(working_dir)
    
    key_files_context = ""
    if state_snapshot:
        key_files_context += f"\n\nLATEST WORKFLOW STATE (from state.jsonl):\n{state_snapshot}"
    if exec_report:
        key_files_context += f"\n\nEXECUTION REPORT (execution_report.md):\n{exec_report}"
    
    # Build conversation history
    history_text = ""
    if conversation_history:
        history_text = "\n\nPrevious Q&A in this session:\n"
        for turn in conversation_history[-5:]:
            history_text += f"  User: {turn['q']}\n  Assistant: {turn['a']}\n"
    
    system_prompt = (
        "You are a molecular dynamics simulation expert assistant. "
        "The user is reviewing results at a human checkpoint in an MD workflow. "
        "Answer their question using the context AND your file-reading tools. "
        "Be concise and specific. If you need to look at a file to answer, use a tool. "
        "Do NOT tell the user to approve or continue — just answer their question.\n\n"
        + _TOOL_INSTRUCTIONS
    )
    
    prompt_text = f"""CHECKPOINT CONTEXT:
{qa_context}
{key_files_context}
{history_text}

USER QUESTION: {user_question}

If you can answer from the context above, give a FINAL ANSWER directly.
If you need to inspect a file, use exactly ONE tool call (>>CALL: format)."""
    
    # Choose LLM call method: prefer prompt_raw to avoid tool-call parser
    llm_call = getattr(llm, 'prompt_raw', None) or llm.prompt
    
    # Tool-calling loop
    response = ""
    for round_idx in range(_MAX_TOOL_ROUNDS):
        try:
            response = llm_call(prompt_text, system=system_prompt)
        except Exception as e:
            return f"[LLM error: {e}]"
        
        if response.startswith("MOCK_LLM_RESPONSE"):
            return None  # Signal mock mode
        
        # Check if response contains a tool call
        tool_match = _TOOL_PATTERN.search(response)
        if not tool_match:
            # No tool call — this is the final answer
            return response.strip()
        
        # Execute the tool
        tool_line = tool_match.group(0)
        tool_result = _execute_tool_call(tool_line, working_dir, agent_dirs)
        
        # Show the user what tool was called (transparency)
        tool_name = tool_match.group(1)
        tool_arg = tool_match.group(2).strip().split("|")[0].strip()
        print(f"  [reading: {tool_arg}]", flush=True)
        
        # Build follow-up prompt with tool result
        prompt_text = f"""CHECKPOINT CONTEXT:
{qa_context}
{key_files_context}
{history_text}

USER QUESTION: {user_question}

You called: {tool_line}
RESULT:
{tool_result}

Now give a FINAL ANSWER based on the result and context.
If you still need more information, make ONE more tool call (>>CALL: format)."""
    
    # Exhausted rounds — return what we have
    return response.strip() if response else "[Could not determine answer]"


def interactive_feedback_handler(summary: Dict[str, Any]) -> str:
    """
    Interactive command-line feedback handler for human-in-the-loop.
    
    Supports a conversational loop with LLM-powered Q&A:
      - User can ask questions about the checkpoint results
      - LLM reads files (state.jsonl, topol.top, MDP files, etc.) to answer
      - Supports: show <file>, files, list <dir>, write <file> <content>
      - Loop continues until user gives an action command
    """
    llm = summary.pop("_llm", None)
    state = summary.pop("_state", {})
    
    checkpoint_type = summary["checkpoint_type"]
    agent_label = _AGENT_DISPLAY_NAMES.get(checkpoint_type, checkpoint_type.title() + " Agent")
    error_triggered = summary.get("error_triggered", False)
    
    # --- Display banner ---
    print("\n" + "="*60, flush=True)
    if error_triggered:
        print(f"  {agent_label} — Human Chat  [ERROR RECOVERY]", flush=True)
    else:
        print(f"  {agent_label} — Human Chat", flush=True)
    print("="*60, flush=True)
    
    if error_triggered:
        print("\n⚠ This agent encountered errors after maximum retries.", flush=True)
        print("  Please review the issues below and provide guidance.", flush=True)
    
    print("\nCurrent State:", flush=True)
    for key, value in summary.get("current_state", {}).items():
        if isinstance(value, list) and len(value) > 10:
            print(f"  {key}: [{len(value)} items]", flush=True)
        elif isinstance(value, str) and len(value) > 200:
            print(f"  {key}: {value[:200]}...", flush=True)
        else:
            print(f"  {key}: {value}", flush=True)
    
    if summary.get("issues_found"):
        print("\n⚠ Issues Found:", flush=True)
        for issue in summary["issues_found"]:
            print(f"  - {issue}", flush=True)
    else:
        print("\n✓ No issues found.", flush=True)
    
    print("\nRecommendations:", flush=True)
    for rec in summary.get("recommendations", []):
        print(f"  - {rec}", flush=True)
    
    # --- Build persistent context for Q&A ---
    qa_context = _build_qa_context(summary)
    conversation_history: List[Dict[str, str]] = []
    
    # Working directory for file lookups
    working_dir = state.get("working_directory", ".")
    agent_dirs = {
        "preprocess": state.get("preprocess_dir", ""),
        "simsetup": state.get("simsetup_dir", ""),
        "hpc": state.get("hpc_dir", ""),
        "analysis": state.get("analysis_dir", ""),
    }
    
    print("\n" + "-"*60, flush=True)
    print(f"{agent_label} — ask questions or give a command:", flush=True)
    print("  Ask anything about the results (LLM can read files to answer)", flush=True)
    print("  'show <filename>' — display a file", flush=True)
    print("  'files' — list generated files", flush=True)
    print("  'list <dir>' — list directory contents", flush=True)
    print("  ---", flush=True)
    print("  'approved' / 'continue' — proceed to next step", flush=True)
    print("  'retry' — redo this step from scratch", flush=True)
    print("  'modify: <instructions>' — redo with specific changes", flush=True)
    if error_triggered:
        print("  'recommend: <your advice>' — agent will retry with your guidance", flush=True)
    print("  'exit' / 'quit' — stop workflow", flush=True)
    print("-"*60 + "\n", flush=True)
    
    while True:
        sys.stdout.flush()
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(interrupted — exiting workflow)", flush=True)
            return "exit"
        
        if not user_input:
            continue
        
        # --- Check for action commands ---
        if _is_action(user_input):
            print(f"\n>> Action: {user_input}\n", flush=True)
            return user_input
        
        # --- Handle 'files' command ---
        if user_input.lower() == "files":
            print("\nGenerated files by agent:", flush=True)
            for agent_name, agent_dir in agent_dirs.items():
                if agent_dir and Path(agent_dir).is_dir():
                    files = sorted(f.name for f in Path(agent_dir).iterdir() if f.is_file())
                    if files:
                        print(f"  [{agent_name}] {agent_dir}/", flush=True)
                        for f in files:
                            print(f"    - {f}", flush=True)
            # Also show supervisor dir
            sup_dir = Path(working_dir) / "supervisor"
            if sup_dir.is_dir():
                files = sorted(f.name for f in sup_dir.iterdir() if f.is_file())
                if files:
                    print(f"  [supervisor] {sup_dir}/", flush=True)
                    for f in files:
                        print(f"    - {f}", flush=True)
            print("", flush=True)
            continue
        
        # --- Handle 'show <file>' command ---
        if user_input.lower().startswith("show "):
            filename = user_input[5:].strip()
            resolved = _resolve_path(filename, working_dir, agent_dirs)
            if resolved:
                print(f"\n--- {resolved} ---", flush=True)
                print(_read_file_snippet(str(resolved), max_lines=80), flush=True)
                print(f"--- end ---\n", flush=True)
            else:
                print(f"\n  File '{filename}' not found in any agent directory.", flush=True)
                print(f"  Tip: use 'files' to see available files.\n", flush=True)
            continue
        
        # --- Handle 'list <dir>' command ---
        if user_input.lower().startswith("list "):
            dir_path = user_input[5:].strip()
            print(f"\n{_list_dir_safe(dir_path, working_dir)}\n", flush=True)
            continue
        
        # --- LLM-powered Q&A with tool access ---
        if llm and getattr(llm, 'available', False):
            answer = _llm_qa_with_tools(
                llm, user_input, qa_context,
                conversation_history, working_dir, agent_dirs,
            )
            if answer is None:
                # Mock mode
                print(f"\n  [LLM unavailable — cannot answer questions in mock mode]", flush=True)
                print(f"  Try: 'show <filename>' or 'files' to inspect results manually.\n", flush=True)
            else:
                print(f"\nAssistant: {answer}\n", flush=True)
                conversation_history.append({"q": user_input, "a": answer})
        else:
            print(f"\n  [LLM not available for Q&A — running in mock mode]", flush=True)
            print(f"  Try: 'show <filename>' or 'files' to inspect results manually.\n", flush=True)

# Remove the old log_workflow_state function since we now use conversation_logger

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LangGraph-based MD Simulation Workflow"
    )
    parser.add_argument("--goal", required=True, 
                       help="Natural language description of simulation goal")
    parser.add_argument("--subtask", default=None, nargs='+',
                       choices=["preprocess", "simsetup", "hpcjob", "analysis", "reporter"],
                       metavar="AGENT",
                       help=("One or more field agents to run, e.g. --subtask analysis reporter. "
                             "Valid values: preprocess simsetup hpcjob analysis reporter. "
                             "Omit to run the full pipeline."))
    parser.add_argument("--use-llm", action="store_true", 
                       help="Use LLM for intelligent planning (recommended)")
    parser.add_argument("--llm-model", default="gpt-oss:20b",
                       help="LLM model to use")
    parser.add_argument("--llm-base-url", default="http://localhost:11434",
                       help="LLM API base URL")
    parser.add_argument("--no-human-loop", action="store_true",
                       help="Skip human checkpoints (auto-approve)")
    parser.add_argument("--force-field", default="amber99sb-ildn",
                       help="Force field to use")
    parser.add_argument("--water-model", default="tip3p", 
                       help="Water model to use")
    parser.add_argument("--working-dir", default=".",
                       help="Base working directory (agents use subdirs: working_dir/preprocess/, working_dir/hpc/, etc.)")
    
    args = parser.parse_args(argv)
    
    # Set up LLM client (required, uses fallback/mock mode if no server)
    llm_client = LLMClient(
        model=args.llm_model,
        base_url=args.llm_base_url if args.use_llm else None
    )
    # Configuration
    config = {
        "force_field": args.force_field,
        "water_model": args.water_model,
        "human_in_loop": not args.no_human_loop,
        "working_directory": args.working_dir
    }
    
    # Pass subtask type directly in config
    if args.subtask:
        single_agent_map = {
            "preprocess": "preprocess_only",
            "simsetup": "setup_only",
            "hpcjob": "hpc_only",
            "analysis": "analysis_only",
            "reporter": "reporter_only"
        }
        if len(args.subtask) == 1:
            # Single agent: use existing specific subtask_type
            config["subtask_type"] = single_agent_map[args.subtask[0]]
        else:
            # Multiple agents: multi_agent mode with ordered agent list
            config["subtask_type"] = "multi_agent"
            config["agent_list"] = args.subtask
    
    goal = args.goal
    
    # Resolve working directory (same logic as workflow._initialize_state)
    from pathlib import Path
    working_dir = args.working_dir
    if working_dir == ".":
        working_dir = "working_dir"
    if not Path(working_dir).is_absolute():
        working_dir = str(Path.cwd() / working_dir)
    Path(working_dir).mkdir(parents=True, exist_ok=True)
    
    # Set up logging inside working_dir (not at project root)
    log_path = str(Path(working_dir) / "agent_conversation.log")
    set_log_file(log_path)
    
    # Initialize workflow
    workflow = MDWorkflow(llm_client)
    
    # Initialize conversation logger
    conversation_logger = get_conversation_logger(log_path)
    
    # Log user prompt
    log_user_prompt(goal, config)
    
    # Run workflow
    print(f"\nStarting MD workflow for: {goal}", flush=True)
    print(f"Configuration: {config}", flush=True)
    if args.subtask:
        agents_label = ", ".join(a.upper() for a in args.subtask)
        print(f"Subtask Mode: {agents_label}", flush=True)
    
    if config["human_in_loop"]:
        print("\n⚠️  HUMAN-IN-THE-LOOP MODE: You will be prompted at checkpoints", flush=True)
        print("    Use --no-human-loop for automatic execution\n", flush=True)
    
    try:
        if config["human_in_loop"]:
            # Run with human feedback
            final_state = workflow.run_with_human_feedback(
                goal, 
                feedback_handler=interactive_feedback_handler,
                config=config
            )
        else:
            # Run automatically
            final_state = workflow.run(goal, config)
        
        # Log workflow completion is handled by conversation_logger
        # No need for separate log_workflow_state since conversation logger captures everything
        
        # Log workflow completion
        success = len(final_state.get('errors', [])) == 0
        summary = f"Workflow completed with {len(final_state.get('errors', []))} errors and {len(final_state.get('warnings', []))} warnings"
        log_workflow_completion(final_state, success, summary)
        
        # Print results
        print("\n" + "="*60)
        print("WORKFLOW COMPLETED")
        print("="*60)
        
        if final_state.get("final_report"):
            print(final_state["final_report"])
        
        if final_state.get("errors"):
            print("\nERRORS:")
            for error in final_state["errors"]:
                print(f"  - {error}")
                
        if final_state.get("warnings"):
            print("\nWARNINGS:")
            for warning in final_state["warnings"]:
                print(f"  - {warning}")
        
        print(f"\nFull conversation log saved to: {log_path}")
        
        # Show execution report path
        report_path = str(Path(working_dir) / "supervisor" / "execution_report.md")
        if Path(report_path).exists():
            print(f"Execution report saved to: {report_path}")
        
        # Return appropriate exit code
        return 0 if not final_state.get("errors") else 1
        
    except KeyboardInterrupt:
        print("\nWorkflow interrupted by user")
        return 130
    except Exception as e:
        print(f"\nWorkflow failed: {e}")
        logging.exception("Workflow execution failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
