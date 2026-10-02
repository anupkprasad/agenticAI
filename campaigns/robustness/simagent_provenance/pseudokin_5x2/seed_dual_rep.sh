#!/usr/bin/env bash
# Seed one SimAgent run directory with dual MD replicates under {label}_ATP.
#
#   {label}_ATP/hpc/rep01  ←  SEED_REP1/{label}/hpc/{md.tpr,mdWrap.xtc}
#   {label}_ATP/hpc/rep02  ←  SEED_REP2/{label}/hpc/{md.tpr,mdWrap.xtc}
#   {label}.pdb            ←  root discovery PDB (from rep1)
#
# Usage:
#   bash seed_dual_rep.sh --dest .../run_01 --labels-file labels.txt \
#     [--rep1 ...] [--rep2 ...] [--case-suffix _ATP]
set -euo pipefail

DEST=""
LABELS_FILE=""
REP1="/scratch/akp66103/pseudoKin"
REP2="/scratch/akp66103/pseudoKin2"
CASE_SUFFIX="${CASE_SUFFIX:-_ATP}"
REQUIRE_TRAJ_HARDLINK="${REQUIRE_TRAJ_HARDLINK:-0}"
TRAJ_LINK_MODE="${TRAJ_LINK_MODE:-auto}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST="$2"; shift 2 ;;
    --labels-file) LABELS_FILE="$2"; shift 2 ;;
    --rep1) REP1="$2"; shift 2 ;;
    --rep2) REP2="$2"; shift 2 ;;
    --case-suffix) CASE_SUFFIX="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$DEST" ]]; then
  echo "ERROR: --dest is required" >&2
  exit 1
fi
if [[ ! -d "$REP1" || ! -d "$REP2" ]]; then
  echo "ERROR: seed dirs missing: $REP1 / $REP2" >&2
  exit 1
fi

declare -a LABELS=()
if [[ -n "$LABELS_FILE" && -f "$LABELS_FILE" ]]; then
  mapfile -t LABELS < <(grep -vE '^\s*(#|$)' "$LABELS_FILE" | sed 's/[[:space:]]//g')
else
  echo "ERROR: --labels-file required" >&2
  exit 1
fi
if [[ ${#LABELS[@]} -eq 0 ]]; then
  echo "ERROR: no labels to seed" >&2
  exit 1
fi

link_traj() {
  local src="$1" dest="$2" kind="$3"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ -L "$dest" && "$(readlink -f "$dest" 2>/dev/null || true)" == "$(readlink -f "$src")" ]]; then
      return 0
    fi
    if [[ -f "$dest" && ! -L "$dest" ]] \
      && [[ "$(stat -c '%d:%i' "$src" 2>/dev/null || true)" == "$(stat -c '%d:%i' "$dest" 2>/dev/null || true)" ]]; then
      return 0
    fi
    rm -f "$dest"
  fi

  local mode="$TRAJ_LINK_MODE"
  if [[ "$REQUIRE_TRAJ_HARDLINK" == "1" ]]; then
    mode=hardlink
  fi

  case "$mode" in
    hardlink)
      if ln -f "$src" "$dest" 2>/dev/null; then
        return 0
      fi
      echo "ERROR: hardlink failed ($kind): $src -> $dest" >&2
      return 1
      ;;
    symlink)
      ln -s "$src" "$dest"
      return 0
      ;;
    auto|*)
      if ln -f "$src" "$dest" 2>/dev/null; then
        return 0
      fi
      ln -s "$src" "$dest"
      return 0
      ;;
  esac
}

mkdir -p "$DEST"
echo "[$(date -Is)] seeding ${#LABELS[@]} labels → $DEST  case_suffix=$CASE_SUFFIX"
echo "  rep01←$REP1  rep02←$REP2  link_mode=$TRAJ_LINK_MODE"

n_ok=0
n_hard=0
n_sym=0
for lab in "${LABELS[@]}"; do
  pdb1="$REP1/${lab}.pdb"
  if [[ ! -f "$pdb1" ]]; then
    echo "WARN: skip $lab (missing $pdb1)" >&2
    continue
  fi
  work="${lab}${CASE_SUFFIX}"
  if [[ ! -f "$DEST/${lab}.pdb" ]]; then
    ln -f "$pdb1" "$DEST/${lab}.pdb" 2>/dev/null || cp "$pdb1" "$DEST/${lab}.pdb"
  fi
  mkdir -p "$DEST/$work"
  if [[ ! -f "$DEST/$work/${lab}.pdb" ]]; then
    ln -f "$pdb1" "$DEST/$work/${lab}.pdb" 2>/dev/null || cp "$pdb1" "$DEST/$work/${lab}.pdb"
  fi

  for pair in "01:$REP1" "02:$REP2"; do
    rid="${pair%%:*}"
    src="${pair#*:}"
    tpr="$src/$lab/hpc/md.tpr"
    xtc="$src/$lab/hpc/mdWrap.xtc"
    gro="$src/$lab/hpc/md.gro"
    if [[ ! -f "$tpr" || ! -f "$xtc" ]]; then
      echo "WARN: skip $lab rep$rid (missing tpr/xtc under $src)" >&2
      continue 2
    fi
    link_traj "$tpr" "$DEST/$work/hpc/rep${rid}/md.tpr" tpr
    link_traj "$xtc" "$DEST/$work/hpc/rep${rid}/mdWrap.xtc" traj
    # md.gro matches traj atom count (prefer over fresh simsetup system.gro)
    if [[ -f "$gro" ]]; then
      link_traj "$gro" "$DEST/$work/hpc/rep${rid}/md.gro" gro
    fi
    if [[ -L "$DEST/$work/hpc/rep${rid}/mdWrap.xtc" ]]; then
      n_sym=$((n_sym + 1))
    else
      n_hard=$((n_hard + 1))
    fi
  done
  n_ok=$((n_ok + 1))
  echo "  $work: hpc/rep01 + hpc/rep02 linked"
done

echo "[$(date -Is)] seeded_ok=$n_ok / ${#LABELS[@]}  (hardlink_slots≈$n_hard symlink_slots≈$n_sym)"
if [[ "$n_ok" -lt 1 ]]; then
  exit 1
fi
if [[ "$n_ok" -ne "${#LABELS[@]}" ]]; then
  echo "ERROR: expected ${#LABELS[@]} systems, got $n_ok" >&2
  exit 1
fi
