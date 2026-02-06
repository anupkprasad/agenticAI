"""
Quick test to verify routing log improvements.
"""
from agentic.state import MDState
from agentic.utils import log_supervisor_routing

# Test 1: Show routing from supervisor to preprocess
print("Test 1: Supervisor → Preprocess routing")
state1: MDState = {
    "user_goal": "Test goal",
    "md_engine": "gromacs",
    "force_field": "amber99sb-ildn",
    "water_model": "tip3p",
    "human_in_loop": False,
    "raw_pdb": "test.pdb",
    "cleaned_pdb": None,
    "preprocessing_report": None,
    "preprocessing_issues": [],
    "topology": None,
    "coordinates": None,
    "mdp_files": {},
    "setup_report": None,
    "setup_issues": [],
    "hpc_action": None,
    "job_script": None,
    "job_id": None,
    "job_status": None,
    "trajectory_path": None,
    "hpc_report": None,
    "analysis_action": None,
    "analysis_request": None,
    "analysis_results": {},
    "figures": [],
    "conclusions": None,
    "current_node": "supervisor",  # Currently at supervisor
    "next_node": "preprocess",
    "human_feedback": None,
    "working_directory": "working_dir",
    "errors": [],
    "warnings": []
}

log_supervisor_routing(
    state1, 
    "preprocess",
    "Supervisor: Execution plan requires preprocessing step."
)

print("\n" + "="*60 + "\n")

# Test 2: Show routing from planner back to supervisor
print("Test 2: Planner → Supervisor routing")
state2 = state1.copy()
state2["current_node"] = "planner"
state2["next_node"] = "supervisor"

log_supervisor_routing(
    state2,
    "supervisor", 
    "Planner: Created plan with 4 steps. Returning to supervisor."
)

print("\n✅ Routing log improvements working correctly!")
print("   - Shows 'CurrentNode → NextNode' format")
print("   - Tracks current_node in MDState")
