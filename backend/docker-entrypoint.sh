#!/bin/sh
set -eu

attempt=1
max_attempts="${MIGRATION_MAX_ATTEMPTS:-30}"
until alembic upgrade head; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "Migrarea bazei de date a eșuat după $attempt încercări." >&2
    exit 1
  fi
  echo "Baza de date nu este pregătită; reîncercare migrare ($attempt/$max_attempts)..." >&2
  attempt=$((attempt + 1))
  sleep "${MIGRATION_RETRY_SECONDS:-5}"
done

python -m app.seed

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
