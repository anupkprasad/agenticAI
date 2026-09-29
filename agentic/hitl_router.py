"""
Human-in-the-loop (HITL) routing: agent switching, context binding, delegated runs.

Used by human_checkpoints, workflow.run_with_human_feedback, and the interactive
CLI handler in SimAgent.py.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

HITL_EXECUTE_PREFIX = "HITL_EXECUTE:"
HITL_SWITCH_PREFIX = "HITL_SWITCH:"

# Persisted across checkpoint saves / resume (see merge_hitl_context_into_state_jsonl)
HITL_CONTEXT_KEYS: Tuple[str, ...] = (
    "hitl_active_agent",
    "hitl_checkpoint_type",
    "hitl_target_sim_label",
    "hitl_last_per_sim_label",
    "hitl_sim_dirs",
    "hitl_agent_working_directory",
    "hitl_agent_output_directory",
    "hitl_view_combined",
)

COMBINED_SCOPE_TOKENS = frozenset({
    "combined", "combine", "cross", "crosssim", "cross-sim", "base", "baselevel",
    "base-level", "aggregate", "overall", "project",
})

AGENT_ALIASES: Dict[str, str] = {
    "preprocess": "preprocess",
    "preprocessing": "preprocess",
    "prep": "preprocess",
    "setup": "setup",
    "simsetup": "setup",
    "simulation setup": "setup",
    "sim setup": "setup",
    "hpc": "hpc",
    "job": "hpc",
    "slurm": "hpc",
    "analysis": "analysis",
    "analyse": "analysis",
    "analyze": "analysis",
    "reporter": "reporter",
    "report": "reporter",
    "reporting": "reporter",
}

CHECKPOINT_FOR_AGENT: Dict[str, str] = {
    "preprocess": "human_preprocess_check",
    "setup": "human_setup_check",
    "hpc": "human_hpc_check",
    "analysis": "human_analysis_check",
    "reporter": "human_reporter_check",
}

AGENT_RUN_NODE: Dict[str, str] = {
    "preprocess": "preprocess",
    "setup": "setup",
    "hpc": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
}

INSTRUCTIONS_KEY: Dict[str, str] = {
    "preprocess": "preprocessing_instructions",
    "setup": "setup_instructions",
    "hpc": "hpc_instructions",
    "analysis": "analysis_instructions",
    "reporter": "reporter_instructions",
}

CLEAR_KEYS_ON_RUN: Dict[str, List[str]] = {
    "preprocess": ["raw_pdb", "cleaned_pdb", "preprocessing_report"],
    "setup": ["topology", "coordinates", "setup_report", "mdp_files"],
    "hpc": ["job_script", "job_id", "job_status", "trajectory_path", "energy_file", "hpc_report"],
    "analysis": ["analysis_results", "figures", "conclusions"],
    "reporter": ["reporter_output"],
}

AGENT_DISPLAY: Dict[str, str] = {
    "preprocess": "Preprocessing Agent",
    "setup": "Simulation Setup Agent",
    "hpc": "HPC Agent",
    "analysis": "Analysis Agent",
    "reporter": "Reporter Agent",
    "combined_analysis": "Combined Analysis (base level)",
    "combined_reporter": "Combined Reporter (base level)",
}


def is_combined_scope_token(token: str) -> bool:
    """True when *token* refers to base-level combined work (not a sim label)."""
    if not token:
        return False
    norm = token.lower().replace("_", "-").strip()
    if norm in COMBINED_SCOPE_TOKENS:
        return True
    return norm.startswith("combined") or norm.startswith("cross")

CHECKPOINT_TYPE_TO_AGENT: Dict[str, str] = {
    "preprocess": "preprocess",
    "preprocessing": "preprocess",
    "setup": "setup",
    "hpc": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
}


def default_agent_for_checkpoint(checkpoint_type: str) -> str:
    """Map human-checkpoint label to canonical field-agent key."""
    return CHECKPOINT_TYPE_TO_AGENT.get(checkpoint_type, checkpoint_type)


def is_combined_workflow_phase(state: Dict[str, Any]) -> bool:
    """True when workflow is in base-level combined analysis or reporting."""
    phase = state.get("multi_sim_phase")
    return phase in ("combined_analysis", "combined_reporter")


def bind_combined_hitl_view(state: Dict[str, Any], agent_key: str) -> None:
    """Point HITL chat/tools at project base (combined analysis/reporter dirs)."""
    base = str(
        Path(state.get("multi_sim_base_dir") or state.get("working_directory") or ".").resolve()
    )
    sub = {
        "preprocess": "preprocess",
        "setup": "simsetup",
        "hpc": "hpc",
        "analysis": "analysis",
        "reporter": "reporter",
    }.get(agent_key, "analysis")
    state["hitl_view_combined"] = True
    state["hitl_target_sim_label"] = None
    state["hitl_agent_working_directory"] = base
    state["analysis_dir"] = str(Path(base) / "analysis")
    state["reporter_dir"] = str(Path(base) / "reporter")
    state["hitl_agent_output_directory"] = str(Path(base) / sub)
    state["hitl_active_agent"] = agent_key


def sync_hitl_active_agent_for_checkpoint(state: Dict[str, Any], checkpoint_type: str) -> str:
    """
    Bind HITL chat to the checkpoint's field agent when entering a new checkpoint.

    Resets stale ``hitl_active_agent`` (e.g. analysis) when the workflow moves to
    reporter review, while preserving in-chat switches within the same checkpoint.
    On a new checkpoint, re-binds the simulation folder to the workflow's active sim
    (from ``multi_sim_progress``), not a stale HITL ``switch`` from a prior step.
    """
    checkpoint_agent = default_agent_for_checkpoint(checkpoint_type)
    if state.get("hitl_checkpoint_type") != checkpoint_type:
        state["hitl_checkpoint_type"] = checkpoint_type
        state["hitl_active_agent"] = checkpoint_agent
        if is_combined_workflow_phase(state):
            bind_combined_hitl_view(state, checkpoint_agent)
        elif state.get("is_multi_simulation"):
            from agentic.multi_sim_progress import workflow_sim_label_for_hitl

            wf_sim = workflow_sim_label_for_hitl(state)
            if wf_sim:
                state["hitl_target_sim_label"] = wf_sim
                state.pop("hitl_view_combined", None)
    elif not state.get("hitl_active_agent"):
        state["hitl_active_agent"] = checkpoint_agent
        if is_combined_workflow_phase(state):
            bind_combined_hitl_view(state, checkpoint_agent)
        elif state.get("is_multi_simulation") and not state.get("hitl_target_sim_label"):
            from agentic.multi_sim_progress import workflow_sim_label_for_hitl

            wf_sim = workflow_sim_label_for_hitl(state)
            if wf_sim:
                state["hitl_target_sim_label"] = wf_sim
    return state["hitl_active_agent"]


def resolve_agent(name: str) -> Optional[str]:
    """Map user text to canonical agent key."""
    if not name:
        return None
    key = name.strip().lower()
    if key in AGENT_ALIASES:
        return AGENT_ALIASES[key]
    key = re.sub(r"^(the\s+)", "", key)
    key = re.sub(r"\s+agent$", "", key).strip()
    if key in AGENT_ALIASES:
        return AGENT_ALIASES[key]
    first = key.split()[0] if key.split() else ""
    return AGENT_ALIASES.get(first)


def agents_in_workflow(state: Dict[str, Any]) -> List[str]:
    """Agents the current workflow may use (from agent_list or subtask)."""
    agent_list = state.get("agent_list") or []
    mapping = {
        "preprocess": "preprocess",
        "simsetup": "setup",
        "setup": "setup",
        "hpcjob": "hpc",
        "hpc": "hpc",
        "analysis": "analysis",
        "reporter": "reporter",
    }
    found: List[str] = []
    for raw in agent_list:
        canon = mapping.get(str(raw).lower())
        if canon and canon not in found:
            found.append(canon)
    if found:
        return found
    subtask = (state.get("subtask_type") or "").lower()
    if subtask == "analysis_only":
        return ["analysis", "reporter"]
    if subtask in ("setup_only",):
        return ["setup"]
    if subtask in ("preprocess_only",):
        return ["preprocess"]
    if subtask in ("reporter_only",):
        return ["reporter"]
    return list(AGENT_RUN_NODE.keys())


def _resolve_sim_label(token: str, state: Dict[str, Any]) -> Optional[str]:
    """Map UniProt label / protein name / path token to simulation label."""
    if not token:
        return None
    raw = token.strip().strip("/")
    base = state.get("multi_sim_base_dir") or state.get("working_directory") or "."
    labels = _discover_sim_labels(str(base))
    low = raw.lower()
    if low.endswith(".pdb"):
        low = low[:-4]
    for label in labels:
        if label.lower() == low or label.lower().startswith(f"{low}_"):
            return label
    name_map: Dict[str, str] = {}
    goal = (state.get("user_goal_original") or state.get("user_goal") or "")
    for m in re.finditer(
        r"\b([A-Za-z0-9]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})",
        goal,
    ):
        name_map[m.group(1).lower()] = m.group(2).lower()
        name_map[m.group(2).lower()] = m.group(1).lower()
    mapped = name_map.get(low)
    if mapped:
        for label in labels:
            if label.lower() == mapped or label.lower().startswith(f"{mapped}_"):
                return label
    return None


def _discover_sim_labels(base_dir: str) -> List[str]:
    base = Path(base_dir)
    if not base.is_dir():
        return []
    skip = {"supervisor", "planner", "programmer", "analysis", "reporter"}
    labels: List[str] = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and d.name not in skip:
            if (d / "supervisor").is_dir() or (d / "analysis").is_dir():
                labels.append(d.name)
    return labels


def parse_hitl_command(
    text: str,
    state: Optional[Dict[str, Any]] = None,
    default_agent: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Parse HITL control commands from user input.

    Returns dict with keys:
      type: ``switch`` | ``execute`` | ``switch_chat``
      agent: canonical agent key
      task: optional task text (execute)
      sim_label: optional simulation label (multi-sim)
    """
    if not text or not text.strip():
        return None
    raw = text.strip()
    low = raw.lower()

    parsed_exec = parse_execute_feedback(raw)
    if parsed_exec:
        agent, task, sim_label = parsed_exec
        combined = sim_label and is_combined_scope_token(sim_label)
        return {
            "type": "execute",
            "agent": agent,
            "task": task,
            "sim_label": None if combined else sim_label,
            "combined": combined,
        }

    if low.startswith(HITL_SWITCH_PREFIX.lower()):
        body = raw[len(HITL_SWITCH_PREFIX):].strip()
        if "|" in body and state:
            sim_tok, agent_tok = body.split("|", 1)
            agent = resolve_agent(agent_tok.strip())
            sim_label = _resolve_sim_label(sim_tok.strip(), state)
            if agent:
                return {
                    "type": "switch",
                    "agent": agent,
                    "task": None,
                    "sim_label": sim_label,
                }
        agent = resolve_agent(body)
        if agent:
            return {"type": "switch", "agent": agent, "task": None, "sim_label": None}
        return None

    # switch / agent <name> — including multi-sim: switch p23458 analysis
    for prefix in ("switch to ", "switch ", "agent ", "go to ", "open "):
        if low.startswith(prefix):
            remainder = raw[len(prefix):].strip()
            if state and remainder:
                parts = remainder.split()
                if len(parts) >= 2:
                    # switch combined analysis | switch analysis combined
                    if is_combined_scope_token(parts[0]):
                        agent = resolve_agent(parts[1])
                        if agent:
                            return {
                                "type": "switch_chat",
                                "agent": agent,
                                "task": None,
                                "sim_label": None,
                                "combined": True,
                            }
                    if is_combined_scope_token(parts[1]):
                        agent = resolve_agent(parts[0])
                        if agent:
                            return {
                                "type": "switch_chat",
                                "agent": agent,
                                "task": None,
                                "sim_label": None,
                                "combined": True,
                            }
                    # switch p23458 analysis
                    sim_label = _resolve_sim_label(parts[0], state)
                    agent = resolve_agent(parts[1])
                    if sim_label and agent:
                        return {
                            "type": "switch_chat",
                            "agent": agent,
                            "task": None,
                            "sim_label": sim_label,
                        }
                    # switch analysis p23458
                    agent = resolve_agent(parts[0])
                    sim_label = _resolve_sim_label(parts[1], state)
                    if agent and sim_label:
                        return {
                            "type": "switch_chat",
                            "agent": agent,
                            "task": None,
                            "sim_label": sim_label,
                        }
                # switch combined (keep current/default agent at base)
                if len(parts) == 1 and is_combined_scope_token(parts[0]) and default_agent:
                    return {
                        "type": "switch_chat",
                        "agent": default_agent,
                        "task": None,
                        "sim_label": None,
                        "combined": True,
                    }
                # switch p23458 (sim only — keep default/current agent)
                if len(parts) == 1 and default_agent:
                    sim_label = _resolve_sim_label(parts[0], state)
                    if sim_label:
                        return {
                            "type": "switch_chat",
                            "agent": default_agent,
                            "task": None,
                            "sim_label": sim_label,
                        }
            agent = resolve_agent(remainder.split(":")[0].strip())
            if agent:
                return {
                    "type": "switch_chat",
                    "agent": agent,
                    "task": None,
                    "sim_label": None,
                }
            break

    # run combined analysis: task
    m = re.match(
        r"^(?:run|execute)\s+combined\s+(\w+)\s*:\s*(.+)$",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        agent = resolve_agent(m.group(1))
        if agent:
            return {
                "type": "execute",
                "agent": agent,
                "task": m.group(2).strip(),
                "sim_label": None,
                "combined": True,
            }

    # run p23458 analysis: task (multi-sim)
    m = re.match(
        r"^(?:run|execute)\s+(\S+)\s+(\w+)\s*:\s*(.+)$",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if m and state:
        label_tok, agent_tok, task = m.group(1), m.group(2), m.group(3).strip()
        agent = resolve_agent(agent_tok)
        if agent and task:
            return {
                "type": "execute",
                "agent": agent,
                "task": task,
                "sim_label": _resolve_sim_label(label_tok, state),
            }

    # run analysis: task
    m = re.match(r"^(?:run|execute)\s+(\w+)\s*:\s*(.+)$", raw, re.IGNORECASE | re.DOTALL)
    if m:
        agent = resolve_agent(m.group(1))
        if agent:
            return {
                "type": "execute",
                "agent": agent,
                "task": m.group(2).strip(),
                "sim_label": None,
            }

    # run: task (current checkpoint agent)
    m = re.match(r"^(?:run|execute)\s*:\s*(.+)$", raw, re.IGNORECASE | re.DOTALL)
    if m and default_agent:
        return {
            "type": "execute",
            "agent": default_agent,
            "task": m.group(1).strip(),
            "sim_label": None,
        }

    return None


def format_execute_command(agent: str, task: str, sim_label: Optional[str] = None) -> str:
    if sim_label:
        return f"{HITL_EXECUTE_PREFIX}{agent}|{sim_label}:{task}"
    return f"{HITL_EXECUTE_PREFIX}{agent}:{task}"


def parse_execute_feedback(feedback: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Parse HITL_EXECUTE:agent:task or HITL_EXECUTE:agent|label:task."""
    if not feedback.startswith(HITL_EXECUTE_PREFIX):
        return None
    body = feedback[len(HITL_EXECUTE_PREFIX):]
    if "|" in body:
        agent_part, rest = body.split("|", 1)
        agent = resolve_agent(agent_part.strip())
        if not agent:
            return None
        if ":" in rest:
            sim_label, task = rest.split(":", 1)
            return agent, task.strip(), sim_label.strip()
        return agent, rest.strip(), None
    if ":" not in body:
        return None
    agent, task = body.split(":", 1)
    canon = resolve_agent(agent.strip())
    if not canon:
        return None
    return canon, task.strip(), None


def hitl_view_working_directory(state: Dict[str, Any]) -> str:
    """Simulation root directory for HITL chat (per-sim folder in multi-sim)."""
    return (
        state.get("hitl_agent_working_directory")
        or state.get("working_directory")
        or state.get("multi_sim_base_dir")
        or "."
    )


def resolve_hitl_sim_label(
    state: Dict[str, Any],
    agent_key: str,
    sim_label: Optional[str] = None,
) -> Optional[str]:
    """
    Choose which simulation folder HITL chat/tools should use.

    At combined reporter review the reporter stays at project base; per-sim field
    agents default to the last simulation the user was working in.
    """
    if sim_label:
        return sim_label
    if state.get("hitl_view_combined") or is_combined_workflow_phase(state):
        return None
    if state.get("hitl_target_sim_label"):
        return state["hitl_target_sim_label"]

    base = Path(str(state.get("multi_sim_base_dir") or state.get("working_directory") or ".")).resolve()
    wd = Path(str(state.get("working_directory") or base)).resolve()
    if wd != base and wd.parent == base:
        return wd.name

    if state.get("multi_sim_phase") == "executing_sims":
        idx = state.get("current_sim_index", 0)
        sim_prompts = state.get("sim_prompts") or []
        if 0 <= idx < len(sim_prompts):
            return sim_prompts[idx].get("label")

    phase = state.get("multi_sim_phase")
    if (
        phase in ("combined_reporter", "combined_analysis", "complete")
        and agent_key == "reporter"
        and not state.get("hitl_target_sim_label")
    ):
        return None

    if state.get("is_multi_simulation"):
        if state.get("hitl_last_per_sim_label"):
            return state["hitl_last_per_sim_label"]
        completed = state.get("completed_sim_states") or []
        for snap in reversed(completed):
            lbl = snap.get("label")
            if lbl:
                return lbl
        labels = _discover_sim_labels(str(base))
        if labels:
            return labels[0]
    return None


def format_hitl_pwd_lines(state: Dict[str, Any], agent_key: str) -> List[str]:
    """Deterministic pwd output for HITL chat (sim dir, agent output, project base)."""
    sim_dir = hitl_view_working_directory(state)
    out_dir = hitl_agent_output_directory(state, agent_key)
    lines = [
        f"  Simulation directory:  {sim_dir}",
        f"  Agent output directory: {out_dir}",
    ]
    label = state.get("hitl_target_sim_label")
    if label:
        lines.append(f"  Bound simulation: {label}")
    elif state.get("hitl_view_combined") or is_combined_workflow_phase(state):
        lines.append("  Scope: combined (project base — cross-simulation)")
    base = state.get("multi_sim_base_dir")
    if base and Path(str(base)).resolve() != Path(sim_dir).resolve():
        lines.append(f"  Project base (routing): {base}")
    sim_dirs = state.get("hitl_sim_dirs") or {}
    if state.get("is_multi_simulation") and sim_dirs and Path(sim_dir).resolve() == Path(str(base)).resolve():
        preview = ", ".join(sorted(sim_dirs.keys())[:8])
        lines.append(f"  Per-simulation directories: {preview}")
        lines.append("  (bind one: switch p23458 analysis)")
    inv_lines = _format_inventory_pwd(out_dir, sim_dir)
    lines.extend(inv_lines)
    return lines


def _format_inventory_pwd(out_dir: str, sim_dir: str) -> List[str]:
    """Print the stage inventory.json rather than guessing artifact paths."""
    try:
        from src.analysis.inventory import INVENTORY_NAME, load_stage_inventory
    except Exception:
        return []
    candidates = [
        Path(out_dir) / INVENTORY_NAME,
        Path(sim_dir) / Path(out_dir).name / INVENTORY_NAME,
    ]
    data = None
    path = None
    for cand in candidates:
        if cand.is_file():
            data = load_stage_inventory(cand.parent)
            path = cand
            break
    if not data:
        return []
    lines = [f"  Stage inventory: {path}"]
    for key in ("topology", "trajectory", "pocket_mapped", "global_mapped", "cleaned_pdb"):
        val = data.get(key)
        if val:
            lines.append(f"    {key}: {val}")
    files = data.get("files") or {}
    if isinstance(files, dict) and files:
        preview = ", ".join(list(files.keys())[:8])
        lines.append(f"    files: {preview}")
    return lines


_AGENT_OUTPUT_DIR_KEY: Dict[str, str] = {
    "preprocess": "preprocess_dir",
    "setup": "simsetup_dir",
    "hpc": "hpc_dir",
    "analysis": "analysis_dir",
    "reporter": "reporter_dir",
}


def hitl_agent_output_directory(state: Dict[str, Any], agent_key: str) -> str:
    """Agent output directory for HITL tool execution (e.g. .../p29597/analysis)."""
    dir_key = _AGENT_OUTPUT_DIR_KEY.get(agent_key, "analysis_dir")
    explicit = state.get(dir_key)
    if explicit:
        return str(Path(explicit).resolve())
    sim_root = hitl_view_working_directory(state)
    sub = {
        "preprocess": "preprocess",
        "setup": "simsetup",
        "hpc": "hpc",
        "analysis": "analysis",
        "reporter": "reporter",
    }.get(agent_key, "analysis")
    return str((Path(sim_root) / sub).resolve())


def format_hitl_directory_context(state: Dict[str, Any], agent_key: str) -> str:
    """
    Authoritative directory block for HITL chat Q&A.

    When the user asks for the current/working directory, answer using these
    paths — NOT state.working_directory at the multi-sim project base.
    """
    sim_dir = hitl_view_working_directory(state)
    out_dir = hitl_agent_output_directory(state, agent_key)
    lines = [
        "HITL ACTIVE CONTEXT (authoritative — use for 'current directory' questions):",
        f"  Active agent: {agent_key}",
        f"  Simulation directory: {sim_dir}",
        f"  Agent output directory (where this agent writes files): {out_dir}",
    ]
    label = state.get("hitl_target_sim_label")
    if label:
        lines.append(f"  Bound simulation label: {label}")
    base = state.get("multi_sim_base_dir")
    if base and Path(str(base)).resolve() != Path(sim_dir).resolve():
        lines.append(
            f"  Multi-sim project base (workflow routing only — NOT your working directory): {base}"
        )
    return "\n".join(lines)


def hitl_agent_dirs(state: Dict[str, Any], sim_root: Optional[str] = None) -> Dict[str, str]:
    """Agent directory map for HITL file tools, keyed by agent name."""
    root = sim_root or hitl_view_working_directory(state)
    return {
        "preprocess": state.get("preprocess_dir") or str(Path(root) / "preprocess"),
        "simsetup": state.get("simsetup_dir") or str(Path(root) / "simsetup"),
        "setup": state.get("simsetup_dir") or str(Path(root) / "simsetup"),
        "hpc": state.get("hpc_dir") or str(Path(root) / "hpc"),
        "analysis": state.get("analysis_dir") or str(Path(root) / "analysis"),
        "reporter": state.get("reporter_dir") or str(Path(root) / "reporter"),
    }


def restore_multi_sim_executing_working_directory(
    state: Dict[str, Any],
    *,
    touch_hitl_view: bool = True,
) -> None:
    """Restore workflow ``working_directory`` to the active per-sim folder."""
    if state.get("multi_sim_phase") != "executing_sims":
        return
    sim_prompts = state.get("sim_prompts") or []
    idx = state.get("current_sim_index", 0)
    if not (0 <= idx < len(sim_prompts)):
        return
    wd = sim_prompts[idx].get("working_dir")
    if not wd:
        return
    sim_root = str(Path(wd).resolve())
    state["working_directory"] = sim_root
    if touch_hitl_view:
        state["preprocess_dir"] = str(Path(sim_root) / "preprocess")
        state["simsetup_dir"] = str(Path(sim_root) / "simsetup")
        state["hpc_dir"] = str(Path(sim_root) / "hpc")
        state["analysis_dir"] = str(Path(sim_root) / "analysis")
        state["reporter_dir"] = str(Path(sim_root) / "reporter")
        state["hitl_agent_working_directory"] = sim_root


def bind_agent_context(
    state: Dict[str, Any],
    agent_key: str,
    sim_label: Optional[str] = None,
    *,
    for_execution: bool = False,
) -> Dict[str, Any]:
    """
    Ensure *state* has directory paths and artifact hints for *agent_key*.

    When *sim_label* is set (multi-sim), binds the HITL view to that simulation.
    With ``for_execution=True`` (delegated agent run), also sets ``working_directory``.
    During in-chat switching at a multi-sim base checkpoint, ``working_directory``
    stays at the project base; use ``hitl_view_working_directory()`` for tools.
    """
    base = state.get("multi_sim_base_dir") or state.get("working_directory") or "."
    base = str(Path(base).resolve())
    if state.get("is_multi_simulation"):
        state.setdefault("multi_sim_base_dir", base)

    use_combined = bool(
        state.get("hitl_view_combined")
        or (is_combined_workflow_phase(state) and not sim_label)
    )
    effective_sim = None if use_combined else resolve_hitl_sim_label(state, agent_key, sim_label)

    if use_combined:
        bind_combined_hitl_view(state, agent_key)
        view_wd = state["hitl_agent_working_directory"]
        if for_execution:
            state["working_directory"] = view_wd
        sim_state_path = Path(view_wd) / "supervisor" / "state.jsonl"
        if sim_state_path.is_file():
            try:
                import json
                entry = json.loads(sim_state_path.read_text(encoding="utf-8"))
                saved = entry.get("state") or {}
                for key in (
                    "analysis_results", "figures", "reporter_output",
                    "execution_plan", "combined_analysis_plan",
                ):
                    if saved.get(key) is not None:
                        state[key] = saved[key]
            except Exception as exc:
                logger.warning("bind_agent_context (combined): %s", exc)
        logger.info(
            "HITL context bound for %s (combined view=%s, exec=%s)",
            agent_key, view_wd, for_execution,
        )
        return state

    if sim_label or effective_sim:
        state.pop("hitl_view_combined", None)

    if effective_sim:
        view_wd = str(Path(base) / effective_sim)
        state["hitl_target_sim_label"] = effective_sim
        state["hitl_last_per_sim_label"] = effective_sim
    else:
        wf_wd = state.get("working_directory") or base
        view_wd = wf_wd
        if state.get("is_multi_simulation") and Path(wf_wd).resolve() == Path(base).resolve():
            state["hitl_sim_dirs"] = {
                label: str(Path(base) / label)
                for label in _discover_sim_labels(str(base))
            }

    view_wd = str(Path(view_wd).resolve())
    state["hitl_agent_working_directory"] = view_wd

    if for_execution:
        state["working_directory"] = view_wd
    elif not state.get("is_multi_simulation"):
        state["working_directory"] = view_wd
    elif state.get("multi_sim_phase") == "executing_sims":
        # Keep workflow routing on the executing sim; HITL may bind a different sim for chat.
        hitl_view_wd = view_wd
        explicit_sim = bool(sim_label or effective_sim)
        restore_multi_sim_executing_working_directory(
            state, touch_hitl_view=not explicit_sim
        )
        if explicit_sim:
            view_wd = hitl_view_wd
        else:
            view_wd = state.get("working_directory") or view_wd
        state["hitl_agent_working_directory"] = view_wd
    else:
        state["working_directory"] = base

    state["preprocess_dir"] = str(Path(view_wd) / "preprocess")
    state["simsetup_dir"] = str(Path(view_wd) / "simsetup")
    state["hpc_dir"] = str(Path(view_wd) / "hpc")
    state["analysis_dir"] = str(Path(view_wd) / "analysis")
    state["reporter_dir"] = str(Path(view_wd) / "reporter")

    # Reload artifact paths from per-sim state.jsonl when present
    sim_state_path = Path(view_wd) / "supervisor" / "state.jsonl"
    if sim_state_path.is_file():
        try:
            import json
            entry = json.loads(sim_state_path.read_text(encoding="utf-8"))
            saved = entry.get("state") or {}
            for key in (
                "trajectory_path", "energy_file", "topology", "coordinates",
                "cleaned_pdb", "raw_pdb", "analysis_results", "figures",
                "reporter_output", "pdb_analysis", "file_registry",
                "execution_plan", "ligand_resnames",
            ):
                if saved.get(key) is not None and state.get(key) is None:
                    state[key] = saved[key]
        except Exception as exc:
            logger.warning("bind_agent_context: could not load %s: %s", sim_state_path, exc)

    state["hitl_active_agent"] = agent_key
    state["hitl_agent_output_directory"] = hitl_agent_output_directory(state, agent_key)
    logger.info(
        "HITL context bound for %s (view=%s, workflow_wd=%s, sim=%s, exec=%s)",
        agent_key,
        view_wd,
        state.get("working_directory"),
        effective_sim or "default",
        for_execution,
    )
    return state


def restore_hitl_session(state: Dict[str, Any]) -> Dict[str, Any]:
    """Re-apply persisted HITL agent/sim binding after loading state.jsonl."""
    agent = state.get("hitl_active_agent")
    if not agent:
        return state
    return bind_agent_context(
        state,
        agent,
        sim_label=state.get("hitl_target_sim_label"),
        for_execution=False,
    )


def _state_jsonl_paths(state: Dict[str, Any]) -> List[Path]:
    """Paths to update when persisting HITL session (base + optional per-sim)."""
    paths: List[Path] = []
    base = state.get("multi_sim_base_dir") or state.get("working_directory") or "."
    paths.append(Path(base) / "supervisor" / "state.jsonl")
    sim = state.get("hitl_target_sim_label")
    if sim:
        sim_path = Path(base) / sim / "supervisor" / "state.jsonl"
        if sim_path.is_file():
            paths.append(sim_path)
    wd_path = Path(state.get("working_directory") or base) / "supervisor" / "state.jsonl"
    if wd_path not in paths and wd_path.is_file():
        paths.append(wd_path)
    return paths


def merge_hitl_context_into_state_jsonl(state: Dict[str, Any]) -> bool:
    """
    Merge HITL session fields into existing state.jsonl checkpoint(s).

    Does not overwrite unrelated workflow fields. Keeps multi-sim base
    ``working_directory`` stable when only the HITL view is bound to a sim.
    """
    import json

    ok = False
    overlay = {k: state[k] for k in HITL_CONTEXT_KEYS if k in state}
    if not overlay:
        return False

    for path in _state_jsonl_paths(state):
        if not path.is_file():
            continue
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            saved = entry.get("state") or {}
            saved.update(overlay)
            # Never persist a transient per-sim working_directory at multi-sim base
            if (
                state.get("is_multi_simulation")
                and state.get("multi_sim_base_dir")
                and state.get("hitl_target_sim_label")
            ):
                base = str(Path(state["multi_sim_base_dir"]).resolve())
                saved["working_directory"] = base
            entry["state"] = saved
            entry["hitl_session_updated"] = datetime.now().isoformat()
            path.write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")
            logger.info("HITL session persisted to %s (%s)", path, list(overlay.keys()))
            ok = True
        except Exception as exc:
            logger.warning("merge_hitl_context_into_state_jsonl failed for %s: %s", path, exc)
    return ok


def prepare_hitl_execution(
    state: Dict[str, Any],
    agent_key: str,
    task: str,
    return_checkpoint: str,
    sim_label: Optional[str] = None,
    *,
    combined: bool = False,
) -> Dict[str, Any]:
    """Configure state for a delegated agent run from HITL."""
    if combined:
        state["hitl_view_combined"] = True
        state.pop("hitl_target_sim_label", None)
    bind_agent_context(state, agent_key, sim_label=sim_label, for_execution=True)

    if combined and agent_key == "analysis":
        state["hitl_combined_execute"] = True
        existing = (state.get("analysis_instructions") or "").strip()
        block = f"HITL combined-analysis task (execute now at project base):\n{task}"
        state["analysis_instructions"] = f"{existing}\n\n{block}".strip() if existing else block
    elif combined and agent_key == "reporter":
        existing = (state.get("reporter_instructions") or "").strip()
        block = f"HITL combined-report task (execute now at project base):\n{task}"
        state["reporter_instructions"] = f"{existing}\n\n{block}".strip() if existing else block

    instr_key = INSTRUCTIONS_KEY.get(agent_key, "analysis_instructions")
    existing = (state.get(instr_key) or "").strip()
    hitl_block = f"HITL delegated task (execute now):\n{task}"
    state[instr_key] = f"{existing}\n\n{hitl_block}".strip() if existing else hitl_block
    state["human_recommendation"] = task
    state["hitl_delegate_agent"] = agent_key
    state["hitl_delegate_task"] = task
    state["hitl_return_checkpoint"] = return_checkpoint

    for key in CLEAR_KEYS_ON_RUN.get(agent_key, []):
        if key in state:
            default: Any = [] if isinstance(state.get(key), list) else (
                {} if isinstance(state.get(key), dict) else None
            )
            state[key] = default

    state.pop("human_feedback", None)
    state["error_triggered_hitl"] = False
    state["next_node"] = AGENT_RUN_NODE[agent_key]
    state.setdefault("warnings", []).append(
        f"HITL delegated run: {agent_key} — {task[:120]}"
    )
    return state


def artifact_summary(state: Dict[str, Any], agent_key: str) -> Dict[str, Any]:
    """Compact artifact map for HITL checkpoint display."""
    wd = hitl_view_working_directory(state)
    summary: Dict[str, Any] = {"working_directory": wd}
    dir_key = {
        "preprocess": "preprocess_dir",
        "setup": "simsetup_dir",
        "hpc": "hpc_dir",
        "analysis": "analysis_dir",
        "reporter": "reporter_dir",
    }.get(agent_key, "analysis_dir")
    agent_dir = state.get(dir_key) or str(Path(wd) / agent_key.replace("setup", "simsetup"))
    summary["agent_directory"] = agent_dir
    if Path(agent_dir).is_dir():
        summary["files"] = sorted(
            p.name for p in Path(agent_dir).iterdir() if p.is_file()
        )[:30]

    for field in (
        "trajectory_path", "topology", "coordinates", "cleaned_pdb",
        "job_id", "job_status", "analysis_results", "reporter_output",
    ):
        val = state.get(field)
        if val:
            summary[field] = val
    if state.get("hitl_sim_dirs"):
        summary["per_simulation_directories"] = state["hitl_sim_dirs"]
    return summary
