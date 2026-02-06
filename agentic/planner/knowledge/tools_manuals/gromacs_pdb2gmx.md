# GROMACS pdb2gmx Command Reference

## Purpose
Convert PDB file to GROMACS topology and coordinate file.

## Basic Syntax
```bash
gmx pdb2gmx -f input.pdb -o output.gro -p topol.top [options]
```

## Common Options

### Force Field Selection
```bash
-ff <forcefield>
```
Examples:
- `amber99sb-ildn` - AMBER99SB-ILDN (recommended for proteins)
- `charmm27` - CHARMM27
- `oplsaa` - OPLS-AA

### Water Model
```bash
-water <model>
```
Examples:
- `tip3p` - TIP3P (use with AMBER)
- `tip4p` - TIP4P
- `spce` - SPC/E

### Hydrogen Handling
```bash
-ignh           # Ignore hydrogens in input (add new ones)
-his            # Interactive histidine protonation
```

### Terminal Groups
```bash
-ter            # Interactive selection of terminal groups
```

### Output Files
- `.gro` - GROMACS coordinate file
- `.top` - Topology file
- `posre.itp` - Position restraints (if generated)

## Usage Examples

### Standard protein preparation
```bash
gmx pdb2gmx -f protein.pdb -o protein.gro -p topol.top \\
    -ff amber99sb-ildn -water tip3p -ignh
```

### With interactive options
```bash
gmx pdb2gmx -f protein.pdb -o protein.gro -p topol.top \\
    -ff amber99sb-ildn -water tip3p -ter -his
```

## Important Notes
- Always use `-ignh` if you added hydrogens externally
- Match water model to force field compatibility
- For AMBER force fields, use TIP3P water
- Check terminal selections (default is charged NH3+/COO-)

## Troubleshooting

### Error: "Residue not found in database"
- Non-standard residue (modified amino acid, ligand)
- Solution: Remove heteroatoms or create custom topology

### Error: "Atom not found"
- Missing atoms in PDB
- Solution: Add missing atoms with modeling software

### Multiple chains
- pdb2gmx handles multiple chains automatically
- Each chain gets separate [ position_restraints ] entry
