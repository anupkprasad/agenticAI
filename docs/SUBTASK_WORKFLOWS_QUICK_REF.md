# Subtask-Specific Workflows - Quick Reference

## Quick Start Examples

### 1. Analysis-Only Workflow (Trajectory Analysis)

```bash
python run_agenticAIWork.py \
  --goal "The simulation production is done with output in working_dir/hpc. \
          Please dont preprocess, do not setup simulation and do not submit job. \
          Only use the analysis agent for trajectory analysis for RMSF calculation \
          of trajectory working_dir/hpc/md.xtc with topology working_dir/hpc/topol.tpr" \
  --use-llm \
  --no-human-loop
```

**What happens:**
- ✅ Supervisor skips PDB file validation
- ✅ Supervisor extracts trajectory paths (md.xtc, topol.tpr)
- ✅ Planner creates plan with ONLY Analysis Agent
- ✅ Analysis Agent calculates RMSF
- ⏭️ Preprocessing, Setup, HPC agents are skipped

**Inputs needed:**
- Trajectory file path (e.g., `.xtc`, `.trr`)
- Topology file path (e.g., `.tpr`, `.gro`)
- Energy file (optional, e.g., `.edr`)

**Outputs generated:**
- RMSF values and plots
- Analysis report
- Visualization files

---

### 2. Setup-Only Workflow (Topology Generation)

```bash
python run_agenticAIWork.py \
  --goal "Set up the MD simulation for my protein in working_dir/protein.pdb. \
          I need topology and coordinate files. \
          Setup only - please do not submit to HPC" \
  --force-field amber99sb-ildn \
  --water-model tip3p \
  --use-llm \
  --no-human-loop
```

**What happens:**
- ✅ Supervisor validates PDB file
- ✅ Supervisor analyzes protein structure
- ✅ Planner creates plan with Preprocessing + Setup Agents
- ✅ Setup Agent generates:
  - Topology file (.top)
  - Coordinate file (.gro)
  - MDP files (minimization, NVT, NPT, MD)
- ⏭️ HPC and Analysis agents are skipped

**Inputs needed:**
- PDB file path
- Force field type (default: amber99sb-ildn)
- Water model (default: tip3p)

**Outputs generated:**
- Topology file
- Coordinate files
- Parameter files (MDP)
- Setup report

---

### 3. Preprocess-Only Workflow (Structure Cleaning)

```bash
python run_agenticAIWork.py \
  --goal "Preprocess my protein structure from working_dir/raw.pdb. \
          I need to remove water molecules and add missing hydrogens. \
          Only preprocessing - no setup or simulation" \
  --use-llm \
  --no-human-loop
```

**What happens:**
- ✅ Supervisor validates raw PDB file
- ✅ Supervisor analyzes structure
- ✅ Planner creates plan with ONLY Preprocessing Agent
- ✅ Preprocessing Agent:
  - Removes water molecules
  - Adds missing hydrogens
  - Validates structure
  - Outputs cleaned PDB
- ⏭️ Setup, HPC, Analysis agents are skipped

**Inputs needed:**
- Raw PDB file path

**Outputs generated:**
- Cleaned PDB file
- Hydrogen-added structure
- Validation report
- Statistics on cleaning operations

---

### 4. Full Pipeline Workflow (Traditional)

```bash
python run_agenticAIWork.py \
  --goal "Run complete MD simulation of working_dir/protein.pdb. \
          Simulate for 1 nanosecond and analyze RMSD and RMSF" \
  --force-field amber99sb-ildn \
  --water-model tip3p \
  --use-llm \
  --no-human-loop
```

**What happens:**
- ✅ Supervisor validates PDB file
- ✅ Supervisor analyzes protein structure
- ✅ Planner creates full pipeline plan
- ✅ All agents executed in sequence:
  1. Preprocessing Agent - cleans structure
  2. Setup Agent - generates topology
  3. HPC Agent - submits SLURM job
  4. Analysis Agent - calculates metrics
- ✅ Full end-to-end molecular dynamics workflow

**Inputs needed:**
- PDB file path
- Simulation duration (detected from goal)
- Force field and water model

**Outputs generated:**
- Cleaned PDB
- Topology and coordinates
- Simulation trajectory
- Analysis results (RMSD, RMSF)
- Visualizations and report

---

## Pattern Detection Guide

The system automatically detects subtask types from natural language. Here are the patterns:

### ✅ Analysis-Only Detection

These phrases trigger analysis-only mode:
```
"only analysis" / "analysis only"
"analyze trajectory" 
"trajectory analysis"
"RMSD calculation" / "RMSF calculation"
+ explicit exclusions like:
  "dont preprocess" / "do not setup" / "dont submit"
  "no preprocessing" / "skip setup"
```

