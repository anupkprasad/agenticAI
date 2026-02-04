"""
Unit Tests for Preprocessing Modular Tools
Tests all @tool functions in src/preprocess/
"""
import unittest
import os
import tempfile
import shutil
from pathlib import Path

# Import tools - access .func to get underlying function from @tool decorator
from src.preprocess.pdb_analyzer import analyze_pdb
from src.preprocess.water_remover import remove_waters
from src.preprocess.altloc_handler import handle_alternate_locations
from src.preprocess.hydrogen_adder import add_hydrogens
from src.preprocess.protonation_assigner import assign_protonation
from src.preprocess.structure_validator import validate_structure

# Get the actual functions from StructuredTool objects
analyze_pdb = analyze_pdb.func if hasattr(analyze_pdb, 'func') else analyze_pdb
remove_waters = remove_waters.func if hasattr(remove_waters, 'func') else remove_waters
handle_alternate_locations = handle_alternate_locations.func if hasattr(handle_alternate_locations, 'func') else handle_alternate_locations
add_hydrogens = add_hydrogens.func if hasattr(add_hydrogens, 'func') else add_hydrogens
assign_protonation = assign_protonation.func if hasattr(assign_protonation, 'func') else assign_protonation
validate_structure = validate_structure.func if hasattr(validate_structure, 'func') else validate_structure


class TestPreprocessingTools(unittest.TestCase):
    """Test suite for preprocessing tools"""
    
    def setUp(self):
        """Create temporary directory and test PDB files"""
        self.test_dir = tempfile.mkdtemp()
        self.test_pdb = self._create_test_pdb()
        self.test_pdb_with_waters = self._create_test_pdb_with_waters()
        self.test_pdb_with_altloc = self._create_test_pdb_with_altloc()
    
    def tearDown(self):
        """Clean up temporary files"""
        shutil.rmtree(self.test_dir)
    
    def _create_test_pdb(self):
        """Create a minimal test PDB file"""
        pdb_content = """ATOM      1  N   MET A   1      27.340  24.430   2.614  1.00  0.00           N
ATOM      2  CA  MET A   1      26.266  25.413   2.842  1.00  0.00           C
ATOM      3  C   MET A   1      26.913  26.639   3.531  1.00  0.00           C
ATOM      4  O   MET A   1      27.886  26.463   4.263  1.00  0.00           O
END
"""
        pdb_file = os.path.join(self.test_dir, "test.pdb")
        with open(pdb_file, 'w') as f:
            f.write(pdb_content)
        return pdb_file
    
    def _create_test_pdb_with_waters(self):
        """Create test PDB with water molecules"""
        pdb_content = """ATOM      1  N   MET A   1      27.340  24.430   2.614  1.00  0.00           N
ATOM      2  CA  MET A   1      26.266  25.413   2.842  1.00  0.00           C
HETATM    3  O   HOH A 101      10.000  10.000  10.000  1.00  0.00           O
HETATM    4  O   HOH A 102      20.000  20.000  20.000  1.00  0.00           O
END
"""
        pdb_file = os.path.join(self.test_dir, "test_waters.pdb")
        with open(pdb_file, 'w') as f:
            f.write(pdb_content)
        return pdb_file
    
    def _create_test_pdb_with_altloc(self):
        """Create test PDB with alternate locations"""
        pdb_content = """ATOM      1  N   MET A   1      27.340  24.430   2.614  1.00  0.50           N
ATOM      2  N  AMET A   1      27.350  24.440   2.624  1.00  0.50           N
ATOM      3  CA  MET A   1      26.266  25.413   2.842  1.00  1.00           C
END
"""
        pdb_file = os.path.join(self.test_dir, "test_altloc.pdb")
        with open(pdb_file, 'w') as f:
            f.write(pdb_content)
        return pdb_file
    
    def test_analyze_pdb(self):
        """Test PDB analysis tool"""
        result = analyze_pdb(self.test_pdb)
        
        self.assertTrue(result["success"])
        analysis = result.get("analysis", {})
        self.assertGreater(analysis.get("atom_count", 0), 0)
        self.assertIn("chain_ids", analysis)
    
    def test_analyze_pdb_nonexistent(self):
        """Test PDB analysis with nonexistent file"""
        result = analyze_pdb("nonexistent.pdb")
        self.assertFalse(result["success"])
        self.assertIn("error", result)
    
    def test_remove_waters(self):
        """Test water removal tool"""
        output_file = os.path.join(self.test_dir, "no_waters.pdb")
        result = remove_waters(self.test_pdb_with_waters, output_file=output_file)
        
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(result.get("removed_count", 0), 0)
        
        # Verify waters were removed
        with open(output_file, 'r') as f:
            content = f.read()
            self.assertNotIn("HOH", content)
    
    def test_handle_alternate_locations(self):
        """Test alternate location handler"""
        output_file = os.path.join(self.test_dir, "no_altloc.pdb")
        result = handle_alternate_locations(
            self.test_pdb_with_altloc,
            output_file=output_file,
            keep_occupancy="highest"
        )
        
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(result.get("alternate_locations_resolved", 0), 0)
    
    def test_add_hydrogens_no_tool(self):
        """Test hydrogen addition with no tool (fallback)"""
        output_file = os.path.join(self.test_dir, "with_h.pdb")
        result = add_hydrogens(
            self.test_pdb,
            output_file=output_file,
            method="none"
        )
        
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(output_file))
        self.assertEqual(result.get("method"), "none")
    
    def test_assign_protonation_copy(self):
        """Test protonation assignment with copy method"""
        output_file = os.path.join(self.test_dir, "protonated.pdb")
        result = assign_protonation(
            self.test_pdb,
            output_file=output_file,
            ph=7.0,
            method="copy"
        )
        
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(output_file))
        self.assertEqual(result.get("ph"), 7.0)
    
    def test_validate_structure(self):
        """Test structure validation"""
        result = validate_structure(self.test_pdb)
        
        self.assertTrue(result["success"])
        self.assertGreater(result.get("atoms", 0), 0)
        self.assertIn("issues", result)
        self.assertIn("warnings", result)
    
    def test_validate_structure_nonexistent(self):
        """Test validation with nonexistent file"""
        result = validate_structure("nonexistent.pdb")
        self.assertFalse(result["success"])


