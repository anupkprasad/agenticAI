"""
Modular MDP File Generator for GROMACS Simulations
Handles: Protein-only, Protein+Ligand, Protein+Ligand+Ion systems
Compatible with AMBER and CHARMM force fields
Based on user's working MDP templates in src/python/setup/
"""
from pathlib import Path
from typing import Dict, Any, Optional


class MDPGenerator:
    """
    Modular MDP file generator that adapts to different system compositions.
    Generates GROMACS MDP files for minimization, NVT, NPT, and production MD.
    """
    
    def __init__(self, force_field: str = "amber99sb-ildn"):
        """
        Initialize MDP generator with force field specific settings.
        
        Args:
            force_field: Force field name (amber99sb-ildn, charmm36-jul2022, etc.)
        """
        self.force_field = force_field.lower()
        self.is_charmm = "charmm" in self.force_field
        
    def _get_cutoff_params(self) -> Dict[str, Any]:
        """Get force field specific cutoff parameters."""
        if self.is_charmm:
            # CHARMM36 parameters
            return {
                "rlist": 1.2,
                "rcoulomb": 1.2,
                "rvdw": 1.2,
                "rvdw_switch": 1.0,
                "vdwtype": "cutoff",
                "vdw_modifier": "force-switch",
                "DispCorr": "no",
            }
        else:
            # AMBER parameters  
            return {
                "rlist": 1.2,
                "rcoulomb": 1.2,
                "rvdw": 1.2,
                "rvdw_switch": 1.0,
                "vdwtype": "cutoff",
                "vdw_modifier": "force-switch",
                "DispCorr": "EnerPres",
            }
    
    def _determine_tc_groups(self, has_ligand: bool, has_ions: bool) -> tuple:
        """
        Determine temperature coupling groups based on system composition.
        For solvated systems (water + ions), always use Protein Non-Protein.
        
        Returns:
            (tc-grps string, number of groups)
        """
        # Solvated systems always have water/ions = Non-Protein
        # Only use "System" for vacuum simulations (rare)
        return "Protein Non-Protein", 2
    
    def _get_position_restraints(self, has_ligand: bool) -> str:
        """Get position restraint definitions."""
        if has_ligand:
            return "-DPOSRES -DPOSRES_LIG"
        else:
            return "-DPOSRES"
    
    def generate_minimization_mdp(
        self,
        output_file: str,
        nsteps: int = 600000,
        emtol: float = 100.0,
        has_ligand: bool = False,
        **kwargs
    ) -> str:
        """Generate energy minimization MDP file."""
        cutoffs = self._get_cutoff_params()
        posres = self._get_position_restraints(has_ligand)
        
        mdp_content = f"""; Energy Minimization
define          = {posres}
integrator      = steep
emtol           = {emtol}
emstep          = 0.01
nsteps          = {nsteps}

; Output control
nstxout                  = 0
nstxout-compressed       = 0
nstvout                  = 0
nstfout                  = 0
nstenergy                = 1000
nstlog                   = 1000

; Neighbor searching
nstlist         = 1
ns_type         = grid
pbc             = xyz

; Bond parameters
constraints     = h-bonds

; Neighbor searching
cutoff-scheme   = Verlet

; Electrostatics
coulombtype     = PME
rlist           = {cutoffs['rlist']}
vdwtype         = {cutoffs['vdwtype']}
vdw-modifier    = {cutoffs['vdw_modifier']}
rvdw            = {cutoffs['rvdw']}
rcoulomb        = {cutoffs['rcoulomb']}
rvdw-switch     = {cutoffs['rvdw_switch']}

; Dispersion correction
DispCorr        = {cutoffs['DispCorr']}
"""
        
        Path(output_file).write_text(mdp_content)
        return output_file
    
    def generate_nvt_mdp(
        self,
        output_file: str,
        nsteps: int = 50000,
        dt: float = 0.002,
        temperature: float = 310.0,
        has_ligand: bool = False,
        has_ions: bool = False,
        **kwargs
    ) -> str:
        """Generate NVT equilibration MDP file."""
        cutoffs = self._get_cutoff_params()
        posres = self._get_position_restraints(has_ligand)
        tc_grps, n_groups = self._determine_tc_groups(has_ligand, has_ions)
        tau_t = " ".join([f"{0.1}" for _ in range(n_groups)])
        ref_t = " ".join([f"{temperature}" for _ in range(n_groups)])
        
        mdp_content = f"""; NVT equilibration
title           = NVT equilibration
define          = {posres}  ; position restrain the protein

; Run parameters
integrator      = md        ; leap-frog integrator
nsteps          = {nsteps}
dt              = {dt}
comm-mode       = Linear

; Output control
nstxout         = 0
nstvout         = 0
nstfout         = 0
nstenergy       = 500
nstlog          = 500
nstxout-compressed = 500

; Bond parameters
continuation         = no        ; first dynamics run
constraint_algorithm = lincs     ; holonomic constraints
constraints          = h-bonds   ; bonds with H-atoms to constraints
lincs_iter           = 1         ; accuracy of LINCS
lincs_order          = 4         ; also related to accuracy

; Neighbor searching
cutoff-scheme   = Verlet
ns_type         = grid      ; search neighboring grid cells
nstlist         = 20        ; 10 fs

; Electrostatics
coulombtype     = PME       ; for long range electrostatics
pme_order       = 4         ; cubic interpolation
fourierspacing  = 0.12      ; grid spacing for FFT
ewald-rtol      = 1e-5
optimize-fft    = yes
rlist           = {cutoffs['rlist']}
vdwtype         = {cutoffs['vdwtype']}
vdw-modifier    = {cutoffs['vdw_modifier']}
rvdw            = {cutoffs['rvdw']}
rcoulomb        = {cutoffs['rcoulomb']}
rvdw-switch     = {cutoffs['rvdw_switch']}

; Temperature coupling (NVT)
tcoupl          = V-rescale
tc-grps         = {tc_grps}
tau_t           = {tau_t}
ref_t           = {ref_t}

; Periodic boundary conditions
pbc             = xyz

; Dispersion correction
DispCorr        = {cutoffs['DispCorr']}

; Pressure coupling is off
pcoupl          = no

; Velocity generation
gen_vel         = yes
gen_temp        = {temperature}
gen_seed        = -1
"""
        
        Path(output_file).write_text(mdp_content)
        return output_file
    
    def generate_npt_mdp(
        self,
        output_file: str,
        nsteps: int = 50000,
        dt: float = 0.002,
        temperature: float = 310.0,
        pressure: float = 1.0,
        has_ligand: bool = False,
        has_ions: bool = False,
        **kwargs
    ) -> str:
        """Generate NPT equilibration MDP file."""
        cutoffs = self._get_cutoff_params()
        posres = self._get_position_restraints(has_ligand)
        tc_grps, n_groups = self._determine_tc_groups(has_ligand, has_ions)
        tau_t = " ".join([f"{0.1}" for _ in range(n_groups)])
        ref_t = " ".join([f"{temperature}" for _ in range(n_groups)])
        
        mdp_content = f"""; NPT equilibration
title           = NPT equilibration
define          = {posres}  ; position restrain the protein

; Run parameters
integrator      = md        ; leap-frog integrator
nsteps          = {nsteps}  ; 2 * 50000 = 100 ps
dt              = {dt}      ; 2 fs
comm-mode       = Linear

; Output control
nstxout         = 0         ; do not write .trr positions
nstvout         = 0         ; do not write velocities to .trr
nstfout         = 0         ; do not write forces to .trr
nstenergy       = 500       ; write energy to .edr every 500 steps
nstlog          = 500
nstxout-compressed = 500    ; write .xtc every 500 steps

; Bond parameters
continuation         = yes       ; continuation from NVT
constraint_algorithm = lincs     ; holonomic constraints
constraints          = h-bonds   ; bonds with H-atoms to constraints
lincs_iter           = 1         ; accuracy of LINCS
lincs_order          = 4         ; also related to accuracy

; Neighbor searching
cutoff-scheme   = Verlet
ns_type         = grid      ; search neighboring grid cells
nstlist         = 20        ; 10 fs

; Electrostatics
coulombtype     = PME       ; for long range electrostatics
pme_order       = 4         ; cubic interpolation
fourierspacing  = 0.12      ; grid spacing for FFT
ewald-rtol      = 1e-5
optimize-fft    = yes
rlist           = {cutoffs['rlist']}
vdwtype         = {cutoffs['vdwtype']}
vdw-modifier    = {cutoffs['vdw_modifier']}
rvdw            = {cutoffs['rvdw']}
rcoulomb        = {cutoffs['rcoulomb']}
rvdw-switch     = {cutoffs['rvdw_switch']}

; Temperature coupling is on
tcoupl          = V-rescale           ; modified Berendsen thermostat
tc-grps         = {tc_grps}           ; two coupling groups - more accurate
tau_t           = {tau_t}             ; time constant, in ps
ref_t           = {ref_t}             ; reference temperature, one for each group, in K

; Periodic boundary conditions
pbc             = xyz       ; 3-D PBC

; Dispersion correction
DispCorr        = EnerPres  ; account for cut-off vdW scheme

; Pressure coupling is on
pcoupl          = Berendsen ; pressure coupling on in NPT
pcoupltype      = isotropic ; uniform scaling of box vectors
tau_p           = 2.0       ; time constant, in ps
ref_p           = {pressure}; reference pressure, in bar
compressibility = 4.5e-5    ; isothermal compressibility of water, bar^-1
refcoord-scaling= all

gen_vel         = no        ; velocities from NVT
"""
        
        Path(output_file).write_text(mdp_content)
        return output_file
    
    def generate_production_mdp(
        self,
        output_file: str,
        nsteps: int = 100000000,
        dt: float = 0.002,
        temperature: float = 310.0,
        pressure: float = 1.0,
        has_ligand: bool = False,
        has_ions: bool = False,
        output_freq: int = 50000,
        **kwargs
    ) -> str:
        """Generate production MD simulation MDP file."""
        cutoffs = self._get_cutoff_params()
        tc_grps, n_groups = self._determine_tc_groups(has_ligand, has_ions)
        tau_t = " ".join([f"{0.1}" for _ in range(n_groups)])
        ref_t = " ".join([f"{temperature}" for _ in range(n_groups)])
        
        mdp_content = f"""; Production MD run
title           = production run

; Run parameters
integrator      = md        ; leap-frog integrator
nsteps          = {nsteps}  ; 100000000 = 200 ns (at dt=0.002)
dt              = {dt}      ; unit in gromacs is ps so it is 2 fs
comm-mode       = Linear

; Output control
nstxout         = 0         ; do not write .trr positions
nstvout         = 0         ; do not write velocities to .trr
nstfout         = 0         ; do not write forces to .trr
nstenergy       = {output_freq}     ; write energy to .edr every {output_freq} steps
nstlog          = {output_freq}
nstxout-compressed = {output_freq}  ; write .xtc every {output_freq} steps

; Bond parameters
continuation         = yes       ; continuation from NPT
constraint_algorithm = lincs     ; holonomic constraints
constraints          = h-bonds   ; bonds with H-atoms to constraints
lincs_iter           = 1         ; accuracy of LINCS
lincs_order          = 6         ; 6 is needed for large time steps with virtual sites or BD

; Neighbor searching
cutoff-scheme   = Verlet
ns_type         = grid      ; search neighboring grid cells
nstlist         = 20        ; 20*2fs = 40 fs

; Electrostatics
coulombtype     = PME       ; for long range electrostatics
ewald-rtol      = 1e-5
pme_order       = 4         ; cubic interpolation
fourierspacing  = 0.12      ; grid spacing for FFT
optimize-fft    = yes
rlist           = {cutoffs['rlist']}            ; short-range neighbor list cutoff (in nm)
rcoulomb        = {cutoffs['rcoulomb']}         ; short-range electrostatic cutoff (in nm)
vdwtype         = {cutoffs['vdwtype']}          ; twin range cutoffs with neighbor list
vdw-modifier    = {cutoffs['vdw_modifier']}     ; smoothly switches the forces to zero
rvdw            = {cutoffs['rvdw']}             ; short-range van der Waals cutoff (in nm)
rvdw-switch     = {cutoffs['rvdw_switch']}      ; where to start switching the LJ force

; Temperature coupling is on
tcoupl          = V-rescale           ; modified Berendsen thermostat
tc-grps         = {tc_grps}           ; two coupling groups - more accurate
tau_t           = {tau_t}             ; time constant, in ps
ref_t           = {ref_t}             ; reference temperature, one for each group, in K

; Periodic boundary conditions
pbc             = xyz       ; 3-D PBC

; Dispersion correction
DispCorr        = no        ; set to 'no' for production runs

; Pressure coupling is on
pcoupl          = Berendsen ; pressure coupling on
pcoupltype      = isotropic ; uniform scaling of box vectors
tau_p           = 2.0       ; time constant, in ps
ref_p           = {pressure}; reference pressure, in bar
compressibility = 4.5e-5    ; isothermal compressibility of water, bar^-1
refcoord-scaling= all

gen_vel         = no        ; velocities from NPT
"""
        
        Path(output_file).write_text(mdp_content)
        return output_file
    
    def generate_ions_mdp(self, output_file: str) -> str:
        """Generate minimal MDP for adding ions with genion."""
        mdp_content = """; ion.mdp - used for ion addition
integrator      = steep        ; steepest descent energy minimization
emtol           = 1000.0       ; stop minimization when Fmax < 1000 kJ/mol/nm
emstep          = 0.01
nsteps          = 50000

cutoff-scheme   = Verlet
nstlist         = 20
ns_type         = grid
coulombtype     = PME
rcoulomb        = 1.0
rvdw            = 1.0
pbc             = xyz
"""
        Path(output_file).write_text(mdp_content)
        return output_file
    
    def generate_all_mdp_files(
        self,
        output_dir: str,
        temperature: float = 310.0,
        pressure: float = 1.0,
        has_ligand: bool = False,
        has_ions: bool = False,
        production_ns: float = 200.0,
        **kwargs
    ) -> Dict[str, str]:
        """
        Generate all MDP files for a complete simulation workflow.
        
        Args:
            output_dir: Directory to write MDP files
            temperature: Simulation temperature (K)
            pressure: Simulation pressure (bar)
            has_ligand: Whether system contains ligand
            has_ions: Whether system contains ions
            production_ns: Production simulation length in nanoseconds
            
        Returns:
            Dict mapping MDP type to file path
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Calculate production nsteps
        production_nsteps = int(production_ns * 1000 / 0.002)
        
        mdp_files = {}
        
        mdp_files['ions'] = self.generate_ions_mdp(
            str(output_dir / "ions.mdp")
        )
        
        mdp_files['minim'] = self.generate_minimization_mdp(
            str(output_dir / "minim.mdp"),
            has_ligand=has_ligand,
            **kwargs
        )
        
        mdp_files['nvt'] = self.generate_nvt_mdp(
            str(output_dir / "nvt.mdp"),
            temperature=temperature,
            has_ligand=has_ligand,
            has_ions=has_ions,
            **kwargs
        )
        
        mdp_files['npt'] = self.generate_npt_mdp(
            str(output_dir / "npt.mdp"),
            temperature=temperature,
            pressure=pressure,
            has_ligand=has_ligand,
            has_ions=has_ions,
            **kwargs
        )
        
        mdp_files['md'] = self.generate_production_mdp(
            str(output_dir / "md.mdp"),
            nsteps=production_nsteps,
            temperature=temperature,
            pressure=pressure,
            has_ligand=has_ligand,
            has_ions=has_ions,
            **kwargs
        )
        
        return mdp_files


def generate_mdp_files(
    output_dir: str,
    force_field: str = "amber99sb-ildn",
    temperature: float = 310.0,
    pressure: float = 1.0,
    has_ligand: bool = False,
    has_ions: bool = False,
    production_ns: float = 200.0,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate all GROMACS MDP files for a complete simulation workflow.
    Adapts to system composition (protein-only, protein+ligand, protein+ligand+ion).
    
    Args:
        output_dir: Directory to write MDP files
        force_field: Force field name (amber99sb-ildn, charmm36-jul2022)
        temperature: Simulation temperature in Kelvin (default: 310K)
        pressure: Simulation pressure in bar (default: 1.0)
        has_ligand: Whether system contains ligand molecules (ATP, GTP, etc.)
        has_ions: Whether system contains ions (MG, MN, etc.)
        production_ns: Production simulation length in nanoseconds
        
    Returns:
        Dict with success status and paths to generated MDP files
    """
    try:
        generator = MDPGenerator(force_field=force_field)
        mdp_files = generator.generate_all_mdp_files(
            output_dir=output_dir,
            temperature=temperature,
            pressure=pressure,
            has_ligand=has_ligand,
            has_ions=has_ions,
            production_ns=production_ns,
            **kwargs
        )
        
        return {
            "success": True,
            "mdp_files": mdp_files,
            "message": f"Generated {len(mdp_files)} MDP files in {output_dir}",
            "parameters": {
                "force_field": force_field,
                "temperature": temperature,
                "pressure": pressure,
                "has_ligand": has_ligand,
                "has_ions": has_ions,
                "production_ns": production_ns
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to generate MDP files: {str(e)}"
        }
