#!/usr/bin/tclsh
#### VMD Pseudokinase Analysis Script - Simplified Version
# Four main tasks: 1) Load molecules, 2) Sequence alignment, 3) Motif representation, 4) Analysis utilities
# Author: Anup K. Prasad (anupkprasad121@gmail.com)

proc checkSimSetup {{base_path "."}} {
    # Load min.tpr from each subdirectory under base_path and rename the molecule to the directory name
    # Useful for quickly checking simulation setup (equilibration/min.tpr presence)

    set scan_path [pwd]

    set dirs [lsort [glob -nocomplain -types d -directory $scan_path *]]
    if {[llength $dirs] == 0} {
        puts "No subdirectories found under: $scan_path"
        return
    }

    puts "Scanning [llength $dirs] directories under: $scan_path"
    foreach dir $dirs {
        set dir_name [file tail $dir]
        set tpr "$dir/equilibration/min.tpr"
        if {[file exists $tpr]} {
            puts "Loading: $tpr"
            cd $dir
            mol new $tpr
            set mid [molinfo top]
            mol rename $mid $dir_name
            puts "  Renamed mol $mid -> $dir_name"
            cd $scan_path
        } else {
            puts "Missing: $tpr"
        }
    }

    cd $scan_path
}

############################################################################################################
### HELPER FUNCTIONS (DEFINED EARLY) ###

# Helper function to extract protein identifiers
proc extractProteinIdentifiers {name} {
    set identifiers {}
    
    # First try to parse the expected format: uniprotid_proteinname_ligand
    if {[regexp {^([A-Z][0-9][A-Z0-9]{3}[0-9])_([^_]+)_([^_]+)$} $name match uniprot_id protein_name ligand]} {
        # This is the format from loaded molecules: Q9Y616_IRAK3_atp
        lappend identifiers $uniprot_id
        return $identifiers
    }
    
    # Try format: uniprotid_proteinname (from alignment sequences)
    if {[regexp {^([A-Z][0-9][A-Z0-9]{3}[0-9])_(.+)$} $name match uniprot_id protein_name]} {
        # This is the format from sequences: Q9Y616_IRAK3
        lappend identifiers $uniprot_id
        return $identifiers
    }
    
    # Fallback: extract any UniProt-like IDs from the name
    set name_upper [string toupper $name]
    foreach match [regexp -all -inline {[A-Z][0-9][A-Z0-9]{3}[0-9]} $name_upper] {
        lappend identifiers $match
    }
    
    return [lsort -unique $identifiers]
}

# Helper function to extract UniProt ID and protein name from simplified sequence names
proc parseSequenceName {seq_name} {
    # Remove leading > if present
    set clean_name [string trimleft $seq_name ">"]
    
    # Parse format: UniprotID_ProteinName (from alignment sequences)
    if {[regexp {^([A-Z][0-9][A-Z0-9]{3}[0-9])_(.+)$} $clean_name match uniprot_id protein_name]} {
        return [list $uniprot_id $protein_name]
    }
    
    # Fallback: try to extract just the UniProt ID
    set identifiers [extractProteinIdentifiers $clean_name]
    if {[llength $identifiers] > 0} {
        return [list [lindex $identifiers 0] "Unknown"]
    }
    
    return {}
}

# Helper function to get original resid for given column ranges
proc getOriginalResidFromMSAColumnRange {residue_results seq_name start_col end_col} {
    if {[llength $residue_results] == 0} {
        return {}
    }
    
    # Find the sequence in residue results
    foreach seq_result $residue_results {
        if {[lindex $seq_result 0] eq $seq_name} {
            set residue_data [lindex $seq_result 1]
            set residue_list {}
            
            # Extract residues within the column range (convert 1-based columns to 0-based indices)
            for {set col $start_col} {$col <= $end_col} {incr col} {
                set list_index [expr {$col - 1}]
                if {$list_index >= 0 && $list_index < [llength $residue_data]} {
                    set residue [lindex $residue_data $list_index]
                    if {$residue ne "" && $residue ne "-" && [string is integer $residue]} {
                        # The residue values coming from the alignment are 1 higher than
                        # the original residue numbering in the structure. Adjust by
                        # subtracting 1 so returned residue IDs match the original
                        # sequence numbering (fixes off-by-one issue: e.g. 26->25).
                        set orig_resid [expr {$residue - 1}]
                        lappend residue_list $orig_resid
                    }
                }
            }
            return $residue_list
        }
    }
    return {}
}

