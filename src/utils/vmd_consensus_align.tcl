################################################################################
# vmd_consensus_align.tcl
#
# VMD helpers to load SimAgent / framework residue_map.csv files, register PDBs
# by protein name, align on consensus Cα residues, and toggle visualization.
#
# Supported CSV formats (auto-detected from headers):
#   - reference_msa_residue_map.csv     (wide: NAME_resid, NAME_aa, …)
#   - reference_pocket_residue_map.csv  (same NAME_resid columns; pocket subset)
#
# PDB naming: each protein is expected as NAME.pdb (case-insensitive stem),
# e.g. JAK1.pdb, MLKL.pdb. Molecules already loaded in VMD can be registered
# by name with  register_protein NAME molid
#
# ---------------------------------------------------------------------------
# Quick start (in VMD TkConsole or: vmd -e vmd_consensus_align.tcl)
# ---------------------------------------------------------------------------
#
#   source /path/to/agenticAI/src/utils/vmd_consensus_align.tcl
#
#   # 1) Load consensus / pocket residue map
#   load_map /path/to/reference_msa_residue_map.csv
#
#   # 2) UniProt ID (q8nb16.pdb) → display name (MLKL)
#   load_aliases /path/to/protein_aliases.csv
#
#   # 3) Load PDBs from a directory (NOT a glob like ./*.pdb)
#   load_pdbs .
#
#   # 4) Align all onto reference
#   align_all MLKL
#
#   # 5) Visibility — names are case-insensitive
#   show all
#   show JAK1 JAK3 MLKL
#   hide all
#   show JAK1
#
#   # 6) Consensus-residue views
#   show_consensus all
#   color_consensus rainbow
#   highlight_consensus only
#
#   help_consensus
#
# ---------------------------------------------------------------------------
# Authors: SimAgent utilities  |  location: src/utils/vmd_consensus_align.tcl
################################################################################

namespace eval ::consensus {
    variable mol_by_name
    array unset mol_by_name
    array set mol_by_name {}

    variable resids_by_name
    array unset resids_by_name
    array set resids_by_name {}

