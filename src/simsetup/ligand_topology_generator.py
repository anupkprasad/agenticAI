#!/usr/bin/env python3
"""
Automated ligand topology generator for agentic AI workflow
Supports multiple methods to generate topology from PDB files
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

class LigandTopologyGenerator:
    """Generates topology files for ligands using various methods"""
    
    def __init__(self, working_dir="."):
        self.working_dir = Path(working_dir)
        self.logger = self._setup_logging()
        
    def _setup_logging(self):
        """Setup logging for the topology generator"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def check_dependencies(self):
        """Check which topology generation tools are available"""
        tools = {}
        
        # Check for acpype
        try:
            result = subprocess.run(['acpype', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                tools['acpype'] = True
                self.logger.info("acpype is available")
            else:
                tools['acpype'] = False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            tools['acpype'] = False
            self.logger.warning("acpype not available or not working")
        
        # Check for antechamber (from AmberTools)
        try:
            result = subprocess.run(['antechamber', '-h'], 
                                  capture_output=True, text=True, timeout=10)
            tools['antechamber'] = True
            self.logger.info("antechamber is available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            tools['antechamber'] = False
            self.logger.warning("antechamber not available")
        
        # Check for GROMACS
        try:
            result = subprocess.run(['gmx', 'help'], 
                                  capture_output=True, text=True, timeout=10)
            tools['gromacs'] = True
            self.logger.info("GROMACS is available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            tools['gromacs'] = False
            self.logger.warning("GROMACS not available")
        
        # Check for OpenEye (if available)
        try:
            import openeye.oechem
            tools['openeye'] = True
            self.logger.info("OpenEye toolkit is available")
        except ImportError:
            tools['openeye'] = False
        
        # Check for RDKit
        try:
            import rdkit
            tools['rdkit'] = True
            self.logger.info("RDKit is available")
        except ImportError:
            tools['rdkit'] = False
        
        return tools
    
    def generate_topology_acpype(self, pdb_file, ligand_name, charge, force_field="gaff2"):
        """Generate topology using acpype"""
        try:
            cmd = [
                'acpype',
                '-i', str(pdb_file),
                '-b', ligand_name,
                '-n', str(charge),
                '-a', force_field
            ]
            
            self.logger.info(f"Running acpype: {' '.join(cmd)}")
            
            # Try with proper environment setup
            env = os.environ.copy()
            if 'CONDA_PREFIX' in env:
                env['LD_LIBRARY_PATH'] = f"{env['CONDA_PREFIX']}/lib:{env.get('LD_LIBRARY_PATH', '')}"
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  cwd=self.working_dir, env=env, timeout=300)
            
            if result.returncode == 0:
                self.logger.info("acpype completed successfully")
                return self._find_acpype_output(ligand_name)
            else:
                self.logger.error(f"acpype failed: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error running acpype: {e}")
            return None
    
    def generate_topology_antechamber(self, pdb_file, ligand_name, charge, force_field="gaff2"):
        """Generate topology using antechamber directly"""
        try:
            # Step 1: Convert PDB to MOL2 with antechamber (using faster charge method)
            mol2_file = f"{ligand_name}.mol2"
            cmd1 = [
                'antechamber',
                '-i', str(pdb_file),
                '-fi', 'pdb',
                '-o', mol2_file,
                '-fo', 'mol2',
                '-c', 'gas',  # Use gas-phase charges (faster than bcc)
                '-nc', str(charge),
                '-at', force_field,
                '-rn', ligand_name.upper()
            ]
            
            self.logger.info(f"Running antechamber: {' '.join(cmd1)}")
            result1 = subprocess.run(cmd1, capture_output=True, text=True,
                                   cwd=self.working_dir, timeout=300)
            
            if result1.returncode != 0:
                self.logger.error(f"Antechamber step 1 failed: {result1.stderr}")
                return None
            
            # Step 2: Generate parameter file with parmchk2
            frcmod_file = f"{ligand_name}.frcmod"
            cmd2 = [
                'parmchk2',
                '-i', mol2_file,
                '-f', 'mol2',
                '-o', frcmod_file
            ]
            
            self.logger.info(f"Running parmchk2: {' '.join(cmd2)}")
            result2 = subprocess.run(cmd2, capture_output=True, text=True,
                                   cwd=self.working_dir, timeout=120)
            
            if result2.returncode != 0:
                self.logger.error(f"parmchk2 failed: {result2.stderr}")
                return None
            
            # Step 3: Generate AMBER topology with tleap
            return self._create_amber_topology_tleap(ligand_name, mol2_file, frcmod_file)
            
        except Exception as e:
            self.logger.error(f"Error running antechamber: {e}")
            return None
    
    def _create_amber_topology_tleap(self, ligand_name, mol2_file, frcmod_file):
        """Create AMBER topology using tleap"""
        try:
            # Create tleap input file
            tleap_input = f"""
source leaprc.gaff2
loadamberparams {frcmod_file}
LIG = loadmol2 {mol2_file}
saveamberparm LIG {ligand_name}.prmtop {ligand_name}.inpcrd
savepdb LIG {ligand_name}_amber.pdb
quit
"""
            
            tleap_file = f"{ligand_name}_tleap.in"
            with open(self.working_dir / tleap_file, 'w') as f:
                f.write(tleap_input)
            
            # Run tleap
            cmd = ['tleap', '-f', tleap_file]
            self.logger.info(f"Running tleap: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd=self.working_dir, timeout=120)
            
            if result.returncode == 0:
                # Convert AMBER files to GROMACS format using parmed
                return self._convert_amber_to_gromacs(ligand_name)
            else:
                self.logger.error(f"tleap failed: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error in tleap: {e}")
            return None
    
    def _convert_amber_to_gromacs(self, ligand_name):
        """Convert AMBER topology to GROMACS format using parmed"""
        try:
            import parmed as pmd
            
            # Load AMBER files
            parm = pmd.load_file(str(self.working_dir / f"{ligand_name}.prmtop"),
                               str(self.working_dir / f"{ligand_name}.inpcrd"))
            
            # Save as GROMACS files
            parm.save(str(self.working_dir / f"{ligand_name}.top"))
            parm.save(str(self.working_dir / f"{ligand_name}.gro"))
            
            self.logger.info("Successfully converted AMBER to GROMACS format")
            
            return {
                'topology': str(self.working_dir / f"{ligand_name}.top"),
                'coordinates': str(self.working_dir / f"{ligand_name}.gro"),
                'itp': str(self.working_dir / f"{ligand_name}.itp")  # parmed should generate this
            }
            
        except Exception as e:
            self.logger.error(f"Error converting AMBER to GROMACS: {e}")
            return None
    
    def generate_topology_rdkit(self, pdb_file, ligand_name, charge):
        """Generate topology using RDKit with simple force field"""
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            
            # Read molecule from PDB
            mol = Chem.MolFromPDBFile(str(pdb_file), removeHs=False)
            if mol is None:
                self.logger.error("Could not read molecule from PDB file")
                return None
            
            # Add hydrogens if missing
            mol = Chem.AddHs(mol)
            
            # Generate 3D coordinates if needed
            AllChem.EmbedMolecule(mol)
            AllChem.MMFFOptimizeMolecule(mol)
            
            # This is a simplified approach - in practice you'd need more sophisticated
            # parameter generation. For a complete workflow, you'd use tools like
            # OpenForceField or other parameter generators
            
            self.logger.warning("RDKit method is simplified - use for testing only")
            return self._create_simple_topology(mol, ligand_name, charge)
            
        except Exception as e:
            self.logger.error(f"Error with RDKit method: {e}")
            return None
    
    def _find_acpype_output(self, ligand_name):
        """Find and return paths to acpype output files"""
        output_files = {}
        patterns = [
            f"{ligand_name}_AC.gro",
            f"{ligand_name}_AC.top",
            f"{ligand_name}.itp"
        ]
        
        for pattern in patterns:
            files = list(self.working_dir.glob(pattern))
            if files:
                key = pattern.split('.')[-1]  # Use file extension as key
                output_files[key] = str(files[0])
        
        return output_files if output_files else None
    
    def generate_topology(self, pdb_file, ligand_name, charge, preferred_method=None):
        """Main method to generate topology using available tools"""
        tools = self.check_dependencies()
        
        methods = []
        if preferred_method and preferred_method in tools and tools[preferred_method]:
            methods = [preferred_method]
        else:
            # Try methods in order of preference for automation
            if tools.get('acpype', False):
                methods.append('acpype')  # Try acpype first since it's usually faster
            if tools.get('antechamber', False):
                methods.append('antechamber')
            if tools.get('rdkit', False):
                methods.append('rdkit')
        
        if not methods:
            self.logger.error("No topology generation tools available!")
            return None
        
        for method in methods:
            self.logger.info(f"Trying method: {method}")
            
            if method == 'acpype':
                result = self.generate_topology_acpype(pdb_file, ligand_name, charge)
            elif method == 'antechamber':
                result = self.generate_topology_antechamber(pdb_file, ligand_name, charge)
            elif method == 'rdkit':
                result = self.generate_topology_rdkit(pdb_file, ligand_name, charge)
            
            if result:
                self.logger.info(f"Successfully generated topology using {method}")
                return result
            else:
                self.logger.warning(f"Method {method} failed, trying next...")
        
        self.logger.error("All topology generation methods failed!")
        return None

def main():
    """Main function for command line usage"""
    if len(sys.argv) < 4:
        print("Usage: python ligand_topology_generator.py <pdb_file> <ligand_name> <charge>")
        print("Example: python ligand_topology_generator.py ATP.pdb ATP -4")
        sys.exit(1)
    
    pdb_file = sys.argv[1]
    ligand_name = sys.argv[2]
    charge = int(sys.argv[3])
    
    generator = LigandTopologyGenerator()
    result = generator.generate_topology(pdb_file, ligand_name, charge)
    
    if result:
        print("Successfully generated topology files:")
        for file_type, file_path in result.items():
            print(f"  {file_type}: {file_path}")
    else:
        print("Failed to generate topology files")
        sys.exit(1)

if __name__ == "__main__":
    main()
