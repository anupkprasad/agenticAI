#!/usr/bin/env bash
# Single SimAgent invoke for one robustness run directory (run_01 or run_02).
#
# Usage:
#   bash run_simagent.sh run_01
#   bash run_simagent.sh run_02
set -euo pipefail

CAMP="$(cd "$(dirname "$0")" && pwd)"
ROBUST="$(cd "$CAMP/../.." && pwd)"
REPO="$(cd "$ROBUST/../.." && pwd)"

# shellcheck disable=SC1091
source "$CAMP/campaign.conf"

RUN_ID="${1:?usage: run_simagent.sh <run_01|run_02>}"
case "$RUN_ID" in
  run_01|run_02) ;;
  *) echo "ERROR: run id must be run_01 or run_02 (got $RUN_ID)" >&2; exit 1 ;;
esac

WD="${WORK_ROOT}/${RUN_ID}"
GOAL="${CAMP}/goal.txt"
LABELS="${CAMP}/labels.txt"

if [[ ! -f "$GOAL" ]]; then
  echo "ERROR: missing $GOAL" >&2
  exit 1
fi
if [[ ! -d "$WD" ]]; then
  echo "ERROR: missing $WD — seed first (seed_dual_rep.sh / launch_runs_nohup.sh)" >&2
  exit 1
fi

# Prefer activated SimAgentEnv, else standard conda envs path.
# Override with CONDA_ENV_BIN.
if [[ -z "${CONDA_ENV_BIN:-}" ]]; then
  if [[ "${CONDA_DEFAULT_ENV:-}" == "SimAgentEnv" && -x "${CONDA_PREFIX:-}/bin/python" ]]; then
    CONDA_ENV_BIN="${CONDA_PREFIX}/bin"
  else
    _conda_base=""
    if command -v conda >/dev/null 2>&1; then
      _conda_base="$(conda info --base 2>/dev/null || true)"
    fi
    for cand in \
      ${_conda_base:+"${_conda_base}/envs/SimAgentEnv/bin"} \
      "${HOME}/.conda/envs/SimAgentEnv/bin"; do
      if [[ -n "${cand:-}" && -x "${cand}/python" ]]; then
        CONDA_ENV_BIN="$cand"
        break
      fi
    done
    unset _conda_base
  fi
fi
if [[ -z "${CONDA_ENV_BIN:-}" || ! -x "${CONDA_ENV_BIN}/python" ]]; then
  echo "ERROR: SimAgentEnv python not found." >&2
  echo "  Create with: conda env create -f environment.yml && conda activate SimAgentEnv" >&2
  echo "  Or set CONDA_ENV_BIN." >&2
  exit 1
fi
export PATH="$CONDA_ENV_BIN:$PATH"
export LD_LIBRARY_PATH="${CONDA_ENV_BIN%/bin}/lib:${LD_LIBRARY_PATH:-}"
PYTHON="${CONDA_ENV_BIN}/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: missing $PYTHON" >&2
  exit 1
fi
if [[ -f /apps/lmod/lmod/init/bash ]]; then
  # shellcheck disable=SC1091
  source /apps/lmod/lmod/init/bash
  module load AmberTools/23.6-foss-2023b 2>/dev/null || true
  module load GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2 2>/dev/null || true
fi

mapfile -t _labels < <(grep -vE '^\s*(#|$)' "$LABELS" | sed 's/[[:space:]]//g')
RETRY_LABELS=("${_labels[@]}")

cd "$REPO"
echo "[$(date -Is)] SimAgent $RUN_ID  wd=$WD  model=$LLM_MODEL  workers=$PARALLEL_WORKERS"
echo "[$(date -Is)] labels=${#RETRY_LABELS[@]}  rep_num=$REP_NUM  reuse-hpc"

# shellcheck disable=SC2086
exec "$PYTHON" SimAgent.py \
  --goal "$(cat "$GOAL")" \
  --working-dir "$WD" \
  --llm-model "$LLM_MODEL" \
  --llm-base-url "$LLM_URL" \
  --force-field amber99sb-ildn \
  --water-model tip3p \
  --rep-num "$REP_NUM" \
  --reuse-hpc \
  --subtask preprocess simsetup hpcjob analysis reporter \
  --parallel-workers "$PARALLEL_WORKERS" \
  --parallel-mem-gb "$PARALLEL_MEM_GB" \
  --llm-concurrency "$LLM_CONCURRENCY" \
  --hpc-check-interval 10m \
  --allowed-hpc-jobs 8 \
  --retry-labels "${RETRY_LABELS[@]}"