    variable proteins {}          ;# ordered protein names present in the map
    variable reference_label ""   ;# from CSV reference_label column / header meta
    variable map_path ""
    variable n_consensus 0
    variable file_alias
    array unset file_alias
    array set file_alias {}
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

proc ::consensus::_toupper {s} {
    return [string toupper $s]
}

proc ::consensus::_normalize_name {name} {
    # Strip path / extension and uppercase for dictionary keys
    set base [file rootname [file tail $name]]
    return [string toupper $base]
}

proc ::consensus::_split_csv_line {line} {
    # Minimal CSV split (no quoted commas in these maps)
    set line [string trimright $line "\r\n"]
    return [split $line ","]
}

proc ::consensus::_log {msg} {
    puts "consensus> $msg"
}

proc ::consensus::_warn {msg} {
    puts "consensus WARNING> $msg"
}

proc ::consensus::_molid {name} {
    variable mol_by_name
    set key [::consensus::_normalize_name $name]
    if {[info exists mol_by_name($key)]} {
        return $mol_by_name($key)
    }
    return -1
}

proc ::consensus::_known_names {} {
    variable mol_by_name
    return [lsort -dictionary [array names mol_by_name]]
}

proc ::consensus::_map_names {} {
    variable proteins
    return $proteins
}

proc ::consensus::_resid_list {name} {
    variable resids_by_name
    set key [::consensus::_normalize_name $name]
    if {[info exists resids_by_name($key)]} {
        return $resids_by_name($key)
    }
    return {}
}

proc ::consensus::_ca_seltext {name} {
    set resids [::consensus::_resid_list $name]
    if {[llength $resids] == 0} {
        return ""
    }
    return "name CA and resid [join $resids]"
}

proc ::consensus::_paired_ca_lists {ref_name mobile_name} {
    # Return two equal-length resid lists (ref, mobile) for positions mapped
    # in *both* proteins, preserving consensus row order.
    variable resids_by_name
    set rk [::consensus::_normalize_name $ref_name]
    set mk [::consensus::_normalize_name $mobile_name]
    if {![info exists resids_by_name($rk)] || ![info exists resids_by_name($mk)]} {
        return [list {} {}]
    }
    set rlist $resids_by_name($rk)
    set mlist $resids_by_name($mk)
    # resids_by_name stores parallel lists including empty slots as "" for gaps;
    # after load_map we store only mapped integers OR parallel with "" — see load_map.
    # For alignment we need matched consensus positions: use paired_lists if stored.
    variable paired
    if {[info exists paired($rk,$mk)]} {
        return $paired($rk,$mk)
    }
    # Fall back: intersect by sequential index when lists are consensus-aligned
    variable aligned_resids
    if {[info exists aligned_resids($rk)] && [info exists aligned_resids($mk)]} {
        set rr $aligned_resids($rk)
        set mm $aligned_resids($mk)
        set out_r {}
        set out_m {}
        set n [llength $rr]
        if {[llength $mm] < $n} { set n [llength $mm] }
        for {set i 0} {$i < $n} {incr i} {
            set a [lindex $rr $i]
            set b [lindex $mm $i]
            if {$a ne "" && $b ne ""} {
                lappend out_r $a
                lappend out_m $b
            }
        }
        return [list $out_r $out_m]
    }
    # Last resort: use unordered resid sets (order may be wrong — avoid)
    return [list $rlist $mlist]
}

# ---------------------------------------------------------------------------
# Map / PDB loading
# ---------------------------------------------------------------------------

proc ::consensus::load_map {csv_path} {
    variable mol_by_name
    variable resids_by_name
    variable aligned_resids
    variable proteins
    variable reference_label
    variable map_path
    variable n_consensus

    if {![file exists $csv_path]} {
        error "load_map: file not found: $csv_path"
    }

    array unset resids_by_name
    array set resids_by_name {}
    array unset aligned_resids
    array set aligned_resids {}
    set proteins {}
    set reference_label ""
    set map_path $csv_path
    set n_consensus 0

    set fh [open $csv_path r]
    set header_line [gets $fh]
    set headers [::consensus::_split_csv_line $header_line]

    # Map column index -> protein name for *_resid columns
    set resid_col {}
    set ref_resid_col -1
    set ref_label_col -1
    set i 0
    foreach h $headers {
        set h [string trim $h]
        if {[string equal -nocase $h "reference_label"]} {
            set ref_label_col $i
        } elseif {[string equal -nocase $h "reference_resid"]} {
            set ref_resid_col $i
        } elseif {[string match -nocase "*_resid" $h]} {
            set pname [string range $h 0 end-6]
            # Prefer protein-specific columns over the reference_resid meta column
            if {![string equal -nocase $pname "reference"]} {
                dict set resid_col $i [::consensus::_normalize_name $pname]
            }
        }
        incr i
    }

    if {[dict size $resid_col] == 0} {
        close $fh
        error "load_map: no NAME_resid columns found in $csv_path"
    }

    foreach pname [lsort -unique [dict values $resid_col]] {
        set aligned_resids($pname) {}
        lappend proteins $pname
    }

    set row 0
    while {[gets $fh line] >= 0} {
        if {[string trim $line] eq ""} { continue }
        set fields [::consensus::_split_csv_line $line]
        if {$ref_label_col >= 0 && $reference_label eq ""} {
            set rl [string trim [lindex $fields $ref_label_col]]
            if {$rl ne ""} {
                set reference_label [::consensus::_normalize_name $rl]
            }
        }
        dict for {col pname} $resid_col {
            set val [string trim [lindex $fields $col]]
            if {$val eq "" || ![string is integer -strict $val]} {
                lappend aligned_resids($pname) ""
            } else {
                lappend aligned_resids($pname) $val
            }
        }
        incr row
    }
    close $fh
    set n_consensus $row

    # Compact resid lists (unique, mapped only) for selection strings
    foreach pname $proteins {
        set compact {}
        foreach r $aligned_resids($pname) {
            if {$r ne ""} { lappend compact $r }
        }
        # unique preserve order
        set seen {}
        set uniq {}
        foreach r $compact {
            if {![dict exists $seen $r]} {
                dict set seen $r 1
                lappend uniq $r
            }
        }
        set resids_by_name($pname) $uniq
    }

    ::consensus::_log "Loaded map: $csv_path"
    ::consensus::_log "  consensus rows: $n_consensus"
    ::consensus::_log "  proteins in map: [llength $proteins]"
    if {$reference_label ne ""} {
        ::consensus::_log "  reference_label: $reference_label"
    }
    return [llength $proteins]
}

proc ::consensus::register_protein {name molid} {
    variable mol_by_name
    set key [::consensus::_normalize_name $name]
    set mol_by_name($key) $molid
    ::consensus::_log "Registered $key → molid $molid ([molinfo $molid get name])"
}

proc ::consensus::load_aliases {alias_path} {
    # Map UniProt / file-stem → display name used in residue_map.csv.
    # Accepts:
    #   - reference_pca_manifest.json  (sim_directories: NAME → …/uniprot)
    #   - two-column CSV/TSV/space:  uniprot,DISPLAY   or  DISPLAY,uniprot
    #   - lines: q8nb16 MLKL
    variable file_alias
    array unset file_alias
    array set file_alias {}

    if {![file exists $alias_path]} {
        error "load_aliases: not found: $alias_path"
    }

    set ext [string tolower [file extension $alias_path]]
    if {$ext eq ".json"} {
        set fh [open $alias_path r]
        set raw [read $fh]
        close $fh
        # Minimal parse: find "DISPLAY": ".../uniprot" entries inside sim_directories
        # Prefer reliable line-oriented scrape of "NAME": ".../uid"
        foreach line [split $raw "\n"] {
            if {[regexp {"([A-Za-z0-9_+-]+)"\s*:\s*"([^"]+)"} $line -> disp path]} {
                set stem [file tail $path]
                # skip non-path-looking values
                if {[string match "*/*" $path] || [string match "*.pdb" $path] || \
                    [regexp {^[opQq][0-9a-zA-Z]+$} $stem]} {
                    set file_alias([string toupper $stem]) [string toupper $disp]
                    set file_alias([string toupper $disp]) [string toupper $disp]
                }
            }
        }
    } else {
        set fh [open $alias_path r]
        while {[gets $fh line] >= 0} {
            set line [string trim $line]
            if {$line eq "" || [string match "#*" $line]} { continue }
            set line [string map {, " " \; " " \t " "} $line]
            set parts [split $line]
            # filter empty
            set toks {}
            foreach p $parts {
                if {[string trim $p] ne ""} { lappend toks [string trim $p] }
            }
            if {[llength $toks] < 2} { continue }
            set a [string toupper [lindex $toks 0]]
            set b [string toupper [lindex $toks 1]]
            # Skip header-ish
            if {$a eq "UNIPROT" || $a eq "LABEL" || $a eq "DISPLAY_NAME"} { continue }
            # uniprot → display (heuristic: uniprot-like first token)
            if {[regexp {^[OPQ][0-9][A-Z0-9]{3}[0-9]$} $a] || [regexp {^[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]$} $a] \
                || [regexp {^[OPQopqn][0-9a-zA-Z]+$} $a]} {
                set file_alias($a) $b
            } else {
                # display,uniprot
                set file_alias($b) $a
                set file_alias($a) $a
            }
        }
        close $fh
    }

    set n [array size file_alias]
    ::consensus::_log "Loaded aliases from $alias_path ($n entries)"
    return $n
}

proc ::consensus::_display_for_stem {stem} {
    variable file_alias
    variable proteins
    set key [string toupper $stem]
    if {[info exists file_alias($key)]} {
        return $file_alias($key)
    }
    # Already a mapped display name?
    foreach p $proteins {
        if {[string equal -nocase $p $stem]} {
            return [string toupper $p]
        }
    }
    return $key
}

proc ::consensus::load_pdb {name pdb_path} {
    if {![file exists $pdb_path]} {
        error "load_pdb: not found: $pdb_path"
    }
    set molid [mol new $pdb_path type pdb waitfor all]
    mol rename $molid [::consensus::_normalize_name $name]
    ::consensus::register_protein $name $molid
    return $molid
}

proc ::consensus::load_pdbs {{dir .}} {
    variable proteins
    variable file_alias

    # Allow a single .pdb path as convenience
    if {[file isfile $dir] && [string match -nocase *.pdb $dir]} {
        set stem [file rootname [file tail $dir]]
        set dname [::consensus::_display_for_stem $stem]
        return [::consensus::load_pdb $dname $dir]
    }

    if {![file isdirectory $dir]} {
        error "load_pdbs: pass a *directory* (e.g. load_pdbs .), not a glob.\n  Your PDBs from pseudoKin/ are usually named by UniProt ID (q8nb16.pdb),\n  while the residue map uses display names (MLKL). Load aliases first:\n    load_aliases /path/to/reference_pca_manifest.json\n    load_pdbs ."
    }

    set pdb_files [lsort [glob -nocomplain -directory $dir *.pdb]]
    if {[llength $pdb_files] == 0} {
        ::consensus::_warn "No *.pdb files in $dir"
        return 0
    }

    set loaded 0
    set skipped {}

    if {[llength $proteins] == 0} {
        foreach f $pdb_files {
            set stem [file rootname [file tail $f]]
            set dname [::consensus::_display_for_stem $stem]
            ::consensus::load_pdb $dname $f
            incr loaded
        }
        ::consensus::_log "Loaded $loaded PDB(s) from $dir (no residue map yet)"
        return $loaded
    }

    # Index files by uppercase stem
    array set by_stem {}
    foreach f $pdb_files {
        set stem [string toupper [file rootname [file tail $f]]]
        set by_stem($stem) $f
    }

    foreach pname $proteins {
        set found ""
        set pu [string toupper $pname]
        # 1) DISPLAY.pdb
        if {[info exists by_stem($pu)]} {
            set found $by_stem($pu)
        }
        # 2) UniProt.pdb via reverse alias (display → uniprot stems)
        if {$found eq "" && [info exists file_alias]} {
            foreach stem [array names by_stem] {
                if {[info exists file_alias($stem)] && \
                    [string equal -nocase $file_alias($stem) $pname]} {
                    set found $by_stem($stem)
                    break
                }
            }
        }
        # 3) Common case variants already covered by uppercase index
        if {$found eq ""} {
            lappend skipped $pname
            continue
        }
        ::consensus::load_pdb $pname $found
        incr loaded
    }

    ::consensus::_log "Loaded $loaded / [llength $proteins] mapped protein PDB(s) from $dir"
    if {[llength $skipped] > 0} {
        ::consensus::_warn "Missing PDB for: [join $skipped {, }]"
        ::consensus::_warn "If files are UniProt-named (q8nb16.pdb), run:"
        ::consensus::_warn "  load_aliases <reference_pca_manifest.json or protein_aliases.csv>"
        ::consensus::_warn "  load_pdbs ."
    }
    return $loaded
}

# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

proc ::consensus::align_to {mobile_name {ref_name ""}} {
    variable reference_label
    if {$ref_name eq ""} {
        if {$reference_label eq ""} {
            error "align_to: set a reference (align_to MOBILE REF) or load_map with reference_label"
        }
        set ref_name $reference_label
    }

    set mid [::consensus::_molid $mobile_name]
    set rid [::consensus::_molid $ref_name]
    if {$mid < 0} { error "align_to: protein not loaded: $mobile_name" }
    if {$rid < 0} { error "align_to: reference not loaded: $ref_name" }
    if {$mid == $rid} { return }

    lassign [::consensus::_paired_ca_lists $ref_name $mobile_name] rres mres
    if {[llength $rres] < 3} {
        error "align_to: fewer than 3 shared consensus Cα between $ref_name and $mobile_name"
    }

    set sel_r [atomselect $rid "name CA and resid [join $rres]"]
    set sel_m [atomselect $mid "name CA and resid [join $mres]"]
    if {[$sel_r num] != [$sel_m num] || [$sel_r num] < 3} {
        set nr [$sel_r num]
        set nm [$sel_m num]
        $sel_r delete
        $sel_m delete
        error "align_to: CA count mismatch ($ref_name=$nr, $mobile_name=$nm); check residue numbers in PDBs"
    }

    set M [measure fit $sel_m $sel_r]
    set all [atomselect $mid all]
    $all move $M
    $all delete
    $sel_r delete
    $sel_m delete
    ::consensus::_log "Aligned $mobile_name → $ref_name  (n_CA=[llength $rres])"
}

proc ::consensus::align_all {{ref_name ""}} {
    variable reference_label
    variable mol_by_name
    if {$ref_name eq ""} {
        set ref_name $reference_label
    }
    if {$ref_name eq ""} {
        error "align_all: provide reference name or load_map with reference_label"
    }
    if {[::consensus::_molid $ref_name] < 0} {
        error "align_all: reference not loaded: $ref_name"
    }
    set n 0
    foreach name [::consensus::_known_names] {
        if {[string equal -nocase $name $ref_name]} { continue }
        if {[catch {::consensus::align_to $name $ref_name} err]} {
            ::consensus::_warn "$name: $err"
        } else {
            incr n
        }
    }
    ::consensus::_log "align_all: aligned $n molecule(s) onto $ref_name"
}

# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

proc ::consensus::_resolve_name_list {args} {
    # Expand: all | protein (synonym) | NAME NAME …
    # Accepts nested lists (e.g. after splat from another proc).
    variable mol_by_name
    set flat [concat {*}$args]
    if {[llength $flat] == 0} {
        return {}
    }
    set first [string tolower [lindex $flat 0]]
    if {$first eq "all" || $first eq "protein" || $first eq "proteins" \
        || $first eq "everything"} {
        return [::consensus::_known_names]
    }
    set out {}
    foreach a $flat {
        set key [::consensus::_normalize_name $a]
        if {[info exists mol_by_name($key)]} {
            lappend out $key
        } else {
            ::consensus::_warn "unknown / not loaded: $a"
        }
    }
    return $out
}

proc ::consensus::show {args} {
    if {[llength $args] == 0} {
        ::consensus::_log "usage: show all | show protein | show NAME \[NAME …\]"
        return
    }
    set names [::consensus::_resolve_name_list {*}$args]
    foreach name [::consensus::_known_names] {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }
        if {[lsearch -exact $names $name] >= 0} {
            mol on $mid
        } else {
            mol off $mid
        }
    }
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid >= 0} { mol on $mid }
    }
    ::consensus::_log "show: [join $names {, }]"
}

