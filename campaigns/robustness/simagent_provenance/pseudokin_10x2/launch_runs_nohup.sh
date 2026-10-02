#!/usr/bin/env bash
# Seed + launch run_01 then run_02 under nohup (survives SSH / terminal close).
# Does NOT start until you invoke this script yourself.
#
# Usage:
#   bash launch_runs_nohup.sh              # seed both, start run_01, then run_02
#   bash launch_runs_nohup.sh --seed-only  # only seed run_01 and run_02
#   bash launch_runs_nohup.sh --run run_01 # seed if needed + start one run
set -euo pipefail

CAMP="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$CAMP/campaign.conf"

SEED_ONLY=0
ONLY_RUN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed-only) SEED_ONLY=1; shift ;;
    --run) ONLY_RUN="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$WORK_ROOT/logs" "$WORK_ROOT/artifacts"
LABELS_FILE="$CAMP/labels.txt"
SEED_SH="$CAMP/seed_dual_rep.sh"
RUN_SH="$CAMP/run_simagent.sh"
chmod +x "$SEED_SH" "$RUN_SH" "$CAMP/launch_runs_nohup.sh" 2>/dev/null || true

seed_one() {
  local run_id="$1"
  local dest="$WORK_ROOT/$run_id"
  echo "[$(date -Is)] seeding $run_id → $dest"
  REQUIRE_TRAJ_HARDLINK="$REQUIRE_TRAJ_HARDLINK" \
  TRAJ_LINK_MODE="$TRAJ_LINK_MODE" \
  CASE_SUFFIX="${CASE_SUFFIX:-_ATP}" \
    bash "$SEED_SH" --dest "$dest" --labels-file "$LABELS_FILE" \
      --rep1 "$SEED_REP1" --rep2 "$SEED_REP2" \
      --case-suffix "${CASE_SUFFIX:-_ATP}"
}

start_one() {
  local run_id="$1"
  local log="$WORK_ROOT/logs/${run_id}.log"
  local pidf="$WORK_ROOT/logs/${run_id}.pid"
  local donef="$WORK_ROOT/logs/${run_id}.DONE"
  rm -f "$donef"
  echo "[$(date -Is)] nohup start $run_id  log=$log"
  nohup bash -lc "
    set -uo pipefail
    set +e
    bash '$RUN_SH' '$run_id'
    ec=\$?
    echo \$ec > '$WORK_ROOT/logs/${run_id}.exit_code'
    date -Is > '$donef'
    exit \$ec
  " > "$log" 2>&1 &
  echo $! > "$pidf"
  echo "  pid=$(cat "$pidf")"
}

wait_one() {
  local run_id="$1"
  local pidf="$WORK_ROOT/logs/${run_id}.pid"
  local donef="$WORK_ROOT/logs/${run_id}.DONE"
  if [[ ! -f "$pidf" ]]; then
    echo "ERROR: missing $pidf" >&2
    return 1
  fi
  local pid
  pid="$(cat "$pidf")"
  echo "[$(date -Is)] waiting for $run_id (pid=$pid) …"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 60
  done
  wait "$pid" 2>/dev/null || true
  local ec=0
  if [[ -f "$WORK_ROOT/logs/${run_id}.exit_code" ]]; then
    ec="$(cat "$WORK_ROOT/logs/${run_id}.exit_code")"
  fi
  echo "[$(date -Is)] $run_id finished exit=$ec done=$(cat "$donef" 2>/dev/null || echo n/a)"
  return "$ec"
}

RUNS=(run_01 run_02)
if [[ -n "$ONLY_RUN" ]]; then
  RUNS=("$ONLY_RUN")
fi

for r in "${RUNS[@]}"; do
  seed_one "$r"
done

if [[ "$SEED_ONLY" -eq 1 ]]; then
  echo "[$(date -Is)] seed-only complete under $WORK_ROOT"
  exit 0
fi

ec_all=0
for r in "${RUNS[@]}"; do
  start_one "$r"
  if ! wait_one "$r"; then
    ec_all=1
    echo "[$(date -Is)] WARNING: $r failed — continuing to next run if any" >&2
  fi
done
echo "[$(date -Is)] all requested runs finished (aggregate_exit=$ec_all)"
exit "$ec_all"