# Helper function to get MSA consensus column(s) from original resid(s) - REVERSE of getOriginalResidFromMSAColumnRange
proc getMSAColumnFromOriginalResid {residue_results seq_name resid_list} {
    if {[llength $residue_results] == 0} {
        return {}
    }
    
    # Find the sequence in residue results
    foreach seq_result $residue_results {
        if {[lindex $seq_result 0] eq $seq_name} {
            set residue_data [lindex $seq_result 1]
            set column_list {}
            
            # For each requested original resid, find its column in the alignment
            foreach orig_resid $resid_list {
                # Adjust: add 1 to match the alignment numbering (reverse of the -1 adjustment)
                set target_resid [expr {$orig_resid + 1}]
                
                # Search through all columns for this residue
                for {set col_idx 0} {$col_idx < [llength $residue_data]} {incr col_idx} {
                    set residue [lindex $residue_data $col_idx]
                    if {$residue ne "" && $residue ne "-" && [string is integer $residue]} {
                        if {$residue == $target_resid} {
                            # Convert 0-based index to 1-based column number
                            set col_num [expr {$col_idx + 1}]
                            lappend column_list $col_num
                            break
                        }
                    }
                }
            }
            return $column_list
        }
    }
    return {}
}

proc getSeqNameFromMSA {{molid top}} {
    global residue_results
    
    # Handle "top" keyword
    if {$molid eq "top"} {
        set molid [molinfo top]
    }
    
    # Get molecule name and extract UniProt ID
    set mol_name [molinfo $molid get name]
    set mol_identifiers [extractProteinIdentifiers $mol_name]
    set mol_uniprot [expr {[llength $mol_identifiers] > 0 ? [lindex $mol_identifiers 0] : ""}]
    
    if {$mol_uniprot eq ""} {
        puts "Error: Could not determine UniProt ID for molecule $molid ($mol_name)"
        return ""
    }
    
    # Check if residue_results is available
    if {[llength $residue_results] == 0} {
        puts "Error: No alignment data loaded (residue_results is empty)"
        return ""
    }
    
    # Find matching sequence in residue_results
    set alignment_seq_name ""
    foreach seq_result $residue_results {
        set seq_name [lindex $seq_result 0]
        set seq_parts [parseSequenceName $seq_name]
        if {[llength $seq_parts] == 2} {
            set seq_uniprot [lindex $seq_parts 0]
            if {[string toupper $seq_uniprot] eq [string toupper $mol_uniprot]} {
                set alignment_seq_name $seq_name
                break
            }
        }
    }
    
    if {$alignment_seq_name eq ""} {
        puts "Error: No alignment sequence found for molecule $molid ($mol_name, UniProt: $mol_uniprot)"
        puts "Available sequences in alignment:"
        foreach seq_result $residue_results {
            set seq_name [lindex $seq_result 0]
            puts "  $seq_name"
        }
        return ""
    }
    
    puts "Molecule $molid ($mol_name) -> Alignment sequence: $alignment_seq_name"
    return $alignment_seq_name
}


proc getOriginalResid {{molid top} args} {
    global residue_results
    
    # Get the alignment sequence name for this molecule
    set alignment_seq_name [getSeqNameFromMSA $molid]
    if {$alignment_seq_name eq ""} {
        puts "Error: Could not find alignment sequence for molecule $molid"
        return {}
    }
    
    set all_residues {}
    
    # Handle different argument formats
    if {[llength $args] == 0} {
        puts "Error: No column ranges or lists provided"
        return {}
    }
    
    foreach arg $args {
        if {[llength $arg] == 1} {
            # Single column number
            set col [lindex $arg 0]
            set residue_list [getOriginalResidFromMSAColumnRange $residue_results $alignment_seq_name $col $col]
            set all_residues [concat $all_residues $residue_list]
            
        } elseif {[llength $arg] == 2} {
            # Could be a range {start end} or two separate columns {col1 col2}
            set first [lindex $arg 0]
            set second [lindex $arg 1]
            
            # Check if it's a range (second > first) or just two columns
            if {$second > $first && ($second - $first) <= 50} {
                # Treat as range
                set residue_list [getOriginalResidFromMSAColumnRange $residue_results $alignment_seq_name $first $second]
                set all_residues [concat $all_residues $residue_list]
            } else {
                # Treat as two separate columns
                foreach col $arg {
                    set residue_list [getOriginalResidFromMSAColumnRange $residue_results $alignment_seq_name $col $col]
                    set all_residues [concat $all_residues $residue_list]
                }
            }
            
        } else {
            # List of multiple columns {25 28 35 40}
            foreach col $arg {
                set residue_list [getOriginalResidFromMSAColumnRange $residue_results $alignment_seq_name $col $col]
                set all_residues [concat $all_residues $residue_list]
            }
        }
    }
    
    # Remove duplicates and sort
    set all_residues [lsort -unique -integer $all_residues]

    if {[llength $all_residues] == 0} {
        puts "No original residues found for the given columns: $arg it is an deletion"
    }
    
    return $all_residues
}


