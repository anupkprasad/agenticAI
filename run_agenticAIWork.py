"""Enhanced LangGraph-based MD Runner with LLM-Powered Supervisor"""
import argparse
import sys
import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from agentic.workflow import MDWorkflow
from agentic.llm import LLMClient
from agentic.utils import (
    get_conversation_logger, log_user_prompt, log_workflow_completion, set_log_file
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def simple_feedback_handler(summary: Dict[str, Any]) -> str:
    """Simple command-line feedback handler for human-in-the-loop."""
    print("\n" + "="*60, flush=True)
    print(f"HUMAN CHECKPOINT: {summary['checkpoint_type'].upper()}", flush=True)
    print("="*60, flush=True)
    
    print("\nCurrent State:", flush=True)
    for key, value in summary['current_state'].items():
        print(f"  {key}: {value}", flush=True)
    
    if summary['issues_found']:
        print("\nIssues Found:", flush=True)
        for issue in summary['issues_found']:
            print(f"  - {issue}", flush=True)
    
    print("\nRecommendations:", flush=True)
    for rec in summary['recommendations']:
        print(f"  - {rec}", flush=True)
    
    print("\nOptions:", flush=True)
    print("  'approved' or 'continue' - proceed to next step", flush=True)
    print("  'retry' - redo this step", flush=True)
    print("  'modify: <instructions>' - modify approach", flush=True)
    print("  'exit' or 'quit' - stop workflow\n", flush=True)
    
    while True:
        sys.stdout.flush()  # Force flush before blocking on input
        feedback = input("Your decision: ").strip()
        if feedback:
            return feedback
        print("Please provide feedback.", flush=True)

# Remove the old log_workflow_state function since we now use conversation_logger

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LangGraph-based MD Simulation Workflow"
    )
    parser.add_argument("--goal", required=True, 
                       help="Natural language description of simulation goal")
    parser.add_argument("--subtask", default=None, nargs='+',
                       choices=["preprocess", "simsetup", "hpcjob", "analysis", "reporter"],
                       metavar="AGENT",
                       help=("One or more field agents to run, e.g. --subtask analysis reporter. "
                             "Valid values: preprocess simsetup hpcjob analysis reporter. "
                             "Omit to run the full pipeline."))
    parser.add_argument("--use-llm", action="store_true", 
                       help="Use LLM for intelligent planning (recommended)")
    parser.add_argument("--llm-model", default="gpt-oss:20b",
                       help="LLM model to use")
    parser.add_argument("--llm-base-url", default="http://localhost:11434",
                       help="LLM API base URL")
    parser.add_argument("--no-human-loop", action="store_true",
                       help="Skip human checkpoints (auto-approve)")
    parser.add_argument("--force-field", default="amber99sb-ildn",
                       help="Force field to use")
    parser.add_argument("--water-model", default="tip3p", 
                       help="Water model to use")
    parser.add_argument("--working-dir", default=".",
                       help="Base working directory (agents use subdirs: working_dir/preprocess/, working_dir/hpc/, etc.)")
    
    args = parser.parse_args(argv)
    
    # Set up LLM client (required, uses fallback/mock mode if no server)
    llm_client = LLMClient(
        model=args.llm_model,
        base_url=args.llm_base_url if args.use_llm else None
    )
    # Configuration
    config = {
        "force_field": args.force_field,
        "water_model": args.water_model,
        "human_in_loop": not args.no_human_loop,
        "working_directory": args.working_dir
    }
    
    # Pass subtask type directly in config
    if args.subtask:
        single_agent_map = {
            "preprocess": "preprocess_only",
            "simsetup": "setup_only",
            "hpcjob": "hpc_only",
            "analysis": "analysis_only",
            "reporter": "reporter_only"
        }
        if len(args.subtask) == 1:
            # Single agent: use existing specific subtask_type
            config["subtask_type"] = single_agent_map[args.subtask[0]]
        else:
            # Multiple agents: multi_agent mode with ordered agent list
            config["subtask_type"] = "multi_agent"
            config["agent_list"] = args.subtask
    
    goal = args.goal
    
    # Set up logging with the specified log file
    set_log_file("agent_conversation.log")
    
    # Initialize workflow
    workflow = MDWorkflow(llm_client)
    
    # Initialize conversation logger
    conversation_logger = get_conversation_logger("agent_conversation.log")
    
    # Log user prompt
    log_user_prompt(goal, config)
    
    # Run workflow
    print(f"\nStarting MD workflow for: {goal}", flush=True)
    print(f"Configuration: {config}", flush=True)
    if args.subtask:
        agents_label = ", ".join(a.upper() for a in args.subtask)
        print(f"Subtask Mode: {agents_label}", flush=True)
    
    if config["human_in_loop"]:
        print("\n⚠️  HUMAN-IN-THE-LOOP MODE: You will be prompted at checkpoints", flush=True)
        print("    Use --no-human-loop for automatic execution\n", flush=True)
    
    try:
        if config["human_in_loop"]:
            # Run with human feedback
            final_state = workflow.run_with_human_feedback(
                goal, 
                feedback_handler=simple_feedback_handler
            )
        else:
            # Run automatically
            final_state = workflow.run(goal, config)
        
        # Log workflow completion is handled by conversation_logger
        # No need for separate log_workflow_state since conversation logger captures everything
        
        # Log workflow completion
        success = len(final_state.get('errors', [])) == 0
        summary = f"Workflow completed with {len(final_state.get('errors', []))} errors and {len(final_state.get('warnings', []))} warnings"
        log_workflow_completion(final_state, success, summary)
        
        # Print results
        print("\n" + "="*60)
        print("WORKFLOW COMPLETED")
        print("="*60)
        
        if final_state.get("final_report"):
            print(final_state["final_report"])
        
        if final_state.get("errors"):
            print("\nERRORS:")
            for error in final_state["errors"]:
                print(f"  - {error}")
                
        if final_state.get("warnings"):
            print("\nWARNINGS:")
            for warning in final_state["warnings"]:
                print(f"  - {warning}")
        
        print(f"\nFull conversation log saved to: agent_conversation.log")
        
        # Return appropriate exit code
        return 0 if not final_state.get("errors") else 1
        
    except KeyboardInterrupt:
        print("\nWorkflow interrupted by user")
        return 130
    except Exception as e:
        print(f"\nWorkflow failed: {e}")
        logging.exception("Workflow execution failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