proc ::consensus::hide {args} {
    if {[llength $args] == 0} {
        ::consensus::_log "usage: hide all | hide NAME \[NAME …\] | hide_everything"
        return
    }
    set names [::consensus::_resolve_name_list {*}$args]
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid >= 0} { mol off $mid }
    }
    ::consensus::_log "hide: [join $names {, }]"
}

proc ::consensus::hide_everything {} {
    # Turn off every molecule currently in VMD
    set n 0
    foreach mid [molinfo list] {
        mol off $mid
        incr n
    }
    ::consensus::_log "hide_everything: hid $n molecule(s)"
}

proc ::consensus::show_everything {} {
    # Turn on every molecule currently in VMD
    set n 0
    foreach mid [molinfo list] {
        mol on $mid
        incr n
    }
    ::consensus::_log "show_everything: showed $n molecule(s)"
}

proc ::consensus::list_proteins {} {
    variable mol_by_name
    variable resids_by_name
    variable reference_label
    ::consensus::_log "reference_label: $reference_label"
    ::consensus::_log "loaded molecules:"
    foreach name [::consensus::_known_names] {
        set mid $mol_by_name($name)
        set nmap 0
        if {[info exists resids_by_name($name)]} {
            set nmap [llength $resids_by_name($name)]
        }
        puts [format "  %-10s  molid=%-4s  consensus_resids=%d  on=%s" \
            $name $mid $nmap [molinfo $mid get displayed]]
    }
    ::consensus::_log "in map but not loaded:"
    foreach pname [::consensus::_map_names] {
        if {[::consensus::_molid $pname] < 0} {
            puts "  $pname"
        }
    }
}

