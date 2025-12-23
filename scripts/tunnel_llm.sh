#!/usr/bin/env bash
# Helper to create an SSH local port forward to a remote LLM API server.
#
# Usage:
#   ./scripts/tunnel_llm.sh [ssh_target] [local_port] [remote_host] [remote_port] [background]
# Example:
#   ./scripts/tunnel_llm.sh ruili@172.22.149.139 11434 localhost 11434
#
# Notes:
# - This script does NOT store or transmit your password. You'll be prompted
#   for the SSH password unless you set up SSH keys (recommended).
# - To run the tunnel in background, pass any non-empty 5th argument (e.g. 'bg').

set -euo pipefail

SSH_TARGET=${1:-}
LOCAL_PORT=${2:-11434}
REMOTE_HOST=${3:-localhost}
REMOTE_PORT=${4:-11434}
KEY_PATH=${5:-$HOME/.ssh/id_ed25519}
BACKGROUND=${6:-}

if [ -z "$SSH_TARGET" ]; then
  echo "Usage: $0 <user@host> [local_port] [remote_host] [remote_port] [background]"
  echo "Example: $0 ruili@172.22.149.139 11434 localhost 11434 bg"
  exit 2
fi

SSH_OPTS=""
if [ -n "$KEY_PATH" ] && [ -f "$KEY_PATH" ]; then
  SSH_OPTS+=" -i $KEY_PATH"
fi

if [ -n "$BACKGROUND" ]; then
  echo "Starting background SSH tunnel: localhost:${LOCAL_PORT} -> ${REMOTE_HOST}:${REMOTE_PORT} on ${SSH_TARGET} (key=${KEY_PATH})"
  eval ssh -f -N -L ${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT} ${SSH_OPTS} ${SSH_TARGET}
  echo "Tunnel started (background). Use 'ps aux | grep ssh' to verify or 'pkill -f \"${SSH_TARGET}\"' to kill."
else
  echo "Opening SSH tunnel (foreground). Press Ctrl-C to close. (key=${KEY_PATH})"
  echo "Forwarding localhost:${LOCAL_PORT} -> ${REMOTE_HOST}:${REMOTE_PORT} on ${SSH_TARGET}"
  eval ssh -L ${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT} ${SSH_OPTS} ${SSH_TARGET}
fi
