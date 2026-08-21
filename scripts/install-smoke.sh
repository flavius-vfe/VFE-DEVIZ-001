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
curl --fail --silent --cookie "$cookie_jar" http://127.0.0.1:8030/api/catalog/categories | python3 -c 'import json,sys; assert len(json.load(sys.stdin))==20'
curl --fail --silent --cookie "$cookie_jar" http://127.0.0.1:8030/api/catalog/work-items | python3 -c 'import json,sys; rows=json.load(sys.stdin); assert len(rows)>=51; assert any(x["name"]=="Zidărie BCA 25 cm" for x in rows)'
project_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST \
  --header 'Content-Type: application/json' \
  --data '{"name":"Proiect smoke Unraid","locality":"Ceahlău","county":"Neamț","default_waste_percent":"5"}' \
  http://127.0.0.1:8030/api/projects)
printf '%s' "$project_json" | grep --quiet '"name":"Proiect smoke Unraid"'
project_id=$(printf '%s' "$project_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl --fail --silent "http://127.0.0.1:3080/projects/$project_id" >/dev/null

building_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"name":"Corp smoke"}' "http://127.0.0.1:8030/api/projects/$project_id/buildings")
building_id=$(printf '%s' "$building_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
level_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"name":"Parter","elevation_m":"0"}' "http://127.0.0.1:8030/api/buildings/$building_id/levels")
level_id=$(printf '%s' "$level_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
section_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"code":"01","name":"Fundații"}' "http://127.0.0.1:8030/api/levels/$level_id/sections")
section_id=$(printf '%s' "$section_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
item_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"code":"01.001","description":"Beton smoke","unit":"m3","quantity":"10","waste_percent":"5","notes":"Integrare frontend/backend"}' "http://127.0.0.1:8030/api/sections/$section_id/items")
item_id=$(printf '%s' "$item_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl --fail --silent --cookie "$cookie_jar" --request PUT --header 'Content-Type: application/json' --data '{"code":"01.001A","description":"Beton actualizat","unit":"m3","quantity":"12","waste_percent":"7","notes":"Actualizat"}' "http://127.0.0.1:8030/api/estimate-items/$item_id" | grep --quiet '"notes":"Actualizat"'

for route in catalog/materiale catalog/manopera catalog/utilaje catalog/lucrari settings/catalog "projects/$project_id/estimate"; do
  curl --fail --silent "http://127.0.0.1:3080/$route" >/dev/null
done

labor_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"code":"MAN-SMOKE","name":"Zidar smoke","unit":"ora","rate_net":"50.1234","vat_rate":"21","active":true}' http://127.0.0.1:8030/api/catalog/labor)
labor_id=$(printf '%s' "$labor_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
work_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"code":"LC-SMOKE","name":"Lucrare smoke","category":"Integrare","unit":"m3","active":true}' http://127.0.0.1:8030/api/catalog/work-items)
work_id=$(printf '%s' "$work_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
recipe_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data "{\"work_item_id\":$work_id,\"scope\":\"STANDARD\",\"version\":1}" http://127.0.0.1:8030/api/recipes)
recipe_id=$(printf '%s' "$recipe_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data "{\"resource_type\":\"LABOR\",\"resource_id\":$labor_id,\"quantity_per_unit\":\"1.5\",\"waste_percent\":\"10\",\"unit\":\"ora\"}" "http://127.0.0.1:8030/api/recipes/$recipe_id/resources" >/dev/null
curl --fail --silent --cookie "$cookie_jar" --request PUT --header 'Content-Type: application/json' --data "{\"code\":\"01.001A\",\"description\":\"Beton actualizat\",\"unit\":\"m3\",\"quantity\":\"12\",\"waste_percent\":\"7\",\"notes\":\"Actualizat\",\"work_item_id\":$work_id}" "http://127.0.0.1:8030/api/estimate-items/$item_id" >/dev/null
curl --fail --silent --cookie "$cookie_jar" --request POST "http://127.0.0.1:8030/api/estimate-items/$item_id/resources/generate" | grep --quiet '"resource_type":"LABOR"'
curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data '{"resource_type":"OTHER","description":"Protecții smoke","unit":"set","quantity":"2","waste_percent":"5","unit_price_net":"10","vat_rate":"21"}' "http://127.0.0.1:8030/api/estimate-items/$item_id/resources" | grep --quiet '"source":"MANUAL"'
curl --fail --silent --cookie "$cookie_jar" "http://127.0.0.1:8030/api/projects/$project_id/estimate-totals" | grep --quiet '"total_gross"'

catalogue_work_id=$(curl --fail --silent --cookie "$cookie_jar" http://127.0.0.1:8030/api/catalog/work-items | python3 -c 'import json,sys; print(next(x["id"] for x in json.load(sys.stdin) if x["name"]=="Zidărie BCA 25 cm"))')
geometry_item_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data "{\"work_item_id\":$catalogue_work_id,\"code\":\"GEO-01\",\"quantity\":\"1\",\"waste_percent\":\"0\"}" "http://127.0.0.1:8030/api/sections/$section_id/items/from-catalog")
geometry_item_id=$(printf '%s' "$geometry_item_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
geometry_json=$(curl --fail --silent --cookie "$cookie_jar" --request POST --header 'Content-Type: application/json' --data "{\"estimate_item_id\":$geometry_item_id,\"geometry_type\":\"ROOM\",\"name\":\"Camera smoke\",\"input_data\":{\"length_m\":\"5\",\"width_m\":\"4\",\"height_m\":\"2.8\",\"openings\":[]},\"selected_result\":\"net_wall_area_m2\",\"waste_percent\":\"5\"}" "http://127.0.0.1:8030/api/projects/$project_id/geometry")
printf '%s' "$geometry_json" | grep --quiet '"geometry_type":"ROOM"'
curl --fail --silent --cookie "$cookie_jar" "http://127.0.0.1:8030/api/sections/$section_id/items" | python3 -c 'import json,sys,decimal; rows=json.load(sys.stdin); row=next(x for x in rows if x["code"]=="GEO-01"); assert decimal.Decimal(str(row["quantity"]))==decimal.Decimal("52.92")'
curl --fail --silent --cookie "$cookie_jar" "http://127.0.0.1:8030/api/estimate-items/$geometry_item_id/resources" | grep --quiet '"source":"RECIPE"'
curl --fail --silent "http://127.0.0.1:3080/projects/$project_id/geometry" >/dev/null
docker compose restart backend >/dev/null
for attempt in $(seq 1 30); do curl --fail --silent http://127.0.0.1:8030/ready >/dev/null && break; sleep 2; done
curl --fail --silent --cookie "$cookie_jar" "http://127.0.0.1:8030/api/projects/$project_id/geometry" | grep --quiet '"name":"Camera smoke"'
curl --fail --silent --cookie "$cookie_jar" "http://127.0.0.1:8030/api/estimate-items/$geometry_item_id/resources" | grep --quiet 'BCA 25 cm'

curl --fail --silent --cookie "$cookie_jar" --request DELETE "http://127.0.0.1:8030/api/estimate-items/$item_id" >/dev/null
curl --fail --silent --cookie "$cookie_jar" --request DELETE "http://127.0.0.1:8030/api/estimate-items/$geometry_item_id" >/dev/null
curl --fail --silent --cookie "$cookie_jar" "http://127.0.0.1:8030/api/sections/$section_id/items" | grep --quiet '^\[\]$'

echo 'Smoke test instalare Unraid: OK'