# ---------------------------------------------------------------------------
# Protein + ligand visualization
# ---------------------------------------------------------------------------

proc ::consensus::_keep_rep0_only {molid} {
    # Drop overlay reps (ATP / consensus) but keep VMD's original rep 0.
    set n [molinfo $molid get numreps]
    for {set i [expr {$n - 1}]} {$i >= 1} {incr i -1} {
        mol delrep $i $molid
    }
}

proc ::consensus::_style_atp_orange {molid} {
    # Add ATP as Licorice / orange. Does not change protein representation.
    set atp_sel {resname ATP}
    set ag [atomselect $molid $atp_sel]
    set natp [$ag num]
    $ag delete
    if {$natp <= 0} {
        return 0
    }
    # ColorID 3 = orange in VMD
    mol color ColorID 3
    mol representation Licorice 0.3 12.0 12.0
    mol selection $atp_sel
    mol material Opaque
    mol addrep $molid
    return 1
}

proc ::consensus::show_protein_atp {args} {
    # Keep VMD default protein representation (rep 0 unchanged).
    # ATP only: Licorice, orange.
    # Usage:  show_protein_atp all
    #         show_protein_atp MLKL JAK1
    if {[llength $args] == 0} { set args all }
    set names [::consensus::_resolve_name_list {*}$args]
    if {[llength $names] == 0} {
        ::consensus::_warn "show_protein_atp: no matching loaded proteins"
        return 0
    }

    set n_ok 0
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }

        # Remove previous overlays; leave original VMD default rep
        ::consensus::_keep_rep0_only $mid
        if {![::consensus::_style_atp_orange $mid]} {
            ::consensus::_warn "$name: no ATP (resname ATP) found"
        }
        mol on $mid
        incr n_ok
    }
    ::consensus::_log "show_protein_atp: [join $names {, }]  (protein=VMD default, ATP=Licorice/orange)"
    return $n_ok
}

