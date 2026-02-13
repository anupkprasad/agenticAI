# Simulation Setup: Component-Based Workflow

## Overview

The simulation setup agent now supports a modular, component-based workflow that mirrors your existing `sim_setup.py` approach. The system can handle:

1. **Protein-only** systems
2. **Protein + Ligand** systems (ATP, GTP, ADP, etc.)
3. **Protein + Ligand + Ion** systems (MG, CA, ZN, MN, FE)

## Architecture

### Modular Tools

All tools are in `src/simsetup/` and exposed via `@tool` decorators for LLM agents:

#### 1. **PDB to GRO Converter** (`pdb_to_gro_converter.py`)
- `convert_pdb_to_gro()` - Convert single PDB to GRO
- `split_complex_pdb_to_gro()` - Split complex into components

#### 2. **GRO Merger** (`gro_merger.py`)
- `merge_gro_files()` - Merge multiple GRO files with proper numbering

#### 3. **Topology Editor** (`topology_editor.py`)
- `edit_topology_file()` - Add ligand/ion entries to topol.top
- Prevents duplicates, adds POSRES_LIG support

#### 4. **Atom Name Mapper** (`atom_name_mapper.py`)
- `map_ligand_atom_names()` - Map AF3/PDB names to force field names
- Handles reordering for topology compatibility

#### 5. **MDP Generator** (`mdp_generator.py`)
- `generate_mdp_files()` - Create adaptive MDP files
- Auto-detects system type (protein/protein+ligand/protein+ligand+ion)
- Force field aware (CHARMM vs AMBER cutoffs)

#### 6. **Ligand Topology Generator** (`ligand_topology.py`)
- `generate_ligand_parameters()` - Run acpype/antechamber
- Generates GAFF/GAFF2 parameters for small molecules

#### 7. **System Builder** (`system_builder.py`)
- `build_simulation_system()` - High-level orchestrator
- Runs complete workflow from components to final system

## Workflow Comparison

### Your Original Workflow (sim_setup.py)
```
1. Copy ligand .itp and force field directory
2. pdbToGr0() - Convert PDB to GRO (with PyRosetta for H)
3. gmx pdb2gmx - Generate protein topology
4. mergeGroFiles() - Merge protein + ligand + ion
5. edit_topology() - Add ligand/ion to topol.top
6. Source simSetupProtLigIon.sh:
   - gmx editconf (box)
   - gmx solvate (water)
   - gmx genion (ions)
   - gmx grompp (TPR)
```

### New Modular Workflow
```
1. [Optional] map_ligand_atom_names() - Fix atom names if needed
2. convert_pdb_to_gro() - Convert components separately
3. gmx pdb2gmx - Generate protein topology
4. merge_gro_files() - Merge all components
5. edit_topology_file() - Update topology
6. gmx editconf - Build box
7. gmx solvate - Add water
8. gmx genion - Add neutralizing ions + salt
9. generate_mdp_files() - Create all MDP files
```

OR use the orchestrator:
```
build_simulation_system(
    protein_pdb, ligand_pdb, ion_pdb,
    ligand_itp, output_dir
)
```

## Key Improvements

### 1. No PyRosetta Dependency
- Preprocessor now adds hydrogens
- Directly use PDB files from preprocessing

### 2. System GROMACS Force Fields
- Uses standard GROMACS force fields by default
- No need to copy `amber99sb-ildn.ff/` directory
- Custom force fields still supported if needed

### 3. All Metal Ions Supported
- MG, CA, ZN, MN, FE (Fe3+), FE2 (Fe2+)
- Automatic charge detection
- Proper residue numbering

### 4. Automatic Ligand Parameterization
- Generates `.itp` files with acpype/antechamber if missing
- GAFF/GAFF2 support
- AM1-BCC charges

### 5. Adaptive MDP Files
- Temperature coupling groups adapt to system composition
  - Protein-only: `tc-grps = System`
  - Complex: `tc-grps = Protein Non-Protein`
- Position restraints adapt to presence of ligands
  - Protein: `-DPOSRES`
  - Protein+Ligand: `-DPOSRES -DPOSRES_LIG`
- Force field specific parameters
  - CHARMM: `DispCorr = no`, `rvdw = 1.2`
  - AMBER: `DispCorr = EnerPres`, `rvdw = 1.0`

## Usage Examples

### Example 1: Protein Only
```python
from agentic.simsetup.tools import build_simulation_system

result = build_simulation_system.func(
    protein_pdb="working_dir/preprocess/protein_h.pdb",
    output_dir="working_dir/simsetup",
    force_field="amber99sb-ildn",
    water_model="tip3p"
)
```

