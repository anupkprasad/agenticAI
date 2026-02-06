"""
Test script for dynamic tools registry and knowledge loader

Demonstrates how the planner discovers tools and loads knowledge dynamically.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agentic.planner import get_tools_registry, get_knowledge_loader


def test_tools_registry():
    """Test the tools registry system."""
    print("=" * 80)
    print("TESTING TOOLS REGISTRY")
    print("=" * 80)
    
    # Get the registry
    registry = get_tools_registry()
    
    # Print summary
    print(f"\nDiscovered {len(registry.tools)} tools across {len(registry.tools_by_agent)} agents\n")
    
    # Show tools by agent
    for agent_name, tools in sorted(registry.tools_by_agent.items()):
        print(f"\n{agent_name.upper()} Agent - {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool['name']}")
            print(f"    {tool['description'][:100]}...")
    
    # Show formatted output for planner
    print("\n" + "=" * 80)
    print("FORMATTED FOR PLANNER LLM:")
    print("=" * 80)
    planner_context = registry.get_tools_for_planner(agent_name="preprocess")
    print(planner_context[:500] + "...\n")


def test_knowledge_loader():
    """Test the knowledge loader system."""
    print("\n" + "=" * 80)
    print("TESTING KNOWLEDGE LOADER")
    print("=" * 80)
    
    # Get the loader
    loader = get_knowledge_loader()
    
    # Print summary
    print(f"\nLoaded {len(loader.knowledge_docs)} documents across {len(loader.knowledge_by_category)} categories\n")
    
    # Show documents by category
    for category in loader.get_categories():
        docs = loader.get_knowledge_by_category(category)
        print(f"\n{category.upper()} - {len(docs)} documents:")
        for doc in docs:
            print(f"  - {doc['name']} ({doc['size']} chars)")
    
    # Search functionality
    print("\n" + "=" * 80)
    print("SEARCH TEST: 'AMBER'")
    print("=" * 80)
    results = loader.search_knowledge("AMBER")
    print(f"Found {len(results)} matching documents:")
    for doc in results:
        print(f"  - {doc['category']}.{doc['name']}")
    
    # Show formatted output for planner
    print("\n" + "=" * 80)
    print("FORMATTED FOR PLANNER LLM:")
    print("=" * 80)
    planner_context = loader.get_knowledge_for_planner(max_chars=1000)
    print(planner_context[:800] + "...\n")


def test_integration():
    """Test integration of both systems."""
    print("\n" + "=" * 80)
    print("INTEGRATION TEST")
    print("=" * 80)
    
    registry = get_tools_registry()
    loader = get_knowledge_loader()
    
    print(f"\nPlanner has access to:")
    print(f"  - {len(registry.tools)} tools from {len(registry.tools_by_agent)} agents")
    print(f"  - {len(loader.knowledge_docs)} knowledge documents")
    
    # Simulate what planner would get
    print("\n" + "-" * 80)
    print("Sample context for preprocessing planning:")
    print("-" * 80)
    
    # Tools for preprocessing agent
    print("\n### Available Tools ###")
    tools = registry.get_tools_for_planner(agent_name="preprocess")
    print(tools[:500] if tools else "No preprocessing tools found")
    
    # Relevant knowledge
    print("\n### Relevant Knowledge ###")
    knowledge = loader.get_knowledge_for_planner(category="protocols", max_chars=800)
    print(knowledge[:500] if knowledge else "No protocol knowledge found")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        test_tools_registry()
        test_knowledge_loader()
        test_integration()
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