### ✅ Setup-Only Detection

```
"setup only" / "only setup"
"topology generation only"
"parameter generation only"
+ explicit HPC exclusion like:
  "no HPC" / "don't submit" / "skip HPC"
  "without HPC" / "locally only"
```

### ✅ Preprocess-Only Detection

```
"only preprocessing" / "preprocess only"
"cleaning only" / "only clean"
"structure cleaning"
+ explicit setup exclusion like:
  "no setup" / "dont setup" / "nothing else"
  "without setup"
```

### ✅ Full Pipeline (Default)

If none of the above patterns match:
```
"Run simulation"
"Complete workflow"
"Preprocess, setup, and simulate"
"End-to-end MD"
```

---

## Input Requirements by Subtask

| Subtask | PDB File | PDB Analysis | Trajectory | Topology |
|---------|----------|--------------|------------|----------|
| **Analysis-only** | ❌ No | ❌ No | ✅ Yes | ✅ Yes |
| **Setup-only** | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Preprocess-only** | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Full pipeline** | ✅ Yes | ✅ Yes | ❌ No | ❌ No |

---

## File Path Examples

### For Analysis-Only Tasks
```bash
# Trajectory files
--goal "... working_dir/hpc/production.xtc ..."
--goal "... results/trajectory/traj.trr ..."
--goal "... ./data/md.dcd ..."

# Topology files  
--goal "... working_dir/hpc/topol.tpr ..."
--goal "... results/system.gro ..."
--goal "... ./coordinates/topology.top ..."

# Energy files
--goal "... working_dir/hpc/energy.edr ..."
--goal "... results/ener.edr ..."
```

### For Setup/Preprocess Tasks
```bash
# Input PDB files
--goal "... working_dir/protein.pdb ..."
--goal "... ./structures/myprotein.pdb ..."
--goal "... ~/projects/md/input.pdb ..."
```

---

## Common Variations

```bash
# Variation 1: Multiple analysis calculations
--goal "Analyze trajectory working_dir/md.xtc with topology working_dir/topol.tpr. \
        Calculate RMSD, RMSF, radius of gyration. Energy analysis too. \
        No preprocessing, no setup, only analysis"

# Variation 2: Setup with specific selections
--goal "Setup simulation for protein chain A from working_dir/complex.pdb. \
        Keep water molecules, add ions. \
        Setup only - no HPC submission"

# Variation 3: Quick preprocessing
--goal "Quickly clean and prepare working_dir/raw.pdb. \
        Remove ligand and ions, keep only protein. \
        Preprocessing step only"

# Variation 4: Full pipeline with detailed requirements
--goal "Complete MD workflow for working_dir/protein.pdb: \
        preprocessing, topology generation, 100ns simulation, \
        then analyze RMSD throughout trajectory"
```

---

## Checking Subtask Detection

To verify what subtask type was detected, check the logs:

```bash
# Look for lines like:
# "SUPERVISOR: Detected subtask type: analysis_only"
# "SUPERVISOR: Detected subtask type: setup_only"
# "SUPERVISOR: Detected subtask type: None" (full pipeline)
```

Or in the agent conversation log:
```
tail -f agent_conversation.log | grep "subtask_type"
```

---

## Troubleshooting

### Q: Analysis-only not detected
**A:** Add explicit exclusion phrases:
- ❌ "Analyze my trajectory"
- ✅ "Only analyze trajectory. No preprocessing or setup."

### Q: Need to include preprocessing in setup-only
**A:** Preprocessing is included automatically when needed. To skip it:
- Provide already-cleaned PDB
- Mention "cleaned" or "preprocessed" in goal

### Q: Trajectory paths not found
**A:** Use full or relative paths:
- ✅ `working_dir/hpc/md.xtc`
- ✅ `./results/trajectory.xtc`
- ❌ `md.xtc` (bare filename)

### Q: Want mixed subtasks?
**A:** Not directly supported. Two options:
1. Run separate commands for different subtasks
2. Use full pipeline to handle everything in sequence

---

## Performance Notes

- **Analysis-only**: Fastest (no topology generation)
- **Setup-only**: Fast (no HPC simulation)
- **Preprocess-only**: Medium (structure analysis + cleaning)
- **Full pipeline**: Slowest (all processing + HPC job)

---

## See Also

- [Detailed Implementation Guide](SUBTASK_WORKFLOWS.md)
- [Main README](../README.md)
- [Architecture Overview](ARCHITECTURE_V2.md)
