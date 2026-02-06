# Knowledge Base Directory

This directory contains domain knowledge for the planner agent to reference during execution planning.

## Structure

### `/md_fundamentals`
Research papers and documentation on molecular dynamics fundamentals:
- MD theory and methods
- Sampling techniques
- Statistical mechanics principles
- Simulation best practices

### `/force_fields`
Information about force fields:
- AMBER99SB-ILDN parameters and usage
- CHARMM force fields
- OPLS-AA documentation
- Small molecule parameterization guides

### `/protocols`
Standard MD protocols and workflows:
- Protein preparation protocols
- Membrane protein setup
- Ligand binding simulations
- Free energy calculations
- Enhanced sampling methods

### `/tools_manuals`
Software tool manuals and command references:
- GROMACS commands and usage
- VMD scripting guides
- Analysis tool documentation
- AmberTools manuals

## Usage

The planner agent automatically loads all documents in this directory structure and uses them as context when creating execution plans. Documents can be in:
- Markdown (.md)
- Plain text (.txt)
- JSON (.json) for structured data
- PDF (.pdf) for papers and manuals

## Adding Knowledge

1. Place documents in the appropriate subdirectory
2. Use descriptive filenames (e.g., `amber99sb_parameters.md`)
3. Keep documents focused and well-organized
4. The planner will automatically discover and load new files

## Examples

```
knowledge/
├── md_fundamentals/
│   ├── md_theory_basics.md
│   └── integration_algorithms.txt
├── force_fields/
│   ├── amber99sb_ildn.md
│   └── tip3p_water_model.md
├── protocols/
│   ├── protein_preparation_workflow.md
│   └── equilibration_protocol.md
└── tools_manuals/
    ├── gromacs_pdb2gmx.md
    └── vmd_selections.txt
```

## Notes

- The planner has a context limit, so keep documents concise
- Focus on actionable information and practical guidance
- Cross-reference related documents when helpful
- Update this README when adding new categories