proc getMSAColumn {{molid top} args} {
    global residue_results
    
    # Get the alignment sequence name for this molecule
    set alignment_seq_name [getSeqNameFromMSA $molid]
    if {$alignment_seq_name eq ""} {
        puts "Error: Could not find alignment sequence for molecule $molid"
        return {}
    }
    
    set all_columns {}
    
    # Handle different argument formats
    if {[llength $args] == 0} {
        puts "Error: No residue IDs or ranges provided"
        puts "Usage: getMSAColumn \[molid\] {resid1 resid2 ...} or {start_resid end_resid}"
        return {}
    }
    
    foreach arg $args {
        if {[llength $arg] == 1} {
            # Single residue ID
            set resid [lindex $arg 0]
            set column_list [getMSAColumnFromOriginalResid $residue_results $alignment_seq_name [list $resid]]
            set all_columns [concat $all_columns $column_list]
            
        } elseif {[llength $arg] == 2} {
            # Could be a range {start end} or two separate resids {resid1 resid2}
            set first [lindex $arg 0]
            set second [lindex $arg 1]
            
            # Check if it's a range (second > first with reasonable gap)
            if {$second > $first && ($second - $first) <= 200} {
                # Treat as range: generate all resids from first to second
                set resid_range {}
                for {set r $first} {$r <= $second} {incr r} {
                    lappend resid_range $r
                }
                set column_list [getMSAColumnFromOriginalResid $residue_results $alignment_seq_name $resid_range]
                set all_columns [concat $all_columns $column_list]
            } else {
                # Treat as two separate resids
                set column_list [getMSAColumnFromOriginalResid $residue_results $alignment_seq_name $arg]
                set all_columns [concat $all_columns $column_list]
            }
            
        } else {
            # List of multiple resids {25 28 35 40}
            set column_list [getMSAColumnFromOriginalResid $residue_results $alignment_seq_name $arg]
            set all_columns [concat $all_columns $column_list]
        }
    }
    
    # Remove duplicates and sort
    set all_columns [lsort -unique -integer $all_columns]

    if {[llength $all_columns] == 0} {
        puts "No MSA columns found for the given residues: $arg it is an insertion"
    }
    
    return $all_columns
}



############################################################################################################
### TASK 1: LOADING MOLECULES ###

proc loadAF3 {protein_list {ligand_list ""}} {
    global current_path data_path DEFAULT_LIGANDS reference_molid PROTEIN_JSON molid_paths
    
    if {$ligand_list eq ""} {
        set ligand_list $DEFAULT_LIGANDS
    }
    
    set first_load 1
    puts "Loading proteins: [join $protein_list {, }] with ligands: [join $ligand_list {, }]"
    
    foreach protein_input $protein_list {
        set uniprot_id [getUniprotFromProteinName $PROTEIN_JSON $protein_input]
        set protein_name [getProteinNameFromUniprot $PROTEIN_JSON $uniprot_id]
        
        foreach variant {kd1 kd2} {
            set base_name "${uniprot_id}_${variant}__amsa_atemp"
            
            foreach lig $ligand_list {
                set full_path "$current_path/${lig}_${base_name}"
                if {[file isdirectory $full_path]} {
                    cd $full_path
                    loadCifAF3
                    
                    set actual_molid [molinfo top]
                    mol rename $actual_molid "${uniprot_id}_${protein_name}_${lig}"
                    puts "  Loaded: ${protein_name}_${lig} (ID: $actual_molid)"
                    
                    # Store molid-to-path mapping for analysis output
                    dict set molid_paths $actual_molid $full_path
                    puts "  Stored path mapping: $actual_molid -> $full_path"
                    
                    if {$first_load} {
                        set reference_molid $actual_molid
                        trajAlign
                        puts "  Set as reference: $actual_molid"
                        set first_load 0

                    }
                    }
            }
        }
    }
    cd $data_path
}



proc loadAF3ByKeyValue {key value} {
    # Load proteins filtered by any field value from the JSON file
    # example: loadAF3ByKeyValue "binding_lig_mg" "Unknown"
    global current_path data_path DEFAULT_LIGANDS reference_molid PROTEIN_JSON molid_paths
    
    # Get the list of proteins matching the field value
    set protein_list [getProteinlistByKeyValue $PROTEIN_JSON $key $value]
    
    if {[llength $protein_list] == 0} {
        puts "No proteins found with $key = $value in $PROTEIN_JSON"
        return
    }
    
    loadAF3 $protein_list
}




proc load_simulation {protein_list {ligand_list ""} {reps "rep1 rep2"}} {
    global current_path data_path DEFAULT_LIGANDS reference_molid PROTEIN_JSON molid_paths
    setPath "sim_done"

    if {$ligand_list eq ""} {
        set ligand_list $DEFAULT_LIGANDS
    }
    
    set first_load 1
    puts "Loading proteins: [join $protein_list {, }] with ligands: [join $ligand_list {, }] with reps: [join $reps {, }]"
    
    foreach protein_input $protein_list {
        set uniprot_id [getUniprotFromProteinName $PROTEIN_JSON $protein_input]
        set protein_name [getProteinNameFromUniprot $PROTEIN_JSON $uniprot_id]
        
        foreach variant {kd1 kd2} {
            set base_name "${uniprot_id}_${variant}__amsa_atemp"
            
            foreach lig $ligand_list {
                foreach rep $reps {
                    set full_path "$current_path/${lig}_${base_name}/${rep}"
                    puts "Checking path: $full_path"
                    if {[file isdirectory $full_path]} {
                        puts "Loading from path: $full_path"
                        cd $full_path
                        mol new md.tpr
                        mol addfile mdWrap10frm1ns.xtc waitfor all
                        
                        set actual_molid [molinfo top]
                        mol rename $actual_molid "${uniprot_id}_${protein_name}_${lig}_${rep}"
                        puts "  Loaded: ${protein_name}_${lig}_${rep} (ID: $actual_molid)"
                        
                        # Store molid-to-path mapping for analysis output
                        dict set molid_paths $actual_molid $full_path
                        puts "  Stored path mapping: $actual_molid -> $full_path"
                        
                        if {$first_load} {
                            set reference_molid $actual_molid
                            trajAlign
                            puts "  Set as reference: $actual_molid"
                            set first_load 0
                        }
                        # REMOVED THE BREAK HERE - now continues to next rep
                    } else {
                        puts "  Path not found: $full_path"
                    }
                }
            }
        }
    }
    cd $data_path
}

