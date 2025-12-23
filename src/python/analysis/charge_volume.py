#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on 2025-10-27 (Y/M/D) at 17:46
@author: Anup K. Prasad
email: anupkprasad121@gmail.com
"""
import MDAnalysis as mda
import numpy as np
from MDAnalysis.analysis.density import DensityAnalysis

path = "/mnt/mydrive/pseudokinase/pseudoNcontrol_AF3/0_MD_simulation/sim_done/atp_o60674_kd1__amsa_atemp/rep1/"

u = mda.Universe(f"{path}md.gro", f"{path}mdWrap10frm1ns.xtc")
# Define pocket region (example: residues around ATP)
pocket_sel = u.select_atoms("(protein or resname MG) and around 6 (resname ATP)")  # adjust selection

# Run occupancy density analysis
d = DensityAnalysis(pocket_sel, delta=1.0)  # 1 Å grid
d.run()

dens = d.results.density
voxel_volume = np.prod(dens.delta)

# Step 1: Normalize occupancy
occ = dens.grid / dens.grid.max()

# Step 2: Mark "empty" voxels = low occupancy
empty_voxels = np.sum(occ < 0.05)   # <5% occupancy = cavity/void
empty_volume = empty_voxels * voxel_volume

print(f"Approximate empty pocket volume: {empty_volume:.2f} Å³")

