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
from src.utils.chat_tools import (
    BUILTIN_TOOL_NAMES as _BUILTIN_TOOLS,
    TOOL_CALL_PATTERN as _TOOL_PATTERN,
    TOOL_INTENT_PATTERNS,
    MAX_TOOL_ROUNDS as _MAX_TOOL_ROUNDS,
    TOOL_INSTRUCTIONS as _TOOL_INSTRUCTIONS,
    resolve_path as _resolve_path,
    read_file_tool as _read_file_snippet,
    list_dir_tool as _list_dir_safe,
    write_file_tool as _write_file_safe,
    extract_tool_intent as _extract_tool_intent,
    execute_tool_call as _execute_tool_call,
    execute_domain_tool as _execute_domain_tool,
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

# Natural-language patterns that map to action keywords.
# Each tuple is (list of phrases, action keyword to return).
_NL_ACTION_PATTERNS = [
    # retry / redo patterns
    (["redo simulation", "redo setup", "redo the setup", "redo the simulation",
      "redo preprocessing", "redo preprocess", "redo analysis", "redo hpc",
      "rerun simulation", "rerun setup", "rerun the setup", "rerun the simulation",
      "please redo", "please retry", "please rerun",
      "run it again", "run again", "run setup again", "run the setup again",
      "re-run", "re-do"], "retry"),
    # approve / continue patterns
    (["looks good", "looks fine", "this is fine", "that's fine", "go ahead",
      "proceed", "move on", "move forward", "all good", "no issues",
      "i'm happy", "i am happy", "i am satisfied", "accept"], "approved"),
    # exit patterns
    (["stop the workflow", "cancel", "abort", "stop everything"], "exit"),
]


def _is_action(text: str) -> bool:
    """Return True if the user input is a workflow action (not a question)."""
    lower = text.lower().strip()
    # Exact match
    if lower in _ACTION_KEYWORDS:
        return True
    # "modify: ..." or "recommend: ..." prefix
    if lower.startswith("modify") or lower.startswith("recommend"):
        return True
    # Natural-language action detection
    if _normalize_action(lower):
        return True
    return False


def _normalize_action(text: str) -> str:
    """Map natural-language input to a canonical action keyword, or return empty string.
    
    If the text contains extra context beyond the action intent, wraps it as
    a 'recommend:' so the agent retries with the human's guidance.
    """
    lower = text.lower().strip()
    
    # Exact keyword match — return as-is
    if lower in _ACTION_KEYWORDS:
        return lower
    if lower.startswith("modify") or lower.startswith("recommend"):
        return lower
    
    for phrases, action in _NL_ACTION_PATTERNS:
        for phrase in phrases:
            if phrase in lower:
                # If the user included extra instructions beyond the action word,
                # convert to "recommend: <full text>" so the agent uses the guidance.
                # e.g. "redo setup with CHARMM force field" -> "recommend: redo setup with CHARMM force field"
                stripped = lower
                for p in phrases:
                    stripped = stripped.replace(p, "").strip()
                # Remove filler words
                for filler in ["please", "the", "with", "using", "and"]:
                    stripped = stripped.replace(filler, "").strip()
                stripped = " ".join(stripped.split())  # collapse whitespace
                
                if stripped and action == "retry" and len(stripped) > 3:
                    # User gave extra context like "updated execution plan" — 
                    # treat as recommend so the agent sees the guidance
                    return f"recommend: {text}"
                return action
    
    return ""


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


# _read_file_snippet, _resolve_path, _list_dir_safe, _write_file_safe
# are imported from src.utils.chat_tools at the top of this file.


def _persist_state_to_jsonl(state: dict, working_dir: str) -> bool:
    """Write state dict to {working_dir}/supervisor/state.jsonl. Returns True on success."""
    state_path = Path(working_dir) / "supervisor" / "state.jsonl"
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"state": state}, indent=2, default=str), encoding="utf-8")
        return True
    except Exception:
        return False


