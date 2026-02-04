"""
Enhanced Logging System for Iterative Workflow
Tracks execution, decisions, errors, and plan revisions
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from ..state import MDState

logger = logging.getLogger(__name__)


class WorkflowMemoryManager:
    """
    Centralized memory management for workflow execution.
    Maintains persistent context across planning iterations.
    """
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize log files
        self.execution_trace_file = self.log_dir / "execution_trace.jsonl"
        self.decision_log_file = self.log_dir / "decision_log.jsonl"
        self.planner_context_file = self.log_dir / "planner_context.json"
        self.error_escalation_file = self.log_dir / "error_escalation.jsonl"
        
        # In-memory caches
        self.planner_context: Dict[str, Any] = {}
        self.execution_history: List[Dict[str, Any]] = []
        
    def log_execution_step(self, 
                          step_type: str, 
                          agent_name: str,
                          action: str,
                          details: Dict[str, Any],
                          state_snapshot: Optional[MDState] = None):
        """Log a single execution step with full context"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "step_type": step_type,  # "validation", "planning", "execution", "error"
            "agent": agent_name,
            "action": action,
            "details": details,
            "state_snapshot": self._sanitize_state(state_snapshot) if state_snapshot else None
        }
        
        # Append to JSONL file (one JSON object per line)
        with open(self.execution_trace_file, 'a') as f:
            f.write(json.dumps(entry) + "\n")
        
        # Keep in memory for quick access
        self.execution_history.append(entry)
        
    def log_supervisor_decision(self,
                               current_node: str,
                               next_node: str,
                               reasoning: str,
                               routing_factors: Dict[str, Any],
                               state: MDState):
        """Log supervisor routing decision with reasoning"""
        decision = {
            "timestamp": datetime.now().isoformat(),
            "current_node": current_node,
            "next_node": next_node,
            "reasoning": reasoning,
            "factors": routing_factors,
            "state_summary": {
                "has_plan": bool(state.get("execution_plan")),
                "completed_steps": len(state.get("completed_steps", [])),
                "pending_plans": len(state.get("pending_field_plans", [])),
                "errors": len(state.get("errors", [])),
                "warnings": len(state.get("warnings", []))
            }
        }
        
        with open(self.decision_log_file, 'a') as f:
            f.write(json.dumps(decision) + "\n")
    
    def log_error_escalation(self,
                            agent_name: str,
                            error: Dict[str, Any],
                            severity: str,
                            escalation_path: List[str],
                            resolution: Optional[str] = None):
        """Track error escalation through the system"""
        escalation = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "error": error,
            "severity": severity,
            "escalation_path": escalation_path,  # ["field_agent", "supervisor", "planner"]
            "resolution": resolution,
            "resolved": resolution is not None
        }
        
        with open(self.error_escalation_file, 'a') as f:
            f.write(json.dumps(escalation) + "\n")
    
    def update_planner_context(self, 
                              plan_version: int,
                              current_step: int,
                              completed_steps: List[Dict[str, Any]],
                              pending_steps: List[Dict[str, Any]],
                              learned_constraints: Dict[str, Any],
                              error_feedback: List[Dict[str, Any]]):
        """Update Planner's working memory for iterative planning"""
        self.planner_context = {
            "last_updated": datetime.now().isoformat(),
            "plan_version": plan_version,
            "current_step": current_step,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "learned_constraints": learned_constraints,
            "error_feedback": error_feedback,
            "revision_history": self.planner_context.get("revision_history", []) + [{
                "version": plan_version,
                "timestamp": datetime.now().isoformat(),
                "reason": "Updated based on execution feedback"
            }]
        }
        
        # Persist to disk
        with open(self.planner_context_file, 'w') as f:
            json.dumps(self.planner_context, indent=2)
    
    def load_planner_context(self) -> Dict[str, Any]:
        """Load Planner's context from previous execution"""
        if self.planner_context_file.exists():
            with open(self.planner_context_file, 'r') as f:
                return json.load(f)
        return {}
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Generate summary of entire workflow execution"""
        return {
            "total_steps": len(self.execution_history),
            "steps_by_agent": self._count_by_agent(),
            "errors_encountered": self._count_errors(),
            "plan_revisions": self.planner_context.get("plan_version", 0),
            "execution_timeline": self._build_timeline()
        }
    
    def get_agent_performance(self, agent_name: str) -> Dict[str, Any]:
        """Get performance metrics for specific agent"""
        agent_steps = [
            step for step in self.execution_history 
            if step.get("agent") == agent_name
        ]
        
        errors = [
            step for step in agent_steps 
            if step.get("step_type") == "error"
        ]
        
        return {
            "agent": agent_name,
            "total_executions": len(agent_steps),
            "errors": len(errors),
            "success_rate": (len(agent_steps) - len(errors)) / len(agent_steps) if agent_steps else 0,
            "average_execution_time": self._calculate_avg_time(agent_steps)
        }
    
    def _sanitize_state(self, state: MDState) -> Dict[str, Any]:
        """Remove sensitive/large data from state snapshot"""
        sanitized = {}
        
        # Include only important fields
        important_fields = [
            "current_node", "next_node", "user_goal", "rephrased_goal",
            "raw_pdb", "cleaned_pdb", "topology", "coordinates",
            "current_plan_step", "plan_executed", "errors", "warnings"
        ]
        
        for field in important_fields:
            if field in state:
                value = state[field]
                # Truncate long strings
                if isinstance(value, str) and len(value) > 200:
                    sanitized[field] = value[:200] + "..."
                else:
                    sanitized[field] = value
        
        return sanitized
    
    def _count_by_agent(self) -> Dict[str, int]:
        """Count execution steps by agent"""
        counts = {}
        for step in self.execution_history:
            agent = step.get("agent", "unknown")
            counts[agent] = counts.get(agent, 0) + 1
        return counts
    
    def _count_errors(self) -> Dict[str, int]:
        """Count errors by severity"""
        if not self.error_escalation_file.exists():
            return {}
        
        error_counts = {"minor": 0, "moderate": 0, "critical": 0}
        with open(self.error_escalation_file, 'r') as f:
            for line in f:
                error = json.loads(line)
                severity = error.get("severity", "unknown")
                if severity in error_counts:
                    error_counts[severity] += 1
        
        return error_counts
    
    def _build_timeline(self) -> List[Dict[str, Any]]:
        """Build execution timeline with key events"""
        timeline = []
        for step in self.execution_history:
            timeline.append({
                "timestamp": step["timestamp"],
                "event": f"{step['agent']}: {step['action']}",
                "type": step["step_type"]
            })
        return timeline
    
    def _calculate_avg_time(self, steps: List[Dict[str, Any]]) -> float:
        """Calculate average execution time (placeholder)"""
        # In real implementation, track start/end times
        return 0.0
    
    def export_full_report(self, output_path: str):
        """Export comprehensive execution report"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "execution_summary": self.get_execution_summary(),
            "planner_context": self.planner_context,
            "execution_history": self.execution_history,
            "error_summary": self._count_errors()
        }
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Full execution report exported to {output_path}")


