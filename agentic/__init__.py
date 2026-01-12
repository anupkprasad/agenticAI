"""Top-level agentic package: exported helpers and agents.

This module exposes the `agent_from_name` factory for async agent
construction and keeps backwards compatibility with the older `agents`
module where convenient.
"""
from .agent_creator import agent_from_name, AgentCreator

__all__ = ["agent_from_name", "AgentCreator"]