proc load_simulation_streamed {protein_list {ligand_list ""} {reps "rep1 rep2"}} {
    # Load trajectories one-by-one to reduce memory: keep first as reference, analyze, delete others
    global current_path data_path DEFAULT_LIGANDS reference_molid PROTEIN_JSON molid_paths
    
    # Ensure we are in simulation path
    setPath "sim_done"

    if {$ligand_list eq ""} {
        set ligand_list $DEFAULT_LIGANDS
    }

    # Normalize reps list (string -> list)
    set reps_list $reps

    set have_ref 0
    puts "Streaming simulation load: [join $protein_list {, }] with ligands: [join $ligand_list {, }] and reps: [join $reps_list {, }]"

    foreach protein_input $protein_list {
        set uniprot_id [getUniprotFromProteinName $PROTEIN_JSON $protein_input]
        set protein_name [getProteinNameFromUniprot $PROTEIN_JSON $uniprot_id]

        foreach variant {kd1 kd2} {
            set base_name "${uniprot_id}_${variant}__amsa_atemp"

            foreach lig $ligand_list {
                foreach rep $reps_list {
                    set full_path "$current_path/${lig}_${base_name}/${rep}"
                    puts "Checking path: $full_path"
                    if {![file isdirectory $full_path]} {
                        puts "  Path not found: $full_path"
                        continue
                    }

                    puts "Loading from path: $full_path"
                    cd $full_path
                    mol new md.tpr
                    mol addfile mdWrap10frm1ns.xtc waitfor all

                    set actual_molid [molinfo top]
                    mol rename $actual_molid "${uniprot_id}_${protein_name}_${lig}_${rep}"
                    puts "  Loaded: ${protein_name}_${lig}_${rep} (ID: $actual_molid)"

                    # Store molid-to-path mapping for analysis output
                    dict set molid_paths $actual_molid $full_path
                    puts "  Stored path mapping: $actual_molid -> $full_path"

                    if {!$have_ref} {
                        # First trajectory: make reference, basic alignment, analyze, and keep
                        set reference_molid $actual_molid
                        trajAlign
                        puts "  Set as reference: $actual_molid"
                        analyzeMolecule $actual_molid
                        set have_ref 1
                    } else {
                        # Align to reference, analyze, then delete to free memory
                        align $actual_molid $reference_molid
                        analyzeMolecule $actual_molid
                        mol delete $actual_molid
                        puts "  Deleted analyzed molecule: $actual_molid"
                    }

                    # Return to the current base path for next iteration
                    cd $current_path
                }
            }
        }
    }

    cd $data_path
    if {$have_ref} {
        puts "Streaming simulation load complete. Reference molid kept: $reference_molid"
    } else {
        puts "Streaming simulation load found no loadable entries."
    }
}




############################################################################################################
### TASK 2: SEQUENCE ALIGNMENT ###

