"""
src/utils/chat_tools.py
=======================
Shared chat-session tools for HITL (human-in-the-loop) checkpoints.

Every field agent's chat loop (preprocessing, simsetup, hpc, analysis, reporter)
gets these built-in tools automatically, in addition to its own domain tools.

Built-in tools exposed to the LLM via the >>CALL: protocol:
  - read_file    — read up to N lines from any file under working_dir
  - list_dir     — list files/dirs under working_dir
  - write_file   — create/overwrite a file under working_dir
  - grep_file    — regex search across one or all files under working_dir

Public API used by SimAgent.py:
  BUILTIN_TOOL_NAMES  — frozenset of built-in tool names
  TOOL_CALL_PATTERN   — compiled re for >>CALL: lines
  TOOL_INTENT_PATTERNS — list of fallback re patterns
  MAX_TOOL_ROUNDS     — default max LLM→tool iterations per question
  TOOL_INSTRUCTIONS   — prompt text describing the tools
  resolve_path(...)   — security-safe path lookup
  extract_tool_intent(response) -> Optional[str]
  execute_tool_call(line, working_dir, agent_dirs, domain_tools) -> str
  execute_domain_tool(tool_name, args_str, tool, working_dir) -> str
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUILTIN_TOOL_NAMES: frozenset = frozenset(
    {"read_file", "list_dir", "write_file", "grep_file", "read_inventory"}
)

# Pattern that matches a >>CALL: invocation anywhere in the LLM response.
# Captures the full argument string (supports key=value and JSON objects).
TOOL_CALL_PATTERN = re.compile(
    r">>CALL:\s*(\w+)\s*\|\s*(.+?)(?:\s*$|\s*\n)",
    re.MULTILINE,
)

# Secondary pattern: find >>CALL: lines embedded in reasoning (greedy args to EOL)
TOOL_CALL_LINE_PATTERN = re.compile(
    r">>CALL:\s*(\w+)\s*\|\s*(.+)$",
    re.MULTILINE,
)

MAX_TOOL_ROUNDS: int = 4
MAX_TASK_TOOL_ROUNDS: int = 10

# File extensions the LLM is likely to reference in intent patterns
_FILE_EXTS = r"pdb|gro|top|itp|mdp|log|txt|xvg|edr|xtc|trr|json|jsonl|csv|sh|slurm|out|py|yaml|yml"

# Fallback patterns: detect when the LLM *describes* wanting to use a tool
# but didn't emit the >>CALL: format
TOOL_INTENT_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"(?:let(?:'s| me|us)|I(?:'ll| will| need to| should|'d like to))\s+"
        r"(?:read|open|inspect|look at|check|view|examine)\s+(?:the\s+)?(?:file\s+)?"
        r"([^\s,;\"']+\.(?:" + _FILE_EXTS + r"))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:call\s+)?read_file\s+(?:on\s+)?([^\s,;\"']+\.[a-zA-Z0-9]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:need to|must|should|want to|going to)\s+(?:read|inspect|open|check|view|look at)\s+"
        r"(?:the\s+)?(?:file\s+)?([^\s,;\"']+\.(?:" + _FILE_EXTS + r"))",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bread\s+(?:the\s+)?(?:file\s+)?([^\s,;\"']+\.(?:" + _FILE_EXTS + r"))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:let(?:'s| me|us)|I(?:'ll| will)|we(?:'ll| need to| should| can| will)"
        r"|need to|should|must|going to)\s+"
        r"(?:list|show|browse|check)\s+(?:the\s+)?(?:files|directory|dir|folder|contents|that|it)",
        re.IGNORECASE,
    ),
    # Domain tool intent: "call analyze_secondary_structure" / "use calculate_rmsf"
    re.compile(
        r"(?:call|use|invoke|run)\s+([a-z][a-z0-9_]{2,})",
        re.IGNORECASE,
    ),
]

TOOL_INSTRUCTIONS: str = r"""
You have access to the following built-in file tools (available in EVERY agent session):

  - read_file  : Read file content (up to 80 lines). Args: filepath
  - list_dir   : List files in a directory. Use "." for the working-directory root. Args: directory_path
  - write_file : Create or overwrite a file. Use ONLY when user explicitly asks to write/edit. Args: filepath | content
  - grep_file  : Search a regex pattern inside a file or all files (use "." to search all). Args: regex_pattern | filepath_or_dot_for_all
  - read_inventory : Read {stage}/inventory.json (traj/topo/pocket_mapped). Args: stage (preprocess|simsetup|hpc|analysis|reporter)

