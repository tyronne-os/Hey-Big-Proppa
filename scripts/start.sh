#!/usr/bin/env bash
# BIG PROPPA launcher — always claims ports 8085 (frontend) and 8086 (backend).
# Reserved range: 8085–9005 for Big Proppa services.
#
# Usage:
#   ./scripts/start.sh          # start both
#   ./scripts/start.sh front    # frontend only
#   ./scripts/start.sh back     # backend only
#   ./scripts/start.sh stop     # kill both

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONT_PORT=8085
BACK_PORT=8086

kill_port() {
  local port="$1"
  local pid
  pid=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    echo "  Clearing port $port (pid $pid)..."
    kill -9 "$pid" 2>/dev/null || true
  fi
}

start_back() {
  echo "🏈 Starting Big Proppa BACKEND on :$BACK_PORT"
  kill_port "$BACK_PORT"
  cd "$ROOT/backend"
  if [[ -f ".venv/bin/uvicorn" ]]; then
    .venv/bin/uvicorn main:app --reload --port "$BACK_PORT" &
  else
    uvicorn main:app --reload --port "$BACK_PORT" &
  fi
  echo "  Backend PID: $!"
}

start_front() {
  echo "🏈 Starting Big Proppa FRONTEND on :$FRONT_PORT"
  kill_port "$FRONT_PORT"
  cd "$ROOT/frontend"
  npm run dev &
  echo "  Frontend PID: $!"
}

case "${1:-both}" in
  back)   start_back ;;
  front)  start_front ;;
  stop)
    echo "Stopping Big Proppa..."
    kill_port "$FRONT_PORT"
    kill_port "$BACK_PORT"
    echo "  Done."
    ;;
  *)
    start_back
    sleep 2
    start_front
    echo ""
    echo "✅ BIG PROPPA IS LIVE"
    echo "   Frontend → http://localhost:$FRONT_PORT"
    echo "   Backend  → http://localhost:$BACK_PORT"
    echo "   Reserved range: 8085–9005"
    ;;
esac
