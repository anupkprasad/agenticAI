"""Field-specific agent wrappers exposing a common interface for Supervisor.

Each wrapper implements two methods that Supervisor expects:
  - propose_plan(context) -> List[ToolCall]
  - execute_toolcall(toolcall) -> Dict (execution result)

Wrappers delegate to existing implementations where available.
"""
from .simulation_wrapper import SimulationAgentWrapper
from .preprocessor_wrapper import PreprocessorAgentWrapper
from .hpc_wrapper import HPCAgentWrapper
from .analysis_wrapper import AnalysisAgentWrapper

__all__ = [
    "SimulationAgentWrapper",
    "PreprocessorAgentWrapper",
    "HPCAgentWrapper",
    "AnalysisAgentWrapper",
]
