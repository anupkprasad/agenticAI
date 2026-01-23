#!/usr/bin/env python3
"""
Universal Ligand Preprocessor for Agentic AI Workflow
Supports ATP, GTP, ADP, NAD, NADH, and any other ligands

This script handles:
1. Automatic ligand type detection from PDB files
2. Addition of missing hydrogen atoms using multiple methods
3. Generation of topology files for molecular dynamics simulations
"""

# Standard library imports
import os
import sys
import subprocess
import logging
import argparse
from pathlib import Path

# Third-party imports (imported conditionally in methods where used)
# rdkit - for molecular manipulation and hydrogen addition
# openbabel - alternative hydrogen addition method
# reduce - protein structure optimization tool
# pdb2pqr - protonation state assignment

class LigandPreprocessor:
    """Add hydrogens to any ligand and generate topology"""
    
    def __init__(self, working_dir="working_dir"):
        self.working_dir = Path(working_dir)
        self.logger = self._setup_logging()
        
        # Common ligand properties database
        self.ligand_properties = {
            'ATP': {'charge': -4, 'name': 'Adenosine Triphosphate'},
            'ADP': {'charge': -3, 'name': 'Adenosine Diphosphate'},
            'AMP': {'charge': -2, 'name': 'Adenosine Monophosphate'},
            'GTP': {'charge': -4, 'name': 'Guanosine Triphosphate'},
            'GDP': {'charge': -3, 'name': 'Guanosine Diphosphate'},
            'GMP': {'charge': -2, 'name': 'Guanosine Monophosphate'},
            'NAD': {'charge': -1, 'name': 'Nicotinamide Adenine Dinucleotide'},
            'NADH': {'charge': -2, 'name': 'Nicotinamide Adenine Dinucleotide (reduced)'},
            'NADP': {'charge': -2, 'name': 'Nicotinamide Adenine Dinucleotide Phosphate'},
            'NADPH': {'charge': -3, 'name': 'Nicotinamide Adenine Dinucleotide Phosphate (reduced)'},
            'CoA': {'charge': -4, 'name': 'Coenzyme A'},
            'FAD': {'charge': -2, 'name': 'Flavin Adenine Dinucleotide'},
            'FADH2': {'charge': -2, 'name': 'Flavin Adenine Dinucleotide (reduced)'},
            'FMN': {'charge': -2, 'name': 'Flavin Mononucleotide'},
            'CTP': {'charge': -4, 'name': 'Cytidine Triphosphate'},
            'CDP': {'charge': -3, 'name': 'Cytidine Diphosphate'},
            'UTP': {'charge': -4, 'name': 'Uridine Triphosphate'},
            'UDP': {'charge': -3, 'name': 'Uridine Diphosphate'},
            'TTP': {'charge': -4, 'name': 'Thymidine Triphosphate'},
            'dATP': {'charge': -4, 'name': 'Deoxyadenosine Triphosphate'},
            'dGTP': {'charge': -4, 'name': 'Deoxyguanosine Triphosphate'},
            'dCTP': {'charge': -4, 'name': 'Deoxycytidine Triphosphate'},
            'dTTP': {'charge': -4, 'name': 'Deoxythymidine Triphosphate'},
        }
    def detect_ligand_type(self, pdb_file):
        """Automatically detect ligand type from PDB file"""
        try:
            with open(pdb_file, 'r') as f:
                content = f.read().upper()
            
            # Check for common ligand identifiers in PDB file
            for ligand, props in self.ligand_properties.items():
                if ligand in content or ligand.lower() in str(pdb_file).lower():
                    self.logger.info(f"Detected ligand type: {ligand} ({props['name']})")
                    return ligand, props['charge']
            
            # If not found in database, try to extract from filename
            filename = Path(pdb_file).stem.upper()
            for ligand in self.ligand_properties.keys():
                if ligand in filename:
                    props = self.ligand_properties[ligand]
                    self.logger.info(f"Detected from filename: {ligand} ({props['name']})")
                    return ligand, props['charge']
            
            # Default fallback
            self.logger.warning("Could not detect ligand type, using default charge 0")
            return "UNKNOWN", 0
            
        except Exception as e:
            self.logger.error(f"Error detecting ligand type: {e}")
        
    def _setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def add_hydrogens_reduce(self, pdb_file, output_file):
        """Add hydrogens using reduce (if available)"""
        try:
            cmd = ['reduce', '-build', str(pdb_file)]
            self.logger.info(f"Running reduce: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                with open(output_file, 'w') as f:
                    f.write(result.stdout)
                self.logger.info(f"Hydrogens added successfully using reduce: {output_file}")
                return True
            else:
                self.logger.warning(f"Reduce failed: {result.stderr}")
                return False
                
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.warning(f"Reduce not available or failed: {e}")
            return False
    
    def add_hydrogens_openbabel(self, pdb_file, output_file):
        """Add hydrogens using OpenBabel"""
        try:
            cmd = ['obabel', str(pdb_file), '-O', str(output_file), '-h']
            self.logger.info(f"Running OpenBabel: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                self.logger.info(f"Hydrogens added successfully using OpenBabel: {output_file}")
                return True
            else:
                self.logger.warning(f"OpenBabel failed: {result.stderr}")
                return False
                
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.warning(f"OpenBabel not available or failed: {e}")
            return False
    
    def add_hydrogens_rdkit(self, pdb_file, output_file):
        """Add hydrogens using RDKit"""
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            
            # Read molecule from PDB
            mol = Chem.MolFromPDBFile(str(pdb_file), removeHs=False)
            if mol is None:
                self.logger.warning("RDKit could not read PDB file")
                return False
            
            # Add hydrogens
            mol_h = Chem.AddHs(mol, addCoords=True)
            
            # Generate 3D coordinates for new hydrogens
            AllChem.EmbedMolecule(mol_h, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
            
            # Write to PDB file
            with open(output_file, 'w') as f:
                f.write(Chem.MolToPDBBlock(mol_h))
            
            self.logger.info(f"Hydrogens added successfully using RDKit: {output_file}")
            return True
            
        except Exception as e:
            self.logger.warning(f"RDKit hydrogen addition failed: {e}")
            return False
    
    def add_hydrogens_pdb2pqr(self, pdb_file, output_file):
        """Add hydrogens using PDB2PQR (if available)"""
        try:
            cmd = ['pdb2pqr30', '--ff=AMBER', '--with-ph=7.0', str(pdb_file), str(output_file)]
            self.logger.info(f"Running PDB2PQR: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                self.logger.info(f"Hydrogens added successfully using PDB2PQR: {output_file}")
                # Convert PQR back to PDB format
                self._pqr_to_pdb(output_file, output_file)
                return True
            else:
                self.logger.warning(f"PDB2PQR failed: {result.stderr}")
                return False
                
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.warning(f"PDB2PQR not available or failed: {e}")
            return False
    
    def _pqr_to_pdb(self, pqr_file, pdb_file):
        """Convert PQR format to PDB format"""
        try:
            with open(pqr_file, 'r') as f:
                lines = f.readlines()
            
            pdb_lines = []
            for line in lines:
                if line.startswith('ATOM') or line.startswith('HETATM'):
                    # Convert PQR line to PDB format
                    # PQR has charge and radius in different positions
                    parts = line.split()
                    if len(parts) >= 9:
                        pdb_line = f"{parts[0]:<6}{parts[1]:>5} {parts[2]:>4} {parts[3]:>3} {parts[4]:>1}{parts[5]:>4}    {float(parts[6]):8.3f}{float(parts[7]):8.3f}{float(parts[8]):8.3f}  1.00 20.00           {parts[2][0]:>1}\n"
                        pdb_lines.append(pdb_line)
            
            with open(pdb_file, 'w') as f:
                f.writelines(pdb_lines)
                
        except Exception as e:
            self.logger.warning(f"PQR to PDB conversion failed: {e}")
    
    def add_hydrogens(self, pdb_file):
        """Try multiple methods to add hydrogens"""
        input_file = self.working_dir / pdb_file
        output_file = self.working_dir / f"{pdb_file.stem}_H.pdb"
        
        self.logger.info(f"Adding hydrogens to {input_file}")
        
        # Try different methods in order of preference
        methods = [
            ('reduce', self.add_hydrogens_reduce),
            ('openbabel', self.add_hydrogens_openbabel),
            ('rdkit', self.add_hydrogens_rdkit),
            ('pdb2pqr', self.add_hydrogens_pdb2pqr)
        ]
        
        for method_name, method_func in methods:
            self.logger.info(f"Trying {method_name}...")
            if method_func(input_file, output_file):
                self.logger.info(f"Successfully added hydrogens using {method_name}")
                return output_file
            
        self.logger.error("All hydrogen addition methods failed!")
        return None
    
    def generate_topology(self, pdb_file_with_h, ligand_name, charge):
        """Generate topology after adding hydrogens"""
        try:
            # Import the topology generator from simsetup module
            sys.path.append(str(self.working_dir.parent / 'simsetup'))
            from ligand_topology_generator import LigandTopologyGenerator
            
            generator = LigandTopologyGenerator(self.working_dir)
            result = generator.generate_topology(pdb_file_with_h.name, ligand_name, charge)
            
            if result:
                self.logger.info("Topology generated successfully!")
                return result
            else:
                self.logger.error("Topology generation failed")
                return None
                
        except Exception as e:
            self.logger.error(f"Error generating topology: {e}")
            return None
    
    def process_ligand(self, pdb_filename, ligand_name=None, charge=None):
        """Complete processing: add hydrogens + generate topology for any ligand"""
        self.logger.info("=== Starting Universal Ligand Preprocessing ===")
        
        pdb_file = Path(pdb_filename)
        self.logger.info(f"Processing ligand from: {pdb_file}")
        
        # Step 1: Detect or use provided ligand information
        if ligand_name and charge is not None:
            detected_ligand = ligand_name.upper()
            detected_charge = charge
            self.logger.info(f"Using provided ligand info: {detected_ligand} (charge: {detected_charge})")
        else:
            detected_ligand, detected_charge = self.detect_ligand_type(self.working_dir / pdb_file)
            
        # Step 2: Add hydrogens
        self.logger.info(f"=== Adding hydrogens to {detected_ligand} ===")
        pdb_with_h = self.add_hydrogens(pdb_file)
        
        if pdb_with_h is None:
            self.logger.error("Failed to add hydrogens")
            return False
        
        # Step 3: Generate topology
        self.logger.info(f"=== Generating topology for {detected_ligand} ===")
        result = self.generate_topology(pdb_with_h, detected_ligand, detected_charge)
        
        if result:
            self.logger.info(f"=== {detected_ligand} processing completed successfully! ===")
            self.logger.info("Generated files:")
            for file_type, file_path in result.items():
                self.logger.info(f"  {file_type}: {file_path}")
            return True
        else:
            self.logger.error(f"=== {detected_ligand} processing failed ===")
            return False
    
    def list_supported_ligands(self):
        """List all supported ligands"""
        self.logger.info("=== Supported Ligands ===")
        for ligand, props in self.ligand_properties.items():
            self.logger.info(f"  {ligand}: {props['name']} (charge: {props['charge']})")
        
        self.logger.info("\n=== Usage Examples ===")
        self.logger.info("  python ligand_preprocessor.py ATP.pdb")
        self.logger.info("  python ligand_preprocessor.py GTP.pdb --ligand GTP --charge -4")
        self.logger.info("  python ligand_preprocessor.py my_ligand.pdb --ligand NADH --charge -2")

def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Universal Ligand Preprocessor for Agentic AI Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
    python ligand_preprocessor.py ATP.pdb                     # Auto-detect ATP
    python ligand_preprocessor.py GTP.pdb --ligand GTP        # Specify ligand type  
    python ligand_preprocessor.py custom.pdb --ligand NAD --charge -1  # Custom charge
    python ligand_preprocessor.py --list                      # List supported ligands
        """
    )
    
    parser.add_argument('pdb_file', nargs='?', help='Input PDB file')
    parser.add_argument('--ligand', '-l', help='Ligand type (e.g., ATP, GTP, NAD)')
    parser.add_argument('--charge', '-c', type=int, help='Net charge of ligand')
    parser.add_argument('--list', action='store_true', help='List supported ligands')
    parser.add_argument('--working-dir', '-w', default='.',
                        help='Working directory (default: current directory)')
    
    args = parser.parse_args()
    
    processor = LigandPreprocessor(args.working_dir)
    
    if args.list:
        processor.list_supported_ligands()
        return
    
    if not args.pdb_file:
        print("Error: PDB file is required unless using --list")
        parser.print_help()
        sys.exit(1)
    
    if not Path(args.working_dir) / args.pdb_file:
        if not Path(args.pdb_file).exists():
            print(f"Error: PDB file '{args.pdb_file}' not found")
            sys.exit(1)
    
    success = processor.process_ligand(args.pdb_file, args.ligand, args.charge)
    
    if not success:
        sys.exit(1)
    else:
        print(f"\n✅ Ligand processing completed successfully!")
        print(f"   Check the working directory for generated files.")

if __name__ == "__main__":
    main()

# ====================================================================
# COMPREHENSIVE USE CASES AND EXAMPLES
# ====================================================================

"""
=== QUICK START GUIDE ===

1. Basic Usage (Auto-detection):
   python ligand_preprocessor.py ATP.pdb
   
2. Specify Ligand Type:
   python ligand_preprocessor.py my_molecule.pdb --ligand ATP --charge -4
   
3. List Supported Ligands:
   python ligand_preprocessor.py --list

=== DETAILED USE CASES ===

# Case 1: Process ATP with auto-detection
processor = LigandPreprocessor("working_dir")
success = processor.process_ligand("ATP.pdb")

# Case 2: Process custom ligand with specified parameters
processor = LigandPreprocessor("working_dir")
success = processor.process_ligand("custom_ligand.pdb", ligand_name="NAD", charge=-1)

# Case 3: Just add hydrogens without topology generation
processor = LigandPreprocessor("working_dir")
pdb_with_h = processor.add_hydrogens(Path("ATP.pdb"))

=== SUPPORTED LIGANDS DATABASE ===
This script automatically detects and handles these common ligands:

Nucleotides:
  - ATP (Adenosine Triphosphate, charge: -4)
  - ADP (Adenosine Diphosphate, charge: -3) 
  - AMP (Adenosine Monophosphate, charge: -2)
  - GTP, GDP, GMP (Guanosine nucleotides)
  - CTP, CDP (Cytidine nucleotides)
  - UTP, UDP (Uridine nucleotides)
  - TTP, dATP, dGTP, dCTP, dTTP (Deoxy nucleotides)

Cofactors:
  - NAD/NADH (Nicotinamide Adenine Dinucleotide)
  - NADP/NADPH (NAD Phosphate)
  - FAD/FADH2 (Flavin Adenine Dinucleotide)
  - FMN (Flavin Mononucleotide)
  - CoA (Coenzyme A)

=== HYDROGEN ADDITION METHODS ===
The script tries multiple methods in order:

1. reduce: Professional protein structure optimization
2. openbabel: Chemical informatics toolkit
3. rdkit: Cheminformatics and machine learning
4. pdb2pqr: Protonation state assignment at specific pH

=== OUTPUT FILES ===
After successful processing, you'll get:
- {ligand}_H.pdb: Original PDB with added hydrogens
- {ligand}.itp: GROMACS topology file
- {ligand}.gro: GROMACS coordinate file
- {ligand}_params.txt: Force field parameters summary

=== ERROR HANDLING ===
The script gracefully handles:
- Missing hydrogen addition tools (tries alternatives)
- Unknown ligand types (uses default charge 0)
- File I/O errors
- Topology generation failures

=== INTEGRATION WITH MD WORKFLOW ===
This preprocessor integrates with the Agentic AI molecular dynamics workflow:

from ligand_preprocessor import LigandPreprocessor

# In your MD workflow
processor = LigandPreprocessor(working_directory)
if processor.process_ligand("ligand.pdb"):
    print("Ligand ready for MD simulation!")
else:
    print("Preprocessing failed, check logs")

=== CUSTOMIZATION ===
To add new ligand types, extend the ligand_properties dictionary:

processor.ligand_properties['CUSTOM'] = {
    'charge': -2, 
    'name': 'Custom Ligand Name'
}

=== DEPENDENCIES ===
Required: Python 3.6+, pathlib
Optional (for hydrogen addition): rdkit, openbabel, reduce, pdb2pqr
Required for topology: ../simsetup/ligand_topology_generator.py

=== TESTING WITH ATP ===
Test the script with the provided ATP.pdb file:

python ligand_preprocessor.py ATP.pdb

Expected output:
- Detection of ATP ligand type
- Addition of missing hydrogens
- Generation of topology files for GROMACS
- Success message with file locations
"""
