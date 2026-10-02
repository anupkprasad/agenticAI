#!/usr/bin/env bash
# Detach the orchestrator (seed + run_01 + run_02) so SSH logout cannot kill it.
#
#   bash start_detached.sh           # seed + both runs
#   bash start_detached.sh --seed-only
#
# Do not auto-chain tiers — start one campaign at a time after inspection.
set -euo pipefail

CAMP="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$CAMP/campaign.conf"

mkdir -p "$WORK_ROOT/logs"
LOG="$WORK_ROOT/logs/orchestrator.log"
PIDF="$WORK_ROOT/logs/orchestrator.pid"
chmod +x "$CAMP/launch_runs_nohup.sh" "$CAMP/run_simagent.sh" "$CAMP/seed_dual_rep.sh"

nohup bash "$CAMP/launch_runs_nohup.sh" "$@" > "$LOG" 2>&1 &
echo $! > "$PIDF"
echo "Orchestrator started pid=$(cat "$PIDF")"
echo "  work_root=$WORK_ROOT"
echo "  log=$LOG"
echo "Monitor: tail -f $LOG"
echo "Per-run:  tail -f $WORK_ROOT/logs/run_01.log"