class TestPreprocessingToolsIntegration(unittest.TestCase):
    """Integration tests for preprocessing tool chains"""
    
    def setUp(self):
        """Create temporary directory and test PDB files"""
        self.test_dir = tempfile.mkdtemp()
        self.test_pdb = self._create_complex_pdb()
    
    def tearDown(self):
        """Clean up temporary files"""
        shutil.rmtree(self.test_dir)
    
    def _create_complex_pdb(self):
        """Create a complex test PDB with waters and alternate locations"""
        pdb_content = """ATOM      1  N   MET A   1      27.340  24.430   2.614  1.00  0.50           N
ATOM      2  N  AMET A   1      27.350  24.440   2.624  1.00  0.50           N
ATOM      3  CA  MET A   1      26.266  25.413   2.842  1.00  1.00           C
HETATM    4  O   HOH A 101      10.000  10.000  10.000  1.00  0.00           O
HETATM    5  O   HOH A 102      20.000  20.000  20.000  1.00  0.00           O
END
"""
        pdb_file = os.path.join(self.test_dir, "complex.pdb")
        with open(pdb_file, 'w') as f:
            f.write(pdb_content)
        return pdb_file
    
    def test_full_preprocessing_pipeline(self):
        """Test complete preprocessing pipeline"""
        current_pdb = self.test_pdb
        
        # Step 1: Analyze
        analysis = analyze_pdb(current_pdb)
        self.assertTrue(analysis["success"])
        
        # Step 2: Remove waters
        if analysis.get("analysis", {}).get("has_waters"):
            result = remove_waters(current_pdb, 
                                  output_file=os.path.join(self.test_dir, "step1.pdb"))
            self.assertTrue(result["success"])
            current_pdb = result["output_file"]
        
        # Step 3: Handle alternate locations
        result = handle_alternate_locations(current_pdb,
                                           output_file=os.path.join(self.test_dir, "step2.pdb"))
        self.assertTrue(result["success"])
        current_pdb = result["output_file"]
        
        # Step 4: Validate final structure
        validation = validate_structure(current_pdb)
        self.assertTrue(validation["success"])
        self.assertEqual(len(validation.get("issues", [])), 0)


if __name__ == '__main__':
    unittest.main()
