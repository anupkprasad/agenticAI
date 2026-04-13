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

Public API used by run_agenticAIWork.py:
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
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUILTIN_TOOL_NAMES: frozenset = frozenset({"read_file", "list_dir", "write_file", "grep_file"})

# Pattern that matches a single >>CALL: line emitted by the LLM
TOOL_CALL_PATTERN = re.compile(
    r"^>>CALL:\s*(\w+)\s*\|\s*(.+)$",
    re.MULTILINE,
)

MAX_TOOL_ROUNDS: int = 4

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
]

TOOL_INSTRUCTIONS: str = r"""
You have access to the following built-in file tools (available in EVERY agent session):

  - read_file  : Read file content (up to 80 lines). Args: filepath
  - list_dir   : List files in a directory. Use "." for the working-directory root. Args: directory_path
  - write_file : Create or overwrite a file. Use ONLY when user explicitly asks to write/edit. Args: filepath | content
  - grep_file  : Search a regex pattern inside a file or all files (use "." to search all). Args: regex_pattern | filepath_or_dot_for_all

When asked "what tools do you have?" ALWAYS list BOTH these built-in tools AND any domain tools shown below.

To call any tool, output EXACTLY one line — no other text on that line:
  >>CALL: read_file  | <filepath>
  >>CALL: list_dir   | <directory_path>
  >>CALL: write_file | <filepath> | <content>
  >>CALL: grep_file  | <regex_pattern> | <filepath_or_dot_for_all>

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
        except ValueError:
            return None
        return None

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

def read_file_tool(path_str: str, max_lines: int = 80) -> str:
    """Return up to *max_lines* lines of content from *path_str*."""
    p = Path(path_str)
    if not p.exists():
        return f"(file not found: {path_str})"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return "\n".join(lines)
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

def extract_tool_intent(response: str) -> Optional[str]:
    """If the LLM described wanting to call a tool without using the ``>>CALL:``
    format, extract the intent and return a synthetic ``>>CALL:`` line.
    Returns ``None`` if no tool intent was detected.
    """
    for pattern in TOOL_INTENT_PATTERNS:
        m = pattern.search(response)
        if m:
            groups = m.groups()
            if groups and groups[0]:
                filepath = groups[0].strip().rstrip(".")
                return f">>CALL: read_file | {filepath}"
            # list_dir intent with no specific path
            return ">>CALL: list_dir | ."
    return None


# ---------------------------------------------------------------------------
# Domain tool executor
# ---------------------------------------------------------------------------

def execute_domain_tool(
    tool_name: str,
    args_str: str,
    tool: Any,
    working_dir: str,
) -> str:
    """Execute a LangChain StructuredTool with ``key=value`` arguments parsed
    from *args_str* (pipe-separated).  File-like values are resolved relative
    to *working_dir* if they exist there.
    """
    kwargs: Dict[str, Any] = {}
    parts = [p.strip() for p in args_str.split("|")]
    for part in parts:
        if "=" in part:
            key, _, value = part.partition("=")
            kwargs[key.strip()] = value.strip()
        elif len(parts) == 1 and part:
            # Single positional arg — map to first required schema field
            if hasattr(tool, "args_schema") and tool.args_schema:
                schema = tool.args_schema.schema()
                required = schema.get("required", [])
                props = list(schema.get("properties", {}).keys())
                first_key = required[0] if required else (props[0] if props else None)
                if first_key:
                    kwargs[first_key] = part

    if not kwargs:
        return f"(no arguments provided for {tool_name}. Use: >>CALL: {tool_name} | key=value)"

    _FILE_LIKE_EXTS = (
        ".pdb", ".gro", ".top", ".itp", ".mdp",
        ".xtc", ".trr", ".edr", ".xvg", ".tpr",
        ".log", ".csv",
    )
    for key, val in list(kwargs.items()):
        if isinstance(val, str) and val.lower().endswith(_FILE_LIKE_EXTS):
            p = Path(val)
            if not p.is_absolute():
                candidate = Path(working_dir) / val
                if candidate.exists():
                    kwargs[key] = str(candidate)

    try:
        result = tool.invoke(kwargs)
        if isinstance(result, dict):
            return json.dumps(result, indent=2, default=str)
        return str(result)
    except Exception as exc:
        return f"(error executing {tool_name}: {exc})"


# ---------------------------------------------------------------------------
# Unified tool-call dispatcher
# ---------------------------------------------------------------------------

def execute_tool_call(
    line: str,
    working_dir: str,
    agent_dirs: Dict[str, str],
    domain_tools: Optional[Dict[str, Any]] = None,
) -> str:
    """Parse one ``>>CALL:`` line and dispatch to the appropriate tool.

    Order:
      1. Built-in file tools  (read_file, list_dir, write_file, grep_file)
      2. Agent domain tools   (StructuredTool objects from domain registry)
    """
    m = TOOL_CALL_PATTERN.match(line.strip())
    if not m:
        return "(invalid tool call format)"

    tool_name = m.group(1)
    args_str = m.group(2).strip()

    # --- Built-in tools ---
    if tool_name == "read_file":
        resolved = resolve_path(args_str, working_dir, agent_dirs)
        if resolved is None:
            return (
                f"(file not found: {args_str}. "
                "Use >>CALL: list_dir | . to browse the working directory.)"
            )
        return read_file_tool(str(resolved), max_lines=80)

    if tool_name == "list_dir":
        return list_dir_tool(args_str, working_dir)

    if tool_name == "write_file":
        parts = args_str.split("|", 1)
        if len(parts) < 2:
            return "(write_file requires: filepath | content)"
        return write_file_tool(parts[0].strip(), parts[1].strip(), working_dir)

    if tool_name == "grep_file":
        parts = [p.strip() for p in args_str.split("|", 1)]
        pattern = parts[0]
        filepath = parts[1] if len(parts) > 1 else "."
        return grep_file_tool(pattern, filepath, working_dir, agent_dirs)

    # --- Agent domain tools ---
    if domain_tools and tool_name in domain_tools:
        return execute_domain_tool(tool_name, args_str, domain_tools[tool_name], working_dir)

    return f"(unknown tool: {tool_name})"