def _replan_with_guidance(
    llm,
    user_input: str,
    state: dict,
    working_dir: str,
) -> Optional[str]:
    """Apply human guidance to structured plans in state and persist.

    1. Detects which agent's plan(s) the guidance targets.
    2. Instantiates the matching field-agent class with the shared LLM client.
    3. Calls agent.replan_with_guidance(user_input, state) — same prompt infra
       as normal planning: planner NL instructions + available tools + human rec.
    4. Stores updated plan + human_recommendation in state and writes state.jsonl.
    5. Returns a printable summary, or None if nothing was updated.
    """
    exec_plan = state.get("execution_plan") or {}
    structured_plans = exec_plan.get("structured_plans", {})

    # Detect targeted agent(s) from the user's text
    _agent_aliases = {
        "preprocess": ["preprocess", "preprocessing"],
        "setup": ["setup", "simsetup", "simulation setup"],
        "hpc": ["hpc"],
        "analysis": ["analysis"],
    }
    inp_lower = user_input.lower()
    targets = [
        key for key, aliases in _agent_aliases.items()
        if any(a in inp_lower for a in aliases) and key in structured_plans
    ]
    if not targets:
        # No named agent — apply to all available structured plans
        targets = list(structured_plans.keys())
    if not targets:
        return None

    # Lazy-import field agent classes to avoid circular imports at module level
    try:
        from agentic.preprocess.preprocessing_agent import PreprocessingAgent as _PreprocessAgent
        from agentic.simsetup.setup_agent import SimSetupAgent as _SetupAgent
        from agentic.analysis.analysis_agent import MDAnalysisAgent as _AnalysisAgent
        from agentic.hpc.hpc_agent import MDHPCAgent as _HPCAgent
    except ImportError as _ie:
        return f"[Import error — cannot replan: {_ie}]"

    _agent_cls_map = {
        "preprocess": _PreprocessAgent,
        "setup": _SetupAgent,
        "analysis": _AnalysisAgent,
        "hpc": _HPCAgent,
    }

    updated_agents = []
    for target_agent in targets:
        agent_cls = _agent_cls_map.get(target_agent)
        if agent_cls is None:
            continue
        try:
            agent_instance = agent_cls(llm_client=llm)
            updated_plan = agent_instance.replan_with_guidance(user_input, state)
        except Exception:
            updated_plan = None
        if not updated_plan:
            continue
        exec_plan.setdefault("structured_plans", {})[target_agent] = updated_plan
        updated_agents.append(target_agent)

    if not updated_agents:
        return None

    # Store guidance in state so agent's LLM planner sees it on next run
    state["human_recommendation"] = user_input
    state["execution_plan"] = exec_plan

    # Apply parameter overrides (force_field, water_model, temperature, pressure)
    _param_patterns = [
        (re.compile(r'\b(?:force.?field|ff)\s*[:=]?\s*([\w-]+)', re.I), "force_field"),
        (re.compile(r'\bwater.?model\s*[:=]?\s*(\w+)', re.I), "water_model"),
        (re.compile(r'\btemperature\s*[:=]?\s*(\d+(?:\.\d+)?)\s*k?\b', re.I), "temperature"),
        (re.compile(r'\bpressure\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:bar)?\b', re.I), "pressure"),
    ]
    for pattern, key in _param_patterns:
        m = pattern.search(user_input)
        if m:
            val = m.group(1)
            if key in ("temperature", "pressure"):
                try:
                    val = float(val)
                except ValueError:
                    pass
            state[key] = val

    _persist_state_to_jsonl(state, working_dir)

    n_steps = {a: len(exec_plan["structured_plans"][a].get("steps", [])) for a in updated_agents}
    summary_lines = [f"Plan updated for: {', '.join(updated_agents)}"]
    for ag in updated_agents:
        summary_lines.append(f"  • {ag}: {n_steps[ag]} steps")
    summary_lines.append(
        "State saved. Type 'retry' to re-run the agent with the updated plan, "
        "or keep chatting to review further."
    )
    return "\n".join(summary_lines)


