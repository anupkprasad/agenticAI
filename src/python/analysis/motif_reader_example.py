#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example usage of the enhanced MotifReader class
Demonstrates both MMA file processing and motif file reading
"""

from motif_reader import MotifReader
import os

def main():
    """Demonstrate MotifReader functionality"""
    
    print("=== MOTIF READER EXAMPLES ===\n")
    
    # Example 1: Load from existing processed motif file
    print("1. Loading from processed motif file:")
    motif_file = "/mnt/mydrive/pseudokinase/James_murphy/seq_analysis/motifs_from_mma.txt"
    
    if os.path.exists(motif_file):
        reader = MotifReader.from_motif_file(motif_file)
        print(f"   Loaded {len(reader.motif_data)} sequences")
        
        # Get motif info for specific UniProt IDs
        test_ids = ["Q8NE28", "P23458", "Q96C45"]
        for uniprot_id in test_ids:
            print(f"\n   UniProt {uniprot_id}:")
            motifs = reader.get_motifs_by_uniprot(uniprot_id)
            ranges = reader.get_motif_ranges_by_uniprot(uniprot_id)
            VAIK, HRD, DFG, all_res = reader.parse_motif_residues(uniprot_id)
            
            print(f"     Motifs: {motifs}")
            print(f"     Ranges: {ranges}")
            print(f"     Key residues: VAIK_K={VAIK}, HRD_D={HRD}, DFG_D={DFG}")
    
    print("\n" + "="*60)
    
    # Example 2: Process MMA file directly (if available)
    print("2. Processing MMA file (if available):")
    mma_file = "/mnt/mydrive/pseudokinase/human_pseudokinases.mma"
    
    if os.path.exists(mma_file):
        print(f"   Processing MMA file: {mma_file}")
        reader2 = MotifReader()
        
        # Process MMA file and generate motif file
        output_file = "/tmp/test_motifs.txt"
        if reader2.process_mma_file(mma_file, output_file):
            print(f"   Generated motif file: {output_file}")
            
            # Load the generated file
            reader2.read_motif_file(output_file)
            print(f"   Loaded {len(reader2.motif_data)} sequences from MMA")
        else:
            print("   Failed to process MMA file")
    else:
        print(f"   MMA file not found: {mma_file}")
    
    print("\n" + "="*60)
    
    # Example 3: Batch processing (if directory exists)
    print("3. Batch processing example:")
    batch_dir = "/mnt/mydrive/pseudokinase/alignments"
    
    if os.path.exists(batch_dir):
        reader3 = MotifReader()
        output_files = reader3.batch_process_mma_files(batch_dir, "/tmp/batch_output")
        print(f"   Processed {len(output_files)} files")
    else:
        print(f"   Batch directory not found: {batch_dir}")
    
    print("\n" + "="*60)
    
    # Example 4: Validation and search functions
    print("4. Validation and search functions:")
    if 'reader' in locals():
        # Find sequences with specific motif patterns
        dfg_sequences = reader.find_sequences_by_motif("DFG")
        print(f"   Found {len(dfg_sequences)} sequences with DFG motif")
        
        # Validate motif extraction
        print("   Running validation...")
        is_valid = reader.validate_motif_extraction()
        print(f"   Validation result: {'PASSED' if is_valid else 'FAILED'}")
    
    print("\n=== EXAMPLES COMPLETE ===")

if __name__ == "__main__":
    main()