### Example 2: Protein + ATP + MG
```python
result = build_simulation_system.func(
    protein_pdb="working_dir/preprocess/protein_h.pdb",
    ligand_pdb="working_dir/preprocess/ATP_h.pdb",
    ion_pdb="working_dir/preprocess/MG.pdb",
    ligand_resname="ATP",
    ligand_itp="ATP.itp",  # Will generate if missing
    ion_resname="MG",
    output_dir="working_dir/simsetup",
    box_distance=1.2,
    ion_concentration=0.15
)
```

### Example 3: Component-by-Component
```python
from agentic.simsetup.tools import (
    convert_pdb_to_gro,
    merge_gro_files,
    edit_topology_file
)

# Step 1: Convert PDB to GRO
convert_pdb_to_gro.func(
    "protein_h.pdb", "protein.gro", "protein"
)

# Step 2: Run gmx pdb2gmx (external)
# gmx pdb2gmx -f protein.gro -o protein_processed.gro ...

# Step 3: Merge components
merge_gro_files.func(
    ["protein_processed.gro", "ATP.gro", "MG.gro"],
    "complex.gro"
)

# Step 4: Edit topology
edit_topology_file.func(
    "topol.top",
    ligand_itp="ATP.itp",
    ligand_resname="ATP",
    ion_resname="MG",
    ion_count=2
)
```

## Agent Integration

All tools are registered in `agentic/simsetup/tools.py`:

```python
from agentic.simsetup.tools import get_simulation_setup_tools

# Get all tools for LLM binding
tools = get_simulation_setup_tools()
# Returns: [build_topology, generate_ligand_parameters, ..., 
#           build_simulation_system, merge_gro_files, ...]

# Tools available to agent:
# - build_simulation_system (high-level orchestrator)
# - convert_pdb_to_gro
# - merge_gro_files
# - edit_topology_file
# - map_ligand_atom_names
# - generate_mdp_files
# - generate_ligand_parameters
# ... (all existing tools)
```

## File Structure

```
working_dir/
├── preprocess/              # From preprocessing agent
│   ├── protein_h.pdb       # Protein with hydrogens
│   ├── ATP_h.pdb           # Ligand with hydrogens
│   └── MG.pdb              # Metal ions
│
└── simsetup/               # Simulation setup outputs
    ├── protein.gro
    ├── ATP.gro
    ├── MG.gro
    ├── protein_processed.gro
    ├── complex.gro
    ├── boxed.gro
    ├── solvated.gro
    ├── system.gro          # Final system
    ├── topol.top           # Complete topology
    ├── posre.itp           # Protein restraints
    ├── ATP.itp             # Ligand topology
    ├── posre_ATP.itp       # Ligand restraints
    ├── ions.tpr            # For ion addition
    └── mdp/                # MDP files
        ├── ions.mdp
        ├── minim.mdp
        ├── nvt.mdp
        ├── npt.mdp
        └── md.mdp
```

## Configuration

Update `agentic/simsetup/config.yaml` to guide the agent:

```yaml
agent:
  capabilities:
    - "Build complete simulation systems from component PDB files"
    - "Handle protein-only, protein+ligand, protein+ligand+ion systems"
    - "Generate adaptive MDP files based on system composition"
    - "Auto-parameterize ligands with acpype/antechamber"
    
tools:
  build_simulation_system:
    description: "High-level orchestrator for complete system setup"
    supported_systems:
      - "protein-only"
      - "protein+ligand"
      - "protein+ligand+ion"
    supported_ions:
      - "MG"  # Magnesium
      - "CA"  # Calcium
      - "ZN"  # Zinc
      - "MN"  # Manganese
      - "FE"  # Iron(III)
      - "FE2" # Iron(II)
```

## Next Steps

1. **Test with Real Data**: Run test_system_builder.py with actual PDB files
2. **Generate Ligand .itp Files**: Create ATP.itp with acpype if needed
3. **Atom Name Mapping**: Create mapping files for AF3 ligands if necessary
4. **Agent Prompts**: Update simsetup agent prompts to use new tools
5. **Integration Test**: Run full preprocessing → simsetup workflow

## Migration from sim_setup.py

To migrate your existing workflow:

1. **Remove PyRosetta calls**: Preprocessor adds hydrogens now
2. **Use system force fields**: No need to copy amber99sb-ildn.ff/
3. **Replace shell script**: Use `build_simulation_system()` instead of sourcing `simSetupProtLigIon.sh`
4. **Update paths**: Use `working_dir/preprocess/` and `working_dir/simsetup/`
5. **Ligand .itp files**: Place in `working_dir/simsetup/` or let tool generate them

## Troubleshooting

### Issue: "Ligand atoms not matching topology"
**Solution**: Use `map_ligand_atom_names()` to fix atom name mismatches

### Issue: "Force field not found"
**Solution**: Verify GROMACS installation has the force field, or provide custom directory

### Issue: "Ion residues duplicated"
**Solution**: PDB converter now auto-fixes residue numbering for ions

### Issue: "Position restraints not working"
**Solution**: Check that ligand_itp and posre_*.itp files exist, topology editor adds #ifdef POSRES_LIG
