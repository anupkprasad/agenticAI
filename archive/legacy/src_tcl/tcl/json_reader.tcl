#!/usr/bin/tclsh
#### JSON Database Reader - General Purpose Protein Information Utilities
# Anup K. Prasad
# anupkprasad121@gmail.com
# Ph.D @IITB-Monash Research Academy
#
# This module provides general-purpose functions for reading and querying
# protein information stored in JSON database files. It includes:
# - Protein information retrieval by UniProt ID or name
# - Data path management for different structure types
# - Search and filtering capabilities
# - Name/ID conversion utilities
#
# Dependencies:
#   - TCL json package (usually available in VMD and modern TCL installations)
# Install with: sudo apt-get install tcllib (on Ubuntu/Debian)
# Or download from: https://core.tcl-lang.org/tcllib/

package require json

############################################################################################################
### Core Database Access Functions ###

proc readProteinInfoFromJson {json_file uniprot_id} {
    # Read protein information from JSON file for a specific UniProt ID
    # Returns a dictionary with protein information or empty dict if not found
    # Now uses proteinSectionDict for better efficiency when called multiple times
    
    set all_proteins [proteinSectionDict $json_file]
    
    if {[dict exists $all_proteins $uniprot_id]} {
        set protein_info [dict get $all_proteins $uniprot_id]
        
        # Add UniProt ID to the returned info for convenience
        dict set protein_info uniprot_id $uniprot_id
        
        # Add sequence length if sequence exists
        if {[dict exists $protein_info sequence]} {
            set sequence [dict get $protein_info sequence]
            dict set protein_info sequence_length [string length $sequence]
        }
        
        return $protein_info
    }
    
    return {}
}

proc getProteinName {json_file uniprot_id} {
    # Get protein name from JSON file for a specific UniProt ID
    # Returns protein name or "Unknown" if not found
    
    set protein_info [readProteinInfoFromJson $json_file $uniprot_id]
    
    if {[dict exists $protein_info name]} {
        return [dict get $protein_info name]
    }
    
    return "Unknown"
}

proc getProteinBindingType {json_file uniprot_id {binding_field "binding_lig_mg"}} {
    # Get specific binding type from JSON file for a specific UniProt ID
    # binding_field can be: "binding_type_JM", "binding_type_visAMP", or "binding_lig_mg"
    # Returns binding type or "Unknown" if not found
    
    set protein_info [readProteinInfoFromJson $json_file $uniprot_id]
    
    if {[dict exists $protein_info $binding_field]} {
        return [dict get $protein_info $binding_field]
    }
    
    return "Unknown"
}

proc getProteinSequence {json_file uniprot_id} {
    # Get protein sequence from JSON file for a specific UniProt ID
    # Returns sequence or empty string if not found
    
    set protein_info [readProteinInfoFromJson $json_file $uniprot_id]
    
    if {[dict exists $protein_info sequence]} {
        return [dict get $protein_info sequence]
    }
    
    return ""
}

proc printProteinInfo {protein_info} {
    # Print protein information in a formatted way
    
    if {[dict size $protein_info] == 0} {
        puts "  No protein information found"
        return
    }
    
    if {[dict exists $protein_info name]} {
        puts "  Protein name: [dict get $protein_info name]"
    }
    
    if {[dict exists $protein_info uniprot_id]} {
        puts "  UniProt ID: [dict get $protein_info uniprot_id]"
    }
    
    if {[dict exists $protein_info description]} {
        puts "  Description: [dict get $protein_info description]"
    }
    
    if {[dict exists $protein_info binding_type_JM]} {
        puts "  Binding type (JM): [dict get $protein_info binding_type_JM]"
    }
    
    if {[dict exists $protein_info binding_lig_mg]} {
        puts "  Binding type (Lig+Mg): [dict get $protein_info binding_lig_mg]"
    }
    
    if {[dict exists $protein_info Mg_in_pocket]} {
        puts "  Mg in pocket: [dict get $protein_info Mg_in_pocket]"
    }
    
    if {[dict exists $protein_info sequence_length]} {
        puts "  Sequence length: [dict get $protein_info sequence_length] residues"
    }
    
    if {[dict exists $protein_info remark]} {
        puts "  Remark: [dict get $protein_info remark]"
    }
}

############################################################################################################
### Data Path Management Functions ###