# ---------------------------------------------------------------------------
# Batch export (uses your VMD  snapshot  proc — do not redefine it here)
# ---------------------------------------------------------------------------

proc ::consensus::snapshot_each {{outdir .} args} {
    # Show one protein at a time (VMD protein default + ATP orange licorice),
    # call your existing  snapshot NAME  (e.g. snapshot MLKL → MLKL.png),
    # and write aligned coordinates as NAME.pdb.
    #
    # Usage:
    #   snapshot_each .                  ;# all loaded proteins
    #   snapshot_each ./shots            ;# PNG + PDB under ./shots/
    #   snapshot_each ./shots MLKL JAK1
    #
    set name_args $args
    if {[llength $name_args] == 0} {
        set name_args all
    }

    if {![file isdirectory $outdir]} {
        file mkdir $outdir
    }

    set names [::consensus::_resolve_name_list {*}$name_args]
    if {[llength $names] == 0} {
        ::consensus::_warn "snapshot_each: no matching loaded proteins"
        return 0
    }

    set oldcwd [pwd]
    if {[file normalize $outdir] ne [file normalize $oldcwd]} {
        cd $outdir
    }

    set snap_cmd [namespace which -command snapshot]
    if {$snap_cmd eq ""} {
        ::consensus::_warn "no  snapshot  proc in VMD — load your snapshot.tcl first"
        if {[file normalize $outdir] ne [file normalize $oldcwd]} {
            cd $oldcwd
        }
        return 0
    }

    set n 0
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }

        ::consensus::hide_everything
        mol on $mid
        ::consensus::_keep_rep0_only $mid
        ::consensus::_style_atp_orange $mid

        display update ui
        display update

        # User-defined VMD proc in global namespace: snapshot MLKL → MLKL.png
        uplevel #0 $snap_cmd $name

        set pdb "${name}.pdb"
        set sel [atomselect $mid all]
        $sel writepdb $pdb
        $sel delete
        ::consensus::_log "wrote structure → [file join [pwd] $pdb]"

        incr n
    }

    if {[file normalize $outdir] ne [file normalize $oldcwd]} {
        cd $oldcwd
    }

    ::consensus::_log "snapshot_each: exported $n protein(s) (snapshot + .pdb)"
    return $n
}

