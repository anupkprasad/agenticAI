"""
MDP File Generator Tool
Generates GROMACS MDP (Molecular Dynamics Parameter) files for different simulation types
"""
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool


@tool
def generate_mdp_file(
    mdp_type: str,
    output_file: Optional[str] = None,
    temperature: float = 300.0,
    pressure: float = 1.0,
    nsteps: int = 50000,
    working_dir: str = "."
) -> Dict[str, Any]:
    """
    Generate GROMACS MDP file for specific simulation type.
    
    Args:
        mdp_type: Type of MDP - 'minim', 'nvt', 'npt', 'md', 'ions'
        output_file: Output MDP file path
        temperature: Temperature in Kelvin
        pressure: Pressure in bar
        nsteps: Number of simulation steps
        working_dir: Working directory for output
        
    Returns:
        Dict with success status and output file path
    """
    wd = Path(working_dir)
    wd.mkdir(parents=True, exist_ok=True)
    
    if not output_file:
        output_file = str(wd / f"{mdp_type}.mdp")
    
    try:
        mdp_templates = {
            "minim": f"""; Energy Minimization MDP
integrator  = steep
nsteps      = {nsteps}
emtol       = 1000.0
emstep      = 0.01

; Output control
nstlog      = 100
nstenergy   = 100

; Neighbor searching
cutoff-scheme = Verlet
ns_type     = grid
nstlist     = 10
rcoulomb    = 1.0
rvdw        = 1.0

; Electrostatics
coulombtype = PME
pme_order   = 4
fourierspacing = 0.16

; Temperature and pressure
tcoupl      = no
pcoupl      = no

; PBC
pbc         = xyz
""",
            "nvt": f"""; NVT Equilibration MDP
define      = -DPOSRES  ; Position restraints

integrator  = md
nsteps      = {nsteps}
dt          = 0.002     ; 2 fs

; Output control
nstlog      = 1000
nstxout-compressed = 1000
nstenergy   = 1000

; Neighbor searching
cutoff-scheme = Verlet
nstlist     = 10
rcoulomb    = 1.0
rvdw        = 1.0

; Electrostatics
coulombtype = PME
pme_order   = 4
fourierspacing = 0.16

; Temperature coupling
tcoupl      = V-rescale
tc-grps     = System
tau_t       = 0.1
ref_t       = {temperature}

; Pressure coupling
pcoupl      = no

; Velocity generation
gen_vel     = yes
gen_temp    = {temperature}
gen_seed    = -1

; PBC
pbc         = xyz
""",
            "npt": f"""; NPT Equilibration MDP
define      = -DPOSRES  ; Position restraints

integrator  = md
nsteps      = {nsteps}
dt          = 0.002     ; 2 fs

; Output control
nstlog      = 1000
nstxout-compressed = 1000
nstenergy   = 1000

; Neighbor searching
cutoff-scheme = Verlet
nstlist     = 10
rcoulomb    = 1.0
rvdw        = 1.0

; Electrostatics
coulombtype = PME
pme_order   = 4
fourierspacing = 0.16

; Temperature coupling
tcoupl      = V-rescale
tc-grps     = System
tau_t       = 0.1
ref_t       = {temperature}

; Pressure coupling
pcoupl      = Parrinello-Rahman
pcoupltype  = isotropic
tau_p       = 2.0
ref_p       = {pressure}
compressibility = 4.5e-5

; Velocity generation
gen_vel     = no

; PBC
pbc         = xyz
""",
            "md": f"""; Production MD MDP

integrator  = md
nsteps      = {nsteps}
dt          = 0.002     ; 2 fs

; Output control
nstlog      = 5000
nstxout-compressed = 5000
nstenergy   = 5000

; Neighbor searching
cutoff-scheme = Verlet
nstlist     = 10
rcoulomb    = 1.0
rvdw        = 1.0

; Electrostatics
coulombtype = PME
pme_order   = 4
fourierspacing = 0.16

; Temperature coupling
tcoupl      = V-rescale
tc-grps     = System
tau_t       = 0.1
ref_t       = {temperature}

; Pressure coupling
pcoupl      = Parrinello-Rahman
pcoupltype  = isotropic
tau_p       = 2.0
ref_p       = {pressure}
compressibility = 4.5e-5

; Velocity generation
gen_vel     = no

; PBC
pbc         = xyz
""",
            "ions": """; Ions MDP (for genion)
; Minimal parameters for TPR generation

integrator  = steep
nsteps      = 0
""",
        }
        
        if mdp_type not in mdp_templates:
            return {
                "success": False,
                "error": f"Unknown MDP type: {mdp_type}. Available: {list(mdp_templates.keys())}"
            }
        
        with open(output_file, 'w') as f:
            f.write(mdp_templates[mdp_type])
        
        return {
            "success": True,
            "output_file": output_file,
            "mdp_type": mdp_type,
            "temperature": temperature,
            "pressure": pressure,
            "nsteps": nsteps,
            "message": f"{mdp_type.upper()} MDP file generated"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"MDP generation failed: {e}"
        }
