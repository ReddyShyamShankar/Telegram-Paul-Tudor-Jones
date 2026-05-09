#!/usr/bin/env bash
# PythonAnywhere always-on supervisor.
#
# Runs both the existing `edgewonk bot` AND the `tsg` daemon under one
# always-on task slot. PA's always-on quota = 2; this collapses two
# logical bots into one slot.
#
# To install: edit the existing edgewonk always-on task and change its
# command to:
#     bash /home/garlareddy/tsg/scripts/pa_supervisor.sh
# Disable + re-enable the task. PA restarts on any crash; this script
# kills both children if either one dies, so PA's restart is unified.
#
# Adjust EDGEWONK_DIR / TSG_DIR via env vars if your paths differ.

set -uo pipefail

EDGEWONK_DIR="${EDGEWONK_DIR:-$HOME/EdgeWonk_journal_V2.0}"
TSG_DIR="${TSG_DIR:-$HOME/tsg}"

log() { echo "[supervisor $(date -u +%FT%TZ)] $*"; }

cleanup() {
    log "supervisor exiting; killing children"
    [[ -n "${EDGEWONK_PID:-}" ]] && kill "$EDGEWONK_PID" 2>/dev/null || true
    [[ -n "${TSG_PID:-}" ]] && kill "$TSG_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM EXIT

# --- start edgewonk ---
log "starting edgewonk (cwd=$EDGEWONK_DIR)"
(
    cd "$EDGEWONK_DIR"
    # shellcheck disable=SC1091
    source venv/bin/activate
    exec python main.py
) &
EDGEWONK_PID=$!
log "edgewonk pid=$EDGEWONK_PID"

# --- start tsg ---
log "starting tsg (cwd=$TSG_DIR)"
(
    cd "$TSG_DIR"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec python run.py
) &
TSG_PID=$!
log "tsg pid=$TSG_PID"

# Wait for either child. If one exits, supervisor exits → PA restarts both.
if wait -n; then
    EXITED_OK=$?
    log "a child exited cleanly (status=$EXITED_OK); supervisor stopping"
else
    EXITED_FAIL=$?
    log "a child exited with error (status=$EXITED_FAIL); supervisor stopping"
fi
exit 1
