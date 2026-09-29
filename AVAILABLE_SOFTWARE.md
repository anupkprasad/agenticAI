# Available software for SimAgent programmer tools

Reference list for the Programmer Agent when generating analysis or setup
helpers. Prefer built-in SimAgent tools first; only create a new tool when
nothing in the registry covers the capability.

## Molecular dynamics engines

| Software | Typical use |
|----------|-------------|
| **GROMACS** (`gmx`) | System preparation, energy minimization, equilibration, production MD, `trjconv` wrapping |
| **OpenMM** | Optional Python MD engine for lightweight / custom workflows |

## Trajectory and structure analysis

| Software | Typical use |
|----------|-------------|
| **MDAnalysis** | Trajectory I/O, selections, RMSD/RMSF, distances, contacts, DCCM inputs |
| **NumPy / SciPy** | Arrays, PCA, clustering math, statistics |
| **pandas** | Feature tables, CSV aggregation |
| **matplotlib / seaborn** | Publication-style 2D plots (when available in the environment) |

## Sequence / structure mapping

| Software | Typical use |
|----------|-------------|
| **MAFFT** | Multiple sequence alignment for cross-system residue mapping |
| **Biopython** | PDB/sequence helpers when needed |

## Clustering and dimensionality reduction

| Software | Typical use |
|----------|-------------|
| **scikit-learn** | Hierarchical clustering, PCA, preprocessing (z-score / robust scaling) |
| **SciPy** (`scipy.cluster`) | Ward linkage / dendrograms |

## Environment notes

- Prefer tools already registered in SimAgent (`agentic/*/tools.py`) over
  inventing duplicates.
- New programmer tools must be pure Python modules under the campaign
  `programmer/` folder and follow the existing `@tool` contract.
- Do not assume GUI apps (PyMOL, VMD) are available on HPC login nodes unless
  the user explicitly lists them.
- Containers / Singularity images may provide GROMACS on compute nodes; local
  analysis usually runs with the Python stack above.