proc align {molid ref_id} {
    global residue_results
    
    set mol_name [molinfo $molid get name]
    set mol_identifiers [extractProteinIdentifiers $mol_name]
    set mol_uniprot [expr {[llength $mol_identifiers] > 0 ? [lindex $mol_identifiers 0] : ""}]
    
    # Try sequence-based alignment
    if {$mol_uniprot ne "" && [llength $residue_results] > 0} {
        set seq_names [getSequenceNames $residue_results]
        set ref_name [molinfo $ref_id get name]
        set ref_identifiers [extractProteinIdentifiers $ref_name]
        set ref_uniprot [expr {[llength $ref_identifiers] > 0 ? [lindex $ref_identifiers 0] : ""}]
        
        if {$ref_uniprot ne ""} {
            # Find matching sequences
            set ref_seq ""
            set mol_seq ""
            foreach seq_result $residue_results {
                set seq_name [lindex $seq_result 0]
                set seq_parts [parseSequenceName $seq_name]
                if {[llength $seq_parts] == 2} {
                    set full_name [lindex $seq_parts 0]
                    set seq_uniprot [lindex [split $full_name "_"] 0]
                    if {[string toupper $seq_uniprot] eq [string toupper $ref_uniprot]} {
                        set ref_seq $seq_name
                    }
                    if {[string toupper $seq_uniprot] eq [string toupper $mol_uniprot]} {
                        set mol_seq $seq_name
                    }
                }
            }
            
            if {$ref_seq ne "" && $mol_seq ne ""} {
                set aligned_pairs [getAlignedResidueListsForVMDFiltered $residue_results $ref_seq $mol_seq $ref_id $molid]
                set ref_residues [lindex $aligned_pairs 0]
                set tgt_residues [lindex $aligned_pairs 1]
                
                if {[llength $ref_residues] > 0 && [llength $tgt_residues] > 0} {
                    set ref_residues_str [join $ref_residues " "]
                    set tgt_residues_str [join $tgt_residues " "]
                    alignTwoMol $ref_id $molid "resid $ref_residues_str and name CA" "resid $tgt_residues_str and name CA"
                    puts "  $mol_name: Sequence-based alignment ([llength $ref_residues] residues)"
                    return 1
                } else {
                    puts "  $mol_name: No aligned residues found (ref_seq: $ref_seq, mol_seq: $mol_seq)"
                }
            } else {
                puts "  $mol_name: No sequence matches found (ref_uniprot: $ref_uniprot, mol_uniprot: $mol_uniprot)"
                set available_seq_names {}
                foreach seq_result $residue_results {
                    lappend available_seq_names [lindex $seq_result 0]
                }
                puts "    Available sequences: [join $available_seq_names {, }]"
            }
        } else {
            puts "  $mol_name: No reference UniProt ID found"
        }
    } else {
        puts "  $mol_name: No UniProt ID or sequence data (uniprot: $mol_uniprot, data: [llength $residue_results])"
    }
    He noticed that there isn't a section in this draft that discusses Figures 3 and 4. Do you have a write-up for this already?
    # Fallback to basic alignment
    mol top $molid
    trajAlign
    puts "  $mol_name: Basic CA alignment"
    return 0
}




proc alignAllMolids {{ref_molid ""}} {
    set all_molecules [molinfo list]
    if {$ref_molid eq ""} {
        set ref_id [molinfo top]
    } else {
        set ref_id $ref_molid
    }
    
    foreach molid $all_molecules {
        align $molid $ref_id
    }
}



############################################################################################################
### TASK 3: REPRESENTATION ###

proc showAllComponentsforAllMolid {{molid_list "all"}} {
    if {$molid_list eq "all"} {
        set mollist [molinfo list]
    } else {
        set mollist $molid_list
    }
    
    if {[llength $mollist] == 0} {
        puts "No structures loaded in VMD"
        return
    }

    puts "Setting up visualization for [llength $mollist] molecules..."
    
    set color_index 0
    foreach molid $mollist {
        set mol_name [molinfo $molid get name]
        puts "  Setting up visualization for molecule ID: $molid ($mol_name)"
        
        # Protein representation
        mol modselect 0 $molid "protein"
        mol modcolor 0 $molid ColorID $color_index
        
        # Ligand representation
        mol selection "resname AMP or resname ADP or resname ATP or resname GTP"
        mol representation Licorice
        mol color ColorID $color_index
        mol addrep $molid
        
        # MG ions
        mol selection "resname MG"
        mol representation VDW
        mol color ColorID 7
        mol addrep $molid
        
        mol off $molid
        incr color_index
    }
    
    puts "Visualization setup complete"
}
proc loadAF3_streamed {protein_list {ligand_list ""}} {
    # Load one by one, align to first as reference, analyze, then delete (to save memory).
    # The first loaded molecule is analyzed and kept as reference.
    global current_path data_path DEFAULT_LIGANDS reference_molid PROTEIN_JSON molid_paths

    if {$ligand_list eq ""} {
        set ligand_list $DEFAULT_LIGANDS
    }

    set have_ref 0
    puts "Streaming load: [join $protein_list {, }] with ligands: [join $ligand_list {, }]"

    foreach protein_input $protein_list {
        set uniprot_id [getUniprotFromProteinName $PROTEIN_JSON $protein_input]
        set protein_name [getProteinNameFromUniprot $PROTEIN_JSON $uniprot_id]

        foreach variant {kd1 kd2} {
            set base_name "${uniprot_id}_${variant}__amsa_atemp"

            foreach lig $ligand_list {
                set full_path "$current_path/${lig}_${base_name}"
                if {![file isdirectory $full_path]} {
                    puts "  Path not found: $full_path"
                    continue
                }

                puts "Loading from path: $full_path"
                cd $full_path
                loadCifAF3

                set actual_molid [molinfo top]
                mol rename $actual_molid "${uniprot_id}_${protein_name}_${lig}"
                dict set molid_paths $actual_molid $full_path
                puts "  Loaded: ${protein_name}_${lig} (ID: $actual_molid)"

                if {!$have_ref} {
                    # First molecule: set as reference, align frames, analyze, keep
                    set reference_molid $actual_molid
                    trajAlign
                    puts "  Set as reference: $actual_molid"
                    analyzeMolecule $actual_molid
                    set have_ref 1
                } else {
                    # Align to reference, analyze, then delete to free memory
                    align $actual_molid $reference_molid
                    analyzeMolecule $actual_molid
                    mol delete $actual_molid
                    puts "  Deleted analyzed molecule: $actual_molid"
                }

                # Return to current base path for next
                cd $current_path
            }
        }
    }

    cd $data_path
    if {$have_ref} {
        puts "Streaming load complete. Reference molid kept: $reference_molid"
    } else {
        puts "Streaming load found no loadable entries."
    }
}


