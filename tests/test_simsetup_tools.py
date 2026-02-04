"""
Unit Tests for Simulation Setup Modular Tools
Tests all @tool functions in src/simsetup/
"""
import unittest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import tools - access .func to get underlying function from @tool decorator
from src.simsetup.topology_builder import build_topology
from src.simsetup.box_builder import build_simulation_box
from src.simsetup.solvator import solvate_system
from src.simsetup.ion_adder import add_ions
from src.simsetup.mdp_generator import generate_mdp_file
from src.simsetup.amber_to_gromacs_converter import convert_amber_to_gromacs
from src.simsetup.ligand_topology_generator import generate_ligand_topology

# Get the actual functions from StructuredTool objects
build_topology = build_topology.func if hasattr(build_topology, 'func') else build_topology
build_simulation_box = build_simulation_box.func if hasattr(build_simulation_box, 'func') else build_simulation_box
solvate_system = solvate_system.func if hasattr(solvate_system, 'func') else solvate_system
add_ions = add_ions.func if hasattr(add_ions, 'func') else add_ions
generate_mdp_file = generate_mdp_file.func if hasattr(generate_mdp_file, 'func') else generate_mdp_file
convert_amber_to_gromacs = convert_amber_to_gromacs.func if hasattr(convert_amber_to_gromacs, 'func') else convert_amber_to_gromacs
generate_ligand_topology = generate_ligand_topology.func if hasattr(generate_ligand_topology, 'func') else generate_ligand_topology


class TestSimulationSetupTools(unittest.TestCase):
    """Test suite for simulation setup tools"""
    
    def setUp(self):
        """Create temporary directory and test files"""
        self.test_dir = tempfile.mkdtemp()
        self.test_pdb = self._create_test_pdb()
        self.test_gro = self._create_test_gro()
        self.test_top = self._create_test_top()
    
    def tearDown(self):
        """Clean up temporary files"""
        shutil.rmtree(self.test_dir)
    
    def _create_test_pdb(self):
        """Create a minimal test PDB file"""
        pdb_content = """ATOM      1  N   MET A   1      27.340  24.430   2.614  1.00  0.00           N
ATOM      2  CA  MET A   1      26.266  25.413   2.842  1.00  0.00           C
END
"""
        pdb_file = os.path.join(self.test_dir, "test.pdb")
        with open(pdb_file, 'w') as f:
            f.write(pdb_content)
        return pdb_file
    
    def _create_test_gro(self):
        """Create a minimal test GRO file"""
        gro_content = """Test system
    2
    1MET      N    1   2.734   2.443   0.261
    1MET     CA    2   2.627   2.541   0.284
   2.0   2.0   2.0
"""
        gro_file = os.path.join(self.test_dir, "test.gro")
        with open(gro_file, 'w') as f:
            f.write(gro_content)
        return gro_file
    
    def _create_test_top(self):
        """Create a minimal test topology file"""
        top_content = """; Test topology
[ system ]
Test System

[ molecules ]
Protein 1
"""
        top_file = os.path.join(self.test_dir, "test.top")
        with open(top_file, 'w') as f:
            f.write(top_content)
        return top_file
    
    @patch('subprocess.run')
    def test_build_topology_mock(self, mock_run):
        """Test topology building with mocked gmx"""
        # Mock successful gmx pdb2gmx execution
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        output_file = os.path.join(self.test_dir, "processed.gro")
        
        # Create expected output files
        with open(output_file, 'w') as f:
            f.write("mock output")
        with open(os.path.join(self.test_dir, "topol.top"), 'w') as f:
            f.write("mock topology")
        
        result = build_topology(
            pdb_file=self.test_pdb,
            force_field="amber99sb-ildn",
            water_model="tip3p",
            output_file=output_file
        )
        
        # Should attempt to run gmx
        self.assertTrue(mock_run.called)
        
        # Check if it would succeed
        if result.get("success"):
            self.assertIn("output_file", result)
            self.assertIn("topology_file", result)
    
    @patch('subprocess.run')
    def test_build_simulation_box_mock(self, mock_run):
        """Test simulation box building with mocked gmx"""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        output_file = os.path.join(self.test_dir, "boxed.gro")
        with open(output_file, 'w') as f:
            f.write("mock boxed system")
        
        result = build_simulation_box(
            coordinate_file=self.test_gro,
            box_type="cubic",
            box_distance=1.0,
            output_file=output_file
        )
        
        self.assertTrue(mock_run.called)
    
    @patch('subprocess.run')
    def test_solvate_system_mock(self, mock_run):
        """Test system solvation with mocked gmx"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Number of solvent molecules: 15000\n",
            stderr=""
        )
        
        output_file = os.path.join(self.test_dir, "solvated.gro")
        with open(output_file, 'w') as f:
            f.write("mock solvated system")
        
        result = solvate_system(
            coordinate_file=self.test_gro,
            topology_file=self.test_top,
            water_model="spc216",
            output_file=output_file
        )
        
        self.assertTrue(mock_run.called)
    
    def test_generate_mdp_file(self):
        """Test MDP file generation"""
        output_file = os.path.join(self.test_dir, "minim.mdp")
        
        result = generate_mdp_file(
            mdp_type="minim",
            temperature=300.0,
            pressure=1.0,
            nsteps=50000,
            output_file=output_file
        )
        
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(output_file))
        
        # Verify content
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn("integrator", content)
            self.assertIn("steep", content)
    
    def test_generate_mdp_all_types(self):
        """Test MDP generation for all simulation types"""
        mdp_types = ["minim", "nvt", "npt", "md", "ions"]
        
        for mdp_type in mdp_types:
            output_file = os.path.join(self.test_dir, f"{mdp_type}.mdp")
            result = generate_mdp_file(
                mdp_type=mdp_type,
                output_file=output_file
            )
            
            self.assertTrue(result["success"], f"Failed for {mdp_type}")
            self.assertTrue(os.path.exists(output_file))
            self.assertEqual(result.get("mdp_type"), mdp_type)
    
    def test_generate_mdp_invalid_type(self):
        """Test MDP generation with invalid type"""
        result = generate_mdp_file(mdp_type="invalid_type")
        self.assertFalse(result["success"])
        self.assertIn("error", result)
    
    @patch('subprocess.run')
    def test_ligand_topology_no_tools(self, mock_run):
        """Test ligand topology generation when no tools available"""
        # Mock all tools as unavailable
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        
        result = generate_ligand_topology(
            pdb_file=self.test_pdb,
            ligand_name="LIG",
            charge=-2
        )
        
        # Should fail gracefully when no tools available
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class TestSimulationSetupToolsIntegration(unittest.TestCase):
    """Integration tests for simulation setup tool chains"""
    
    def setUp(self):
        """Create temporary directory"""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files"""
        shutil.rmtree(self.test_dir)
    
    def test_mdp_file_generation_pipeline(self):
        """Test generating all required MDP files"""
        mdp_types = ["minim", "nvt", "npt", "md"]
        generated_files = {}
        
        for mdp_type in mdp_types:
            output_file = os.path.join(self.test_dir, f"{mdp_type}.mdp")
            result = generate_mdp_file(
                mdp_type=mdp_type,
                temperature=300.0,
                pressure=1.0,
                output_file=output_file
            )
            
            self.assertTrue(result["success"])
            self.assertTrue(os.path.exists(output_file))
            generated_files[mdp_type] = output_file
        
        # Verify all files were generated
        self.assertEqual(len(generated_files), 4)
    
    def test_mdp_parameter_customization(self):
        """Test MDP generation with custom parameters"""
        output_file = os.path.join(self.test_dir, "custom_npt.mdp")
        
        result = generate_mdp_file(
            mdp_type="npt",
            temperature=310.0,  # Custom temperature
            pressure=1.5,       # Custom pressure
            nsteps=100000,      # Custom steps
            output_file=output_file
        )
        
        self.assertTrue(result["success"])
        
        # Verify custom parameters in file
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertIn("310", content)  # Temperature
            self.assertIn("1.5", content)  # Pressure


