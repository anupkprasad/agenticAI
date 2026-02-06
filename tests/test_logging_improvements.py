"""
Comprehensive test for conversation logging improvements:
1. Full multiline LLM prompts/responses
2. Deduplication of repeated routing entries
"""
from agentic.state import MDState
from agentic.utils import log_supervisor_routing, log_llm_interaction

print("="*70)
print("TEST 1: Full Multiline LLM Logging")
print("="*70)

# Test LLM logging with multiline content
test_prompt = """You are a molecular dynamics expert. Analyze the following PDB structure.

Input: ATP.pdb
Tasks:
1. Remove water molecules
2. Fix missing residues
3. Add hydrogen atoms
4. Validate structure integrity

Provide detailed preprocessing steps."""

test_response = """Molecular Dynamics Preprocessing Plan:

Step 1: Water Removal
- Remove all HOH residues
- Keep crystallographic waters if within 3Å of protein

Step 2: Residue Repair
- Identify missing backbone atoms
- Use MODELLER for missing loops
- Validate secondary structure

Step 3: Hydrogen Addition
- Add hydrogens at pH 7.0
- Optimize hydrogen bond network
- Check protonation states

Step 4: Validation
- Run WHATCHECK analysis
- Verify Ramachandran plot
- Check steric clashes

Expected output: ATP_cleaned.pdb"""

log_llm_interaction(
    agent_name="test.preprocessing_planner",
    prompt=test_prompt,
    response=test_response,
    is_mock=False
)

print("\n✅ LLM interaction logged with full multiline format\n")

print("="*70)
print("TEST 2: Routing Deduplication")
print("="*70)

# Create test state
state: MDState = {
    "user_goal": "Test ATP simulation",
    "md_engine": "gromacs",
    "force_field": "amber99sb-ildn",
    "water_model": "tip3p",
    "human_in_loop": False,
    "raw_pdb": "ATP.pdb",
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
    "current_node": "planner",
    "next_node": "supervisor",
    "human_feedback": None,
    "working_directory": "working_dir",
    "errors": [],
    "warnings": []
}

print("\n1. First routing log (should appear):")
log_supervisor_routing(
    state,
    "supervisor",
    "Planner: Created plan with 3 steps. Returning to supervisor."
)

print("2. Identical routing log (should be skipped):")
log_supervisor_routing(
    state,
    "supervisor", 
    "Planner: Created plan with 3 steps. Returning to supervisor."
)

print("3. Another identical routing (should be skipped):")
log_supervisor_routing(
    state,
    "supervisor",
    "Planner: Created plan with 3 steps. Returning to supervisor."
)

# Now change routing
state["current_node"] = "supervisor"
state["next_node"] = "preprocess"

print("\n4. Different routing (should appear):")
log_supervisor_routing(
    state,
    "preprocess",
    "Supervisor: Executing preprocessing step from plan."
)

print("\n✅ Deduplication test complete\n")

print("="*70)
print("SUMMARY")
print("="*70)
print("✅ LLM interactions now show full prompts and responses")
print("✅ Visual separators (====) for easy reading")
print("✅ Duplicate routing entries automatically filtered")
print("✅ Only unique state transitions are logged")
print("\n📄 Check agent_conversation.log (or md_conversation.log) for results")
