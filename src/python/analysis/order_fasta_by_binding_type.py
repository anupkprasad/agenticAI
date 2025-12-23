#!/usr/bin/env python3
"""
Script to reorder FASTA sequences based on binding_type_visAMP from protein_info.json

Author: GitHub Copilot
Description: Reads protein information from JSON and reorders FASTA sequences
             in the order: No-binding -> Nucleotide-binding -> Cation-binding -> Nucleotide-Cation-binding
"""

import json
import sys
from pathlib import Path

def parse_fasta(fasta_file):
    """
    Parse FASTA file and return a dictionary of sequences
    Key: UniProt ID extracted from header
    Value: (header, sequence)
    """
    sequences = {}
    current_header = None
    current_seq = []
    
    with open(fasta_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                # Save previous sequence if exists
                if current_header:
                    sequences[uniprot_id] = (current_header, ''.join(current_seq))
                
                # Extract UniProt ID from header
                # Format: >KinDom1_194-469|>Q8NB16|MLKL_HUMAN|OS=Homo sapiens
                current_header = line
                parts = line.split('|')
                if len(parts) >= 2:
                    uniprot_id = parts[1].replace('>', '')
                else:
                    print(f"Warning: Could not extract UniProt ID from header: {line}")
                    uniprot_id = line.replace('>', '').split()[0]
                
                current_seq = []
            else:
                current_seq.append(line)
        
        # Save last sequence
        if current_header:
            sequences[uniprot_id] = (current_header, ''.join(current_seq))
    
    return sequences

def load_protein_info(json_file):
    """
    Load protein information from JSON file
    """
    with open(json_file, 'r') as f:
        data = json.load(f)
    return data['proteins']

def order_sequences_by_binding_type(sequences, protein_info):
    """
    Order sequences based on binding_type_visAMP in the specified order:
    1. No-binding
    2. Nucleotide-binding  
    3. Cation-binding
    4. Nucleotide-Cation-binding
    """
    
    # Define the desired order
    binding_order = [
        "No-binding",
        "Nucleotide-binding", 
        "Cation-binding",
        "Nucleotide-Cation-binding"
    ]
    
    # Group sequences by binding type
    grouped_sequences = {binding_type: [] for binding_type in binding_order}
    unmatched_sequences = []
    
    for uniprot_id, (header, sequence) in sequences.items():
        if uniprot_id in protein_info:
            binding_type = protein_info[uniprot_id].get('binding_type_visAMP', 'Unknown')
            if binding_type in grouped_sequences:
                grouped_sequences[binding_type].append((uniprot_id, header, sequence))
            else:
                print(f"Warning: Unknown binding type '{binding_type}' for {uniprot_id}")
                unmatched_sequences.append((uniprot_id, header, sequence))
        else:
            print(f"Warning: UniProt ID {uniprot_id} not found in protein_info.json")
            unmatched_sequences.append((uniprot_id, header, sequence))
    
    return grouped_sequences, unmatched_sequences

def write_ordered_fasta(grouped_sequences, unmatched_sequences, output_file, binding_order):
    """
    Write sequences to output FASTA file in the specified order
    """
    with open(output_file, 'w') as f:
        for binding_type in binding_order:
            sequences_in_group = grouped_sequences[binding_type]
            if sequences_in_group:
                for uniprot_id, header, sequence in sequences_in_group:
                    f.write(f"{header}\n")
                    f.write(f"{sequence}\n")
        
        # Write unmatched sequences at the end
        if unmatched_sequences:
            for uniprot_id, header, sequence in unmatched_sequences:
                f.write(f"{header}\n")
                f.write(f"{sequence}\n")

def print_summary(grouped_sequences, unmatched_sequences, binding_order):
    """
    Print summary of the ordering
    """
    print("\n=== FASTA Reordering Summary ===")
    total_sequences = sum(len(grouped_sequences[bt]) for bt in binding_order) + len(unmatched_sequences)
    print(f"Total sequences processed: {total_sequences}")
    print()
    
    for binding_type in binding_order:
        sequences_in_group = grouped_sequences[binding_type]
        print(f"{binding_type}: {len(sequences_in_group)} sequences")
        if sequences_in_group:
            names = [seq[0] for seq in sequences_in_group]  # UniProt IDs
            print(f"  {', '.join(names)}")
        print()
    
    if unmatched_sequences:
        print(f"Unmatched sequences: {len(unmatched_sequences)}")
        names = [seq[0] for seq in unmatched_sequences]
        print(f"  {', '.join(names)}")
    print()

def main():
    # File paths
    root = "/mnt/mydrive/pseudokinase/"
    json_file = root + "protein_info.json"
    fasta_file = root + "James_murphy/seq_analysis/pseudokinases_kinase_domains_msa.fasta"
    output_file = root + "James_murphy/seq_analysis/pseudokinases_kinase_domains_ordered_by_binding_type.fasta"

    
    print("Loading protein information from JSON...")
    protein_info = load_protein_info(json_file)
    print(f"Loaded information for {len(protein_info)} proteins")
    
    print("Parsing FASTA sequences...")
    sequences = parse_fasta(fasta_file)
    print(f"Parsed {len(sequences)} sequences from FASTA file")
    
    print("Ordering sequences by binding type...")
    binding_order = ["No-binding", "Nucleotide-binding", "Cation-binding", "Nucleotide-Cation-binding"]
    grouped_sequences, unmatched_sequences = order_sequences_by_binding_type(sequences, protein_info)
    
    print("Writing ordered FASTA file...")
    write_ordered_fasta(grouped_sequences, unmatched_sequences, output_file, binding_order)
    
    print_summary(grouped_sequences, unmatched_sequences, binding_order)
    
    print(f"Ordered FASTA file written to: {output_file}")

if __name__ == "__main__":
    main()