def _llm_route_or_replan(
    llm,
    user_input: str,
    state: dict,
    working_dir: str,
    agent_name: str = "MD Workflow Assistant",
) -> Optional[str]:
    """Use the LLM to decide intent: answer question OR update a structured plan.

    The LLM sees the current structured plans + available tools and responds with
    either a plain answer or a JSON plan update (signalled by a sentinel prefix).

    Returns:
        str  — human-readable message to print (answer OR "Plan updated: ...")
        None — LLM unavailable / mock mode
    """
    import json as _j

    exec_plan = state.get("execution_plan") or {}
    structured_plans = exec_plan.get("structured_plans", {})
    avail_agents = list(structured_plans.keys())

    # Snapshot of current plans to give the LLM full context
    plans_snapshot = ""
    if structured_plans:
        try:
            plans_snapshot = (
                "\n\nCURRENT STRUCTURED PLANS (JSON):\n"
                + _j.dumps(structured_plans, indent=2)
            )
        except Exception:
            plans_snapshot = f"\n\nStructured plans available for: {', '.join(avail_agents)}"

    prompt = f"""You are the {agent_name} in a molecular dynamics simulation workflow.
Your name is '{agent_name}'. When asked your name or role, identify yourself as the {agent_name}.
The human is chatting with you about the current workflow state and plans.

Your job is to decide whether the human's message is:
(A) A QUESTION  — answer it using the context provided.
(B) A PLAN UPDATE REQUEST — the human wants to change something in a structured plan.

For (B), you must:
1. Identify which agent's plan to change (preprocess / setup / hpc / analysis).
2. Return the full updated plan as valid JSON.
3. Start your response with EXACTLY the sentinel: PLAN_UPDATE:<agent_key>
   followed immediately by the JSON on the next line.
   agent_key must be one of: preprocess, setup, hpc, analysis.

For (A), just answer the question directly. Do NOT include a sentinel.

Context:
- Working directory: {state.get("working_directory", ".")}
- Force field: {state.get("force_field", "amber99sb-ildn")}
- Water model: {state.get("water_model", "tip3p")}
- Temperature: {state.get("temperature", 300.0)} K
- Available structured plans: {avail_agents if avail_agents else "none yet"}
{plans_snapshot}

Human message:
{user_input}
"""

    try:
        resp = llm.prompt(prompt, temperature=0.1)
    except Exception as e:
        return f"[LLM error: {e}]"

    if not resp or resp.startswith("MOCK_LLM_RESPONSE") or resp.startswith("LLM_ERROR"):
        return None

    # Check if LLM decided this is a plan update
    import re as _re
    sentinel_match = _re.match(r'PLAN_UPDATE:(\w+)\s*\n([\s\S]+)', resp.strip())
    if sentinel_match:
        agent_key = sentinel_match.group(1).strip().lower()
        json_body = sentinel_match.group(2).strip()

        # Strip markdown code fences if present
        json_body = _re.sub(r'^```(?:json)?\s*', '', json_body, flags=_re.MULTILINE)
        json_body = _re.sub(r'```\s*$', '', json_body, flags=_re.MULTILINE).strip()

        if agent_key not in ("preprocess", "setup", "hpc", "analysis"):
            # Not a recognised key — treat as plain answer
            return resp.strip()

        try:
            updated_plan = _j.loads(json_body)
        except _j.JSONDecodeError:
            # JSON extraction fallback
            m = _re.search(r'\{[\s\S]*\}', json_body)
            if not m:
                return "Could not parse updated plan JSON from LLM response. Please rephrase."
            try:
                updated_plan = _j.loads(m.group())
            except _j.JSONDecodeError:
                return "Could not parse updated plan JSON from LLM response. Please rephrase."

        exec_plan.setdefault("structured_plans", {})[agent_key] = updated_plan
        state["execution_plan"] = exec_plan
        state["human_recommendation"] = user_input

        # Apply scalar parameter overrides extracted from user text
        _param_patterns = [
            (_re.compile(r'\b(?:force.?field|ff)\s*[:=]?\s*([\w-]+)', _re.I), "force_field"),
            (_re.compile(r'\bwater.?model\s*[:=]?\s*(\w+)', _re.I), "water_model"),
            (_re.compile(r'\btemperature\s*[:=]?\s*(\d+(?:\.\d+)?)\s*k?\b', _re.I), "temperature"),
            (_re.compile(r'\bpressure\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:bar)?\b', _re.I), "pressure"),
        ]
        for pat, key in _param_patterns:
            pm = pat.search(user_input)
            if pm:
                val: Any = pm.group(1)
                if key in ("temperature", "pressure"):
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                state[key] = val

        _persist_state_to_jsonl(state, working_dir)
        n_steps = len(updated_plan.get("steps", []))
        return (
            f"Plan updated for '{agent_key}' agent ({n_steps} steps). "
            f"Changes saved to state.\n"
            f"Type 'show {agent_key} plan' to review, or 'retry' to re-run."
        )

    # Plain answer — return as-is
    return resp.strip()


