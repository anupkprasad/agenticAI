#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions to load and use protein information from JSON file
"""
import json
import os

def load_protein_info(json_path="/mnt/mydrive/pseudokinase/protein_info.json"):
    """
    Load protein information from JSON file
    
    Returns:
        dict: Complete protein information dictionary
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Protein info file not found: {json_path}")
    
    with open(json_path, 'r') as f:
        protein_data = json.load(f)
    
    return protein_data

def get_protein_name(uniprot_id, protein_data=None):
    """
    Get protein name from UniProt ID
    
    Args:
        uniprot_id (str): UniProt identifier
        protein_data (dict, optional): Pre-loaded protein data
    
    Returns:
        str: Protein name or UniProt ID if not found
    """
    if protein_data is None:
        protein_data = load_protein_info()
    
    return protein_data['proteins'].get(uniprot_id, {}).get('name', uniprot_id)

def get_binding_type(uniprot_id, protein_data=None):
    """
    Get binding type from UniProt ID
    
    Args:
        uniprot_id (str): UniProt identifier
        protein_data (dict, optional): Pre-loaded protein data
    
    Returns:
        str: Binding type or 'Unknown' if not found
    """
    if protein_data is None:
        protein_data = load_protein_info()
    
    return protein_data['proteins'].get(uniprot_id, {}).get('binding_type', 'Unknown')

def get_binding_type_color(binding_type, protein_data=None):
    """
    Get color for a binding type
    
    Args:
        binding_type (str): Binding type
        protein_data (dict, optional): Pre-loaded protein data
    
    Returns:
        str: Hex color code or default gray
    """
    if protein_data is None:
        protein_data = load_protein_info()
    
    return protein_data['binding_types'].get(binding_type, {}).get('color', '#808080')

def get_all_protein_names(protein_data=None):
    """
    Get dictionary mapping UniProt IDs to protein names
    
    Args:
        protein_data (dict, optional): Pre-loaded protein data
    
    Returns:
        dict: {uniprot_id: protein_name}
    """
    if protein_data is None:
        protein_data = load_protein_info()
    
    return {uid: info['name'] for uid, info in protein_data['proteins'].items()}

def get_all_binding_types(protein_data=None, binding_type_field='binding_type_JM'):
    """
    Get dictionary mapping UniProt IDs to binding types
    
    Args:
        protein_data (dict, optional): Pre-loaded protein data
        binding_type_field (str): Which binding type field to use ('binding_type_JM', 'binding_type_visAMP', 'binding_lig_mg')
    
    Returns:
        dict: {uniprot_id: binding_type}
    """
    if protein_data is None:
        protein_data = load_protein_info()
    
    return {uid: info.get(binding_type_field, 'Unknown') for uid, info in protein_data['proteins'].items()}

def add_protein(uniprot_id, name, binding_type, description="", family="Pseudokinase", 
                organism="Unknown", json_path="/mnt/mydrive/pseudokinase/protein_info.json"):
    """
    Add a new protein to the JSON file
    
    Args:
        uniprot_id (str): UniProt identifier
        name (str): Protein name
        binding_type (str): Binding type
        description (str, optional): Protein description
        family (str, optional): Protein family
        organism (str, optional): Organism name
        json_path (str, optional): Path to JSON file
    """
    protein_data = load_protein_info(json_path)
    
    protein_data['proteins'][uniprot_id] = {
        'name': name,
        'binding_type': binding_type,
        'description': description,
        'family': family,
        'organism': organism
    }
    
    # Update total count
    protein_data['metadata']['total_proteins'] = len(protein_data['proteins'])
    
    # Save back to file
    with open(json_path, 'w') as f:
        json.dump(protein_data, f, indent=2)
    
    print(f"Added protein {uniprot_id} ({name}) to database")

def print_protein_summary(protein_data=None, binding_type_field='binding_type_JM'):
    """
    Print a summary of all proteins in the database
    
    Args:
        protein_data (dict, optional): Pre-loaded protein data
        binding_type_field (str): Which binding type field to use for summary
    """
    if protein_data is None:
        protein_data = load_protein_info()
    
    print(f"Protein Database Summary")
    print(f"Version: {protein_data['metadata']['version']}")
    print(f"Total proteins: {protein_data['metadata']['total_proteins']}")
    print(f"Created: {protein_data['metadata']['created_date']}")
    print(f"Using binding type field: {binding_type_field}")
    print()
    
    print(f"{'UniProt ID':<12} {'Name':<12} {'Binding Type':<30} {'Description':<40}")
    print("-" * 110)
    
    for uid, info in sorted(protein_data['proteins'].items()):
        binding_type = info.get(binding_type_field, 'Unknown')
        description = info.get('description', 'N/A')[:38]  # Truncate long descriptions
        print(f"{uid:<12} {info['name']:<12} {binding_type:<30} {description:<40}")
    
    print()
    print("Binding Type Distribution:")
    binding_counts = {}
    for info in protein_data['proteins'].values():
        bt = info.get(binding_type_field, 'Unknown')
        binding_counts[bt] = binding_counts.get(bt, 0) + 1
    
    for bt, count in sorted(binding_counts.items()):
        # Try to get color from binding_types, but handle cases where the specific binding type isn't defined
        color = '#808080'  # Default gray
        # Extract base binding type for color lookup (e.g., 'Nucleotide-Cation-binding-Mg1' -> 'Nucleotide-Cation-binding')
        for base_type in protein_data['binding_types'].keys():
            if bt.startswith(base_type):
                color = protein_data['binding_types'][base_type].get('color', '#808080')
                break
        print(f"  {bt:<30}: {count:>2} proteins (color: {color})")

if __name__ == "__main__":
    # Example usage
    try:
        # Load protein data
        data = load_protein_info()
        
        # Print summary
        print_protein_summary(data)
        
        # Example queries
        print("\nExample queries:")
        print(f"Q27007 name: {get_protein_name('Q27007', data)}")
        print(f"Q27007 binding type: {get_binding_type('Q27007', data)}")
        print(f"Cation-binding color: {get_binding_type_color('Cation-binding', data)}")
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Make sure the protein_info.json file exists in the correct location.")
