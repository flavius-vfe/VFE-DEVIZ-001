#!/usr/bin/env bash
set -euo pipefail

export COMPOSE_PROJECT_NAME=vfe-deviz-smoke
export POSTGRES_PASSWORD=smoke-test-db-password
export DATABASE_URL=postgresql+psycopg://deviz:smoke-test-db-password@postgres:5432/deviz
export SERVER_IP=127.0.0.1
export FRONTEND_PORT=3080
export BACKEND_PORT=8030
export POSTGRES_DATA="${RUNNER_TEMP:-$PWD/.data}/vfe-deviz-smoke/postgres"
export BACKEND_DATA="${RUNNER_TEMP:-$PWD/.data}/vfe-deviz-smoke/backend"
export DEVIZ_DATA="${RUNNER_TEMP:-$PWD/.data}/vfe-deviz-smoke/deviz-data"
export API_BASE_URL=

cleanup() {
  docker compose down --volumes --remove-orphans || true
}
trap cleanup EXIT

docker compose config --quiet
docker compose build frontend backend worker
docker compose up --detach postgres backend worker frontend

for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8030/ready >/dev/null \
    && curl --fail --silent http://127.0.0.1:3080/ >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    docker compose ps
    docker compose logs
    exit 1
  fi
  sleep 2
done

docker compose exec -T backend alembic current | grep --quiet '(head)'

test -z "$(docker port vfe-deviz-postgres)"
test -z "$(docker port vfe-deviz-worker)"

curl --fail --silent http://127.0.0.1:3080/runtime-config.js | grep --quiet 'API_URL: ""'
curl --fail --silent http://127.0.0.1:3080/ | grep --quiet '/runtime-config.js'

cors_headers=$(curl --silent --dump-header - --output /dev/null \
  --request OPTIONS \
  --header 'Origin: http://127.0.0.1:3080' \
  --header 'Access-Control-Request-Method: POST' \
  http://127.0.0.1:8030/api/auth/login)
printf '%s' "$cors_headers" | tr -d '\r' | grep --ignore-case --quiet '^access-control-allow-origin: http://127.0.0.1:3080$'
printf '%s' "$cors_headers" | tr -d '\r' | grep --ignore-case --quiet '^access-control-allow-credentials: true$'

curl --fail --silent http://127.0.0.1:8030/api/setup/status | grep --quiet '"configured":false'
curl --fail --silent --request POST \
  --header 'Content-Type: application/json' \
  --data '{"username":"administrator","password":"Parola-Smoke-Sigura-123!","server_ip":"127.0.0.1","locality":"Ceahlău","county":"Neamț","currency":"RON","vat_rate":"21"}' \
  http://127.0.0.1:8030/api/setup >/dev/null

cookie_jar=$(mktemp)
curl --fail --silent --cookie-jar "$cookie_jar" --request POST \
  --header 'Content-Type: application/json' \
  --data '{"username":"administrator","password":"Parola-Smoke-Sigura-123!"}' \
  http://127.0.0.1:8030/api/auth/login >/dev/null
curl --fail --silent --cookie "$cookie_jar" http://127.0.0.1:8030/api/auth/me | grep --quiet '"username":"administrator"'
curl --fail --silent --cookie "$cookie_jar" --request POST \
  --header 'Content-Type: application/json' \
  --data '{"name":"Proiect smoke Unraid","locality":"Ceahlău","county":"Neamț","default_waste_percent":"5"}' \
  http://127.0.0.1:8030/api/projects | grep --quiet '"name":"Proiect smoke Unraid"'

echo 'Smoke test instalare Unraid: OK'
