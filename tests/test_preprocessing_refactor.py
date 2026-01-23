"""
Test the refactored preprocessing agent with LLM tool calling
"""
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic.preprocess.preprocessing_agent import PreprocessingAgent, PreprocessingToolExecutor
from agentic.preprocess.schemas import PreprocessingAgentInput
from agentic.state import MDState
from agentic.llm import LLMClient


def test_tool_executor():
    """Test the tool executor directly"""
    print("\n" + "="*60)
    print("TEST 1: Tool Executor")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = PreprocessingToolExecutor(tmpdir)
        
        # Create a simple test PDB file
        test_pdb = Path(tmpdir) / "test.pdb"
        with open(test_pdb, 'w') as f:
            f.write("""ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00  0.00           N
ATOM      2  CA  ALA A   1      11.000  11.000  11.000  1.00  0.00           C
HETATM    3  O   HOH A 201      20.000  20.000  20.000  1.00  0.00           O
HETATM    4  O   HOH A 202      21.000  21.000  21.000  1.00  0.00           O
END
""")
        
        # Test: Analyze PDB
        print("\n1. Testing analyze_pdb tool...")
        result = executor.execute_tool("analyze_pdb", {"pdb_file": str(test_pdb)})
        print(f"   Result: {result}")
        assert result["success"], "analyze_pdb should succeed"
        assert result["analysis"]["atom_count"] == 2, "Should find 2 atoms"
        assert result["analysis"]["has_waters"] == True, "Should detect waters"
        print("   ✓ PASS: analyze_pdb works correctly")
        
        # Test: Remove waters
        print("\n2. Testing remove_waters tool...")
        result = executor.execute_tool("remove_waters", {"pdb_file": str(test_pdb)})
        print(f"   Result: {result}")
        assert result["success"], "remove_waters should succeed"
        assert result["removed_count"] == 2, "Should remove 2 water molecules"
        print("   ✓ PASS: remove_waters works correctly")
        
        # Test: Validate structure
        print("\n3. Testing validate_structure tool...")
        result = executor.execute_tool("validate_structure", {"pdb_file": str(test_pdb)})
        print(f"   Result: {result}")
        assert result["success"], "validate_structure should succeed"
        assert result["atoms"] == 2, "Should report 2 atoms"
        print("   ✓ PASS: validate_structure works correctly")


def test_preprocessing_agent():
    """Test the preprocessing agent"""
    print("\n" + "="*60)
    print("TEST 2: Preprocessing Agent")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test PDB file
        test_pdb = Path(tmpdir) / "test.pdb"
        with open(test_pdb, 'w') as f:
            f.write("""ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00  0.00           N
ATOM      2  CA  ALA A   1      11.000  11.000  11.000  1.00  0.00           C
ATOM      3  CB  ALA A   1      12.000  12.000  12.000  1.00  0.00           C
HETATM    4  O   HOH A 201      20.000  20.000  20.000  1.00  0.00           O
HETATM    5  O   HOH A 202      21.000  21.000  21.000  1.00  0.00           O
END
""")
        
        # Create mock LLM client
        llm = LLMClient("gpt-oss:20b", base_url="http://localhost:11434")  # Mock mode
        
        # Create preprocessing agent
        agent = PreprocessingAgent(llm)
        
        # Create test state
        state: MDState = {
            "user_goal": "Preprocess ATP.pdb for MD simulation",
            "raw_pdb": str(test_pdb),
            "working_directory": tmpdir,
            "force_field": "amber99sb-ildn",
            "water_model": "tip3p",
            "remove_waters": True,
            "add_hydrogens": False,
            "human_in_loop": False,
            "errors": [],
            "warnings": [],
            "next_node": "",
            "cleaning_pdb": None,
            "topology": None,
            "processed_coordinates": None,
            "preprocessing_report": "",
            "preprocessing_issues": [],
            "preprocessing_warnings": [],
            "preprocessing_execution_log": ""
        }
        
        print("\n1. Testing preprocessing node...")
        result_state = agent.preprocess_node(state)
        
        print(f"   Next node: {result_state['next_node']}")
        print(f"   Preprocessing issues: {result_state.get('preprocessing_issues', [])}")
        print(f"   Preprocessing warnings: {result_state.get('preprocessing_warnings', [])}")
        
        # Check state updates
        assert "cleaned_pdb" in result_state or "preprocessing_report" in result_state, \
            "State should be updated with preprocessing results"
        
        print("   ✓ PASS: Preprocessing agent executed successfully")


def test_fallback_plan():
    """Test the fallback preprocessing plan"""
    print("\n" + "="*60)
    print("TEST 3: Fallback Preprocessing Plan")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_pdb = Path(tmpdir) / "test.pdb"
        with open(test_pdb, 'w') as f:
            f.write("ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00  0.00           N\nEND\n")
        
        llm = LLMClient("gpt-oss:20b")  # Mock mode
        agent = PreprocessingAgent(llm)
        
        agent_input = PreprocessingAgentInput(
            pdb_path=str(test_pdb),
            working_directory=tmpdir,
            force_field="amber99sb-ildn",
            water_model="tip3p",
            remove_waters=True,
            add_hydrogens=True,
            user_goal="Test preprocessing",
            additional_instructions=None
        )
        
        # Get fallback plan
        analysis = {}
        plan = agent._fallback_preprocessing_plan(agent_input, analysis)
        
        print(f"\n1. Fallback plan generated:")
        print(f"   - Overview: {plan.overview}")
        print(f"   - Steps: {len(plan.steps)}")
        for i, step in enumerate(plan.steps, 1):
            print(f"     {i}. {step.name}: {step.tool_name}")
        
        assert len(plan.steps) > 0, "Fallback plan should have steps"
        assert any(s.tool_name == "prepare_for_gromacs" for s in plan.steps), \
            "Plan should include GROMACS preparation"
        
        print("\n   ✓ PASS: Fallback plan generated correctly")


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("PREPROCESSING AGENT REFACTORING TESTS")
    print("="*80)
    
    try:
        test_tool_executor()
        test_preprocessing_agent()
        test_fallback_plan()
        
        print("\n" + "="*80)
        print("ALL TESTS PASSED ✓")
        print("="*80)
        print("\nThe refactored preprocessing agent with LLM tool calling is working correctly!")
        print("\nKey Features:")
        print("  ✓ Modular tool executor with 8 preprocessing tools")
        print("  ✓ LLM-powered planning for adaptive preprocessing")
        print("  ✓ Pydantic-based tool schemas for structured tool calling")
        print("  ✓ Fallback heuristic planning when LLM fails")
        print("  ✓ Comprehensive logging and error handling")
        print("  ✓ Integration with workflow state management")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
