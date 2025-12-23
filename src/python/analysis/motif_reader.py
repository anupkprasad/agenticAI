#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on 2025-06-20 (Y/M/D) at 15:44
@author: Anup K. Prasad
email: anupkprasad121@gmail.com
"""
from Bio.Align.Applications import MuscleCommandline
from Bio import AlignIO
import os
import re


def parseMMAFile(mma_file):
    """Parse MMA format file and return sequence data"""
    sequences = []
    
    with open(mma_file, 'r') as f:
        content = f.read()
    
    # Split by sequence entries (each starts with $)
    entries = re.split(r'\$\d+', content)[1:]  # Skip first empty part
    
    for entry in entries:
        lines = entry.strip().split('\n')
        if len(lines) < 2:
            continue
            
        # Parse header line (contains length info)
        header_line = lines[0]
        
        # Parse sequence name line (starts with >)
        seq_name_line = None
        seq_data_line = None
        
        for line in lines[1:]:
            if line.startswith('>'):
                seq_name_line = line[1:].strip()  # Remove >
            elif line.startswith('{') and line.endswith('}*'):
                seq_data_line = line[1:-2]  # Remove { and }*
        
        if seq_name_line and seq_data_line:
            sequences.append({
                'name': seq_name_line,
                'sequence': seq_data_line
            })
    
    return sequences

def extractMotifsFromMMA(mma_file, column_ranges, output_file):
    """Extract motifs from MMA format alignment using first sequence as reference for column ranges"""
    sequences = parseMMAFile(mma_file)
    
    if not sequences:
        return None
    
    # Process sequences and separate flanking regions from alignment
    processed_sequences = []
    reference_clean_alignment = None
    
    for i, seq_data in enumerate(sequences):
        name = seq_data['name']
        full_seq = seq_data['sequence']
        
        # Extract flanking regions
        flanking_start = ""
        flanking_end = ""
        alignment_seq = full_seq
        
        # Remove start flanking region in parentheses
        start_match = re.match(r'^\(([^)]*)\)', full_seq)
        if start_match:
            flanking_start = start_match.group(1)
            alignment_seq = full_seq[len(start_match.group(0)):]
        
        # Remove end flanking region in parentheses  
        end_match = re.search(r'\(([^)]*)\)$', alignment_seq)
        if end_match:
            flanking_end = end_match.group(1)
            alignment_seq = alignment_seq[:end_match.start()]
        
        # Create clean alignment (uppercase + dashes only) for motif extraction
        clean_alignment = ''.join(c for c in alignment_seq if c.isupper() or c == '-')
        
        processed_sequences.append({
            'name': name,
            'flanking_start': flanking_start,
            'flanking_end': flanking_end,
            'full_alignment': alignment_seq,  # with insertions
            'clean_alignment': clean_alignment  # without insertions
        })
        
        # Use first sequence clean alignment as reference
        if i == 0:
            reference_clean_alignment = clean_alignment
    
    # Validate column ranges against first sequence clean alignment
    ref_length = len(reference_clean_alignment)
    for start_col, end_col in column_ranges:
        if start_col < 1 or end_col > ref_length:
            print(f"Error: Column range {start_col}-{end_col} exceeds reference clean alignment length ({ref_length})")
            return None
    
    # Extract motifs for each sequence
    all_results = {}
    
    for seq_data in processed_sequences:
        seq_name = seq_data['name']
        flanking_start = seq_data['flanking_start']
        flanking_end = seq_data['flanking_end']
        full_alignment = seq_data['full_alignment']
        clean_alignment = seq_data['clean_alignment']
        
        all_results[seq_name] = []
        
        for start_col, end_col in column_ranges:
            # Handle sequences shorter than reference
            if end_col > len(clean_alignment):
                motif_data = {'motif': '---', 'range': 'N/A', 'alignment_region': 'TRUNCATED'}
            else:
                # Extract motif from clean alignment (1-based indexing)
                motif_region_clean = clean_alignment[start_col-1:end_col]
                ungapped_motif = motif_region_clean.replace('-', '')
                
                if ungapped_motif:
                    # Calculate original residue positions in the full protein sequence
                    # We need to map back from clean alignment position to full alignment position
                    
                    # Find the position in full alignment that corresponds to start_col in clean alignment
                    clean_pos = 0
                    full_pos = 0
                    start_full_pos = 0
                    
                    # Map clean alignment start position to full alignment position
                    while clean_pos < start_col - 1 and full_pos < len(full_alignment):
                        char = full_alignment[full_pos]
                        if char.isupper() or char == '-':
                            if clean_pos == start_col - 1:
                                start_full_pos = full_pos
                                break
                            clean_pos += 1
                        full_pos += 1
                    
                    if clean_pos == start_col - 1:
                        start_full_pos = full_pos
                    
                    # Count residues before the motif start in original protein
                    # Include: flanking_start + all letters (upper+lower) before start position, exclude dashes
                    residues_before_motif = full_alignment[:start_full_pos]
                    residue_count_before = len(flanking_start) + len([c for c in residues_before_motif if c.isalpha()])
                    
                    original_start = residue_count_before + 1
                    original_end = original_start + len(ungapped_motif) - 1
                    
                    # Get the alignment region with insertions for display
                    end_full_pos = start_full_pos
                    clean_chars_found = 0
                    while end_full_pos < len(full_alignment) and clean_chars_found < (end_col - start_col + 1):
                        char = full_alignment[end_full_pos]
                        if char.isupper() or char == '-':
                            clean_chars_found += 1
                        end_full_pos += 1
                    
                    alignment_region_with_insertions = full_alignment[start_full_pos:end_full_pos]
                    
                    motif_data = {
                        'motif': ungapped_motif,
                        'range': f"{original_start}-{original_end}",
                        'alignment_region': alignment_region_with_insertions
                    }
                else:
                    # All gaps case
                    # Still need to find the corresponding region in full alignment
                    clean_pos = 0
                    full_pos = 0
                    start_full_pos = 0
                    
                    while clean_pos < start_col - 1 and full_pos < len(full_alignment):
                        char = full_alignment[full_pos]
                        if char.isupper() or char == '-':
                            if clean_pos == start_col - 1:
                                start_full_pos = full_pos
                                break
                            clean_pos += 1
                        full_pos += 1
                    
                    if clean_pos == start_col - 1:
                        start_full_pos = full_pos
                    
                    end_full_pos = start_full_pos
                    clean_chars_found = 0
                    while end_full_pos < len(full_alignment) and clean_chars_found < (end_col - start_col + 1):
                        char = full_alignment[end_full_pos]
                        if char.isupper() or char == '-':
                            clean_chars_found += 1
                        end_full_pos += 1
                    
                    alignment_region_with_insertions = full_alignment[start_full_pos:end_full_pos]
                    
                    motif_data = {
                        'motif': '---',
                        'range': 'N/A',
                        'alignment_region': alignment_region_with_insertions
                    }
            
            all_results[seq_name].append(motif_data)
    
    # Write results with proper alignment
    with open(output_file, 'w') as f:
        f.write(f"MOTIF EXTRACTION FROM MMA (Column ranges based on first sequence clean alignment): {column_ranges}\n")
        f.write("=" * 120 + "\n")
        
        # Calculate column widths for proper alignment
        max_seq_name_len = max(len(seq_name) for seq_name in all_results.keys()) if all_results else 20
        max_seq_name_len = max(max_seq_name_len, len("Sequence_Name"))
        
        # Calculate max widths for each motif column
        motif_widths = []
        alignment_widths = []
        range_widths = []
        
        for i in range(len(column_ranges)):
            max_motif_len = max(len(motifs[i]['motif']) for motifs in all_results.values()) if all_results else 4
            max_alignment_len = max(len(motifs[i]['alignment_region']) for motifs in all_results.values()) if all_results else 10
            max_range_len = max(len(motifs[i]['range']) for motifs in all_results.values()) if all_results else 8
            
            # Ensure minimum widths for headers
            max_motif_len = max(max_motif_len, len(f"Motif_{i+1}"))
            max_alignment_len = max(max_alignment_len, len(f"Alignment_Region_{i+1}"))
            max_range_len = max(max_range_len, len(f"Original_Range_{i+1}"))
            
            motif_widths.append(max_motif_len)
            alignment_widths.append(max_alignment_len)
            range_widths.append(max_range_len)
        
        # Create aligned header with comma separation
        header_line = f"{('Sequence_Name').ljust(max_seq_name_len)}"
        for i, (start_col, end_col) in enumerate(column_ranges):
            header_line += f", {f'Motif_{i+1}'.ljust(motif_widths[i])}"
            header_line += f", {f'Alignment_Region_{i+1}'.ljust(alignment_widths[i])}"
            header_line += f", {f'Original_Range_{i+1}'.ljust(range_widths[i])}"
        
        f.write(header_line + "\n")
        f.write("-" * len(header_line) + "\n")
        
        # Write data rows with proper alignment and comma separation
        for seq_name, motifs in all_results.items():
            line = f"{seq_name.ljust(max_seq_name_len)}"
            for i, motif_data in enumerate(motifs):
                line += f", {motif_data['motif'].ljust(motif_widths[i])}"
                line += f", {motif_data['alignment_region'].ljust(alignment_widths[i])}"
                line += f", {motif_data['range'].ljust(range_widths[i])}"
            f.write(line + "\n")
    
    return all_results

def get_alignment_residue_numbers(mma_file, output_excel=None):
    """
    For each sequence in the MMA file, return a pandas DataFrame mapping each alignment position (uppercase or dash)
    to its original residue number (1-based, including flanking regions and insertions) or NaN for dashes.
    Also writes the result to an Excel file if output_excel is provided.
    Includes flanking regions and insertions (lowercase) in residue number calculations.
    Returns: pandas.DataFrame
    """
    import math
    import pandas as pd
    seqs = parseMMAFile(mma_file)
    result = {}
    for seq in seqs:
        full_seq = seq['sequence']
        
        # Extract flanking regions
        flanking_start = ""
        flanking_end = ""
        alignment_seq = full_seq
        
        # Remove start flanking region in parentheses
        start_match = re.match(r'^\(([^)]*)\)', full_seq)
        if start_match:
            flanking_start = start_match.group(1)
            alignment_seq = full_seq[len(start_match.group(0)):]
        
        # Remove end flanking region in parentheses  
        end_match = re.search(r'\(([^)]*)\)$', alignment_seq)
        if end_match:
            flanking_end = end_match.group(1)
            alignment_seq = alignment_seq[:end_match.start()]
        
        # Calculate residue numbers including flanking regions and insertions
        # Start with flanking region count
        resnum = len(flanking_start)
        arr = []
        
        for c in alignment_seq:
            if c.isupper():
                # Uppercase letter: increment residue number and record it
                resnum += 1
                arr.append(resnum)
            elif c == '-':
                # Dash: record NaN
                arr.append(float('nan'))
            elif c.islower():
                # Lowercase (insertion): increment residue number but don't record in array
                resnum += 1
        
        result[seq['name']] = arr
    # Convert to DataFrame
    max_len = max(len(arr) for arr in result.values())
    df = pd.DataFrame.from_dict(result, orient='index')
    df.columns = [f"Pos_{i+1}" for i in range(max_len)]
    df.insert(0, 'Sequence', df.index)
    df.reset_index(drop=True, inplace=True)
    # Write to Excel if requested
    if output_excel:
        df.to_excel(output_excel, index=False, na_rep='NaN')
        print(f"Residue number mapping written to {output_excel}")
    return df

# CONFIGURATION
path = "/mnt/mydrive/pseudokinase/seq_analysis/"

# Check for MMA file first, then FASTA
mma_file = f"{path}all_msa.mma"


# Column ranges to extract (based on first sequence in MMA or alignment columns in FASTA)
COLUMN_RANGES = [(27,30), (117, 119), (137, 139)]
COLUMN_RANGES = [(137,137)]

# Process MMA file if it exists, otherwise use FASTA workflow
if os.path.exists(mma_file):
    print("Processing MMA format file...")
    mma_motif_output =mma_file.replace(".mma", "_motifs_extracted.txt")
    result = extractMotifsFromMMA(mma_file, COLUMN_RANGES, mma_motif_output)
    output_excel = f"{path}residue_number_map.xlsx"
    resid_df = get_alignment_residue_numbers(mma_file, output_excel=output_excel)
    # Optionally print or use resid_df as needed

print("Analysis completed successfully!")




uid = []
for key, value in result.items():
    print(f"Motif for {key}: {value[0].get('motif')}")
    if value[0].get('motif') != 'D':
        uid.append(key.split('_')[0])

