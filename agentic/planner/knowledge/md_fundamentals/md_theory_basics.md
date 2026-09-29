# MD Theory — Practical Notes

## Integrator
Leap-frog / Verlet, `dt = 0.002 ps` with LINCS on h-bonds is the SimAgent default.
Do not change `dt` without rewriting MDP generators.

## Ensembles
- Minimisation: no ensemble (steepest descents / l-bfgs).
- NVT: thermostat only (V-rescale).
- NPT: thermostat + barostat (C-rescale recommended).
- Production: NPT unless the goal asks for NVT or NVE.

## Periodic boundaries
Analyse **wrapped** trajectories (`mdWrap.xtc`, protein+ligand centered).
Unwrapped `md.xtc` breaks RMSD/RMSF/COM when the protein jumps boxes.

## Sampling
- Robustness family campaigns: **200 ns** production per replicate.
- Independent replicates (`--rep-num N`) are better than one long traj for
  clustering error bars. Fan-out writes `hpc/repXX` and `analysis/avg/`.

## Observables
- RMSD / RMSF / Rg: global stability and flexibility.
- DCCM: correlated Cα motion (N-lobe ↔ C-lobe for kinases).
- Dihedral PCA FEL entropy: conformational-landscape volume.
- Pocket COM + axis-angle: ligand pose vs `pocket_mapped` residues.
