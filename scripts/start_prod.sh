#!/bin/sh
set -e
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
PORT="${PORT:-8000}"
exec uvicorn app.api.server:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
