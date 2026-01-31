"""Top-level agentic package: LangGraph MD workflow components.

This module exposes the main workflow components for the MD simulation pipeline.
"""
# Lazy imports to avoid circular dependency issues
def __getattr__(name):
    if name == "MDWorkflow":
        from .workflow import MDWorkflow
        return MDWorkflow
    elif name == "MDSupervisor":
        from .supervisor import MDSupervisor
        return MDSupervisor
    elif name == "MDState":
        from .state import MDState
        return MDState
    elif name == "LLMClient":
        from .llm import LLMClient
        return LLMClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["MDWorkflow", "MDSupervisor", "MDState", "LLMClient"]