proc showMotifs {column_ranges {molid_list "all"}} {
    global residue_results

    if {$molid_list eq "all"} {
        set molid_list [molinfo list]
    }
    
    if {[llength $residue_results] == 0} {
        puts "No residue data available"
        return
    }
    
    puts "Creating motif representations for molecules: [join $molid_list {, }]"
    puts "Column ranges: $column_ranges"

    foreach molid $molid_list {
        if {[catch {molinfo $molid get name}]} {
            puts "  Molecule $molid does not exist, skipping"
            continue
        }
        
        set mol_name [molinfo $molid get name]
        set mol_identifiers [extractProteinIdentifiers $mol_name]
        set mol_uniprot [expr {[llength $mol_identifiers] > 0 ? [lindex $mol_identifiers 0] : ""}]
        
        if {$mol_uniprot eq ""} {
            puts "  $mol_name: Could not determine UniProt ID, skipping"
            continue
        }
        
        # Find matching sequence in residue_results
        set alignment_seq_name ""
        foreach seq_result $residue_results {
            set seq_name [lindex $seq_result 0]
            set seq_parts [parseSequenceName $seq_name]
            if {[llength $seq_parts] == 2} {
                set seq_uniprot [lindex $seq_parts 0]
                if {[string toupper $seq_uniprot] eq [string toupper $mol_uniprot]} {
                    set alignment_seq_name $seq_name
                    break
                }
            }
        }
        
        if {$alignment_seq_name eq ""} {
            puts "  $mol_name: No alignment sequence found, skipping"
            continue
        }
        
        # Create representations for each column range
        set total_motifs 0
        foreach range $column_ranges {
            # Handle both single values and ranges
            if {[llength $range] == 1} {
                # Single column value
                set start_col [lindex $range 0]
                set end_col $start_col
            } else {
                # Range of columns
                set start_col [lindex $range 0]
                set end_col [lindex $range 1]
            }
            
            set residue_list [getOriginalResidFromMSAColumnRange $residue_results $alignment_seq_name $start_col $end_col]
            
            if {[llength $residue_list] > 0} {
                set residue_str [join $residue_list " "]
                mol selection "resid $residue_str"
                getResnameResid $molid "resid $residue_str" ; # print resid and name
                mol representation VDW
                mol color ColorID [expr {$total_motifs % 16}]
                mol material Opaque
                mol addrep $molid
                incr total_motifs
                if {$start_col == $end_col} {
                    puts "    Motif col $start_col: [llength $residue_list] residues"
                } else {
                    puts "    Motif cols $start_col-$end_col: [llength $residue_list] residues"
                }
            }
        }
        
        puts "  $mol_name: $total_motifs motif representations created"
    }
}



proc showKinasePocket {{molid top} {distance 5.0} {color_id 1} {material Opaque}} {
    # Add a NEW representation on top (do not modify existing reps)
    # Selection: protein within <distance> of nucleotide ligands
    if {$molid eq "top"} {
        set molid [molinfo top]
    }

    set lig_sel "resname AMP or resname ADP or resname ATP or resname GTP"
    set sel "protein and within $distance of ($lig_sel)"

    # Set representation state, then add a new rep to the given molecule
    mol selection $sel
    mol representation QuickSurf
    mol color ColorID $color_id
    mol material $material
    mol addrep $molid

    # Report where it was added
    set nreps [molinfo $molid get numreps]
    puts "Pocket representation added on top as rep index [expr {$nreps - 1}] for molecule $molid"
}


proc showCatalyticResidues {{molid top} {color_id 2} {material Opaque}} {
    if {$molid eq "top"} {
        set molid [molinfo top]
    }
    
    set key_catalytic_residues [getOriginalResid $molid 30 119 137]
    if {[llength $key_catalytic_residues] == 0} {
        puts "No catalytic residues found for molecule $molid"
        return
    }
    
    set resid_str [join $key_catalytic_residues " "]
    mol selection "resid $resid_str and name CA"
    mol representation VDW 1.0 12.0
    mol color ColorID $color_id
    mol material $material
    mol addrep $molid
    
    puts "Catalytic residues representation added for molecule $molid (resid: $resid_str)"
}


