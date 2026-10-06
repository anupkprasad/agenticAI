#!/usr/bin/env bash
# Launch the four-pseudokinase apo/holo example with nohup.
# Review goal.txt, then: bash run_simagent_nohup.sh
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$EXAMPLE_DIR/../.." && pwd)"
GOAL_FILE="${EXAMPLE_DIR}/goal.txt"
LOG="${EXAMPLE_DIR}/simagent_nohup.log"
PID_FILE="${EXAMPLE_DIR}/simagent_nohup.pid"

# Prefer SimAgentEnv; fall back to legacy ollama_env if present.
if [[ -z "${CONDA_ENV_BIN:-}" ]]; then
  if [[ -x "${HOME}/conda_envs/SimAgentEnv/bin/python" ]]; then
    CONDA_ENV_BIN="${HOME}/conda_envs/SimAgentEnv/bin"
  else
    CONDA_ENV_BIN="${HOME}/conda_envs/ollama_env/bin"
  fi
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