proc getDataPaths {json_file} {
    # Get all data paths from JSON file
    # Returns a dictionary with data path mappings or empty dict if not found
    
    if {![file exists $json_file]} {
        puts "Warning: JSON file not found: $json_file"
        return {}
    }
    
    # Read JSON file into a string
    set fp [open $json_file r]
    set json_str [read $fp]
    close $fp
    
    # Parse JSON -> Tcl dict
    set data [json::json2dict $json_str]
    
    # Navigate to data_path section
    if {[dict exists $data data_path]} {
        return [dict get $data data_path]
    }
    
    return {}
}

####### get sepecific key data from json file ########
proc getJsonDataFromKey {key json_file} {
    # Read JSON file into a string
    set fp [open $json_file r]
    set json_str [read $fp]
    close $fp
    set data [json::json2dict $json_str]
    if {[dict exists $data $key]} {
        return [dict get $data $key]
    }
    return {}
}

proc getDataPath {json_file path_key} {
    # Get specific data path from JSON file
    # path_key can be: "ground-truth", "af3_lig_2mg", "af3_lig_1mg", etc.
    # Returns path string or empty string if not found
    
    set data_paths [getDataPaths $json_file]
    
    if {[dict exists $data_paths $path_key]} {
        return [dict get $data_paths $path_key]
    }
    
    return ""
}

proc listDataPaths {json_file} {
    # List all available data path keys
    # Returns list of available path keys
    
    set data_paths [getDataPaths $json_file]
    return [dict keys $data_paths]
}

proc validateDataPath {json_file path_key} {
    # Validate that a data path exists on the filesystem
    # Returns 1 if path exists, 0 if not found or doesn't exist
    
    set data_path [getDataPath $json_file $path_key]
    
    if {$data_path eq ""} {
        puts "Warning: Data path key '$path_key' not found in JSON"
        return 0
    }
    
    if {[file exists $data_path]} {
        return 1
    } else {
        puts "Warning: Data path '$data_path' does not exist on filesystem"
        return 0
    }
}

proc constructFilePath {json_file path_key filename} {
    # Construct a full file path using a data path key and filename
    # Returns full path or empty string if path_key not found
    
    set data_path [getDataPath $json_file $path_key]
    
    if {$data_path eq ""} {
        puts "Warning: Data path key '$path_key' not found"
        return ""
    }
    
    return [file join $data_path $filename]
}

proc getProteinStructurePath {json_file uniprot_id structure_type {extension ".pdb"}} {
    # Get the path to a specific protein structure file
    # structure_type can be: "ground-truth", "af3_lig_2mg", "af3_lig_1mg"
    # extension defaults to ".pdb" but can be ".cif" or others
    # Returns full path or empty string if not found
    
    set data_path [getDataPath $json_file $structure_type]
    
    if {$data_path eq ""} {
        puts "Warning: Structure type '$structure_type' not found"
        return ""
    }
    
    set filename "${uniprot_id}${extension}"
    return [file join $data_path $filename]
}

############################################################################################################
### Main Utility Functions ###

proc proteinSectionDict {json_file} {
    # Main utility function to get all protein information from JSON file
    # Returns a dictionary with all proteins data or empty dict if file not found
    # This is the base function that other procedures can use efficiently
    
    if {![file exists $json_file]} {
        puts "Warning: JSON file not found: $json_file"
        return {}
    }
    
    # Read JSON file into a string (do this only once)
    set fp [open $json_file r]
    set json_str [read $fp]
    close $fp
    
    # Parse JSON -> Tcl dict
    set data [json::json2dict $json_str]
    
    # Return the proteins section
    if {[dict exists $data proteins]} {
        return [dict get $data proteins]
    }
    
    return {}
}

proc listAllProteins {json_file} {
    # List all proteins with name:uniprot_id format
    # Returns a list of "name:uniprot_id" strings
    
    set all_proteins [proteinSectionDict $json_file]
    set protein_list {}
    
    if {[dict size $all_proteins] == 0} {
        puts "No proteins found in database"
        return {}
    }
    
    puts "\n=== All Proteins in Database ==="
    puts [format "%-15s %-12s %-30s" "Name" "UniProt ID" "Description"]
    puts [string repeat "-" 60]
    
    dict for {uniprot_id protein_info} $all_proteins {
        set name [dict get $protein_info name]
        set description [dict get $protein_info description]
        
        # Truncate description if too long
        if {[string length $description] > 25} {
            set description "[string range $description 0 22]..."
        }
        
        puts [format "%-15s %-12s %-30s" $name $uniprot_id $description]
        lappend protein_list "$name:$uniprot_id"
    }
    
    puts [string repeat "=" 60]
    puts "Total proteins: [dict size $all_proteins]"
    
    return $protein_list
}

