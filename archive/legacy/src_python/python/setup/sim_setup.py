import os
import sys
import subprocess

sys.path.append('/home/anup/myScripts/simulations/')
from groTopManager import pdbToGr0, mergeGroFiles, edit_topology

def run_cmd(cmd, shell=False):
    """Helper to execute shell commands safely and print them."""
    if isinstance(cmd, list):
        print("Running:", " ".join(cmd))
    else:
        print("Running:", cmd)
    subprocess.run(cmd, check=True, shell=shell)


def simulation_setup(src_path, wdir, pdb_file, ligand, metal_ion=None, metal_ion_count=None, pyro_init=True):
    """Sets up the simulation environment by copying necessary files and preparing input files."""
    try:
        original_dir = os.getcwd()
    except FileNotFoundError:
        original_dir = os.path.expanduser("~")  # or any safe base
    print("Changing directory to:", wdir)
    os.chdir(wdir)
    
    equilibration_dir = os.path.join(wdir, 'equilibration')
    os.makedirs(equilibration_dir, exist_ok=True)

    ##### Copy simSetupProtLigIon.sh #####
    src_file = src_path + 'simSetupProtLigIon.sh'
    dst_file = './simSetupProtLigIon.sh'
    run_cmd(["cp", src_file, dst_file])

    ##### Copy ligand.itp #####
    src_file = src_path + f'amber_donor_prm/{ligand}.itp'
    dst_file = equilibration_dir + f'/{ligand}.itp'
    run_cmd(["cp", src_file, dst_file])

    ##### Copy ligand posre #####
    src_file = src_path + f'amber_donor_prm/posre_{ligand}.itp'
    dst_file = equilibration_dir + f'/posre_{ligand}.itp'
    run_cmd(["cp", src_file, dst_file])


    ##### Copy amber99sb-ildn.ff directory #####
    src_dir = src_path + 'amber_donor_prm/amber99sb-ildn.ff'
    dst_dir = './amber99sb-ildn.ff'
    # If destination exists, skip or overwrite safely
    if os.path.exists(dst_dir):
        print(f"Directory {dst_dir} already exists — skipping copy.")
    else:
        run_cmd(["cp", "-r", src_dir, dst_dir])

    ##### Convert PDB to GRO #####
    pdbToGr0(pdb_file, path="./", ligand=   ligand, metal_ion= metal_ion, pyro_init=pyro_init)

    ############ GROMACS STEPS ############

    # Input files
    protein_pdb = "protein.gro"

    # Generate topology using GROMACS
    run_cmd([
        "gmx", "pdb2gmx",
        "-f", protein_pdb,
        "-o", "protein_processed.gro",
        "-p", "topol.top",
        "-i", "posre.itp",
        "-ff", "amber99sb-ildn",
        "-water", "tip3p",
        "-ignh"
    ])
    
    ################# Merge GRO files #################
    if metal_ion:
        mergeGroFiles(["protein_processed.gro", f"{ligand}.gro", f"{metal_ion}.gro"], output_file="complex.gro")
    else:
        mergeGroFiles(["protein_processed.gro", f"{ligand}.gro"], output_file="complex.gro")

    ################# Edit topology #################
    edit_topology(top_path="topol.top", lig_itp=f"{ligand}.itp", metal_ion=metal_ion, metal_ion_count=metal_ion_count)

    ############## Source Shell Script ##############
    # Equivalent to: source simSetupProtLigIon.sh
    run_cmd('bash -c "source simSetupProtLigIon.sh"', shell=True)

    os.chdir(original_dir)


def call_simulation_setup(pdb_file, wdir):
    src_path = '/home/anup/myScripts/simulations/gmx/simulationSetup/'
    simulation_setup(src_path, wdir, pdb_file=pdb_file, ligand='ATP', metal_ion='MG', metal_ion_count=2, pyro_init=True)
    return {"status": "success",
        "output_dir": wdir,
        "message": f"Simulation setup completed for {pdb_file} in {wdir}"}

if __name__ == "__main__":
    wdir = '/home/anup/workspace/temp/sim_test/'
    call_simulation_setup(wdir=wdir, pdb_file="0.pdb")