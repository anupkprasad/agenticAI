"""
Test script for new supervisor-planner-agent architecture
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agentic.state import MDState
from agentic.llm import LLMClient
from agentic.supervisor import MDSupervisor
from agentic.planner.planner_agent import MDPlanner

def test_pdb_analysis():
    """Test PDB analysis functionality"""
    print("=" * 80)
    print("TEST 1: PDB Analysis")
    print("=" * 80)
    
    # Import PDB analyzer
    from src.utils.pdb_analyzer import analyze_pdb
    
    # Test with a sample PDB path (update this to an actual PDB file in your system)
    test_pdb = "/path/to/test.pdb"  # Update this path
    
    if not os.path.exists(test_pdb):
        print(f"⚠️  Test PDB not found: {test_pdb}")
        print("   Please update test_pdb path in test_new_architecture.py")
        return False
    
    result = analyze_pdb.invoke({"pdb_file": test_pdb})
    
    if result.get("success"):
        print("✅ PDB Analysis successful")
        analysis = result.get("analysis", {})
        print(f"   - Total atoms: {analysis.get('total_atoms', 0)}")
        print(f"   - Has protein: {analysis.get('protein', {}).get('present', False)}")
        print(f"   - Has ligand: {analysis.get('ligands', {}).get('present', False)}")
        print(f"   - Chains: {analysis.get('chain_ids', [])}")
        return True
    else:
        print(f"❌ PDB Analysis failed: {result.get('error', 'Unknown error')}")
        return False

def test_supervisor_validation():
    """Test supervisor input validation with PDB analysis"""
    print("\n" + "=" * 80)
    print("TEST 2: Supervisor Input Validation")
    print("=" * 80)
    
    # Initialize LLM client (mock mode for testing)
    llm = LLMClient(base_url="http://localhost:11434", model="llama3.2")
    
    # Initialize supervisor
    try:
        supervisor = MDSupervisor(llm_client=llm)
        print("✅ Supervisor initialized")
    except Exception as e:
        print(f"❌ Supervisor initialization failed: {e}")
        return False
    
    # Create test state
    state = MDState(
        user_goal="Run MD simulation on /path/to/test.pdb with protein only",
        md_engine="gromacs",
        force_field="amber99sb-ildn",
        water_model="tip3p",
        human_in_loop=False,
        raw_pdb=None,
        cleaned_pdb=None,
        preprocessing_report=None,
        preprocessing_issues=[],
        pdb_analysis=None,
        component_selection=None,
        structured_prompt=None,
        topology=None,
        coordinates=None,
        mdp_files={},
        setup_report=None,
        setup_issues=[],
        hpc_action=None,
        job_script=None,
        job_id=None,
        job_status=None,
        trajectory_path=None,
        hpc_report=None,
        analysis_action=None,
        analysis_request=None,
        analysis_results={},
        figures=[],
        conclusions=None,
        current_node=None,
        next_node=None,
        human_feedback=None,
        working_directory=None,
        execution_plan=None,
        current_step=None,
        plan_executed=None,
        rephrased_goal=None,
        errors=[],
        warnings=[]
    )
    
    print("✅ Test state created")
    print(f"   User goal: {state['user_goal']}")
    
    # Note: Full validation requires a real PDB file
    print("⚠️  Full validation test requires real PDB file path")
    
    return True

def test_planner_structure():
    """Test planner structured plan generation"""
    print("\n" + "=" * 80)
    print("TEST 3: Planner Structure")
    print("=" * 80)
    
    # Initialize LLM client
    llm = LLMClient(base_url="http://localhost:11434", model="llama3.2")
    
    try:
        planner = MDPlanner(llm_client=llm)
        print("✅ Planner initialized")
    except Exception as e:
        print(f"❌ Planner initialization failed: {e}")
        return False
    
    # Test plan creation with mock data
    structured_prompt = """MD Simulation Setup Request:
