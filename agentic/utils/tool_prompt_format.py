"""
Format tool metadata for LLM planning prompts.

Docstring Args/Returns are the single source of truth; schema metadata fills gaps
(required/optional flags, missing parameters) without duplicating a Parameters block.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# Matches:  topology_file: desc
#           topology_file (required): desc
_ARG_LINE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((required|optional)\))?\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _is_useful_schema_desc(desc: str) -> bool:
    d = (desc or "").strip().lower()
    return d not in ("", "no description", "n/a", "none")


def _merge_arg_description(body: str, schema_desc: str) -> str:
    """Combine docstring arg text with schema description without redundancy."""
    body = (body or "").strip()
    schema_desc = (schema_desc or "").strip()
    if not _is_useful_schema_desc(schema_desc):
        return body
    if not body or body.lower() in ("no description", "n/a"):
        return schema_desc
    if schema_desc.lower() in body.lower():
        return body
    return body


def annotate_args_required_optional(
    description: str,
    args_meta: Dict[str, Dict[str, Any]],
) -> str:
    """Inline required/optional flags inside an existing Args section."""
    if not description or not args_meta or "Args:" not in description:
        return description

    lines = description.split("\n")
    in_args = False
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Args:"):
            in_args = True
            out.append(line)
            continue
        if in_args and (
            stripped.startswith("Returns:")
            or stripped.startswith("Raises:")
        ):
            in_args = False
            out.append(line)
            continue

        if in_args:
            match = _ARG_LINE.match(stripped)
            if match:
                arg_name, _req_flag, rest = match.groups()
                if arg_name in args_meta:
                    req = "required" if args_meta[arg_name].get("required") else "optional"
                    schema_desc = (args_meta[arg_name].get("description") or "").strip()
                    body = _merge_arg_description(rest, schema_desc)
                    indent = line[: len(line) - len(line.lstrip())]
                    out.append(f"{indent}{arg_name} ({req}): {body}")
                    continue

        out.append(line)

    return "\n".join(out)


def _documented_arg_names(description: str) -> Set[str]:
    """Arg names listed between Args: and Returns:/Raises:."""
    if "Args:" not in description:
        return set()

    lines = description.split("\n")
    in_args = False
    names: Set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Args:"):
            in_args = True
            continue
        if in_args and (
            stripped.startswith("Returns:")
            or stripped.startswith("Raises:")
        ):
            break
        if in_args:
            match = _ARG_LINE.match(stripped)
            if match:
                names.add(match.group(1))
    return names


def enrich_tool_description_with_args(
    description: str,
    args_meta: Dict[str, Dict[str, Any]],
) -> str:
    """Merge schema metadata into Args; append Args block when the docstring lacks one."""
    desc = annotate_args_required_optional(description or "", args_meta)
    if not args_meta:
        return desc.strip()

    documented = _documented_arg_names(desc)
    missing = [
        (name, meta)
        for name, meta in args_meta.items()
        if name not in documented
    ]

    if "Args:" not in desc:
        lines = [desc.rstrip(), "", "Args:"]
        for name, meta in args_meta.items():
            req = "required" if meta.get("required") else "optional"
            adesc = (meta.get("description") or "").strip()
            adesc = adesc if _is_useful_schema_desc(adesc) else "See tool defaults."
            lines.append(f"    {name} ({req}): {adesc}")
        if "Returns:" not in desc:
            lines.extend(["", "Returns:", "    Dict with tool results"])
        return "\n".join(lines).strip()

    if not missing:
        return desc.strip()

    lines = desc.split("\n")
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if line.strip().startswith("Returns:") or line.strip().startswith("Raises:"):
            insert_at = i
            break

    extra: List[str] = []
    for name, meta in missing:
        req = "required" if meta.get("required") else "optional"
        adesc = (meta.get("description") or "").strip()
        adesc = adesc if _is_useful_schema_desc(adesc) else "See tool defaults."
        extra.append(f"        {name} ({req}): {adesc}")

    merged = lines[:insert_at] + extra + lines[insert_at:]
    return "\n".join(merged).strip()


def format_tool_for_llm_prompt(
    name: str,
    description: str,
    args_meta: Dict[str, Dict[str, Any]],
) -> str:
    """Single tool block: name + docstring (Args annotated, no duplicate parameter list)."""
    body = enrich_tool_description_with_args(description, args_meta)
    body_indented = "\n  ".join(body.split("\n"))
    return f"→ {name}\n  {body_indented}"


def format_tools_for_llm_prompt(tool_metadata: Dict[str, Dict[str, Any]]) -> str:
    """Format all tools for an LLM planning prompt (blank line between each tool)."""
    entries = [
        format_tool_for_llm_prompt(
            tool_info.get("name", "unknown"),
            tool_info.get("description", ""),
            tool_info.get("args") or {},
        )
        for tool_info in tool_metadata.values()
    ]
    return "\n\n".join(entries)
