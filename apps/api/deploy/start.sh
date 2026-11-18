#!/bin/sh
# Container entrypoint: migrate, seed (idempotent), start the automation worker, then serve the API.
set -eu

echo "[start] applying database migrations"
python -m alembic upgrade head

echo "[start] syncing permissions, roles and workflow definitions (idempotent)"
python -m app.seed
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  # Hosted evaluation demo (staging only): the extra Marketing Specialist demo account; skips if it exists.
  python -m app.seed.demo_marketing || true
fi

echo "[start] starting automation worker"
# Restarted automatically if it ever exits; it stops with the container.
( while true; do python -m app.automation.worker --poll 5 || true; sleep 5; done ) &

echo "[start] serving API on port ${PORT:-8000}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips "*"
