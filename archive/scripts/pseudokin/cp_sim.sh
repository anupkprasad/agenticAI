#!/bin/bash

# Usage:
#   ./cp_sim.sh SOURCE_DIR DEST_DIR REP
#
# For each simulation under SOURCE_DIR, copies production MD outputs from REP/
# into DEST_DIR/<uniprot>/hpc/ with original names (md.xtc, md.tpr, ...).
# Skips wrapped trajectories (mdWrap*.xtc) and GROMACS backup files (#...#).

set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "Usage: $0 SOURCE_DIR DEST_DIR REP" >&2
    echo "Example: $0 pseudokinase/batch_sim_1/ /scratch/akp66103/pseudoKincopy/ rep1" >&2
    exit 1
fi

SOURCE_DIR="$1"
DEST_DIR="$2"
REP="$3"

mkdir -p "$DEST_DIR"

for simdir in "$SOURCE_DIR"/*; do

[[ -d "$simdir" ]] || continue

simname=$(basename "$simdir")

# Extract UniProt ID
uniprot=$(echo "$simname" | cut -d'_' -f2)

src_rep_dir="$simdir/$REP"

if [[ ! -d "$src_rep_dir" ]]; then
    echo "Skipping $simname : $REP not found"
    continue
fi

target_dir="$DEST_DIR/$uniprot/hpc"
mkdir -p "$target_dir"

# Copy structure file
pdb_file=$(find "$simdir" -maxdepth 1 -type f -name '*_h.pdb' | head -n 1)

if [[ -n "$pdb_file" ]]; then
    cp "$pdb_file" "$DEST_DIR/${uniprot}.pdb"
else
    echo "Missing *_h.pdb in $simdir"
fi

# Simulation outputs only — keep original names.
# Include md.xtc (production traj); skip other .xtc (mdWrap*) and GROMACS backups (#...#).
copy_names=(
    md.cpt
    md_prev.cpt
    md.edr
    md.gro
    md.log
    md.tpr
    md.xtc
    prod.sh
)

for name in "${copy_names[@]}"; do
    if [[ -f "$src_rep_dir/$name" ]]; then
        cp "$src_rep_dir/$name" "$target_dir/$name"
    else
        echo "Missing: $src_rep_dir/$name"
    fi
done

# Optional SLURM stdout (same basename)
shopt -s nullglob
for slurm_out in "$src_rep_dir"/slurm-*.out; do
    cp "$slurm_out" "$target_dir/$(basename "$slurm_out")"
done
shopt -u nullglob

echo "Processed $uniprot"

done

echo "Finished copying files from $REP."