# Singleton instance
_memory_manager: Optional[WorkflowMemoryManager] = None


def get_memory_manager(log_dir: str = "logs") -> WorkflowMemoryManager:
    """Get or create the singleton memory manager"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = WorkflowMemoryManager(log_dir)
    return _memory_manager


# Convenience functions for common logging operations
def log_execution(step_type: str, agent: str, action: str, 
                 details: Dict[str, Any], state: Optional[MDState] = None):
    """Log execution step"""
    manager = get_memory_manager()
    manager.log_execution_step(step_type, agent, action, details, state)


def log_routing_decision(current: str, next_node: str, reasoning: str,
                        factors: Dict[str, Any], state: MDState):
    """Log supervisor routing decision"""
    manager = get_memory_manager()
    manager.log_supervisor_decision(current, next_node, reasoning, factors, state)


def log_error_escalation(agent: str, error: Dict[str, Any], severity: str,
                        path: List[str], resolution: Optional[str] = None):
    """Log error escalation"""
    manager = get_memory_manager()
    manager.log_error_escalation(agent, error, severity, path, resolution)


def update_planner_memory(plan_version: int, current_step: int,
                         completed: List[Dict], pending: List[Dict],
                         constraints: Dict[str, Any], feedback: List[Dict]):
    """Update Planner's working memory"""
    manager = get_memory_manager()
    manager.update_planner_context(
        plan_version, current_step, completed, pending, constraints, feedback
    )
