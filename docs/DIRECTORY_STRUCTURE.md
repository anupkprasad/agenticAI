# Directory Structure and File Management

## Hardcoded Directory Rules

All agents now follow strict directory isolation to prevent path confusion:

### Directory Structure
```
working_dir/
├── preprocess/          # Preprocessing Agent domain
│   ├── input.pdb       # Original input
│   ├── protein_h.pdb   # Processed protein
│   ├── ATP_h.pdb       # Processed ligand
│   └── MG.pdb          # Ions
│
└── simsetup/           # Simulation Setup Agent domain
    ├── protein.gro     # Copied from preprocess
    ├── ATP.gro         # Converted from preprocess
    ├── complex.gro     # Merged structure
    ├── topol.top       # Topology
    └── mdp/            # MDP files
```

## Agent Rules

### Preprocessing Agent (`agentic/preprocess/`)

**HARDCODED RULES:**
1. **ALL inputs** read from `working_dir/preprocess/`
2. **ALL outputs** written to `working_dir/preprocess/`
3. LLM-generated output paths are **STRIPPED** before execution
4. Overrides any `output_dir`, `output_file`, `protein_output`, `ligand_output`, `ion_output` in plans

**Implementation:**
- `preprocessing_agent.py` lines 555-560: Strips unwanted path parameters
- `preprocessing_agent.py` lines 575-595: Forces all outputs to `self.tool_executor.working_dir`
- `config.yaml` planning prompt: Instructs LLM to NOT specify output paths

### Simulation Setup Agent (`agentic/simsetup/`)

**HARDCODED RULES:**
1. **Copies inputs** from `working_dir/preprocess/` to `working_dir/simsetup/`
2. **ALL outputs** written to `working_dir/simsetup/`
3. All GROMACS commands use absolute paths within simsetup directory

**Implementation:**
- `setup_agent.py` lines 101-130: `_copy_preprocessed_files()` copies from preprocess
- `setup_agent.py` lines 389-468: All tools use `os.path.join(simsetup_dir, ...)` for outputs
- `config.yaml`: Declares `working_directory` and `input_from` directories

## File Flow

### Example: Protein + Ligand Workflow

```
1. PREPROCESSING (working_dir/preprocess/)
   Input:  working_dir/preprocess/complex.pdb
   
   Actions:
   - separate_complex_components() → protein.pdb, ATP.pdb, MG.pdb
   - add_hydrogens() → protein_h.pdb, ATP_h.pdb
   
   Outputs: ALL in working_dir/preprocess/
   
2. SIMULATION SETUP (working_dir/simsetup/)
   Copy from preprocess:
   - protein_h.pdb → working_dir/simsetup/protein_h.pdb
   - ATP_h.pdb → working_dir/simsetup/ATP_h.pdb
   - MG.pdb → working_dir/simsetup/MG.pdb
   
   Actions:
   - convert_pdb_to_gro() → protein.gro, ATP.gro, MG.gro
   - gmx pdb2gmx → protein_processed.gro, topol.top
   - merge_gro_files() → complex.gro
   - gmx editconf → boxed.gro
   - gmx solvate → solvated.gro
   - gmx genion → system.gro
   
   Outputs: ALL in working_dir/simsetup/
```

## LLM Planning Changes

### Before (❌ Problem)
LLM could generate plans like:
```json
{
  "tool_name": "separate_complex_components",
  "tool_params": {
    "pdb_file": "working_dir/preprocess/input.pdb",
    "output_dir": "working_dir/separated/",  ❌ WRONG!
    "protein_output": "working_dir/output/protein.pdb"  ❌ WRONG!
  }
}
```

### After (✅ Solution)
LLM generates minimal plans:
```json
{
  "tool_name": "separate_complex_components",
  "tool_params": {
    "pdb_file": "input.pdb"  ✅ Only input, system handles outputs
  }
}
```

**System automatically:**
1. Strips any `output_dir`, `output_file`, etc. from plan
2. Forces all outputs to agent's directory
3. Logs actual paths used (after override)

## Config Updates

### `agentic/preprocess/config.yaml`
Added to planning prompt:
```yaml
**CRITICAL OUTPUT DIRECTORY RULES:**
- ALL preprocessing outputs MUST go to working_dir/preprocess/
- DO NOT specify output_dir, output_file, protein_output, ligand_output, or ion_output
- The system will automatically handle all output paths
- Only specify pdb_file for input files
```

### `agentic/simsetup/config.yaml`
Added directory declarations:
```yaml
agent:
  working_directory: "working_dir/simsetup"
  input_from: "working_dir/preprocess"
```

## Code Changes Summary

### `agentic/preprocess/preprocessing_agent.py`
```python
# Line 555-560: Strip LLM-generated output paths
for unwanted_key in ["output_dir", "output_file", "protein_output", "ligand_output", "ion_output"]:
    if unwanted_key in tool_params:
        del tool_params[unwanted_key]

# Line 586: Force output_dir
tool_params["output_dir"] = str(self.tool_executor.working_dir)

# Line 588-593: Force explicit output paths
tool_params["protein_output"] = str(Path(self.tool_executor.working_dir) / f"{base_name}_protein.pdb")
tool_params["ligand_output"] = str(Path(self.tool_executor.working_dir) / f"{base_name}_ligand.pdb")
```

### `agentic/simsetup/setup_agent.py`
```python
# Line 101-130: Copy from preprocess directory
def _copy_preprocessed_files(self, state: MDState, simsetup_dir: str):
    preprocess_dir = state.get("preprocess_directory")
    # Copy cleaned_pdb, topology, etc.
    
# Line 395: Force output to simsetup directory
output_file=os.path.join(simsetup_dir, "processed.gro")
```

## Testing

To verify directory isolation:
```bash
# Run preprocessing
python run_agenticAIWork.py --goal "Preprocess PDB" --pdb test.pdb

# Check outputs are in preprocess/
ls -la working_dir/preprocess/

# Run simsetup
python run_agenticAIWork.py --goal "Setup simulation" --pdb test.pdb

# Check outputs are in simsetup/
ls -la working_dir/simsetup/
```

## Benefits

1. **No Path Confusion**: Each agent has its own directory
2. **LLM-Proof**: System overrides any incorrect paths from LLM
3. **Clean Separation**: Preprocessing and setup artifacts isolated
4. **Easy Debugging**: Know exactly where to find files
5. **Reproducible**: Consistent structure across runs

## Migration Notes

If you have existing code that specifies output paths:
- ✅ Keep input paths (pdb_file, etc.)
- ❌ Remove output_dir, output_file parameters
- ✅ System will auto-generate correct paths
