#!/bin/sh
set -eu

DATA_DIR="${CARELOG_DATA:-/data}"
echo "[carelog] data dir: ${DATA_DIR}"
mkdir -p "${DATA_DIR}/uploads"

if [ "${CARELOG_SECRET:-change-me-in-production}" = "change-me-in-production" ] || \
   [ "${CARELOG_SECRET:-}" = "replace-with-a-random-64-character-secret" ]; then
  echo "[carelog] WARNING: CARELOG_SECRET is insecure. Set a random value before public use."
fi

# CLI initialization must not launch the background scheduler.
CARELOG_START_SCHEDULER=0 flask --app app init-db

if [ "${SEED_DEMO:-0}" = "1" ]; then
  CARELOG_START_SCHEDULER=0 flask --app app seed-demo
fi

echo "[carelog] starting waitress on :8501 (TZ=${TZ:-Asia/Taipei})"
exec waitress-serve --host 0.0.0.0 --port 8501 \
  --threads "${WAITRESS_THREADS:-4}" --call app:create_app