############################################################################################################
### TASK 4: ANALYSIS ###
proc analyzeMolecule {{molid_list ""}} {
    global molid_paths
    if {$molid_list eq ""} {
        set molid_list [molinfo list]
    }
    foreach molid $molid_list {
        if {[dict exists $molid_paths $molid]} {
            set mol_path [dict get $molid_paths $molid]
            mol top $molid
            cd $mol_path
            puts "Analyzing molecule ID $molid at path: $mol_path"
            ## Add analysis commands here, e.g., calculating distances, angles, etc.
            
            # RMSF for protein CA atoms ##########################################
            calcRmsfReference $molid "protein and name CA" $molid "protein and name CA" "rmsf.dat" "rmsf.pdb"
            # RMSF for all atoms including water######################################
            ###calcRmsfReference $molid "all" $molid "all" "rmsf_all.dat" "rmsf__all.pdb"
            calcRmsdReference $molid "protein and name CA" $molid "protein and name CA" "rmsd.dat"

            # RMSF for ligand (if present)
            set lig_sel "resname AMP or resname ADP or resname ATP or resname GTP"
            set lig_atoms [atomselect $molid $lig_sel]
            if {[$lig_atoms num] > 0} {
                calcRmsfReference $molid $lig_sel $molid $lig_sel "rmsf_ligand.dat" "rmsf_ligand.pdb"
                puts "  Analysis complete (protein + ligand)"
            } else {
                puts "  Analysis complete (protein only)"
            }
            $lig_atoms delete

            ################# COM of selections ##########################
            set key_catalytic_residues [getOriginalResid $molid 30 119 137]
            calcCenterOfMassMultiple $molid [list \
            "name CA and resid $key_catalytic_residues" \
            "resname AMP or resname ADP or resname ATP or resname GTP" \
            "resname MG"] \
            "com_trajectory.dat"
            ################# System Info ##########################
            animate goto 0
            getSysInfo $molid yes
    } else {
        puts "No path mapping found for molecule ID $molid"
    }
}
}


############################################################################################################
### UTILITY FUNCTIONS ###
proc availablePaths {} {
    global PROTEIN_JSON current_path
    set paths [listDataPaths $PROTEIN_JSON]
    puts "\nAvailable paths:"
    foreach path_key $paths {
        set path_value [getDataPath $PROTEIN_JSON $path_key]
        set status [expr {[file exists $path_value] ? "✓" : "✗"}]
        set current [expr {$path_value eq $current_path ? " (CURRENT)" : ""}]
        puts "  $path_key -> $path_value $status$current"
    }
}


proc setPath {path_key} {
    global PROTEIN_JSON current_path
    set new_path [getDataPath $PROTEIN_JSON $path_key]
    if {$new_path eq ""} {
        puts "Error: Path '$path_key' not found"
        availablePaths
        return 0
    }
    if {![file exists $new_path]} {
        puts "Warning: Path does not exist: $new_path"
    }
    set current_path $new_path
    puts "Changed path to: $current_path"
    return 1
}

proc clearMolidPaths {} {
    global molid_paths
    set molid_paths {}
    puts "Cleared all molid-to-path mappings"
}

proc getMolidPath { {molid_list "all"} } {
    global reference_molid molid_paths
    if {$molid_list ne "all"} {
        set all_molecules $molid_list
    } else {
        set all_molecules [molinfo list]
    }  

    if {[llength $all_molecules] == 0} {
        puts "No molecules loaded"
        return
    }
    
    puts "\nLoaded molecules (Reference: $reference_molid):"
    foreach molid $all_molecules {
        puts "$molid: [dict get $molid_paths $molid]"
    }
}

proc setReference {molid} {
    global reference_molid
    
    if {[catch {molinfo $molid get name}]} {
        puts "Error: Molecule ID $molid does not exist"
        return 0
    }
    
    set reference_molid $molid
    puts "Set reference molecule to ID: $molid"
    return 1
}

proc getProteinlist {} {
    global PROTEIN_JSON
    set proteins [getAllProteins $PROTEIN_JSON]
    puts $PROTEIN_JSON
    puts "\nAvailable proteins ([dict size $proteins] total):"
    dict for {id info} $proteins {
        set name [expr {[dict exists $info name] ? [dict get $info name] : "Unknown"}]
        puts "  $name ([string tolower $id])"
    }
}


proc simSettingFile { {sel all} } {
    set name [molinfo top get name]
    set uid [extractProteinIdentifiers $name]
    set folder [string tolower "atp_${uid}_kd1__amsa_atemp"]
    exec mkdir -p $folder
    cd $folder
    writePdbSel $sel
    cd ..
}


proc writePdbForPyrosetta {{molid_list ""}} {
    global molid_paths
    if {$molid_list eq ""} {
        set molid_list [molinfo list]
    }
    foreach molid $molid_list {
        if {[dict exists $molid_paths $molid]} {
            set mol_path [dict get $molid_paths $molid]
            mol top $molid
            cd $mol_path
            puts "Writing Pdb of molecule ID $molid at path: $mol_path"
            if {![file exists "0_pdbs"]} {
                exec mkdir -p 0_pdbs
            }
            cd 0_pdbs
            trajWritepdb all {0 20}

        } else {
            puts "No path mapping found for molecule ID $molid"
        }
    }
}