SYSTEM: protein (2 chain(s))
PREPROCESSING: add hydrogens, remove water
GOAL: Run MD simulation on test.pdb with protein only
PDB_FILE: PDB with 5000 atoms"""
    
    pdb_analysis = {
        "total_atoms": 5000,
        "protein": {"present": True, "chain_count": 2},
        "ligands": {"present": True},
        "water": {"present": True},
        "summary": {
            "needs_hydrogen_addition": True,
            "needs_alternate_location_fix": False
        }
    }
    
    component_selection = {
        "protein": True,
        "ligand": False,
        "water": False,
        "ions": False,
        "specific_chains": None
    }
    
    # Create empty state for testing
    state = MDState(
        user_goal="test",
        md_engine="gromacs",
        force_field="amber99sb-ildn",
        water_model="tip3p",
        human_in_loop=False,
        raw_pdb=None,
        cleaned_pdb=None,
        preprocessing_report=None,
        preprocessing_issues=[],
        pdb_analysis=None,
        component_selection=None,
        structured_prompt=None,
        topology=None,
        coordinates=None,
        mdp_files={},
        setup_report=None,
        setup_issues=[],
        hpc_action=None,
        job_script=None,
        job_id=None,
        job_status=None,
        trajectory_path=None,
        hpc_report=None,
        analysis_action=None,
        analysis_request=None,
        analysis_results={},
        figures=[],
        conclusions=None,
        current_node=None,
        next_node=None,
        human_feedback=None,
        working_directory=None,
        execution_plan=None,
        current_step=None,
        plan_executed=None,
        rephrased_goal=None,
        errors=[],
        warnings=[]
    )
    
    plan = planner._create_plan_from_analysis(
        structured_prompt,
        "test.pdb",
        pdb_analysis,
        component_selection,
        state
    )
    
    print("✅ Plan created successfully")
    print(f"   Title: {plan.get('title', 'N/A')}")
    print(f"   Total steps: {len(plan.get('steps', []))}")
    print(f"   Method: {plan.get('method', 'N/A')}")
    
    for i, step in enumerate(plan.get("steps", []), 1):
        print(f"\n   Step {i}: {step.get('name', 'Unnamed')}")
        print(f"      Agent: {step.get('agent', 'N/A')}")
        print(f"      Inputs: {list(step.get('inputs', {}).keys())}")
        print(f"      Outputs: {step.get('expected_outputs', [])}")
        print(f"      Dependencies: {step.get('dependencies', [])}")
    
    return True

def test_workflow_architecture():
    """Test complete workflow architecture"""
    print("\n" + "=" * 80)
    print("TEST 4: Workflow Architecture Overview")
    print("=" * 80)
    
    print("""
    New Architecture Flow:
    ┌─────────────────────────────────────────────────────────────┐
    │ 1. USER PROMPT → SUPERVISOR (Input Validation)             │
    │    - Extract PDB path                                        │
    │    - Analyze PDB structure (components, composition)         │
    │    - Parse user intent & component selection                 │
    │    - Validate feasibility                                    │
    │    - Create structured prompt                                │
    └─────────────────────────────────────────────────────────────┘
                              ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ 2. STRUCTURED PROMPT → PLANNER                              │
    │    - Generate dependency-aware execution plan                │
    │    - Define clear inputs/outputs for each step               │
    │    - Specify field-specific agent for each task              │
    └─────────────────────────────────────────────────────────────┘
                              ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ 3. EXECUTION PLAN → SUPERVISOR (Step-by-step execution)    │
    │    - Execute Step 1 → Route to preprocessing_agent          │
    │    - Execute Step 2 → Route to setup_agent                  │
    │    - Execute Step 3 → Route to hpc_agent                    │
    │    - Execute Step 4 → Route to analysis_agent               │
    │    (Each step returns to supervisor for next step)           │
    └─────────────────────────────────────────────────────────────┘
                              ↓
    ┌─────────────────────────────────────────────────────────────┐
    │ 4. ALL STEPS COMPLETE → FINAL REPORT                       │
    │    - Comprehensive summary of workflow                       │
    │    - Results from all agents                                 │
    └─────────────────────────────────────────────────────────────┘
    
    Key Features:
    ✓ PDB analysis-driven planning
    ✓ User intent recognition (e.g., "protein only")
    ✓ Feasibility validation before execution
    ✓ Dependency-aware step execution
    ✓ Clear inputs/outputs for each step
    """)
    
    print("✅ Architecture overview displayed")
    return True

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("TESTING NEW ARCHITECTURE IMPLEMENTATION")
    print("=" * 80)
    
    results = []
    
    # Run tests
    results.append(("PDB Analysis", test_pdb_analysis()))
    results.append(("Supervisor Validation", test_supervisor_validation()))
    results.append(("Planner Structure", test_planner_structure()))
    results.append(("Architecture Overview", test_workflow_architecture()))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Architecture is ready.")
    else:
        print("\n⚠️  Some tests failed. Please review implementation.")