def _load_full_state_from_jsonl(working_dir: str) -> dict:
    """Return the raw state dict from state.jsonl, or empty dict on failure."""
    state_path = Path(working_dir) / "supervisor" / "state.jsonl"
    if not state_path.exists():
        return {}
    try:
        content = state_path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        entry = json.loads(content)
        return entry.get("state", {})
    except Exception:
        return {}


def _load_last_state_snapshot(working_dir: str) -> str:
    """Load the current workflow state from state.jsonl for LLM context.
    Includes execution_plan summary so the LLM can quote plans verbatim.
    """
    st = _load_full_state_from_jsonl(working_dir)
    if not st:
        return ""
    try:
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

        # Include execution_plan info for plan-related questions
        exec_plan = st.get("execution_plan")
        if exec_plan and isinstance(exec_plan, dict):
            plan_summary: dict = {}
            full_plan = exec_plan.get("full_plan", "")
            if full_plan:
                # Include first 1500 chars of full NL plan
                plan_summary["full_plan"] = (
                    full_plan[:1500] + ("...(truncated)" if len(full_plan) > 1500 else "")
                )
            plan_summary["agent_sequence"] = exec_plan.get("agent_sequence", [])
            plan_summary["title"] = exec_plan.get("title", "")
            # Include structured plans as-is (usually compact JSON)
            structured_plans = exec_plan.get("structured_plans", {})
            if structured_plans:
                plan_summary["structured_plans"] = structured_plans
            # Include per-agent NL instruction sections
            agent_plans = exec_plan.get("agent_plans", {})
            if agent_plans:
                plan_summary["agent_nl_instructions"] = {
                    k: (v[:800] + "...(truncated)" if len(v) > 800 else v)
                    for k, v in agent_plans.items()
                }
            filtered["execution_plan"] = plan_summary

        return json.dumps(filtered, indent=2, default=str)
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


# Tool constants and helpers are imported from src.utils.chat_tools:
#   TOOL_CALL_PATTERN, BUILTIN_TOOL_NAMES, TOOL_INTENT_PATTERNS, extract_tool_intent
#   execute_domain_tool, TOOL_INSTRUCTIONS, MAX_TOOL_ROUNDS, execute_tool_call

# ---------------------------------------------------------------------------
# Agent domain tool registry — loads StructuredTool objects per checkpoint type
# ---------------------------------------------------------------------------

