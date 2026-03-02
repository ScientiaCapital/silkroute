#!/usr/bin/env bash
set -euo pipefail

echo "=== SilkRoute API Starting ==="
echo "Version: $(python -c 'import silkroute; print(silkroute.__version__)' 2>/dev/null || echo 'unknown')"
echo "Port: ${PORT:-8787}"

# Initialize database schema if Postgres URL is set
if [ -n "${SILKROUTE_DB_POSTGRES_URL:-}" ]; then
    echo "Waiting for Postgres..."
    for i in $(seq 1 30); do
        if pg_isready -d "$SILKROUTE_DB_POSTGRES_URL" -q 2>/dev/null; then
            echo "Postgres is ready."
            echo "Running schema init..."
            psql "$SILKROUTE_DB_POSTGRES_URL" -f /app/sql/init.sql --quiet 2>&1 || echo "WARN: Schema init returned non-zero (may be OK if tables exist)"
            break
        fi
        echo "Postgres not ready (attempt $i/30)..."
        sleep 1
    done
fi

# Start API server
# Uses $PORT (Railway-assigned) with fallback to 8787
exec uvicorn silkroute.api.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port "${PORT:-8787}" \
    --workers 1 \
    --log-level info \
    --access-log
