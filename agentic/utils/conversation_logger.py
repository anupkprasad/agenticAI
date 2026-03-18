"""Comprehensive conversation logger for MD workflow.

This module provides centralized logging for all user interactions, supervisor decisions,
agent actions, and LLM conversations throughout the MD workflow.
"""
import logging
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path

class ConversationLogger:
    """
    Centralized logger that captures all conversations and actions in the MD workflow.
    
    Logs everything from user prompts to supervisor routing to agent actions and LLM calls.
    Creates a comprehensive record of the entire workflow execution.
    """
    
    def __init__(self, log_file: str = "agent_conversation.log"):
        self.log_file = log_file
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Track last routing to avoid duplicates
        self._last_routing = None
        
        # Set up the conversation logger
        self.logger = logging.getLogger("md_conversation")
        self.logger.setLevel(logging.DEBUG)  # Capture all levels
        self.logger.propagate = False  # Don't propagate to root logger
        
        # Remove existing handlers to avoid duplication
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create file handler with proper buffering
        handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        handler.setLevel(logging.DEBUG)
        
        # Create detailed formatter - timestamps only on major sections
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Store handler for flushing
        self.file_handler = handler
        
        # Start session
        self._log_session_start()
        self._flush()
    
    def _flush(self):
        """Flush the file handler to ensure data is written immediately."""
        if hasattr(self, 'file_handler'):
            self.file_handler.flush()
    
    def _timestamp(self) -> str:
        """Get current timestamp for major events."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _log_session_start(self):
        """Log the start of a new workflow session."""
        self.logger.info("="*80)
        self.logger.info(f"NEW MD WORKFLOW SESSION STARTED - {self._timestamp()}")
        self.logger.info(f"Session ID: {self.session_id}")
        self.logger.info("="*80)
        self._flush()
    
    def log_user_prompt(self, goal: str, config: Dict[str, Any]):
        """Log the initial user prompt and configuration."""
        self.logger.info("")
        self.logger.info(f"🎯 USER PROMPT [{self._timestamp()}]:")
        self.logger.info(f"   Goal: {goal}")
        self.logger.info(f"   Configuration: {json.dumps(config, indent=4)}")
        self.logger.info("")
        self._flush()
    
    def log_supervisor_routing(self, current_state: Dict[str, Any], next_node: str, reasoning: str = ""):
        """Log supervisor routing decisions."""
        # Create a signature for this routing to detect duplicates
        current_node = current_state.get('current_node', 'start')
        routing_signature = f"{current_node}->{next_node}:{reasoning}"
        
        # Skip if this is an exact duplicate of the last routing
        if self._last_routing == routing_signature:
            return
        
        self._last_routing = routing_signature
        
        self.logger.info(f"🎛️  SUPERVISOR ROUTING [{self._timestamp()}]:")
        self.logger.info(f"   Current State Summary:")
        
        # Log key state indicators
        key_fields = ['raw_pdb', 'cleaned_pdb', 'coordinates', 'job_id', 'analysis_results']
        for field in key_fields:
            value = current_state.get(field)
            status = "✅" if value else "❌"
            self.logger.info(f"     {status} {field}: {value or 'Not set'}")
        
        # Show routing path: CurrentNode → NextNode
        self.logger.info(f"   📍 Routing: {current_node} → {next_node}")
        if reasoning:
            self.logger.info(f"   💭 Reasoning: {reasoning}")
        
        # Log any errors or warnings
        errors = current_state.get('errors', [])
        warnings = current_state.get('warnings', [])
        if errors:
            self.logger.info("   ⚠️  Errors: %s", errors)  # Don't use f-string - errors may contain {}
        if warnings:
            self.logger.info("   ⚠️  Warnings: %s", warnings)  # Don't use f-string - warnings may contain {}
        self.logger.info("")
        self._flush()
    
    def log_agent_start(self, agent_name: str, agent_type: str, input_data: Dict[str, Any]):
        """Log when an agent starts processing."""
        self.logger.info(f"🤖 {agent_type.upper()} AGENT ({agent_name}) STARTING [{self._timestamp()}]:")
        self.logger.info(f"   Input Data Summary:")
        
        # Log relevant input fields
        # If planner instructions available, show that instead of user_goal
        if input_data.get('planner_instructions'):
            relevant_fields = ['raw_pdb', 'cleaned_pdb', 'planner_instructions', 'force_field', 'water_model']
        else:
            relevant_fields = ['raw_pdb', 'cleaned_pdb', 'user_goal', 'force_field', 'water_model']
        
        for field in relevant_fields:
            value = input_data.get(field)
            if value:
                # Truncate long planner instructions for log readability
                if field == 'planner_instructions' and isinstance(value, str) and len(value) > 200:
                    display_value = value[:200] + "... [truncated, see full plan above]"
                else:
                    display_value = value
                self.logger.info(f"     • {field}: {display_value}")
        self.logger.info("")
        self._flush()
    
    def log_llm_interaction(self, agent_name: str, prompt: str, response: str, is_mock: bool = False):
        """Log LLM interactions with prompts and responses."""
        llm_type = "🔀 MOCK LLM" if is_mock else "🧠 LLM"
        self.logger.info(f"{llm_type} INTERACTION ({agent_name}) [{self._timestamp()}]:")
        self.logger.info(f"   📝 Prompt:")
        self.logger.info("   " + "="*70)
        
        # Log full prompt with indentation for easy reading
        prompt_lines = prompt.strip().split('\n')
        for line in prompt_lines:
            self.logger.info(f"   {line}")
        
        self.logger.info("   " + "="*70)
        self.logger.info(f"   💭 Response:")
        self.logger.info("   " + "="*70)
        
        # Log full response with indentation
        # Try to format JSON responses for better readability
        response_str = response.strip()
        try:
            # Check if response is wrapped in markdown code blocks
            if response_str.startswith('```'):
                # Handle both multi-line and single-line markdown blocks
                if '\n' in response_str:
                    # Multi-line: Extract content between ``` markers
                    lines = response_str.split('\n')
                    # Remove first line (```json or ```) and last line (```)
                    if len(lines) > 2 and lines[-1].strip() == '```':
                        response_str = '\n'.join(lines[1:-1])
                else:
                    # Single-line: ```json { ... } ```
                    # Remove ``` markers and optional language identifier
                    response_str = response_str.strip('`')
                    if response_str.startswith('json'):
                        response_str = response_str[4:].strip()
                    elif response_str.startswith('python'):
                        response_str = response_str[6:].strip()
            
            # Check if response is JSON
            if response_str.strip().startswith('{') or response_str.strip().startswith('['):
                # Try to parse and pretty-print JSON
                import json
                parsed = json.loads(response_str)
                formatted = json.dumps(parsed, indent=2)
                response_lines = formatted.split('\n')
            else:
                response_lines = response_str.split('\n')
        except (json.JSONDecodeError, ValueError) as e:
            # Not JSON or malformed, just split by newlines
            response_lines = response_str.split('\n')
        
        for line in response_lines:
            self.logger.info(f"   {line}")
        
        self.logger.info("   " + "="*70)
        self.logger.info("")
        self._flush()
    
    def log_agent_action(self, agent_name: str, action: str, details: Dict[str, Any]):
        """Log specific actions taken by agents."""
        self.logger.info(f"⚡ AGENT ACTION ({agent_name}):")
        self.logger.info(f"   🎬 Action: {action}")
        
        # Log action details
        for key, value in details.items():
            if isinstance(value, (list, dict)):
                self.logger.info(f"   📊 {key}: {json.dumps(value, indent=6)}")
            else:
                self.logger.info(f"   📊 {key}: {value}")
        self.logger.info("")
        self._flush()
    
    def log_file_operation(self, agent_name: str, operation: str, file_path: str, success: bool, details: str = ""):
        """Log file operations (creation, reading, validation)."""
        status = "✅ SUCCESS" if success else "❌ FAILED"
        self.logger.info(f"📁 FILE OPERATION ({agent_name}):")
        self.logger.info(f"   Operation: {operation}")
        self.logger.info(f"   File: {file_path}")
        self.logger.info(f"   Status: {status}")
        if details:
            self.logger.info(f"   Details: {details}")
        self.logger.info("")
        self._flush()
    
    def log_human_checkpoint(self, checkpoint_type: str, context: Dict[str, Any], user_choice: str, feedback: str = ""):
        """Log human checkpoint interactions."""
        self.logger.info("👤 HUMAN CHECKPOINT:")
        self.logger.info(f"   🔍 Checkpoint Type: {checkpoint_type}")
        self.logger.info(f"   📋 Context: {json.dumps(context, indent=6)}")
        self.logger.info(f"   ✋ User Choice: {user_choice}")
        if feedback:
            self.logger.info(f"   💬 User Feedback: {feedback}")
        self.logger.info("")
        self._flush()
    
    def log_agent_completion(self, agent_name: str, agent_type: str, output_data: Dict[str, Any], success: bool):
        """Log when an agent completes processing."""
        status = "✅ COMPLETED" if success else "❌ FAILED"
        self.logger.info(f"🏁 {agent_type.upper()} AGENT ({agent_name}) {status} [{self._timestamp()}]:")
        
        # Log key outputs - different agents produce different outputs
        if agent_name == "preprocessing":
            # Preprocessing only produces cleaned PDB files
            output_fields = ['cleaned_pdb', 'preprocessing_report']
        elif agent_name == "setup":
            # Setup produces topology, coordinates, and mdp files
            output_fields = ['topology', 'coordinates', 'mdp_files']
        else:
            # Generic fields for other agents
            output_fields = ['cleaned_pdb', 'topology', 'coordinates', 'mdp_files', 'execution_log']
        
        self.logger.info(f"   📤 Output Summary:")
        for field in output_fields:
            value = output_data.get(field)
            if value:
                if isinstance(value, dict):
                    self.logger.info(f"     • {field}: {len(value)} items")
                    for k, v in value.items():
                        self.logger.info(f"       - {k}: {v}")
                elif isinstance(value, list):
                    self.logger.info(f"     • {field}: {len(value)} items")
                else:
                    self.logger.info(f"     • {field}: {value}")
        
        # Log any issues
        issues = output_data.get('preprocessing_issues', []) or output_data.get('setup_issues', [])
        if issues:
            self.logger.info(f"   ⚠️  Issues: {issues}")
        
        self.logger.info("")
        self._flush()
    
    def log_workflow_completion(self, final_state: Dict[str, Any], success: bool, summary: str):
        """Log the completion of the entire workflow."""
        status = "✅ SUCCESS" if success else "❌ FAILED"
        self.logger.info(f"🎯 WORKFLOW COMPLETION [{self._timestamp()}]:")
        self.logger.info(f"   Status: {status}")
        self.logger.info(f"   📋 Summary:")
        for line in summary.strip().split('\n'):
            self.logger.info(f"      {line}")
        
        # Log final file counts
        files_created = []
        for field in ['cleaned_pdb', 'topology', 'coordinates']:
            if final_state.get(field):
                files_created.append(field)
        
        mdp_files = final_state.get('mdp_files', {})
        if mdp_files:
            files_created.append(f"{len(mdp_files)} MDP files")
        
        self.logger.info(f"   📁 Files Created: {', '.join(files_created) if files_created else 'None'}")
        
        # Log final error count
        errors = final_state.get('errors', [])
        warnings = final_state.get('warnings', [])
        self.logger.info(f"   ⚠️  Errors: {len(errors)}")
        self.logger.info(f"   ⚠️  Warnings: {len(warnings)}")
        self.logger.info("="*80)
        self._flush()
        
        self.logger.info("="*80)
        self.logger.info(f"SESSION {self.session_id} COMPLETED - {self._timestamp()}")
        self.logger.info("="*80)
        self.logger.info("")
        self._flush()

    def log_error(self, context: str, error: Exception, details: Dict[str, Any] = None):
        """Log errors with full context."""
        self.logger.error(f"💥 ERROR in {context} [{self._timestamp()}]:")
        self.logger.error(f"   Exception: {type(error).__name__}: {str(error)}")
        if details:
            self.logger.error(f"   Details: {json.dumps(details, indent=6)}")
        self.logger.error("")
        self._flush()

# Global conversation logger instance
_conversation_logger: Optional[ConversationLogger] = None
_log_file_override: Optional[str] = None

def get_conversation_logger(log_file: str = "md_conversation.log") -> ConversationLogger:
    """Get or create the global conversation logger instance."""
    global _conversation_logger, _log_file_override
    
    # Use the override if set
    if _log_file_override:
        log_file = _log_file_override
    
    if _conversation_logger is None or _conversation_logger.log_file != log_file:
        _conversation_logger = ConversationLogger(log_file)
    return _conversation_logger

def set_log_file(log_file: str):
    """Set the log file path for the conversation logger."""
    global _log_file_override
    _log_file_override = log_file
    # Reset the global logger so it will be recreated with the new file
    global _conversation_logger
    _conversation_logger = None

def log_user_prompt(goal: str, config: Dict[str, Any]):
    """Convenience function to log user prompt."""
    get_conversation_logger().log_user_prompt(goal, config)

def log_supervisor_routing(current_state: Dict[str, Any], next_node: str, reasoning: str = ""):
    """Convenience function to log supervisor routing."""
    get_conversation_logger().log_supervisor_routing(current_state, next_node, reasoning)

def log_agent_start(agent_name: str, agent_type: str, input_data: Dict[str, Any]):
    """Convenience function to log agent start."""
    get_conversation_logger().log_agent_start(agent_name, agent_type, input_data)

def log_llm_interaction(agent_name: str, prompt: str, response: str, is_mock: bool = False):
    """Convenience function to log LLM interaction."""
    get_conversation_logger().log_llm_interaction(agent_name, prompt, response, is_mock)

def log_agent_action(agent_name: str, action: str, details: Dict[str, Any]):
    """Convenience function to log agent action."""
    get_conversation_logger().log_agent_action(agent_name, action, details)

def log_file_operation(agent_name: str, operation: str, file_path: str, success: bool, details: str = ""):
    """Convenience function to log file operation."""
    get_conversation_logger().log_file_operation(agent_name, operation, file_path, success, details)

def log_human_checkpoint(checkpoint_type: str, context: Dict[str, Any], user_choice: str, feedback: str = ""):
    """Convenience function to log human checkpoint."""
    get_conversation_logger().log_human_checkpoint(checkpoint_type, context, user_choice, feedback)

def log_agent_completion(agent_name: str, agent_type: str, output_data: Dict[str, Any], success: bool):
    """Convenience function to log agent completion."""
    get_conversation_logger().log_agent_completion(agent_name, agent_type, output_data, success)

def log_workflow_completion(final_state: Dict[str, Any], success: bool, summary: str):
    """Convenience function to log workflow completion."""
    get_conversation_logger().log_workflow_completion(final_state, success, summary)

def log_error(context: str, error: Exception, details: Dict[str, Any] = None):
    """Convenience function to log errors."""
    get_conversation_logger().log_error(context, error, details)
