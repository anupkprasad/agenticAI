"""Workflow Visualization Utility

This module provides functionality to visualize the actual LangGraph MD workflow
by introspecting the real workflow structure from md_workflow.py
"""
import os
import logging
import inspect
from typing import Dict, List, Tuple, Optional, Set, Any
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.patches import FancyBboxPatch
    import networkx as nx
    VISUALIZATION_AVAILABLE = True
    DiGraph = nx.DiGraph
except ImportError:
    VISUALIZATION_AVAILABLE = False
    plt = None
    patches = None
    nx = None
    DiGraph = Any  # Fallback type for when NetworkX not available

logger = logging.getLogger(__name__)

class WorkflowVisualizer:
    """
    Creates visual representations of the actual MD workflow graph by 
    introspecting the LangGraph structure.
    """
    
    def __init__(self):
        if not VISUALIZATION_AVAILABLE:
            logger.warning("Visualization libraries not available. Install with: pip install matplotlib networkx")
            return
            
        self.node_colors = {
            'supervisor': '#FF6B6B',      # Red - Controller
            'input_validation': '#4ECDC4', # Teal - Input
            'preprocess': '#45B7D1',      # Blue - Processing
            'setup': '#96CEB4',           # Green - Setup
            'human_preprocess_check': '#FFEAA7', # Yellow - Human
            'human_setup_check': '#FFEAA7',      # Yellow - Human
            'final_report': '#DDA0DD',    # Purple - Output
            '__start__': '#90EE90',       # Light Green
            '__end__': '#FFB6C1'          # Light Pink
        }
        
        self.node_shapes = {
            'supervisor': 'diamond',
            'input_validation': 'box',
            'preprocess': 'box',
            'setup': 'box', 
            'human_preprocess_check': 'ellipse',
            'human_setup_check': 'ellipse',
            'final_report': 'box',
            '__start__': 'box',
            '__end__': 'box'
        }
        
        self.node_descriptions = {
            'supervisor': 'Supervisor\n(Route Controller)',
            'input_validation': 'Input Validation\n(Extract PDB)',
            'preprocess': 'Preprocessing\n(Clean PDB)',
            'setup': 'System Setup\n(Solvation & Ions)',
            'human_preprocess_check': 'Human Checkpoint\n(Review Cleaning)',
            'human_setup_check': 'Human Checkpoint\n(Review Setup)',
            'final_report': 'Final Report\n(Summary)',
            '__start__': 'START',
            '__end__': 'END'
        }

    def extract_actual_workflow_graph(self):
        """
        Extract the actual workflow graph by introspecting the MDWorkflow class.
        """
        if not VISUALIZATION_AVAILABLE:
            logger.error("Cannot create graph - visualization libraries not available")
            return None
            
        try:
            # Import and instantiate the actual workflow
            from .md_workflow import MDWorkflow
            from .llm import LLMClient
            
            # Create a minimal LLM client for graph construction
            llm_client = LLMClient(model="test")
            workflow_instance = MDWorkflow(llm_client)
            
            # Access the compiled LangGraph
            langgraph = workflow_instance.graph
            
            # Extract nodes and edges from the actual LangGraph
            G = nx.DiGraph()
            
            # Get all nodes from the LangGraph
            nodes = self._extract_nodes_from_langgraph(langgraph)
            edges = self._extract_edges_from_langgraph(langgraph)
            
            # Add nodes to NetworkX graph
            for node in nodes:
                G.add_node(node, 
                          label=self.node_descriptions.get(node, node.replace('_', ' ').title()),
                          color=self.node_colors.get(node, '#CCCCCC'),
                          shape=self.node_shapes.get(node, 'box'))
            
            # Add edges to NetworkX graph
            for source, targets in edges.items():
                if isinstance(targets, list):
                    for target in targets:
                        G.add_edge(source, target, label='')
                elif isinstance(targets, dict):
                    for condition, target in targets.items():
                        label = condition if condition not in ['__start__', '__end__'] else ''
                        G.add_edge(source, target, label=label)
                else:
                    G.add_edge(source, targets, label='')
                    
            return G
            
        except Exception as e:
            logger.error(f"Failed to extract actual workflow graph: {e}")
            return self._create_fallback_graph()

    def _extract_nodes_from_langgraph(self, langgraph) -> List[str]:
        """Extract node names from the LangGraph instance."""
        try:
            # Try to access nodes from the graph
            if hasattr(langgraph, 'nodes'):
                nodes = list(langgraph.nodes.keys())
            elif hasattr(langgraph, '_nodes'):
                nodes = list(langgraph._nodes.keys()) 
            elif hasattr(langgraph, 'graph') and hasattr(langgraph.graph, 'nodes'):
                nodes = list(langgraph.graph.nodes())
            else:
                # Fallback: inspect the graph structure
                nodes = []
                for attr_name in dir(langgraph):
                    if 'node' in attr_name.lower():
                        attr_value = getattr(langgraph, attr_name)
                        if callable(attr_value) or isinstance(attr_value, dict):
                            continue
                        nodes.append(attr_name)
            
            # Ensure we have start and end nodes
            if '__start__' not in nodes:
                nodes.insert(0, '__start__')
            if '__end__' not in nodes:
                nodes.append('__end__')
                
            logger.info(f"Extracted nodes: {nodes}")
            return nodes
            
        except Exception as e:
            logger.warning(f"Could not extract nodes from LangGraph: {e}")
            return ['__start__', 'supervisor', 'input_validation', 'preprocess', 
                   'setup', 'human_preprocess_check', 'human_setup_check', 
                   'final_report', '__end__']

    def _extract_edges_from_langgraph(self, langgraph) -> Dict[str, List]:
        """Extract edges from the LangGraph instance."""
        try:
            edges = {}
            
            # Try different ways to access the graph structure
            if hasattr(langgraph, 'edges'):
                raw_edges = langgraph.edges
            elif hasattr(langgraph, '_edges'):
                raw_edges = langgraph._edges
            elif hasattr(langgraph, 'graph') and hasattr(langgraph.graph, 'edges'):
                raw_edges = langgraph.graph.edges()
            else:
                logger.warning("Could not find edges in LangGraph")
                return self._create_fallback_edges()
            
            # Process the edges
            if isinstance(raw_edges, dict):
                for source, target_info in raw_edges.items():
                    if isinstance(target_info, dict):
                        edges[source] = target_info
                    else:
                        edges[source] = [target_info] if not isinstance(target_info, list) else target_info
            else:
                # Handle edge list format
                for edge in raw_edges:
                    if isinstance(edge, tuple) and len(edge) >= 2:
                        source, target = edge[0], edge[1]
                        if source not in edges:
                            edges[source] = []
                        edges[source].append(target)
            
            logger.info(f"Extracted edges: {edges}")
            return edges
            
        except Exception as e:
            logger.warning(f"Could not extract edges from LangGraph: {e}")
            return self._create_fallback_edges()

    def _create_fallback_graph(self):
        """Create a fallback graph when introspection fails."""
        logger.info("Creating fallback workflow graph")
        
        G = nx.DiGraph()
        
        # Add nodes
        nodes = [
            '__start__',
            'supervisor', 
            'input_validation',
            'preprocess',
            'setup',
            'human_preprocess_check',
            'human_setup_check', 
            'final_report',
            '__end__'
        ]
        
        for node in nodes:
            G.add_node(node, 
                      label=self.node_descriptions.get(node, node.replace('_', ' ').title()),
                      color=self.node_colors.get(node, '#CCCCCC'),
                      shape=self.node_shapes.get(node, 'box'))
        
        # Add edges based on the actual workflow logic
        edges = [
            ('__start__', 'supervisor', 'Entry'),
            ('supervisor', 'input_validation', 'No PDB'),
            ('input_validation', 'supervisor', 'PDB Found'),
            ('supervisor', 'preprocess', 'Need Clean'),
            ('preprocess', 'supervisor', 'Complete'),
            ('preprocess', 'human_preprocess_check', 'Issues'),
            ('human_preprocess_check', 'supervisor', 'Approved'),
            ('human_preprocess_check', 'preprocess', 'Retry'),
            ('supervisor', 'setup', 'Need Setup'),
            ('setup', 'supervisor', 'Complete'),
            ('setup', 'human_setup_check', 'Issues'),
            ('human_setup_check', 'supervisor', 'Approved'),
            ('human_setup_check', 'setup', 'Retry'),
            ('supervisor', 'final_report', 'All Done'),
            ('final_report', '__end__', 'Finished')
        ]
        
        for source, target, label in edges:
            G.add_edge(source, target, label=label)
            
        return G

    def _create_fallback_edges(self) -> Dict[str, List]:
        """Create fallback edges when extraction fails."""
        return {
            '__start__': ['supervisor'],
            'supervisor': ['input_validation', 'preprocess', 'setup', 'final_report'],
            'input_validation': ['supervisor'],
            'preprocess': ['supervisor', 'human_preprocess_check'],
            'human_preprocess_check': ['supervisor', 'preprocess'],
            'setup': ['supervisor', 'human_setup_check'],
            'human_setup_check': ['supervisor', 'setup'],
            'final_report': ['__end__']
        }

    def visualize_workflow(self, output_file: str = "md_workflow_graph.png", 
                          figsize: Tuple[int, int] = (16, 12),
                          dpi: int = 300, 
                          use_actual_graph: bool = True) -> bool:
        """
        Create and save a visualization of the MD workflow.
        
        Args:
            output_file: Output PNG file path
            figsize: Figure size (width, height) in inches
            dpi: Image resolution
            use_actual_graph: If True, extract from actual LangGraph; if False, use static
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not VISUALIZATION_AVAILABLE:
            logger.error("Cannot visualize - matplotlib and networkx not available")
            logger.info("Install with: pip install matplotlib networkx")
            return False
            
        try:
            # Get the graph
            if use_actual_graph:
                G = self.extract_actual_workflow_graph()
                title = 'MD Workflow - Current LangGraph Structure'
            else:
                G = self._create_fallback_graph()
                title = 'MD Workflow - Static Structure'
                
            if G is None:
                return False
                
            # Create figure
            fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
            
            # Use hierarchical layout
            pos = self._create_hierarchical_layout(G)
            
            # Draw edges first (so they appear behind nodes)
            self._draw_edges(G, pos, ax)
            
            # Draw nodes
            self._draw_nodes(G, pos, ax)
            
            # Add title and labels
            ax.set_title(title, fontsize=20, fontweight='bold', pad=20)
            
            # Add metadata
            node_count = len(G.nodes())
            edge_count = len(G.edges())
            ax.text(0.02, 0.02, f'Nodes: {node_count} | Edges: {edge_count}', 
                   transform=ax.transAxes, fontsize=10,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgray', alpha=0.7))
            
            # Add legend
            self._add_legend(ax)
            
            # Clean up the plot
            ax.set_xlim(-1.5, 1.5)
            ax.set_ylim(-1.2, 1.2)
            ax.axis('off')
            
            # Save the figure
            plt.tight_layout()
            plt.savefig(output_file, dpi=dpi, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()
            
            logger.info(f"Workflow visualization saved to: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create workflow visualization: {e}")
            return False

    def _create_hierarchical_layout(self, G) -> Dict:
        """Create a hierarchical layout for the workflow graph."""
        # Define layers from top to bottom - handle both START/END and __start__/__end__
        layers = {
            0: ['START', '__start__'],
            1: ['supervisor'],
            2: ['input_validation'],
            3: ['preprocess', 'human_preprocess_check'],
            4: ['setup', 'human_setup_check'],
            5: ['final_report'],
            6: ['END', '__end__']
        }
        
        pos = {}
        layer_height = 0.3
        
        for layer_idx, nodes in layers.items():
            # Only consider nodes that actually exist in the graph
            existing_nodes = [node for node in nodes if G.has_node(node)]
            
            if not existing_nodes:
                continue
                
            y = 1.0 - (layer_idx * layer_height)
            
            if len(existing_nodes) == 1:
                pos[existing_nodes[0]] = (0, y)
            else:
                # Distribute nodes horizontally
                x_positions = []
                if len(existing_nodes) == 2:
                    x_positions = [-0.4, 0.4]
                else:
                    x_positions = [i * 0.3 - (len(existing_nodes)-1) * 0.15 for i in range(len(existing_nodes))]
                
                for i, node in enumerate(existing_nodes):
                    pos[node] = (x_positions[i], y)
        
        return pos

    def _draw_edges(self, G, pos: Dict, ax):
        """Draw edges with labels."""
        for edge in G.edges(data=True):
            source, target, data = edge
            
            # Get positions
            x1, y1 = pos[source]
            x2, y2 = pos[target]
            
            # Determine edge style based on type
            if 'Retry' in data.get('label', ''):
                edge_style = '--'
                edge_color = '#FF6B6B'
                alpha = 0.7
            elif 'Human' in source or 'Human' in target:
                edge_style = '-'
                edge_color = '#FFA500'
                alpha = 0.8
            else:
                edge_style = '-'
                edge_color = '#666666'
                alpha = 0.8
            
            # Draw arrow
            ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                       arrowprops=dict(arrowstyle='->', 
                                     color=edge_color,
                                     alpha=alpha,
                                     linestyle=edge_style,
                                     linewidth=1.5))
            
            # Add edge label
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
            ax.text(mid_x, mid_y, data.get('label', ''), 
                   fontsize=8, ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                           alpha=0.8, edgecolor='none'))

    def _draw_nodes(self, G, pos: Dict, ax):
        """Draw nodes with labels and colors."""
        for node, (x, y) in pos.items():
            node_data = G.nodes[node]
            color = node_data.get('color', '#CCCCCC')
            label = node_data.get('label', node)
            shape = node_data.get('shape', 'box')
            
            # Determine node size based on type
            if node in ['START', 'END']:
                width, height = 0.15, 0.08
                fontsize = 10
            elif 'human' in node:
                width, height = 0.25, 0.12
                fontsize = 9
            elif node == 'supervisor':
                width, height = 0.2, 0.1
                fontsize = 9
            else:
                width, height = 0.22, 0.1
                fontsize = 9
            
            # Create node shape
            if shape == 'diamond':
                # Diamond shape for supervisor
                diamond = patches.RegularPolygon((x, y), 4, radius=0.12,
                                               orientation=3.14159/4,
                                               facecolor=color, 
                                               edgecolor='black',
                                               linewidth=2)
                ax.add_patch(diamond)
            elif shape == 'ellipse':
                # Ellipse for human checkpoints
                ellipse = patches.Ellipse((x, y), width, height,
                                        facecolor=color,
                                        edgecolor='black',
                                        linewidth=2)
                ax.add_patch(ellipse)
            else:
                # Rectangle for regular nodes
                rect = FancyBboxPatch((x - width/2, y - height/2), 
                                    width, height,
                                    boxstyle="round,pad=0.01",
                                    facecolor=color,
                                    edgecolor='black',
                                    linewidth=2)
                ax.add_patch(rect)
            
            # Add node label
            ax.text(x, y, label, ha='center', va='center', 
                   fontsize=fontsize, fontweight='bold',
                   wrap=True)

    def _add_legend(self, ax):
        """Add a legend explaining the node types."""
        legend_elements = [
            patches.Patch(color='#FF6B6B', label='Controller (Supervisor)'),
            patches.Patch(color='#4ECDC4', label='Input Processing'),
            patches.Patch(color='#45B7D1', label='PDB Processing'), 
            patches.Patch(color='#96CEB4', label='System Setup'),
            patches.Patch(color='#FFEAA7', label='Human Checkpoints'),
            patches.Patch(color='#DDA0DD', label='Output/Report'),
            patches.Patch(color='#90EE90', label='Start/End Nodes')
        ]
        
        ax.legend(handles=legend_elements, loc='upper left', 
                 bbox_to_anchor=(0.02, 0.98), fontsize=10)

def create_workflow_diagram(output_file: str = "md_workflow_graph.png", 
                          use_actual_graph: bool = True) -> bool:
    """
    Convenience function to create and save workflow diagram from actual LangGraph.
    
    Args:
        output_file: Output PNG file path
        use_actual_graph: If True, extract from actual LangGraph structure
        
    Returns:
        bool: True if successful, False otherwise
    """
    visualizer = WorkflowVisualizer()
    return visualizer.visualize_workflow(output_file, use_actual_graph=use_actual_graph)

def create_current_workflow_diagram(output_file: str = "current_md_workflow.png") -> bool:
    """
    Create diagram of the current actual workflow structure.
    This will reflect any changes you make to md_workflow.py
    """
    return create_workflow_diagram(output_file, use_actual_graph=True)

def create_static_workflow_diagram(output_file: str = "static_md_workflow.png") -> bool:
    """
    Create diagram of the static workflow structure (fallback).
    """
    return create_workflow_diagram(output_file, use_actual_graph=False)

def check_visualization_dependencies() -> bool:
    """Check if required visualization libraries are available."""
    return VISUALIZATION_AVAILABLE

def get_workflow_info() -> Dict[str, any]:
    """
    Get information about the current workflow structure.
    Returns node and edge counts, and whether introspection worked.
    """
    visualizer = WorkflowVisualizer()
    
    try:
        G = visualizer.extract_actual_workflow_graph()
        if G:
            return {
                "introspection_success": True,
                "node_count": len(G.nodes()),
                "edge_count": len(G.edges()),
                "nodes": list(G.nodes()),
                "visualization_available": VISUALIZATION_AVAILABLE
            }
    except Exception as e:
        logger.warning(f"Could not introspect workflow: {e}")
    
    return {
        "introspection_success": False,
        "fallback_used": True,
        "visualization_available": VISUALIZATION_AVAILABLE
    }

if __name__ == "__main__":
    # Test the visualization when run directly
    if check_visualization_dependencies():
        print("Creating workflow visualization from actual LangGraph...")
        
        # Get workflow info
        info = get_workflow_info()
        print(f"Workflow info: {info}")
        
        # Create current workflow diagram
        success = create_current_workflow_diagram("test_current_workflow.png")
        if success:
            print("✅ Current workflow diagram created successfully!")
        else:
            print("❌ Failed to create current workflow diagram")
            
        # Also create static fallback for comparison
        fallback_success = create_static_workflow_diagram("test_static_workflow.png") 
        if fallback_success:
            print("✅ Static workflow diagram created for comparison!")
            
    else:
        print("❌ Visualization dependencies not available")
        print("Install with: pip install matplotlib networkx")
