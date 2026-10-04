#!/bin/bash
# start.sh — bring the full Big Proppa stack back up in one command
# Run this any time the servers die: ./start.sh

set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$REPO/backend"
FRONTEND="$REPO/frontend"
VENV_PY="$BACKEND/.venv/bin/python"

echo "=== HEY BIG PROPPA — STARTUP ==="

# Kill any stale processes
pkill -f "uvicorn main:app" 2>/dev/null && echo "Killed stale backend" || true
pkill -f "vite.*8085" 2>/dev/null && echo "Killed stale frontend" || true
sleep 1

# Backend
echo "Starting backend (port 8086)..."
cd "$BACKEND"
"$VENV_PY" -m uvicorn main:app --host 0.0.0.0 --port 8086 --no-access-log > /tmp/backend.log 2>&1 &
BACK_PID=$!

# Frontend
echo "Starting frontend (port 8085)..."
cd "$FRONTEND"
npm run dev -- --host 0.0.0.0 --port 8085 > /tmp/frontend.log 2>&1 &
FRONT_PID=$!

# Wait and verify
sleep 7
BACK_OK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8086/api/espn/ticker 2>/dev/null)
FRONT_OK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8085/ 2>/dev/null)

echo ""
echo "Backend  (8086): $( [ "$BACK_OK" = "200" ] && echo "✅ UP" || echo "❌ DOWN (check /tmp/backend.log)" )"
echo "Frontend (8085): $( [ "$FRONT_OK" = "200" ] && echo "✅ UP" || echo "❌ DOWN (check /tmp/frontend.log)" )"
echo ""
echo "Sunday Slips → http://localhost:8085/sunday"
echo "Leaders      → http://localhost:8085/leaders"
echo "Home         → http://localhost:8085/home/index.html"