proc getUniprotIdByName {json_file protein_name} {
    # Find UniProt ID by protein name (case-insensitive search)
    # Returns UniProt ID or empty string if not found
    
    set all_proteins [proteinSectionDict $json_file]
    set protein_name_lower [string tolower $protein_name]
    
    dict for {uniprot_id protein_info} $all_proteins {
        set current_name [dict get $protein_info name]
        set current_name_lower [string tolower $current_name]
        
        if {$current_name_lower eq $protein_name_lower} {
            return $uniprot_id
        }
    }
    
    # If exact match not found, try partial match
    dict for {uniprot_id protein_info} $all_proteins {
        set current_name [dict get $protein_info name]
        set current_name_lower [string tolower $current_name]
        
        if {[string match "*${protein_name_lower}*" $current_name_lower]} {
            puts "Found partial match: $current_name ($uniprot_id)"
            return $uniprot_id
        }
    }
    
    puts "Warning: Protein name '$protein_name' not found"
    return ""
}

proc getProteinlistByKeyValue {json_file field_name field_value} {
    # Search proteins by any field value
    # Returns dictionary of matching proteins
    
    set all_proteins [proteinSectionDict $json_file]
    set matches {}
    
    dict for {uniprot_id protein_info} $all_proteins {
        if {[dict exists $protein_info $field_name]} {
            set current_value [dict get $protein_info $field_name]
            if {[string match "*${field_value}*" $current_value]} {
                lappend matches $uniprot_id
            }
        }
    }
    
    return $matches
}

############################################################################################################
### Name/ID Conversion Functions ###

proc getUniprotFromProteinName {json_file protein_name} {
    # Find UniProt ID by protein name (exact or partial match)
    # Returns UniProt ID (lowercase) or the input if not found
    
    set all_proteins [proteinSectionDict $json_file]
    set protein_name_lower [string tolower $protein_name]
    
    # First try exact name match
    dict for {uniprot_id protein_info} $all_proteins {
        if {[dict exists $protein_info name]} {
            set name [string tolower [dict get $protein_info name]]
            if {$name eq $protein_name_lower} {
                return [string tolower $uniprot_id]
            }
        }
    }
    
    # If no exact match, try partial match
    dict for {uniprot_id protein_info} $all_proteins {
        if {[dict exists $protein_info name]} {
            set name [string tolower [dict get $protein_info name]]
            if {[string match "*$protein_name_lower*" $name]} {
                return [string tolower $uniprot_id]
            }
        }
    }
    
    # If still no match, assume it's already a UniProt ID
    return [string tolower $protein_name]
}

proc getProteinNameFromUniprot {json_file uniprot_id} {
    # Get protein name from UniProt ID
    # Returns protein name or the UniProt ID if name not found
    
    set all_proteins [proteinSectionDict $json_file]
    set uniprot_upper [string toupper $uniprot_id]
    
    if {[dict exists $all_proteins $uniprot_upper]} {
        set protein_info [dict get $all_proteins $uniprot_upper]
        if {[dict exists $protein_info name]} {
            return [dict get $protein_info name]
        }
    }
    
    return $uniprot_id
}









############################################################################################################
### Help and Documentation Functions ###

