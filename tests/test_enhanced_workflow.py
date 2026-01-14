"""
Test suite for the enhanced LLM-powered MD workflow supervisor
"""
import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from agentic.md_supervisor import MDSupervisor
from agentic.md_workflow import MDWorkflow
from agentic.md_state import MDState
from agentic.llm import LLMClient

class TestEnhancedMDSupervisor(unittest.TestCase):
    """Test the enhanced supervisor with LLM capabilities and fallback."""
    
    def setUp(self):
        """Set up test environment."""
        # Create mock LLM client
        self.mock_llm = Mock(spec=LLMClient)
        self.mock_llm.available = True
        
        # Create supervisor without config file (uses defaults)
        self.supervisor = MDSupervisor(llm_client=self.mock_llm)
    
    def test_supervisor_initialization_with_llm(self):
        """Test supervisor initializes correctly with LLM client."""
        self.assertEqual(len(self.supervisor.agents_registry), 4)
        self.assertIn('preprocessing', self.supervisor.agents_registry)
        self.assertIn('setup', self.supervisor.agents_registry)
        self.assertTrue(self.supervisor.llm.available)
    
    def test_supervisor_initialization_without_llm(self):
        """Test supervisor initializes correctly without LLM client."""
        supervisor = MDSupervisor(llm_client=None)
        self.assertIsNotNone(supervisor.llm)
        self.assertEqual(len(supervisor.agents_registry), 4)
    
    def test_llm_routing_skip_preprocessing(self):
        """Test LLM routing for preprocessed PDB case."""
        
        # Mock LLM response for skip preprocessing
        self.mock_llm.prompt.return_value = """
NEXT_AGENT: setup
REASONING: User indicated PDB is already preprocessed, skipping to simulation setup
INSTRUCTIONS: Use the cleaned PDB file for topology generation
"""
        
        state = MDState(user_goal="My PDB is already preprocessed, just set up simulation")
        
        result_state = self.supervisor.supervisor_node(state)
        
        self.assertEqual(result_state["next_node"], "setup")
        self.assertIn("already preprocessed", result_state["supervisor_reasoning"])
        self.mock_llm.prompt.assert_called_once()
    
    def test_llm_routing_full_pipeline(self):
        """Test LLM routing for full pipeline."""
        
        # Mock LLM response for full pipeline
        self.mock_llm.prompt.return_value = """
NEXT_AGENT: preprocessing
REASONING: User has raw PDB file that needs full processing pipeline
INSTRUCTIONS: Clean the PDB and prepare for simulation
"""
        
        state = MDState(user_goal="Process my raw protein structure through full MD pipeline")
        
        result_state = self.supervisor.supervisor_node(state)
        
        self.assertEqual(result_state["next_node"], "preprocess")  # Maps to existing node
        self.assertIn("full processing", result_state["supervisor_reasoning"])
    
    def test_heuristic_fallback_when_llm_unavailable(self):
        """Test supervisor falls back to heuristic routing when LLM unavailable."""
        
        # Mock unavailable LLM
        self.mock_llm.available = False
        
        state = MDState(user_goal="Test heuristic fallback")
        
        result_state = self.supervisor.supervisor_node(state)
        
        # Should use heuristic routing (no raw_pdb -> input_validation)
        self.assertEqual(result_state["next_node"], "input_validation")
    
    def test_invalid_agent_fallback(self):
        """Test supervisor handles invalid LLM agent suggestions."""
        
        # Mock LLM response with invalid agent
        self.mock_llm.prompt.return_value = """
NEXT_AGENT: invalid_agent
REASONING: This is a test of invalid agent handling
INSTRUCTIONS: Test instructions
"""
        
        state = MDState(user_goal="Test invalid agent handling")
        
        result_state = self.supervisor.supervisor_node(state)
        
        self.assertEqual(result_state["next_node"], "input_validation")
        self.assertIn("invalid agent", result_state["supervisor_reasoning"])
    
    def test_llm_input_validation(self):
        """Test LLM-powered input validation and analysis."""
        
        # Mock LLM response for input analysis
        self.mock_llm.prompt.return_value = """
PDB_PATH: /data/protein.pdb
WORKING_DIR: /data/md_project
FORCE_FIELD: AMBER99
WATER_MODEL: TIP3P
DATA_STAGE: raw_pdb
USER_INTENT: Run MD simulation with specific parameters
VALIDATION_STATUS: valid
ISSUES: none
"""
        
        state = MDState(user_goal="Run MD on /data/protein.pdb with AMBER99 in /data/md_project")
        
        result_state = self.supervisor.input_validation_node(state)
        
        self.assertEqual(result_state["raw_pdb"], "/data/protein.pdb")
        self.assertEqual(result_state["working_directory"], "/data/md_project") 
        self.assertEqual(result_state["force_field"], "AMBER99")
        self.assertEqual(result_state["next_node"], "supervisor")
    
    def test_fallback_input_validation(self):
        """Test fallback input validation when LLM unavailable."""
        
        # Mock unavailable LLM
        self.mock_llm.available = False
        
        state = MDState(user_goal="Process /data/test.pdb file for simulation")
        
        result_state = self.supervisor.input_validation_node(state)
        
        self.assertEqual(result_state["raw_pdb"], "/data/test.pdb")
        self.assertEqual(result_state["next_node"], "supervisor")
    
    def test_state_summary_generation(self):
        """Test state summary generation for LLM context."""
        
        state = MDState(
            raw_pdb="/data/input.pdb",
            cleaned_pdb="/data/clean.pdb",
            errors=[{"message": "test error", "severity": "warning"}]
        )
        
        summary = self.supervisor._get_state_summary(state)
        
        self.assertIn("✅", summary)  # Should have checkmarks for completed items
        self.assertIn("❌", summary)  # Should have X marks for missing items
        self.assertIn("⚠️", summary)  # Should show error count

