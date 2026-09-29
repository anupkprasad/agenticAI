# Equilibration Protocol

Standard GROMACS equilibration after solvation and ions, before production MD.

## Energy minimisation
- Steepest descents until max force < 1000 kJ mol⁻¹ nm⁻¹ (typically 500–5000 steps).
- Check `em.gro` exists and `em.log` reports a finite potential.

## NVT (temperature)
- Short restrained NVT (100–500 ps) with protein heavy atoms restrained (1000 kJ mol⁻¹ nm⁻²).
- V-rescale thermostat; target 300 K unless the goal says otherwise.
- Confirm temperature plateaus in `nvt.edr` before continuing.

## NPT (pressure)
- Restrained NPT (100–500 ps) with C-rescale or Parrinello–Rahman barostat; 1 bar.
- Box edges should stabilize. Do not start production if density is still drifting.

## Production
- Release restraints. Typical robustness campaigns use **200 ns** production
  (`nsteps` consistent with `dt = 0.002 ps`).
- Write `md.tpr` + a PBC-wrapped `mdWrap.xtc` for analysis.

## Tools
`generate_em_mdp`, `generate_nvt_mdp`, `generate_npt_mdp`, `generate_md_mdp`,
`grompp` / SLURM `mdrun`. Prefer the MDP generators over hand-written files.