class TestMDPTemplates(unittest.TestCase):
    """Test MDP templates for correctness"""
    
    def setUp(self):
        """Create temporary directory"""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files"""
        shutil.rmtree(self.test_dir)
    
    def test_minim_mdp_content(self):
        """Test energy minimization MDP content"""
        output_file = os.path.join(self.test_dir, "minim.mdp")
        result = generate_mdp_file(mdp_type="minim", output_file=output_file)
        
        with open(output_file, 'r') as f:
            content = f.read()
            # Check required parameters for minimization
            self.assertIn("integrator", content)
            self.assertIn("steep", content)
            self.assertIn("emtol", content)
    
    def test_nvt_mdp_content(self):
        """Test NVT equilibration MDP content"""
        output_file = os.path.join(self.test_dir, "nvt.mdp")
        result = generate_mdp_file(mdp_type="nvt", output_file=output_file)
        
        with open(output_file, 'r') as f:
            content = f.read()
            # Check NVT-specific parameters
            self.assertIn("integrator", content)
            self.assertIn("md", content)
            self.assertIn("tcoupl", content)
            self.assertNotIn("pcoupl", content.replace("; pcoupl", ""))  # No pressure coupling
    
    def test_npt_mdp_content(self):
        """Test NPT equilibration MDP content"""
        output_file = os.path.join(self.test_dir, "npt.mdp")
        result = generate_mdp_file(mdp_type="npt", output_file=output_file)
        
        with open(output_file, 'r') as f:
            content = f.read()
            # Check NPT-specific parameters
            self.assertIn("pcoupl", content)  # Pressure coupling enabled
            self.assertIn("Parrinello-Rahman", content)


if __name__ == '__main__':
    unittest.main()
