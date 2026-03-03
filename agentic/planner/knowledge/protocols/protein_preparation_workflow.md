# Standard Protein Preparation Protocol

## Overview
This protocol outlines the standard steps for preparing a protein structure for MD simulation.

## Step-by-Step Workflow

### 1. PDB Cleaning
**Goal**: Obtain clean protein structure
- Remove water molecules (unless specifically required)
- Remove heteroatoms (ligands, ions) if doing protein-only simulation
- Keep ligands/ions if studying protein-ligand interactions
- Extract specific chains if needed

**Tools**: `separate_complex_components`, MDAnalysis selection

### 2. Hydrogen Addition
**Goal**: Add missing hydrogen atoms
- Use `reduce` for proteins (handles flips, protonation states)
- pH 7.0 default for neutral conditions
- Alternative: `pdb2pqr` for pH-dependent protonation

**Important**: AMBER force fields expect all hydrogens present

### 3. Topology Generation
**Goal**: Create force field topology
- Use `gmx pdb2gmx` with AMBER99SB-ILDN
- Select TIP3P water model for compatibility
- Generates: `.gro` (coordinates), `.top` (topology)

**Command**:
```bash
gmx pdb2gmx -f protein_h.pdb -o protein.gro -p topol.top \\
    -ff amber99sb-ildn -water tip3p -ignh
```

### 4. Solvation
**Goal**: Add explicit water box
- Define box with `gmx editconf` (1.0 nm minimum distance)
- Add water with `gmx solvate`
- Box type: cubic or dodecahedron

**Commands**:
```bash
gmx editconf -f protein.gro -o box.gro -d 1.0 -bt cubic
gmx solvate -cp box.gro -cs spc216.gro -o solvated.gro -p topol.top
```

### 5. Ion Addition
**Goal**: Neutralize system and add physiological salt
- Neutralize with counter-ions (Na+/Cl-)
- Add 0.15 M NaCl for physiological conditions
- Use `gmx genion` with ion placement MDP

**Commands**:
```bash
gmx grompp -f ions.mdp -c solvated.gro -p topol.top -o ions.tpr
gmx genion -s ions.tpr -o ionized.gro -p topol.top -pname NA -nname CL -neutral -conc 0.15
```

### 6. Energy Minimization
**Goal**: Remove bad contacts and relax structure
- Steepest descent algorithm
- Convergence: Fmax < 1000 kJ/mol/nm
- Typical: 5000-50000 steps

**Critical**: Always minimize before MD!

### 7. Equilibration
**Goal**: Gradually heat and equilibrate system

**Phase 1 - NVT (100 ps)**:
- Constant Volume and Temperature
- Heat from 0 to 300 K
- Position restraints on protein

**Phase 2 - NPT (100 ps)**:
- Constant Pressure and Temperature
- Equilibrate density
- Position restraints on protein

### 8. Production MD
**Goal**: Collect trajectory data
- NPT ensemble
- No position restraints
- Duration: depends on research question (typically 100-500 ns)

## Common Mistakes to Avoid
1. Skipping energy minimization
2. Not adding hydrogens before topology generation
3. Insufficient equilibration time
4. Box too small (periodic boundary artifacts)
5. Wrong force field for water model

## Quality Checks
- Check for negative charges in topology (should be neutral or close)
- Monitor energy during minimization (should decrease)
- Check temperature and pressure during equilibration (should stabilize)
- Verify RMSD plateaus during equilibration