When asked "what tools do you have?" ALWAYS list BOTH these built-in tools AND any domain tools shown below.

To call any tool, output EXACTLY one line — no other text on that line:
  >>CALL: read_file  | <filepath>
  >>CALL: list_dir   | <directory_path>
  >>CALL: write_file | <filepath> | <content>
  >>CALL: grep_file  | <regex_pattern> | <filepath_or_dot_for_all>
  >>CALL: read_inventory | <stage_or_dot>

Rules:
- Paths are relative to the working directory unless absolute.
- Call ONE tool per response. Wait for the result before calling another.
- When you have enough information, give a FINAL ANSWER (no tool call).
- NEVER describe wanting to call a tool — just call it directly.

EXAMPLES:
  User: "How many residues are in protein_h.pdb?"  →  >>CALL: read_file | protein_h.pdb
  User: "What files were generated?"               →  >>CALL: list_dir | .
  User: "Find all itp includes in topol.top"       →  >>CALL: grep_file | #include.*\.itp | topol.top
""".strip()


# ---------------------------------------------------------------------------
# Security-safe path resolution
# ---------------------------------------------------------------------------

def resolve_path(
    filename: str,
    working_dir: str,
    agent_dirs: Dict[str, str],
) -> Optional[Path]:
    """Resolve *filename* to an absolute path that is guaranteed to live under
    *working_dir*.  Returns ``None`` if the file cannot be found or would
    escape the sandbox.
    """
    wd = Path(working_dir).resolve()

    # Absolute path — verify it stays inside working_dir
    candidate = Path(filename)
    if candidate.is_absolute():
        try:
            candidate.resolve().relative_to(wd)
            if candidate.exists():
                return candidate
            # Safe path but file not at that exact location (e.g. LLM used
            # working_dir root but file is in analysis/ subdir).  Fall
            # through to the recursive basename search below.
            filename = candidate.name
        except ValueError:
            return None  # path escapes sandbox — reject

    # Search order: agent dirs → supervisor → reporter → working_dir root
    search_dirs: List[str] = list(agent_dirs.values()) + [
        str(wd / "supervisor"),
        str(wd / "reporter"),
        working_dir,
    ]
    for d in search_dirs:
        if not d:
            continue
        p = Path(d) / filename
        if p.exists():
            try:
                p.resolve().relative_to(wd)
                return p
            except ValueError:
                pass  # outside sandbox — skip

    # Recursive fallback: search entire working_dir tree by basename
    basename = Path(filename).name
    for match in sorted(wd.rglob(basename)):
        try:
            match.resolve().relative_to(wd)
            return match
        except ValueError:
            pass

    return None


# ---------------------------------------------------------------------------
# Built-in tool implementations
# ---------------------------------------------------------------------------

def read_file_tool(path_str: str, max_lines: int = 500) -> str:
    """Return up to *max_lines* lines of content from *path_str*.

    For files where users ask about statistics (e.g. atom counts in a PDB),
    the truncation notice includes pre-computed summary statistics so that
    the LLM can answer accurately even when the full file exceeds *max_lines*.
    """
    p = Path(path_str)
    if not p.exists():
        return f"(file not found: {path_str})"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        if total_lines <= max_lines:
            return "\n".join(lines)

        # File is longer than the cap — compute useful summary statistics before
        # truncating so the LLM can answer count/statistics questions correctly.
        suffix = p.suffix.lower()
        summary_parts: list = [f"total lines: {total_lines}"]

        if suffix in (".pdb", ".ent"):
            atom_count = sum(
                1 for ln in lines if ln.startswith("ATOM  ") or ln.startswith("HETATM")
            )
            residue_set = set()
            for ln in lines:
                if ln.startswith("ATOM  ") or ln.startswith("HETATM"):
                    residue_set.add((ln[21:22].strip(), ln[22:26].strip()))
            summary_parts.append(f"ATOM+HETATM records: {atom_count}")
            summary_parts.append(f"unique residues: {len(residue_set)}")
        elif suffix in (".gro",):
            # GRO files have the atom count on line 2
            if total_lines >= 2:
                summary_parts.append(f"atom count (from header): {lines[1].strip()}")
        elif suffix in (".dat", ".csv", ".tsv", ".xvg"):
            data_lines = [ln for ln in lines if ln.strip() and not ln.startswith(("#", "@"))]
            summary_parts.append(f"data rows: {len(data_lines)}")

        summary_str = " | ".join(summary_parts)
        return (
            "\n".join(lines[:max_lines])
            + f"\n... ({total_lines - max_lines} more lines not shown"
            + f" — FILE SUMMARY: {summary_str})"
        )
    except Exception as exc:
        return f"(error reading file: {exc})"


def list_dir_tool(dir_path: str, working_dir: str) -> str:
    """List directory contents, restricted to the *working_dir* tree."""
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


def write_file_tool(filepath: str, content: str, working_dir: str) -> str:
    """Create or overwrite *filepath* (restricted to *working_dir* tree)."""
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


def grep_file_tool(
    pattern: str,
    filepath: str,
    working_dir: str,
    agent_dirs: Optional[Dict[str, str]] = None,
    max_matches: int = 40,
) -> str:
    """Search *pattern* (Python regex) in *filepath*.

    If *filepath* is "." or empty, search all text files under *working_dir*.
    Returns matching lines with ``<file>:<lineno>: <line>`` format.
    """
    agent_dirs = agent_dirs or {}
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"(invalid regex '{pattern}': {exc})"

    wd = Path(working_dir)
    text_exts = {
        ".pdb", ".gro", ".top", ".itp", ".mdp", ".log", ".txt",
        ".xvg", ".json", ".jsonl", ".csv", ".sh", ".slurm",
        ".out", ".py", ".yaml", ".yml",
    }

    def _search_file(path: Path) -> List[str]:
        results: List[str] = []
        try:
            for i, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if rx.search(line):
                    rel = path.relative_to(wd) if path.is_relative_to(wd) else path
                    results.append(f"{rel}:{i}: {line.rstrip()}")
        except Exception:
            pass
        return results

    if filepath in (".", ""):
        # Search all text files under working_dir
        all_matches: List[str] = []
        for f in sorted(wd.rglob("*")):
            if f.is_file() and f.suffix.lower() in text_exts:
                all_matches.extend(_search_file(f))
                if len(all_matches) >= max_matches:
                    all_matches.append(f"... (truncated at {max_matches} matches)")
                    break
        return "\n".join(all_matches) if all_matches else f"(no matches for '{pattern}')"

    resolved = resolve_path(filepath, working_dir, agent_dirs)
    if resolved is None:
        return f"(file not found: {filepath})"
    results = _search_file(resolved)
    if not results:
        return f"(no matches for '{pattern}' in {filepath})"
    if len(results) > max_matches:
        results = results[:max_matches] + [f"... (truncated at {max_matches} matches)"]
    return "\n".join(results)


# ---------------------------------------------------------------------------
# Tool intent extraction (LLM forgot to use >>CALL: format)
# ---------------------------------------------------------------------------

def extract_tool_call_line(response: str) -> Optional[re.Match]:
    """Return the first >>CALL: match in *response*, preferring a clean single line."""
    for pattern in (TOOL_CALL_LINE_PATTERN, TOOL_CALL_PATTERN):
        m = pattern.search(response)
        if m:
            return m
    return None


def extract_tool_intent(
    response: str,
    domain_tools: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """If the LLM described wanting to call a tool without using the ``>>CALL:``
    format, extract the intent and return a synthetic ``>>CALL:`` line.
    Returns ``None`` if no tool intent was detected.
    """
    m = extract_tool_call_line(response)
    if m:
        return m.group(0).strip()

    domain_tools = domain_tools or {}
    _known_exts = (
        ".pdb", ".gro", ".xtc", ".trr", ".tpr", ".mdp", ".dat", ".csv",
        ".json", ".jsonl", ".txt", ".log", ".top", ".itp", ".edr", ".xvg",
    )
    for pattern in TOOL_INTENT_PATTERNS:
        m = pattern.search(response)
        if not m:
            continue
        groups = m.groups()
        if groups and groups[0]:
            token = groups[0].strip().rstrip(".")
            if token in domain_tools:
                return f">>CALL: {token} |"
            low = token.lower()
            if any(low.endswith(ext) for ext in _known_exts):
                return f">>CALL: read_file | {token}"
            return f">>CALL: read_file | {token}"
        return ">>CALL: list_dir | ."
    return None


# ---------------------------------------------------------------------------
# Domain tool executor
# ---------------------------------------------------------------------------

def parse_tool_kwargs(args_str: str, tool: Any) -> Dict[str, Any]:
    """Parse >>CALL: arguments as key=value pairs or a JSON object."""
    args_str = args_str.strip()
    if not args_str:
        return {}

    if args_str.startswith("{"):
        try:
            parsed = json.loads(args_str)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    kwargs: Dict[str, Any] = {}
    parts = [p.strip() for p in args_str.split("|")]
    for part in parts:
        if "=" in part:
            key, _, value = part.partition("=")
            kwargs[key.strip()] = value.strip()
        elif len(parts) == 1 and part:
            if hasattr(tool, "args_schema") and tool.args_schema:
                schema = tool.args_schema.schema()
                required = schema.get("required", [])
                props = list(schema.get("properties", {}).keys())
                first_key = required[0] if required else (props[0] if props else None)
                if first_key:
                    kwargs[first_key] = part
    return kwargs


def append_execution_log(log_path: str, block: str) -> None:
    """Append a timestamped block to an agent execution_log.txt."""
    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"\n{'=' * 72}\nHITL CHAT EXECUTION — {stamp}\n{'=' * 72}\n")
            fh.write(block.rstrip() + "\n")
    except Exception as exc:
        logger.warning("Could not append execution log %s: %s", log_path, exc)


def _sim_root_for_paths(working_dir: str, output_dir: Optional[str] = None) -> Path:
    """Simulation root for resolving hpc/ and relative input paths."""
    base = Path(output_dir or working_dir)
    if base.name in ("analysis", "hpc", "preprocess", "simsetup", "reporter"):
        return base.parent
    return base


def execute_domain_tool(
    tool_name: str,
    args_str: str,
    tool: Any,
    working_dir: str,
    output_dir: Optional[str] = None,
) -> str:
    """Execute a LangChain StructuredTool with ``key=value`` or JSON arguments."""
    kwargs = parse_tool_kwargs(args_str, tool)
    if not kwargs:
        return f"(no arguments provided for {tool_name}. Use: >>CALL: {tool_name} | key=value)"

    exec_dir = output_dir or working_dir
    sim_root = _sim_root_for_paths(working_dir, output_dir)

    _FILE_LIKE_EXTS = (
        ".pdb", ".gro", ".top", ".itp", ".mdp",
        ".xtc", ".trr", ".edr", ".xvg", ".tpr",
        ".log", ".csv",
    )
    for key, val in list(kwargs.items()):
        if isinstance(val, str) and val.lower().endswith(_FILE_LIKE_EXTS):
            p = Path(val)
            if not p.is_absolute():
                for candidate in (
                    sim_root / val,
                    sim_root / "hpc" / Path(val).name,
                    Path(working_dir) / val,
                    Path(exec_dir) / val,
                ):
                    if candidate.exists():
                        kwargs[key] = str(candidate.resolve())
                        break
                else:
                    candidate = sim_root / val
                    if candidate.exists():
                        kwargs[key] = str(candidate.resolve())

    # Ensure tools that accept working_dir write into the agent output directory
    if exec_dir:
        if "working_dir" in kwargs or hasattr(tool, "args_schema"):
            try:
                schema = tool.args_schema.schema() if tool.args_schema else {}
                if "working_dir" in schema.get("properties", {}):
                    kwargs["working_dir"] = exec_dir
            except Exception:
                kwargs.setdefault("working_dir", exec_dir)

    original_cwd = os.getcwd()
    try:
        Path(exec_dir).mkdir(parents=True, exist_ok=True)
        os.chdir(exec_dir)
        result = tool.invoke(kwargs)
        if isinstance(result, dict):
            return json.dumps(result, indent=2, default=str)
        return str(result)
    except Exception as exc:
        return f"(error executing {tool_name}: {exc})"
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Unified tool-call dispatcher
# ---------------------------------------------------------------------------

def execute_tool_call(
    line: str,
    working_dir: str,
    agent_dirs: Dict[str, str],
    domain_tools: Optional[Dict[str, Any]] = None,
    log_path: Optional[str] = None,
    user_request: str = "",
    output_dir: Optional[str] = None,
    conversation_log_path: Optional[str] = None,
) -> str:
    """Parse one ``>>CALL:`` line and dispatch to the appropriate tool.

    Order:
      1. Built-in file tools  (read_file, list_dir, write_file, grep_file)
      2. Agent domain tools   (StructuredTool objects from domain registry)
    """
    m = extract_tool_call_line(line) or TOOL_CALL_PATTERN.match(line.strip())
    if not m:
        return "(invalid tool call format)"

    tool_name = m.group(1)
    args_str = m.group(2).strip().strip('"').strip("'")

    result = ""

    # --- Built-in tools ---
    if tool_name == "read_file":
        resolved = resolve_path(args_str, working_dir, agent_dirs)
        if resolved is None:
            result = (
                f"(file not found: {args_str}. "
                "Use >>CALL: list_dir | . to browse the working directory.)"
            )
        else:
            result = read_file_tool(str(resolved))

    elif tool_name == "list_dir":
        result = list_dir_tool(args_str, working_dir)

    elif tool_name == "write_file":
        parts = args_str.split("|", 1)
        if len(parts) < 2:
            result = "(write_file requires: filepath | content)"
        else:
            result = write_file_tool(parts[0].strip(), parts[1].strip(), working_dir)

    elif tool_name == "grep_file":
        parts = [p.strip() for p in args_str.split("|", 1)]
        pattern = parts[0]
        filepath = parts[1] if len(parts) > 1 else "."
        result = grep_file_tool(pattern, filepath, working_dir, agent_dirs)

    elif tool_name == "read_inventory":
        try:
            from agentic.utils.sandbox_files import execute_sandbox_tool

            sand = execute_sandbox_tool(
                "read_inventory",
                {"stage": args_str if args_str not in (".", "") else ""},
                roots=[Path(working_dir)],
                sim_root=working_dir,
            )
            result = (sand or {}).get("message") or (sand or {}).get("error") or "(no inventory)"
        except Exception as exc:
            result = f"(read_inventory failed: {exc})"

    elif domain_tools and tool_name in domain_tools:
        result = execute_domain_tool(
            tool_name, args_str, domain_tools[tool_name], working_dir,
            output_dir=output_dir,
        )

    else:
        result = f"(unknown tool: {tool_name})"

    if log_path and tool_name not in ("read_file", "list_dir", "grep_file"):
        clean_call = line.strip().split("\n")[0][:500]
        append_execution_log(
            log_path,
            f"User request: {(user_request or '(chat)')[:300]}\n"
            f"Output directory: {output_dir or working_dir}\n"
            f"Tool call: {clean_call}\n"
            f"Result summary: { _summarize_tool_result(result) }",
        )
    if conversation_log_path and tool_name not in ("read_file", "list_dir", "grep_file"):
        clean_call = line.strip().split("\n")[0][:500]
        append_execution_log(
            conversation_log_path,
            f"Tool: {tool_name}\n"
            f"Call: {clean_call}\n"
            f"Summary: {_summarize_tool_result(result)}",
        )
    return result


def _summarize_tool_result(result: str) -> str:
    """Compact one-line summary for logs (no full JSON dumps)."""
    if not result:
        return "(empty)"
    text = result.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if data.get("success") is False:
                    return f"FAILED: {str(data.get('error', data))[:200]}"
                parts = [f"success={data.get('success', True)}"]
                if data.get("output_files"):
                    names = list(data["output_files"].values())[:5]
                    parts.append(f"files={names}")
                elif data.get("message"):
                    parts.append(str(data["message"])[:120])
                return " | ".join(parts)
        except json.JSONDecodeError:
            pass
    if len(text) > 300:
        return text[:300] + "…"
    return text