def _load_agent_domain_tools(checkpoint_type: str, working_dir: str = "") -> Tuple[Dict[str, Any], str]:
    """Load domain-specific tools for the agent at a checkpoint.

    Returns:
        (tool_objects, tool_instructions_text)
        - tool_objects: Dict mapping tool name -> StructuredTool object
        - tool_instructions_text: Formatted text describing the tools for the LLM prompt
    """
    tools_map: Dict[str, Any] = {}
    metadata: Dict[str, Dict[str, Any]] = {}

    try:
        if checkpoint_type == "preprocess":
            from agentic.preprocess.tools import get_preprocessing_tools, get_tool_metadata
            for tool in get_preprocessing_tools():
                tools_map[tool.name] = tool
            metadata = get_tool_metadata()

        elif checkpoint_type == "setup":
            from agentic.simsetup.tools import get_simulation_setup_tools
            from agentic.simsetup.tools import get_tool_metadata as _get_meta
            for tool in get_simulation_setup_tools():
                tools_map[tool.name] = tool
            metadata = _get_meta()

        elif checkpoint_type == "hpc":
            from agentic.hpc.tools import (
                copy_simulation_files, estimate_simulation_time,
                create_slurm_script, submit_job, check_job_status, download_results,
            )
            hpc_tools = [
                copy_simulation_files, estimate_simulation_time,
                create_slurm_script, submit_job, check_job_status, download_results,
            ]
            for tool in hpc_tools:
                tools_map[tool.name] = tool
            # Build metadata manually (HPC has no standalone get_tool_metadata)
            for tool in hpc_tools:
                tool_info: Dict[str, Any] = {"name": tool.name, "description": tool.description, "args": {}}
                if hasattr(tool, "args_schema") and tool.args_schema:
                    schema = tool.args_schema.schema()
                    if "properties" in schema:
                        tool_info["args"] = {
                            k: {
                                "type": v.get("type", "string"),
                                "description": v.get("description", ""),
                                "required": k in schema.get("required", []),
                            }
                            for k, v in schema["properties"].items()
                        }
                metadata[tool.name] = tool_info

        elif checkpoint_type == "analysis":
            from agentic.analysis.tools import get_analysis_tools
            from agentic.analysis.tools import get_tool_metadata as _get_meta_a
            for tool in get_analysis_tools():
                tools_map[tool.name] = tool
            metadata = _get_meta_a(working_directory=working_dir or None)

        elif checkpoint_type == "reporter":
            from agentic.reporter.tools import get_reporter_tools
            from agentic.reporter.tools import get_tool_metadata as _get_meta_r
            for tool in get_reporter_tools():
                tools_map[tool.name] = tool
            metadata = _get_meta_r()

    except Exception as e:
        logger.warning(f"Could not load domain tools for {checkpoint_type}: {e}")
        return {}, ""

    if not metadata:
        return tools_map, ""

    # Build formatted instructions text
    agent_label = _AGENT_DISPLAY_NAMES.get(checkpoint_type, checkpoint_type.title())
    lines = [f"\nIn addition to the built-in file tools above, you have these {agent_label} domain tools:"]
    for name, info in metadata.items():
        desc = info.get("description", "")
        if len(desc) > 200:
            desc = desc[:200] + "..."
        lines.append(f"  - {name}: {desc}")
        args = info.get("args", {})
        if args:
            arg_parts = []
            for arg_name, arg_info in args.items():
                req = " (required)" if arg_info.get("required") else ""
                arg_parts.append(f"{arg_name}{req}")
            lines.append(f"    Args: {', '.join(arg_parts)}")

    lines.append("")
    lines.append("To call a domain tool, use the same >>CALL: format with key=value args separated by |:")
    lines.append("  >>CALL: <tool_name> | key1=value1 | key2=value2")
    lines.append("Examples:")
    # Add 1-2 examples based on checkpoint type
    if checkpoint_type == "preprocess":
        lines.append("  >>CALL: analyze_pdb | pdb_path=protein.pdb")
    elif checkpoint_type == "setup":
        lines.append("  >>CALL: build_simulation_system | working_dir=simsetup | system_type=protein-only")
    elif checkpoint_type == "analysis":
        lines.append("  >>CALL: calculate_rmsd | tpr_file=em.tpr | xtc_file=md.xtc | output_dir=analysis")
    elif checkpoint_type == "hpc":
        lines.append("  >>CALL: estimate_simulation_time | system_size=50000 | simulation_ns=100")

    return tools_map, "\n".join(lines)


# _execute_domain_tool, _TOOL_INSTRUCTIONS, _MAX_TOOL_ROUNDS, _execute_tool_call
# are imported from src.utils.chat_tools at the top of this file.


