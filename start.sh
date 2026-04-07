#!/bin/bash
set -e

# Start Redis server in background (no password for dev)
redis-server --daemonize yes --port 6379 --loglevel warning

# Wait for Redis to be ready
for i in $(seq 1 10); do
    if redis-cli ping > /dev/null 2>&1; then
        echo "Redis is ready"
        break
    fi
    sleep 0.5
done

# Start FastAPI app on port 5000
exec uvicorn main:app --host 0.0.0.0 --port 5000 --log-level info
