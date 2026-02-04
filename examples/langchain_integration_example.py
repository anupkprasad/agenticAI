#!/usr/bin/env python3
"""
Example: Using Preprocessing Tools with LangChain Agent
Demonstrates real LLM tool calling with the improved architecture
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic.preprocess.tools import get_preprocessing_tools, get_tool_metadata


def example_1_direct_llm_binding():
    """
    Example 1: Bind tools directly to LLM for tool calling
    """
    print("=" * 80)
    print("Example 1: Direct LLM Tool Binding")
    print("=" * 80)
    
    # Get tools with full @tool metadata
    tools = get_preprocessing_tools()
    
    print(f"\nStep 1: Get {len(tools)} StructuredTool objects")
    print("These objects contain:")
    print("  • Tool name")
    print("  • Description (from docstring)")
    print("  • Argument schema (from type hints)")
    print("  • Callable function")
    
    print("\nStep 2: Bind to LLM (pseudo-code, requires LangChain setup):")
    print("""
    from langchain_openai import ChatOpenAI
    from agentic.preprocess.tools import get_preprocessing_tools
    
    # Initialize LLM
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    
    # Get preprocessing tools
    tools = get_preprocessing_tools()
    
    # Bind tools to LLM - now LLM can call them!
    llm_with_tools = llm.bind_tools(tools)
    
    # LLM decides which tool(s) to use
    response = llm_with_tools.invoke("Clean protein.pdb and add hydrogens")
    
    # Response will include tool_calls with:
    # - Which tool to call (e.g., "remove_waters")
    # - What arguments to use (e.g., {"pdb_file": "protein.pdb"})
    """)


def example_2_agent_executor():
    """
    Example 2: Create a full LangChain agent with tool calling
    """
    print("\n" + "=" * 80)
    print("Example 2: LangChain Agent with Preprocessing Tools")
    print("=" * 80)
    
    print("\nCreating an agent that can autonomously use preprocessing tools:")
    print("""
    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
    from agentic.preprocess.tools import get_preprocessing_tools
    
    # 1. Setup LLM
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    
    # 2. Get preprocessing tools
    tools = get_preprocessing_tools()
    
    # 3. Create agent prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", '''You are a molecular dynamics preprocessing expert.
        Use the available tools to prepare PDB files for MD simulation.
        
        Always follow this general workflow:
        1. Analyze the PDB structure
        2. Remove water molecules if present
        3. Handle alternate locations
        4. Add missing hydrogens
        5. Validate the final structure
        
        Be smart about which tools to use based on the analysis results.'''),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    
    # 4. Create agent with tools
    agent = create_openai_tools_agent(llm, tools, prompt)
    
    # 5. Create executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=10
    )
    
    # 6. Run agent - it will autonomously call tools!
    result = agent_executor.invoke({
        "input": "Prepare 1abc.pdb for MD simulation. Remove waters and add hydrogens."
    })
    
    print(result["output"])
    """)
    
    print("\nWhat happens:")
    print("  1. LLM reads the user request")
    print("  2. LLM decides to call analyze_pdb first")
    print("  3. Tool executes, returns results to LLM")
    print("  4. LLM sees waters present, calls remove_waters")
    print("  5. Tool executes, returns cleaned file")
    print("  6. LLM calls add_hydrogens on cleaned file")
    print("  7. Tool executes, returns final file")
    print("  8. LLM calls validate_structure to verify")
    print("  9. LLM composes final answer for user")


def example_3_dynamic_metadata():
    """
    Example 3: Use dynamic tool metadata for custom workflows
    """
    print("\n" + "=" * 80)
    print("Example 3: Dynamic Tool Metadata for Custom Workflows")
    print("=" * 80)
    
    # Get all tool metadata
    metadata = get_tool_metadata()
    
    print(f"\nDynamically discovered {len(metadata)} tools:")
    
    # Show we can programmatically work with tool metadata
    print("\nTools that work with PDB files:")
    for name, info in metadata.items():
        if 'pdb_file' in info['args']:
            required_args = [arg for arg, details in info['args'].items() 
                           if details['required']]
            print(f"  • {name}: {required_args}")
    
    print("\n\nBuilding custom LLM prompt with tool list:")
    print("```")
    tools_description = "\n".join([
        f"{i+1}. {name}: {info['description'][:60]}..."
        for i, (name, info) in enumerate(metadata.items())
    ])
    
    custom_prompt = f"""You are a preprocessing expert with these tools:

{tools_description}

Use them to prepare protein.pdb for simulation."""
    
    print(custom_prompt)
    print("```")
    
    print("\n✓ Tool metadata auto-updates when you add/remove tools!")


def example_4_mixing_approaches():
    """
    Example 4: Mix LLM-guided and programmatic tool use
    """
    print("\n" + "=" * 80)
    print("Example 4: Hybrid Approach - LLM Planning + Programmatic Execution")
    print("=" * 80)
    
    print("\nUse LLM for planning, executor for execution:")
    print("""
    from agentic.preprocess.tools import get_preprocessing_tools, PreprocessingToolExecutor
    from langchain_openai import ChatOpenAI
    
    # 1. Use LLM to create intelligent plan
    llm = ChatOpenAI(model="gpt-4")
    tools = get_preprocessing_tools()
    
    # Get tool descriptions for prompt
    tool_list = "\\n".join([f"- {t.name}: {t.description}" for t in tools])
    
    plan_prompt = f'''Create a preprocessing plan for protein.pdb
    
    Available tools:
    {tool_list}
    
    Output as JSON: {{"steps": [{{"tool": "tool_name", "params": {{...}}}}]}}'''
    
    response = llm.invoke(plan_prompt)
    plan = json.loads(response.content)
    
    # 2. Execute plan programmatically (no LLM overhead per step)
    executor = PreprocessingToolExecutor(working_dir="working_dir")
    
    for step in plan['steps']:
        tool_name = step['tool']
        params = step['params']
        result = executor.execute_tool(tool_name, params)
        
        if not result['success']:
            print(f"Error in {tool_name}: {result['error']}")
            break
    
    # Best of both worlds:
    # - LLM intelligence for planning
    # - Direct execution for speed
    # - No token cost for each tool call
    """)


def show_simsetup_tools():
    """
    Show that the same pattern applies to simulation setup tools
    """
    print("\n" + "=" * 80)
    print("Bonus: Simulation Setup Tools Use Same Pattern")
    print("=" * 80)
    
    print("\nThe same improvements apply to simulation setup:")
    print("""
    from agentic.simsetup.tools import get_simulation_setup_tools
    
    # Get all simulation setup tools with @tool metadata
    tools = get_simulation_setup_tools()
    
    # Tools available:
    # - build_topology
    # - generate_ligand_topology  (NEW!)
    # - convert_amber_to_gromacs
    # - build_simulation_box
    # - solvate_system
    # - add_ions
    # - generate_mdp_file
    
    # Same benefits:
    # - Direct LLM binding
    # - Auto-discovered metadata
    # - Clean config.yaml
    """)


def main():
    print("\n" + "=" * 80)
    print("LANGCHAIN INTEGRATION EXAMPLES")
    print("Preprocessing Tools with Real LLM Tool Calling")
    print("=" * 80)
    
    example_1_direct_llm_binding()
    example_2_agent_executor()
    example_3_dynamic_metadata()
    example_4_mixing_approaches()
    show_simsetup_tools()
    
    print("\n" + "=" * 80)
    print("Key Takeaways")
    print("=" * 80)
    print("""
    1. @tool decorators now properly expose tools to LangChain
       → LLM can understand and call tools autonomously
    
    2. Tool metadata auto-extracted from code
       → No config.yaml maintenance, always in sync
    
    3. Multiple usage patterns supported:
       → Full LangChain agent (autonomous tool calling)
       → LLM planning + programmatic execution (hybrid)
       → Pure programmatic (existing code, backward compatible)
    
    4. Adding new tools is trivial:
       → Create @tool function
       → Import in tools.py
       → Auto-discovered and exposed!
    
    5. Applies to all agent modules:
       → preprocessing tools (6 tools)
       → simulation setup tools (7 tools)
       → analysis tools (future)
       → Any new agent module
    """)
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