def _llm_qa_with_tools(
    llm,
    user_question: str,
    qa_context: str,
    conversation_history: List[Dict[str, str]],
    working_dir: str,
    agent_dirs: Dict[str, str],
    domain_tools: Optional[Dict[str, Any]] = None,
    domain_tool_instructions: str = "",
    agent_name: str = "MD Workflow",
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
        f"You are the {agent_name} in a molecular dynamics simulation workflow. "
        f"Your name is '{agent_name}'. When asked your name or role, identify yourself as the {agent_name}. "
        "The user is reviewing results at a human checkpoint in an MD workflow. "
        "IMPORTANT: The current workflow state is provided in the CHECKPOINT CONTEXT below. "
        "ALWAYS try to answer the question from the state and context FIRST. "
        "Only call a tool if the state context does not contain enough detail to answer. "
        "Be concise and specific. "
        "Do NOT tell the user to approve or continue \u2014 just answer their question.\n"
        "PLAN QUESTIONS: When the user asks about any plan (full plan, structured plan, "
        "agent plan, execution plan), ALWAYS reproduce the EXACT content from "
        "execution_plan in the workflow state \u2014 do NOT paraphrase, summarize or rephrase. "
        "Show exact tool names, parameters, step descriptions as stored in "
        "structured_plans or full_plan fields of the state.\n\n"
        + _TOOL_INSTRUCTIONS
        + (("\n" + domain_tool_instructions) if domain_tool_instructions else "")
    )
    
    prompt_text = f"""CHECKPOINT CONTEXT:
{qa_context}
{key_files_context}
{history_text}

USER QUESTION: {user_question}

If you can answer from the context above, give a FINAL ANSWER directly.
If you need to inspect a file, output ONLY a tool call line — nothing else:
>>CALL: read_file | <filename>
Do NOT describe what you want to do. Just call the tool."""
    
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
            # No explicit >>CALL: — check if the LLM described wanting to call a tool
            synthetic_call = _extract_tool_intent(response)
            if synthetic_call:
                # LLM intended to call a tool but didn't use the format
                tool_match = _TOOL_PATTERN.search(synthetic_call)
                if tool_match:
                    # Use the synthetic call line as if the LLM emitted it
                    response = synthetic_call
            
            if not tool_match:
                # No tool call at all — this is the final answer
                return response.strip()
        
        # Execute the tool
        tool_line = tool_match.group(0)
        tool_result = _execute_tool_call(tool_line, working_dir, agent_dirs, domain_tools)
        
        # Show the user what tool was called (transparency)
        tool_name = tool_match.group(1)
        tool_arg = tool_match.group(2).strip().split("|")[0].strip()
        if tool_name in _BUILTIN_TOOLS:
            print(f"  [reading: {tool_arg}]", flush=True)
        else:
            print(f"  [executing: {tool_name}({tool_arg})]", flush=True)
        
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
If you still need more information, output ONLY a tool call line — nothing else:
>>CALL: <tool_name> | <args>"""
    
    # Exhausted rounds.  If the last response is still a raw >>CALL: line the LLM
    # never gave a plain answer.  Make one final call with tools disabled.
    final_text = response.strip() if response else ""
    if _TOOL_PATTERN.search(final_text) or not final_text:
        try:
            no_tool_prompt = (
                f"USER QUESTION: {user_question}\n\n"
                f"You have already read files during this session. "
                f"Now give a concise PLAIN TEXT answer — no tool calls, no >>CALL: lines. "
                f"If the file content wasn't useful, say so directly."
            )
            final_text = llm_call(no_tool_prompt, system=(
                f"You are the {agent_name} in a molecular dynamics simulation workflow. "
                f"Your name is '{agent_name}'. "
                "Answer the user's question in plain text. No tool calls."
            )).strip()
        except Exception:
            pass
    # Strip any residual >>CALL: lines the model insists on emitting
    clean_lines = [l for l in final_text.splitlines()
                   if not l.strip().startswith(">>CALL:")]
    final_text = "\n".join(clean_lines).strip()
    return final_text or "[Could not determine answer]"


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

    # Load agent-specific domain tools for this checkpoint
    working_dir = state.get("working_directory", ".")
    domain_tools, domain_tool_instructions = _load_agent_domain_tools(checkpoint_type, working_dir)
    
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
        if key == "execution_log_tail" and isinstance(value, str) and "\n" in value:
            # Show multiline log tail in a compact block
            lines = value.strip().splitlines()
            print(f"  {key}: ({len(lines)} lines)", flush=True)
            for line in lines[-15:]:
                print(f"    {line}", flush=True)
        elif isinstance(value, list) and len(value) > 10:
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
    
    # Working directory for file lookups (already set above for domain tools)
    agent_dirs = {
        "preprocess": state.get("preprocess_dir", ""),
        "simsetup": state.get("simsetup_dir", ""),
        "hpc": state.get("hpc_dir", ""),
        "analysis": state.get("analysis_dir", ""),
    }
    
    print("\n" + "-"*60, flush=True)
    print(f"{agent_label} — ask questions or give a command:", flush=True)
    # Indicate whether state was loaded
    _state_snap = _load_last_state_snapshot(working_dir)
    if _state_snap:
        print("  ✓ Workflow state loaded — LLM will use it to answer questions first", flush=True)
    if domain_tools:
        print(f"  Domain tools available ({len(domain_tools)}): {', '.join(domain_tools.keys())}", flush=True)
    print("  'show <filename>' — display a file", flush=True)
    print("  'files' — list generated files", flush=True)
    print("  'list <dir>' — list directory contents", flush=True)
    print("  'tools' — show detailed tool descriptions", flush=True)
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
            normalized = _normalize_action(user_input.lower().strip())
            action = normalized or user_input
            print(f"\n>> Action: {action}\n", flush=True)
            return action
        
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
        
        # --- Handle 'tools' command — show detailed domain tool descriptions ---
        if user_input.lower().strip() == "tools":
            print(f"\n  Built-in tools: read_file, list_dir, write_file", flush=True)
            if domain_tools:
                print(f"\n  {agent_label} domain tools:", flush=True)
                for tname, tobj in domain_tools.items():
                    desc = getattr(tobj, 'description', '') or ''
                    if len(desc) > 200:
                        desc = desc[:200] + "..."
                    print(f"    • {tname}: {desc}", flush=True)
                    if hasattr(tobj, 'args_schema') and tobj.args_schema:
                        try:
                            schema = tobj.args_schema.schema()
                            props = schema.get("properties", {})
                            req = set(schema.get("required", []))
                            if props:
                                arg_strs = []
                                for aname, ainfo in props.items():
                                    marker = " (required)" if aname in req else ""
                                    arg_strs.append(f"{aname}: {ainfo.get('type', '?')}{marker}")
                                print(f"      Args: {', '.join(arg_strs)}", flush=True)
                        except Exception:
                            pass
            else:
                print(f"\n  No domain tools loaded for {agent_label}.", flush=True)
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
        
        # Re-read state.jsonl every iteration so plan data is always fresh.
        # Use .update() (not rebind) so the original LangGraph state dict reference
        # is preserved — the dict IS the state object that run_with_human_feedback
        # holds and will pass forward to the next node on retry.
        _live_state = _load_full_state_from_jsonl(working_dir)
        if _live_state:
            state.update(_live_state)

        # --- All remaining input goes through the LLM router ---
        # The LLM decides whether the human wants to:
        #   (A) ask a question / inspect results  → answered via _llm_qa_with_tools
        #   (B) update a structured plan          → handled via _llm_route_or_replan

        if not (llm and getattr(llm, 'available', False)):
            print(f"\n  [LLM not available — cannot process requests in mock mode]", flush=True)
            print(f"  Try: 'show <filename>' or 'files' to inspect results manually.\n", flush=True)
            continue

        # Fast-path: if no structured plans exist at all, skip the route+replan step
        # and go straight to Q&A so plan-display questions still work
        _has_structured_plans = bool(
            (state.get("execution_plan") or {}).get("structured_plans")
        )

        if _has_structured_plans:
            route_result = _llm_route_or_replan(llm, user_input, state, working_dir, agent_name=agent_label)
            if route_result is None:
                # Mock / LLM unavailable
                print(f"\n  [LLM unavailable — cannot process request]", flush=True)
                print(f"  Try: 'show <filename>' or 'files' to inspect results manually.\n", flush=True)
                continue
            # If the LLM decided this was a plan update, route_result is the confirmation msg;
            # otherwise it's the plain answer.  Either way we print it.
            print(f"\nAssistant: {route_result}\n", flush=True)
            conversation_history.append({"q": user_input, "a": route_result[:200]})
        else:
            # No structured plans yet — use standard Q&A (plan display, file reads, etc.)
            answer = _llm_qa_with_tools(
                llm, user_input, qa_context,
                conversation_history, working_dir, agent_dirs,
                domain_tools=domain_tools,
                domain_tool_instructions=domain_tool_instructions,
                agent_name=agent_label,
            )
            if answer is None:
                print(f"\n  [LLM unavailable — cannot answer questions in mock mode]", flush=True)
                print(f"  Try: 'show <filename>' or 'files' to inspect results manually.\n", flush=True)
            else:
                print(f"\nAssistant: {answer}\n", flush=True)
                conversation_history.append({"q": user_input, "a": answer})

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
