# AMBER99SB-ILDN Force Field

## Overview
AMBER99SB-ILDN is an improvement of the AMBER99SB force field with optimized side-chain torsion potentials for isoleucine, leucine, aspartic acid, and asparagine.

## Key Features
- **Optimized for**: Protein simulations
- **Improvements**: Better sampling of side-chain rotamers
- **Compatible with**: TIP3P, TIP4P-Ew water models
- **GROMACS name**: `amber99sb-ildn`

## Usage in GROMACS

### pdb2gmx command
```bash
gmx pdb2gmx -f input.pdb -o output.gro -p topol.top -ff amber99sb-ildn -water tip3p
```

### When to Use
- General protein simulations
- Protein-ligand complexes
- Multi-domain proteins
- Membrane proteins (with appropriate lipid parameters)

### When NOT to Use
- Intrinsically disordered proteins (consider CHARMM36m)
- RNA/DNA (use ff99bsc0 corrections)
- Small molecules only (parameterize separately)

## Common Parameters
- **Temperature**: 300 K typical
- **Pressure**: 1 bar
- **Timestep**: 2 fs (with constraints)
- **Cutoffs**: 1.0-1.2 nm for non-bonded interactions

## References
- Lindorff-Larsen et al., Proteins (2010) 78:1950-1958
- Hornak et al., Proteins (2006) 65:712-725
