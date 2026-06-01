#!/bin/sh
set -e

WORKERS="${GUNICORN_WORKERS:-1}"

exec gunicorn \
    --chdir src \
    app:app \
    --bind 0.0.0.0:8000 \
    --workers "$WORKERS" \
    --timeout 120