proc writeDockedPdbs {{molid_list ""}} {
    set molref 0
    global molid_paths
    if {$molid_list eq ""} {
        set molid_list [molinfo list]
    }
    foreach molid $molid_list {
        if {[dict exists $molid_paths $molid]} {
            set mol_path [dict get $molid_paths $molid]
            mol top $molid
            cd $mol_path
            puts "Writing Pdb of molecule ID $molid at path: $mol_path"
            if {![file exists "docked_pdbs_ref_KAPCA"]} {
                exec mkdir -p docked_pdbs_ref_KAPCA
            }
            cd docked_pdbs_ref_KAPCA
            for {set frame 0} {$frame < 20} {incr frame} {
                animate goto $frame
                set fname "${frame}.pdb"
                writeTwoSelectionsToOnePDB $molid "protein" $molref "resname AMP or resname ADP or resname ATP or resname GTP or resname MG" $fname
            }

        } else {
            puts "No path mapping found for molecule ID $molid"
        }
    }
}


proc showUsage {} {
    puts "\n=== VMD Pseudokinase Analysis - Three Main Tasks ==="
    puts ""
    puts "1. LOAD MOLECULES:"
    puts "   loadAF3_streamed {proteins} \[ligands\] - Load one-by-one, align to first as reference, analyze, then delete"
    puts "   loadAF3_streamed {proteins} \[ligands\]       - AF3: load first as reference, analyze; analyze+delete others"
    puts "   load_simulation_streamed {proteins} \[ligands\] \[reps\] - Sims: stream rep by rep; keep first as reference"
    puts "   load {protein_names} \[ligands\]              - Load proteins by name or UniProt ID"
    puts "   loadAF3ByKeyValue {key} {value}      - Load proteins filtered by database field"
    puts "   Examples:"
    puts "     load {ROP5Bi EpHB6}             - Load by protein names"
    puts "     load {f2ygr7 O15197}            - Load by UniProt IDs"
    puts "     load {ROP5Bi} {atp adp}         - Load with specific ligands"
    puts "     loadAF3ByKeyValue \"binding_lig_mg\" \"Nucleotide-Cation-binding-Mg1\""
    puts "                                     - Load all Mg2+-binding proteins"
    puts "     loadAF3ByKeyValue \"binding_type_JM\" \"No-binding\""
    puts "                                     - Load non-binding proteins (JM classification)"
    puts ""
    puts "2. SEQUENCE ALIGNMENT:"
    puts "   align \[ref_molid\]                - Align all molecules to reference"
    puts "   setReference <molid>              - Set reference molecule"
    puts "   Examples:"
    puts "     align                           - Align to current reference"
    puts "     align 2                         - Align to molecule 2"
    puts ""
    puts "3. MOTIF REPRESENTATION:"
    puts "   showMotifs {molids} {ranges}      - Create VDW representations for motifs"
    puts "   Examples:"
    puts "     showMotifs {0 1 2} {{27 30} {117 119}}  - VAIK and HRD motifs (ranges)"
    puts "     showMotifs {0} {{137 139}}               - DFG motif for molecule 0 (range)"
    puts "     showMotifs {0} {{55}}                    - Single column 55 for molecule 0"
    puts "     showMotifs {0 1} {{55} {60 65}}          - Column 55 and range 60-65"
    puts ""
    puts "UTILITIES:"
    puts "   printMolidNPath                     - List loaded molecules with paths"
    puts "   getMolidPath <molid>              - Get loaded path for molid"
    puts "   clearMolidPaths                   - Clear all molid-to-path mappings"
    puts ""
}

############################################################################################################
### INITIALIZATION ###

proc initializeScript {} {
    global PROTEIN_JSON MMA_FILE current_path motif_results residue_results molid_paths pseudo_uids fnl_uids grtrth_uids all_uids
    
    puts "=== VMD Pseudokinase Analysis Script ==="
    
    # Set default path
    set current_path [getDataPath $PROTEIN_JSON "af3_lig_2mg"]
    puts "Default path: $current_path"
    
    # Show available proteins' uniprots
    set pseudo_uids [getJsonDataFromKey "pseudokinase" $PROTEIN_JSON]
    set fnl_uids [getJsonDataFromKey "functional_kinase_missing_keyRes" $PROTEIN_JSON]
    set grtrth_uids [getJsonDataFromKey "ground_truth_kinase_uids" $PROTEIN_JSON]
    set all_uids [lsort -unique [concat $pseudo_uids $fnl_uids $grtrth_uids]]
    puts "Available proteins ([llength $all_uids] total):"

    # Load alignment data
    if {[file exists $MMA_FILE]} {
        set alignment_results [analyzeMMAlignment $MMA_FILE {{27 30} {117 119} {137 139}}]
        set motif_results [lindex $alignment_results 0]
        set residue_results [lindex $alignment_results 1]
        puts "Loaded alignment for [llength $residue_results] sequences"
    } else {
        puts "Warning: MMA file not found: $MMA_FILE"
    }
    
    showUsage
}

# Initialize the script
initializeScript
