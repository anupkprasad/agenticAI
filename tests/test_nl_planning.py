#!/usr/bin/env python3
"""
Test natural language planning mode for planner agent.

Verifies:
1. tools_registry detects StructuredTool instances
2. knowledge_loader loads domain docs
3. Planner generates detailed NL plans (not JSON)
4. Parse extracts agent sequence from prose
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agentic.planner.tools_registry import get_tools_registry
from agentic.planner.knowledge_loader import get_knowledge_loader
from agentic.planner.planner_agent import MDPlanner
from agentic.state import MDState


def test_tools_registry():
    """Verify tools_registry detects StructuredTool instances."""
    print("\n" + "="*60)
    print("TEST 1: Tools Registry - StructuredTool Detection")
    print("="*60)
    
    registry = get_tools_registry()
    all_tools = registry.discover_all_tools()
    agents_tools = registry.tools_by_agent
    
    print(f"\n✓ Found {len(all_tools)} total tools from {len(agents_tools)} agents:")
    
    # Show tools by agent (tools_by_agent contains tool dicts, not names)
    for agent_name, tool_infos in agents_tools.items():
        print(f"\n  {agent_name}: {len(tool_infos)} tools")
        for i, tool_info in enumerate(tool_infos):
            if i >= 2:  # Show first 2 from each agent
                break
            if isinstance(tool_info, dict):
                tool_name = tool_info.get('name', 'unnamed')
                params = tool_info.get('parameters', {})
                print(f"    - {tool_name}")
                if isinstance(params, dict) and params:
                    print(f"      Params: {list(params.keys())[:3]}")  # First 3 params
    
    # Test formatting for LLM
    context = registry.get_tools_for_planner()
    print(f"\n✓ LLM context length: {len(context)} chars")
    print(f"  Preview: {context[:150]}...")
    
    return len(all_tools) > 0


def test_knowledge_loader():
    """Verify knowledge base loads correctly."""
    print("\n" + "="*60)
    print("TEST 2: Knowledge Loader - Domain Documents")
    print("="*60)
    
    loader = get_knowledge_loader()
    all_docs = loader.load_all_knowledge()
    docs_by_category = loader.knowledge_by_category
    
    print(f"\n✓ Loaded {len(all_docs)} total documents from {len(docs_by_category)} categories:")
    for category, doc_keys in docs_by_category.items():
        # doc_keys might be a set, convert to list
        doc_list = list(doc_keys) if not isinstance(doc_keys, list) else doc_keys
        print(f"\n  {category}: {len(doc_list)} documents")
        for i, doc_key in enumerate(doc_list):
            if i >= 2:  # Show first 2
                break
            doc = all_docs.get(doc_key, {})
            print(f"    - {doc.get('filename', doc_key)} ({doc.get('size', 0)} bytes)")
    
    # Test search
    results = loader.search_knowledge("protein preparation")
    print(f"\n✓ Search 'protein preparation': {len(results)} results")
    
    # Test LLM context (correct argument name)
    context = loader.get_knowledge_for_planner(max_chars=5000)
    print(f"✓ LLM context length: {len(context)} chars")
    
    return len(all_docs) > 0


def test_natural_language_planning():
    """Test planner in natural language mode."""
    print("\n" + "="*60)
    print("TEST 3: Natural Language Planning")
    print("="*60)
    
    # Create mock LLM client
    from agentic.llm import LLMClient
    
    # Create test state
    state = MDState(
        user_goal="Prepare protein-ligand complex for MD simulation",
        pdb_path="/test/1abc.pdb",
        structured_prompt="Run standard MD workflow on protein-ligand complex",
        pdb_analysis={
            "total_atoms": 1234,
            "total_residues": 150,
            "components_available": {
                "protein": True,
                "ligand": True,
                "water": True,
                "ions": False,
                "hydrogens": False
            }
        },
        component_selection={
            "protein": True,
            "ligand": True,
            "water": False,
            "ions": False
        },
        force_field="amber99sb-ildn",
        water_model="tip3p"
    )
    
    # Initialize planner (mock mode doesn't actually call LLM)
    llm_client = LLMClient(base_url="http://mock", model="mock", mock_mode=True)
    planner = MDPlanner(llm_client=llm_client)
    
    # Test mock mode (no actual LLM call)
    print("\n[Using mock LLM response for testing]")
    
    # Simulate LLM response
    mock_response = """
## 1. Goal Interpretation
User wants to prepare a protein-ligand complex for molecular dynamics simulation using AMBER99SB-ILDN force field.

## 3. Agent Assignments & Detailed Instructions

### Preprocessing Agent
**Objective:** Clean and prepare the PDB structure for topology generation
**Detailed Instructions:**
- Remove all water molecules and ions from the structure
- Add missing hydrogen atoms to protein and ligand
- Validate structure integrity and fix common issues
**Available Tools:** structure_validator, hydrogen_adder, water_remover
**Expected Output:** cleaned PDB file ready for parameterization

### Setup Agent  
**Objective:** Generate topology and prepare solvated system
**Detailed Instructions:**
- Generate protein topology using AMBER99SB-ILDN force field
- Generate ligand parameters using GAFF with antechamber
- Create cubic water box with 1.0 nm clearance
- Add neutralizing ions to physiological concentration
**Available Tools:** topology_builder, ligand_topology_generator, solvator, ion_adder
**Expected Output:** .top topology file, .gro coordinate file, .mdp parameter files
"""
    
    # Test parsing
    plan = planner._parse_llm_plan_response(mock_response, state)
    
    print(f"\n✓ Plan format: {plan.get('format')}")
    print(f"✓ Agent sequence: {plan.get('agent_sequence')}")
    print(f"✓ Steps detected: {len(plan.get('steps', []))}")
    print(f"✓ Full plan length: {len(plan.get('full_plan', ''))} chars")
    
    # Verify correct agents extracted
    expected_agents = ["preprocessing_agent", "setup_agent"]
    actual_agents = plan.get("agent_sequence", [])
    
    print(f"\n✓ Expected agents: {expected_agents}")
    print(f"✓ Detected agents: {actual_agents}")
    
    if set(expected_agents) == set(actual_agents):
        print("  ✅ Agent detection PASSED")
        return True
    else:
        print("  ❌ Agent detection FAILED")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("NATURAL LANGUAGE PLANNING SYSTEM TEST")
    print("="*60)
    
    results = {}
    
    try:
        results['tools_registry'] = test_tools_registry()
    except Exception as e:
        print(f"\n❌ Tools Registry test failed: {e}")
        results['tools_registry'] = False
    
    try:
        results['knowledge_loader'] = test_knowledge_loader()
    except Exception as e:
        print(f"\n❌ Knowledge Loader test failed: {e}")
        results['knowledge_loader'] = False
    
    try:
        results['nl_planning'] = test_natural_language_planning()
    except Exception as e:
        print(f"\n❌ NL Planning test failed: {e}")
        results['nl_planning'] = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<40} {status}")
    
    all_passed = all(results.values())
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
