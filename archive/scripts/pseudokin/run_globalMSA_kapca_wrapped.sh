#!/usr/bin/env bash
# Wrap all pseudoKin trajs (Protein|ATP) then replicate
# globalMSA_KAPCAPoc_consensusFEL-RMSF into a fresh *_wrapped output dir.
#
# Usage (background / laptop sleep safe):
#   nohup bash scripts/run_globalMSA_kapca_wrapped.sh \
#     > docs/ment/globalMSA_KAPCAPoc_consensusFEL-RMSF_wrapped/pipeline.log 2>&1 &
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

OUT_DIR="$REPO/docs/ment/globalMSA_KAPCAPoc_consensusFEL-RMSF_wrapped"
PY="${HOME}/conda_envs/ollama_env/bin/python"
GMX_BIN="${HOME}/conda_envs/ollama_env/bin"
WRAP_WORKERS="${WRAP_WORKERS:-8}"
PIPE_WORKERS="${PIPE_WORKERS:-48}"
FORCE_WRAP="${FORCE_WRAP:-0}"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: python not found at $PY" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
export PATH="${GMX_BIN}:${PATH}"
# Isolate conda libs — EasyBuild libstdc++ breaks conda sqlite/MDA (CXXABI).
export LD_LIBRARY_PATH="${HOME}/conda_envs/ollama_env/lib"
export PYTHONPATH="$REPO"
export MAFFT_BINARIES="${MAFFT_BINARIES:-/apps/eb/MAFFT/7.526-GCC-13.2.0-with-extensions/libexec/mafft}"
# Drop module-polluted paths from the calling shell.
unset PYTHONHOME 2>/dev/null || true

echo "================================================================"
echo "globalMSA KAPCA wrapped pipeline"
echo "  repo:          $REPO"
echo "  out:           $OUT_DIR"
echo "  python:        $PY"
echo "  gmx:           $(command -v gmx || true)"
echo "  wrap_workers:  $WRAP_WORKERS"
echo "  pipe_workers:  $PIPE_WORKERS"
echo "  force_wrap:    $FORCE_WRAP"
echo "  start:         $(date -Is)"
echo "================================================================"

echo ""
echo "=== Step 0: Protein+ATP wrap (mdWrap.xtc) ==="
WRAP_ARGS=(--max-workers "$WRAP_WORKERS" --ligand ATP --dt 100)
if [[ "$FORCE_WRAP" == "1" ]]; then
  WRAP_ARGS+=(--force)
fi
"$PY" "$REPO/scripts/wrap_pseudokin_protein_atp.py" "${WRAP_ARGS[@]}"

N_WRAP=$(ls -1 "$REPO"/pseudoKin/*/hpc/mdWrap.xtc 2>/dev/null | wc -l | tr -d ' ')
echo "mdWrap.xtc present: $N_WRAP"
if [[ "$N_WRAP" -lt 1 ]]; then
  echo "ERROR: no mdWrap.xtc produced" >&2
  exit 1
fi

echo ""
echo "=== Steps 1–6: MSA → pocket → FEL → RMSF → cluster ==="
"$PY" "$OUT_DIR/run_pipeline.py" \
  --steps msa,pocket_definition,fast_pocket,fel,rmsf,cluster \
  --workers "$PIPE_WORKERS" \
  --overwrite-fel \
  --overwrite-rmsf

echo ""
echo "================================================================"
echo "DONE $(date -Is)"
echo "Outputs: $OUT_DIR"
echo "Panel:   $OUT_DIR/clustering/hybrid_dendrogram_heatmap.png"
echo "Minmax:  $OUT_DIR/clustering/hybrid_dendrogram_heatmap_minmax.png"
echo "================================================================"