# ---------------------------------------------------------------------------
# Consensus residue visualization
# ---------------------------------------------------------------------------

proc ::consensus::_clear_reps {molid} {
    set n [molinfo $molid get numreps]
    for {set i [expr {$n - 1}]} {$i >= 0} {incr i -1} {
        mol delrep $i $molid
    }
}

proc ::consensus::show_consensus {args} {
    # NewCartoon protein (silver) + consensus licorice colored by ResID / ColorID
    if {[llength $args] == 0} { set args all }
    set names [::consensus::_resolve_name_list {*}$args]
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }
        set resids [::consensus::_resid_list $name]
        if {[llength $resids] == 0} {
            ::consensus::_warn "$name: no consensus residues in map"
            continue
        }
        ::consensus::_clear_reps $mid
        mol color ColorID 8
        mol representation NewCartoon 0.3 10.0 4.1
        mol selection {protein}
        mol material Opaque
        mol addrep $mid

        mol color ResID
        mol representation Licorice 0.2 12.0 12.0
        mol selection "protein and resid [join $resids]"
        mol material Opaque
        mol addrep $mid

        mol on $mid
    }
    ::consensus::_log "show_consensus: [join $names {, }]"
}

proc ::consensus::color_consensus {{scheme blue} args} {
    # Recolor consensus representation created by show_consensus / highlight
    if {[llength $args] == 0} { set args all }
    set names [::consensus::_resolve_name_list {*}$args]
    set scheme_l [string tolower $scheme]

    array set cid {
        blue 0 red 1 gray 2 grey 2 orange 3 yellow 4 tan 5 silver 6 green 7
        white 8 pink 9 cyan 10 purple 11 lime 12 mauve 13 ochre 14
        iceblue 15 black 16
    }

    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }
        set resids [::consensus::_resid_list $name]
        if {[llength $resids] == 0} { continue }

        # Keep cartoon (rep 0) if present; replace / create consensus licorice
        set nrep [molinfo $mid get numreps]
        if {$nrep == 0} {
            mol color ColorID 8
            mol representation NewCartoon 0.3 10.0 4.1
            mol selection {protein}
            mol addrep $mid
            set nrep 1
        }
        if {$nrep >= 2} {
            mol delrep 1 $mid
        }

        if {$scheme_l eq "rainbow" || $scheme_l eq "resid"} {
            mol color ResID
        } elseif {$scheme_l eq "name" || $scheme_l eq "element"} {
            mol color Name
        } elseif {[info exists cid($scheme_l)]} {
            mol color ColorID $cid($scheme_l)
        } else {
            ::consensus::_warn "unknown color '$scheme' — using blue"
            mol color ColorID 0
        }
        mol representation Licorice 0.2 12.0 12.0
        mol selection "protein and resid [join $resids]"
        mol material Opaque
        mol addrep $mid
    }
    ::consensus::_log "color_consensus $scheme: [join $names {, }]"
}

