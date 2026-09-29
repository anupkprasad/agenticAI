"""Build a retrieval catalog from ToolsRegistry metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def tool_embed_text(tool: Dict[str, Any]) -> str:
    name = str(tool.get("name") or "")
    desc = str(tool.get("description") or "")
    agent = str(tool.get("agent") or "")
    params = tool.get("parameters") or {}
    param_names = " ".join(str(k) for k in params.keys())
    return f"{agent} {name} {name.replace('_', ' ')} {desc} {param_names}"


def catalog_from_registry(
    registry: Any,
    *,
    agent_name: Optional[str] = None,
    exclude_combined_tools: bool = False,
) -> List[Dict[str, Any]]:
    """Flatten ToolsRegistry entries into retrievable records."""
    records: List[Dict[str, Any]] = []
    if agent_name:
        tools = registry.get_tools_for_agent(
            agent_name,
            exclude_combined_tools=exclude_combined_tools and agent_name == "analysis",
        ) or []
        source = [(agent_name, tools)]
    else:
        source = list((registry.tools_by_agent or {}).items())

    seen = set()
    for agent, tools in source:
        for tool in tools or []:
            name = str(tool.get("name") or "")
            key = f"{agent}.{name}"
            if not name or key in seen:
                continue
            seen.add(key)
            rec = {
                "key": key,
                "name": name,
                "agent": agent,
                "description": str(tool.get("description") or ""),
                "embed_text": tool_embed_text({**tool, "agent": agent}),
                "tool": tool,
            }
            records.append(rec)
    return records
