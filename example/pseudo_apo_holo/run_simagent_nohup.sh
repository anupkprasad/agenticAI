#!/usr/bin/env bash
# Launch the four-pseudokinase apo/holo example with nohup.
# Review goal.txt, then: bash run_simagent_nohup.sh
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$EXAMPLE_DIR/../.." && pwd)"
GOAL_FILE="${EXAMPLE_DIR}/goal.txt"
LOG="${EXAMPLE_DIR}/simagent_nohup.log"
PID_FILE="${EXAMPLE_DIR}/simagent_nohup.pid"

# Prefer an already-activated SimAgentEnv, else the standard conda location
# ($(conda info --base)/envs/SimAgentEnv or ~/.conda/envs/SimAgentEnv).
# Override with CONDA_ENV_BIN or PYTHON.
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
  echo "  Or set CONDA_ENV_BIN / PYTHON to that env's bin/python." >&2
  exit 1
fi
export PATH="$CONDA_ENV_BIN:$PATH"
export LD_LIBRARY_PATH="${CONDA_ENV_BIN%/bin}/lib:${LD_LIBRARY_PATH:-}"
PYTHON="${PYTHON:-$CONDA_ENV_BIN/python}"

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: python not found at $PYTHON (set CONDA_ENV_BIN or PYTHON)" >&2
  exit 1
fi
if [[ ! -f "$GOAL_FILE" ]]; then
  echo "ERROR: missing $GOAL_FILE" >&2
  exit 1
fi
if [[ ! -f "$REPO/SimAgent.py" ]]; then
  echo "ERROR: SimAgent.py not found under $REPO" >&2
  exit 1
fi

cd "$REPO"
nohup "$PYTHON" SimAgent.py \
  --goal "$(cat "$GOAL_FILE")" \
  --working-dir "$EXAMPLE_DIR" \
  --force-field amber99sb-ildn \
  --water-model tip3p \
  --llm-model gpt-oss:20b \
  --llm-base-url http://127.0.0.1:11434 \
  --subtask preprocess simsetup hpcjob analysis reporter \
  --hpc-check-interval 10m \
  --allowed-hpc-jobs 4 \
  >"$LOG" 2>&1 &

echo $! >"$PID_FILE"
echo "Started SimAgent pid=$(cat "$PID_FILE")"
echo "  working-dir: $EXAMPLE_DIR"
echo "  log:         $LOG"
echo "  tail -f $LOG"