proc listJsonReaderProcs {} {
    # List all available procedures in json_reader.tcl with descriptions
    # Use this in VMD console to see what functions are available
    
    puts "\n=== JSON Reader Procedures ==="
    puts "Available procedures for protein database management:\n"
    
    puts "MAIN UTILITY FUNCTIONS:"
    puts "  proteinSectionDict json_file"
    puts "    -> Get all protein data as dictionary (base function for efficiency)"
    puts "  listAllProteins json_file"
    puts "    -> Display formatted list of all proteins with name:uniprot_id"
    puts "  getUniprotIdByName json_file protein_name"
    puts "    -> Find UniProt ID by protein name (case-insensitive)"
    puts "  getUniprotFromProteinName json_file protein_name"
    puts "    -> Convert protein name to UniProt ID (exact/partial match)"
    puts "  getProteinNameFromUniprot json_file uniprot_id"
    puts "    -> Convert UniProt ID to protein name"
    puts ""
    
    puts "PROTEIN INFORMATION FUNCTIONS:"
    puts "  readProteinInfoFromJson json_file uniprot_id"
    puts "    -> Get complete protein info dictionary for specific UniProt ID"
    puts "  getProteinName json_file uniprot_id"
    puts "    -> Get protein name for specific UniProt ID"
    puts "  getProteinBindingType json_file uniprot_id ?binding_field?"
    puts "    -> Get binding type (default: binding_lig_mg)"
    puts "  getProteinSequence json_file uniprot_id"
    puts "    -> Get protein sequence string"
    puts "  printProteinInfo protein_info_dict"
    puts "    -> Print formatted protein information"
    puts "  getProteinlistByKeyValue json_file field_name field_value"
    puts "    -> Search proteins by any field value (returns uniprot_id list)"
    puts "Example: set no_binding_proteins [getProteinlistByKeyValue $json_file "binding_lig_mg" "Unknown"]"
    
    puts "DATA PATH FUNCTIONS:"
    puts "  getDataPaths json_file"
    puts "    -> Get all data path mappings as dictionary"
    puts "  getDataPath json_file path_key"
    puts "    -> Get specific data path (ground-truth, af3_lig_2mg, af3_lig_1mg)"
    puts "  listDataPaths json_file"
    puts "    -> List all available data path keys"
    puts "  validateDataPath json_file path_key"
    puts "    -> Check if data path exists on filesystem (returns 1/0)"
    puts ""
    
    puts "FILE PATH UTILITIES:"
    puts "  constructFilePath json_file path_key filename"
    puts "    -> Construct full file path using data path and filename"
    puts "  getProteinStructurePath json_file uniprot_id structure_type ?extension?"
    puts "    -> Get path to protein structure file (default extension: .pdb)"
    puts ""
    
    puts "HELP:"
    puts "  listJsonReaderProcs"
    puts "    -> Display this help message"
    puts ""
    
    puts "EXAMPLE USAGE:"
    puts "  set json_file \"protein_info.json\""
    puts "  set uniprot_id [getUniprotIdByName \$json_file \"CASK\"]"
    puts "  set protein_info [readProteinInfoFromJson \$json_file \$uniprot_id]"
    puts "  printProteinInfo \$protein_info"
    puts "  set structure_path [getProteinStructurePath \$json_file \$uniprot_id \"ground-truth\"]"
    puts ""
    
    puts "=== End of JSON Reader Procedures ==="
}

proc listJsonReaderProcsCompact {} {
    # Show a compact list of all available procedures
    
    puts "\n=== JSON Reader Procedures (Compact) ==="
    puts "Main:     proteinSectionDict, listAllProteins, getUniprotIdByName"
    puts "          getUniprotFromProteinName, getProteinNameFromUniprot"
    puts "Info:     readProteinInfoFromJson, getProteinName, getProteinBindingType"
    puts "          getProteinSequence, printProteinInfo"
    puts "Search:   getProteinlistByKeyValue"
    puts "Paths:    getDataPaths, getDataPath, listDataPaths, validateDataPath"
    puts "Utils:    constructFilePath, getProteinStructurePath"
    puts "Help:     listJsonReaderProcs, helpJsonReader, listJsonReaderProcsCompact"
    puts "=========================================="
}

proc helpJsonReader {} {
    # Alias for listJsonReaderProcs - shorter command
    listJsonReaderProcs
}

proc jsonReaderHelp {} {
    # Another alias for listJsonReaderProcs
    listJsonReaderProcs
}

# Example usage:
# set json_file "protein_info.json"
#
# # Main utility functions
# set all_proteins [proteinSectionDict $json_file]
# set protein_list [listAllProteins $json_file]
#
# # Find UniProt ID by protein name
# set uniprot_id [getUniprotIdByName $json_file "CASK"]
# puts "Found UniProt ID: $uniprot_id"
#
# # Read specific protein information
# set protein_info [readProteinInfoFromJson $json_file $uniprot_id]
# printProteinInfo $protein_info
#
# # Get specific fields
# set name [getProteinName $json_file $uniprot_id]
# set binding_type [getProteinBindingType $json_file $uniprot_id]
# set sequence [getProteinSequence $json_file $uniprot_id]
#
# # Search proteins by field
# set no_binding_proteins [getProteinlistByKeyValue $json_file "binding_lig_mg" "No-binding"]
#
# # Work with data paths
# set all_paths [getDataPaths $json_file]
# set path_keys [listDataPaths $json_file]
# set ground_truth_path [getDataPath $json_file "ground-truth"]
#
# # Validate and construct paths
# if {[validateDataPath $json_file "ground-truth"]} {
#     set structure_file [getProteinStructurePath $json_file $uniprot_id "ground-truth"]
#     puts "Structure file: $structure_file"
# }
#
# # Construct custom file paths
# set custom_file [constructFilePath $json_file "af3_lig_2mg" "analysis_results.txt"]