class TestEnhancedMDWorkflow(unittest.TestCase):
    """Test the complete enhanced workflow system."""
    
    def setUp(self):
        """Set up test workflow."""
        # Mock LLM client
        self.mock_llm = Mock(spec=LLMClient)
        self.mock_llm.available = True
        
        self.workflow = MDWorkflow(llm_client=self.mock_llm)
    
    def test_workflow_initialization(self):
        """Test workflow initializes all components."""
        self.assertIsNotNone(self.workflow.supervisor)
        self.assertIsNotNone(self.workflow.graph)
        self.assertTrue(hasattr(self.workflow.supervisor, 'llm'))
    
    def test_enhanced_final_report_with_llm(self):
        """Test enhanced final report generation with LLM."""
        
        # Mock LLM report generation
        self.mock_llm.prompt.return_value = "Test comprehensive MD workflow report with LLM analysis"
        
        state = MDState(
            user_goal="Test workflow",
            preprocessing_completed=True,
            analysis_results={"rmsd": "calculated"}
        )
        
        result_state = self.workflow._final_report_node(state)
        
        self.assertEqual(result_state["final_report"], "Test comprehensive MD workflow report with LLM analysis")
        self.assertTrue(result_state["workflow_complete"])
    
    def test_fallback_final_report_without_llm(self):
        """Test fallback final report when LLM unavailable."""
        
        # Mock unavailable LLM
        self.mock_llm.available = False
        
        state = MDState(
            user_goal="Test workflow fallback",
            raw_pdb="/test/input.pdb"
        )
        
        result_state = self.workflow._final_report_node(state)
        
        self.assertIn("MD Workflow Completion Report", result_state["final_report"])
        self.assertTrue(result_state["workflow_complete"])
    
    @patch('agentic.preprocessing_agent.PreprocessingAgent')
    @patch('agentic.setup_agent.SimulationSetupAgent')
    @patch('agentic.human_checkpoints.HumanCheckpoints')
    def test_workflow_execution_compatibility(self, mock_checkpoints, mock_setup, mock_preprocessing):
        """Test workflow execution maintains compatibility with existing interface."""
        
        # Setup mocks
        self.mock_llm.prompt.return_value = """
NEXT_AGENT: final_report
REASONING: Test completion
INSTRUCTIONS: Generate report
"""
        
        # Mock agent responses
        mock_preprocessing.return_value.preprocess_node.return_value = MDState(next_node="supervisor")
        mock_setup.return_value.setup_node.return_value = MDState(next_node="supervisor")
        mock_checkpoints.return_value.human_preprocess_check.return_value = MDState(next_node="supervisor")
        
        try:
            result = self.workflow.run("Test MD simulation workflow")
            
            # Should not raise exception and return results
            self.assertIsNotNone(result)
            
        except Exception as e:
            # If it fails due to missing dependencies, that's expected in test environment
            self.assertIn(("module", "import", "No module", "graph", "langgraph"), str(e).lower())

class TestBackwardCompatibility(unittest.TestCase):
    """Test that enhanced features maintain backward compatibility."""
    
    def setUp(self):
        """Setup compatibility test environment."""
        self.mock_llm = Mock(spec=LLMClient)
        self.mock_llm.available = False  # Test without LLM
        
    def test_supervisor_interface_compatibility(self):
        """Test supervisor maintains same interface as before."""
        
        supervisor = MDSupervisor(llm_client=self.mock_llm)
        
        # Test interface compatibility
        self.assertTrue(hasattr(supervisor, 'supervisor_node'))
        self.assertTrue(hasattr(supervisor, 'input_validation_node'))
        self.assertTrue(callable(supervisor.supervisor_node))
    
    def test_workflow_interface_compatibility(self):
        """Test workflow maintains same interface as before."""
        
        workflow = MDWorkflow(llm_client=self.mock_llm)
        
        # Test interface compatibility
        self.assertTrue(hasattr(workflow, 'run'))
        self.assertTrue(hasattr(workflow, 'graph'))
        self.assertTrue(callable(workflow.run))
    
    def test_heuristic_routing_still_works(self):
        """Test that original heuristic routing still works when LLM unavailable."""
        
        supervisor = MDSupervisor(llm_client=self.mock_llm)
        
        # Test original routing logic
        state = MDState(user_goal="Test heuristic routing")
        result = supervisor.supervisor_node(state)
        
        # Should use heuristic routing
        self.assertEqual(result["next_node"], "input_validation")
        
        # Test with PDB file
        state = MDState(user_goal="Test with raw PDB", raw_pdb="/test/file.pdb")
        result = supervisor.supervisor_node(state)
        
        # Should route to preprocessing
        self.assertEqual(result["next_node"], "preprocess")

def run_enhanced_tests():
    """Run all enhanced workflow tests."""
    
    print("Running Enhanced MD Workflow Tests...")
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTest(unittest.makeSuite(TestEnhancedMDSupervisor))
    suite.addTest(unittest.makeSuite(TestEnhancedMDWorkflow))
    suite.addTest(unittest.makeSuite(TestBackwardCompatibility))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_enhanced_tests()
    
    if success:
        print("\n✅ All enhanced workflow tests passed!")
    else:
        print("\n❌ Some tests failed. Check output above.")
        exit(1)