proc ::consensus::show_consensus_vdw {args} {
    # Consensus residues ONLY, drawn as VDW. Turns those molecules ON;
    # does not change visibility of other molecules (use hide_everything first
    # if you want a clean view).
    # Usage:  show_consensus_vdw all
    #         show_consensus_vdw MLKL
    #         show_consensus_vdw JAK1 JAK3
    if {[llength $args] == 0} { set args all }
    set names [::consensus::_resolve_name_list {*}$args]
    if {[llength $names] == 0} {
        ::consensus::_warn "show_consensus_vdw: no matching loaded proteins"
        return 0
    }
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }
        set resids [::consensus::_resid_list $name]
        if {[llength $resids] == 0} {
            ::consensus::_warn "$name: no consensus residues in map"
            continue
        }
        ::consensus::_clear_reps $mid
        mol color ResID
        mol representation VDW 1.0 12.0
        mol selection "protein and resid [join $resids]"
        mol material Opaque
        mol addrep $mid
        mol on $mid
    }
    ::consensus::_log "show_consensus_vdw: [join $names {, }]"
    return [llength $names]
}

proc ::consensus::highlight_consensus {args} {
    # highlight_consensus vdw all
    # highlight_consensus vdw MLKL
    # highlight_consensus only all
    # highlight_consensus both JAK1
    # highlight_consensus off all
    if {[llength $args] == 0} {
        ::consensus::_log "usage: highlight_consensus vdw|only|both|off  [all|NAME …]"
        return
    }
    set mode [string tolower [lindex $args 0]]
    set rest [lrange $args 1 end]
    if {[llength $rest] == 0} { set rest all }

    if {$mode eq "vdw" || $mode eq "only_vdw"} {
        ::consensus::show_consensus_vdw {*}$rest
        return
    }

    set names [::consensus::_resolve_name_list {*}$rest]
    foreach name $names {
        set mid [::consensus::_molid $name]
        if {$mid < 0} { continue }
        set resids [::consensus::_resid_list $name]
        if {[llength $resids] == 0} { continue }
        ::consensus::_clear_reps $mid
        if {$mode eq "off"} {
            mol color Structure
            mol representation NewCartoon 0.3 10.0 4.1
            mol selection {protein}
            mol addrep $mid
        } elseif {$mode eq "both"} {
            ::consensus::show_consensus $name
            continue
        } else {
            # only (cartoon + licorice of consensus)
            mol color ResID
            mol representation NewCartoon 0.3 10.0 4.1
            mol selection "protein and resid [join $resids]"
            mol addrep $mid
            mol color Name
            mol representation Licorice 0.2 12.0 12.0
            mol selection "protein and resid [join $resids]"
            mol addrep $mid
        }
        mol on $mid
    }
    ::consensus::_log "highlight_consensus $mode: [join $names {, }]"
}

