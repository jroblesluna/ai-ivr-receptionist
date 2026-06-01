#!/bin/sh
set -e

WORKERS="${GUNICORN_WORKERS:-1}"

# Trap SIGTERM and SIGINT for graceful shutdown of both processes
cleanup() {
    echo "Shutting down services..."
    if [ -n "$GUNICORN_PID" ]; then
        kill -TERM "$GUNICORN_PID" 2>/dev/null || true
        wait "$GUNICORN_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup TERM INT

# Start Gunicorn (Flask) in background on port 8000
gunicorn \
    --chdir src \
    app:app \
    --bind 0.0.0.0:8000 \
    --workers "$WORKERS" \
    --timeout 120 &

GUNICORN_PID=$!

# Start Uvicorn (FastAPI real-time voice) on port 8001 as the foreground process
exec uvicorn \
    src.realtime.server:app \
    --host 0.0.0.0 \
    --port 8001 \
    --workers 1
