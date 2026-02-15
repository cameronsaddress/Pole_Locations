#!/usr/bin/env bash

LOG_DIR="$(dirname "$0")/logs"
PILOT_LOG="$(dirname "$0")/run_pilot.log"

mkdir -p "$LOG_DIR"
touch "$PILOT_LOG"
touch "$LOG_DIR/backend.log"
touch "$LOG_DIR/frontend.log"

echo "Tailing:"
echo "  $PILOT_LOG"
echo "  $LOG_DIR/backend.log"
echo "  $LOG_DIR/frontend.log"
echo "Press Ctrl+C to stop."

tail -F \
  "$PILOT_LOG" \
  "$LOG_DIR/backend.log" \
  "$LOG_DIR/frontend.log"