proc ::consensus::sel_consensus {name} {
    # Return atomselect text for consensus residues of NAME (Tcl use)
    set resids [::consensus::_resid_list $name]
    if {[llength $resids] == 0} {
        return "none"
    }
    return "protein and resid [join $resids]"
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

proc ::consensus::help {} {
    puts {
consensus / SimAgent VMD helpers
--------------------------------
  load_map FILE.csv          Load MSA or pocket residue_map.csv
  load_aliases FILE          UniProt↔name map (JSON manifest or CSV)
  load_pdbs DIR              Load PDBs from a directory (not a glob)
  load_pdb NAME FILE.pdb     Load one structure and register as NAME
  register_protein NAME ID   Attach an already-loaded molid to NAME

  align_to MOBILE [REF]      Fit MOBILE→REF on shared consensus Cα
  align_all [REF]            Align every loaded protein onto REF

  show all | show protein    Show all registered proteins
  show JAK1 JAK3 MLKL        Show only these (hide other registered)
  hide all | hide NAME …     Hide molecules
  hide_everything            Hide ALL molecules in VMD
  show_everything            Show ALL molecules in VMD
  show_protein_atp [NAMES…]  Keep VMD protein default; ATP = Licorice/orange
  snapshot NAME              Your VMD proc (e.g. snapshot MLKL → MLKL.png)
  snapshot_each [DIR] [NAMES]  One-by-one view + snapshot + NAME.pdb

  show_consensus [NAMES…]    Cartoon + colored consensus licorice
  show_consensus_vdw [NAMES…] Consensus ONLY as VDW
  color_consensus SCHEME …   rainbow | blue | red | …
  highlight_consensus vdw all
  highlight_consensus vdw MLKL
  highlight_consensus only|both|off  [NAMES…]
  list_proteins              Table of loaded / mapped names
  help_consensus             This message

Typical case (PDBs = UniProt IDs like q8nb16.pdb; map = MLKL, JAK1, …):
  source vmd_consensus_align.tcl
  load_map reference_msa_residue_map.csv
  load_aliases protein_aliases.csv
  load_pdbs .
  align_all MLKL
  show_protein_atp all
  snapshot MLKL
  snapshot_each ./shots
}
}

# ---------------------------------------------------------------------------
# Global short names (VMD console convenience)
# ---------------------------------------------------------------------------

proc load_map {args} { ::consensus::load_map {*}$args }
proc load_aliases {args} { ::consensus::load_aliases {*}$args }
proc load_pdbs {args} { ::consensus::load_pdbs {*}$args }
proc load_pdb {args} { ::consensus::load_pdb {*}$args }
proc register_protein {args} { ::consensus::register_protein {*}$args }
proc align_to {args} { ::consensus::align_to {*}$args }
proc align_all {args} { ::consensus::align_all {*}$args }
proc show {args} { ::consensus::show {*}$args }
proc hide {args} { ::consensus::hide {*}$args }
proc hide_everything {args} { ::consensus::hide_everything }
proc Hide_everything {args} { ::consensus::hide_everything }
proc show_everything {args} { ::consensus::show_everything }
proc Show_everything {args} { ::consensus::show_everything }
proc show_protein_atp {args} { ::consensus::show_protein_atp {*}$args }
proc snapshot_each {args} { ::consensus::snapshot_each {*}$args }
proc show_consensus {args} { ::consensus::show_consensus {*}$args }
proc show_consensus_vdw {args} { ::consensus::show_consensus_vdw {*}$args }
proc color_consensus {args} { ::consensus::color_consensus {*}$args }
proc highlight_consensus {args} { ::consensus::highlight_consensus {*}$args }
proc list_proteins {args} { ::consensus::list_proteins {*}$args }
proc help_consensus {args} { ::consensus::help {*}$args }
proc sel_consensus {args} { ::consensus::sel_consensus {*}$args }

::consensus::_log "Loaded vmd_consensus_align.tcl — type  help_consensus  for usage"
