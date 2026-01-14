"""Enhanced LangGraph-based MD Runner with LLM-Powered Supervisor"""
import argparse
import sys
import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from agentic.md_workflow import MDWorkflow
from agentic.llm import LLMClient
from agentic.conversation_logger import (
    get_conversation_logger, log_user_prompt, log_workflow_completion
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def simple_feedback_handler(summary: Dict[str, Any]) -> str:
    """Simple command-line feedback handler for human-in-the-loop."""
    print("\n" + "="*60)
    print(f"HUMAN CHECKPOINT: {summary['checkpoint_type'].upper()}")
    print("="*60)
    
    print("\nCurrent State:")
    for key, value in summary['current_state'].items():
        print(f"  {key}: {value}")
    
    if summary['issues_found']:
        print("\nIssues Found:")
        for issue in summary['issues_found']:
            print(f"  - {issue}")
    
    print("\nRecommendations:")
    for rec in summary['recommendations']:
        print(f"  - {rec}")
    
    print("\nOptions:")
    print("  'approved' or 'continue' - proceed to next step")
    print("  'retry' - redo this step")
    print("  'modify: <instructions>' - modify approach")
    
    while True:
        feedback = input("\nYour decision: ").strip()
        if feedback:
            return feedback
        print("Please provide feedback.")

# Remove the old log_workflow_state function since we now use conversation_logger

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LangGraph-based MD Simulation Workflow"
    )
    parser.add_argument("--goal", required=True, 
                       help="Natural language description of simulation goal")
    parser.add_argument("--use-llm", action="store_true", 
                       help="Use LLM for intelligent planning (recommended)")
    parser.add_argument("--llm-model", default="gpt-oss:120b",
                       help="LLM model to use")
    parser.add_argument("--llm-base-url", default="http://172.22.149.139:11434",
                       help="LLM API base URL")
    parser.add_argument("--no-human-loop", action="store_true",
                       help="Skip human checkpoints (auto-approve)")
    parser.add_argument("--force-field", default="amber99sb-ildn",
                       help="Force field to use")
    parser.add_argument("--water-model", default="tip3p", 
                       help="Water model to use")
    parser.add_argument("--working-dir", default=None,
                       help="Working directory for files")
    
    args = parser.parse_args(argv)
    
    # Set up LLM client
    llm_client = None
    if args.use_llm:
        llm_client = LLMClient(
            model=args.llm_model,
            base_url=args.llm_base_url
        )
    
    # Initialize workflow
    workflow = MDWorkflow(llm_client)
    
    # Configuration
    config = {
        "force_field": args.force_field,
        "water_model": args.water_model,
        "human_in_loop": not args.no_human_loop
    }
    
    if args.working_dir:
        config["working_directory"] = args.working_dir

    # Initialize conversation logger
    conversation_logger = get_conversation_logger("md_conversation.log")
    
    # Log user prompt
    log_user_prompt(args.goal, config)
    
    # Run workflow
    print(f"Starting MD workflow for: {args.goal}")
    print(f"Configuration: {config}")
    
    try:
        if config["human_in_loop"]:
            # Run with human feedback
            final_state = workflow.run_with_human_feedback(
                args.goal, 
                feedback_handler=simple_feedback_handler
            )
        else:
            # Run automatically
            final_state = workflow.run(args.goal, config)
        
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
        
        print(f"\nFull conversation log saved to: md_conversation.log")
        
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
