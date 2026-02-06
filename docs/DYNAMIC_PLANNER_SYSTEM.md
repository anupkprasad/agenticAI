# Dynamic Tools & Knowledge System for Planner

## Overview

The planner now has **dynamic access** to:
1. **All tools** across the project (auto-discovered from `tools.py` files)
2. **Knowledge base** (research papers, protocols, manuals in `/planner/knowledge`)

This eliminates hardcoded descriptions and makes the system extensible.

## Architecture

### Tools Registry (`tools_registry.py`)
- **Auto-discovers** tools from all agent `tools.py` files
- **Extracts** function names, descriptions, parameters from docstrings
- **Organizes** tools by agent for easy lookup
- **Formats** for LLM consumption

### Knowledge Loader (`knowledge_loader.py`)
- **Loads** markdown, text, JSON, and PDF documents
- **Categorizes** by subdirectory (protocols, force_fields, etc.)
- **Searches** across documents
- **Formats** for LLM context with size limits

### Integration Flow

```
User Goal
    ↓
Supervisor (validates PDB, creates structured prompt)
    ↓
Planner:
  1. Discovers tools from all agents
  2. Loads relevant knowledge
  3. Builds LLM prompt with:
     - User goal + PDB analysis
     - Available tools descriptions
     - Domain knowledge
  4. LLM creates high-level execution plan
    ↓
Field Agent (e.g., Preprocessing):
  1. Receives high-level plan from planner
  2. Uses own tools to create detailed execution
  3. Executes tool calls
```

## Usage

### For Planner Development

```python
from agentic.planner import get_tools_registry, get_knowledge_loader

# Get tools
registry = get_tools_registry()
tools_for_preprocessing = registry.get_tools_for_agent("preprocess")
tools_context = registry.get_tools_for_planner()  # All tools formatted

# Get knowledge
loader = get_knowledge_loader()
protocols = loader.get_knowledge_by_category("protocols")
knowledge_context = loader.get_knowledge_for_planner(max_chars=5000)
```

### Adding New Tools

Simply add functions to any agent's `tools.py`:

```python
# agentic/newagent/tools.py

def my_new_tool(input_file: str, option: bool = False) -> Dict[str, Any]:
    """
    Brief description of what this tool does.
    
    Args:
        input_file: Path to input file
        option: Optional flag for special behavior
        
    Returns:
        Dict with results
    """
    # Implementation
    pass
```

The planner will **automatically discover** it on next initialization.

### Adding Knowledge Documents

Place documents in `/agentic/planner/knowledge/`:

```
knowledge/
├── protocols/
│   └── my_protocol.md
├── force_fields/
│   └── new_forcefield.md
└── tools_manuals/
    └── tool_guide.txt
```

The planner will **automatically load** them.

## Knowledge Base Organization

### `/md_fundamentals`
- MD theory and methods
- Sampling techniques
- Statistical mechanics

### `/force_fields`
- AMBER99SB-ILDN parameters
- Water model documentation
- Parameterization guides

### `/protocols`
- Standard MD workflows
- Best practices
- Equilibration protocols

### `/tools_manuals`
- GROMACS command references
- VMD scripting
- Software documentation

## Benefits

1. **Dynamic**: No hardcoded tool descriptions
2. **Extensible**: Add tools/knowledge without code changes
3. **Maintainable**: Single source of truth (docstrings)
4. **Intelligent**: LLM has full context for planning
5. **Scalable**: Easy to add new agents and knowledge

## Testing

Run the test script:

```bash
python tests/test_dynamic_planner.py
```

This will:
- Discover all tools
- Load all knowledge
- Show formatted output for LLM
- Test search functionality

## Implementation Details

### Tools Discovery Process
1. Scan `agentic/` for agent directories
2. Load each `tools.py` file dynamically
3. Extract functions with proper docstrings
4. Parse docstring for description and parameters
5. Store in registry with agent context

### Knowledge Loading Process
1. Scan `/knowledge/` recursively
2. Load files by extension (.md, .txt, .json, .pdf)
3. Extract text content
4. Categorize by subdirectory
5. Enable search and filtering

### LLM Prompt Construction
```python
# Planner builds context
tools_context = registry.get_tools_for_planner()
knowledge_context = loader.get_knowledge_for_planner(max_chars=8000)

prompt = f"""
{user_goal}
{pdb_analysis}

Available Tools:
{tools_context}

Domain Knowledge:
{knowledge_context}

Create execution plan...
"""
```

## Future Enhancements

- [ ] Tool usage analytics
- [ ] Knowledge relevance ranking
- [ ] Semantic search across knowledge base
- [ ] Tool dependency graph
- [ ] Version tracking for tools and knowledge
- [ ] Caching for faster initialization

## Migration Notes

**Old System**: Hardcoded tool descriptions in YAML
**New System**: Dynamic discovery from code

All existing functionality preserved with fallback to template-based planning if LLM unavailable.
