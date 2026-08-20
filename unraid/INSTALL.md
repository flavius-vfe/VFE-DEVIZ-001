# Instalare Unraid

## Rețea Docker internă
Creează o singură dată rețeaua Docker:
`docker network create vfe-deviz`

Toate cele patru containere trebuie conectate la `vfe-deviz`.
PostgreSQL rămâne fără port public și este accesat ca `vfe-deviz-postgres:5432`.

## Porturi
- Frontend host `3080` → container `3000`
- Backend host `8030` → container `8000`
- PostgreSQL: fără port host
- Worker: fără port host

## Persistență
- PostgreSQL: `/mnt/user/appdata/deviz/postgresql`
- Date proiect: `/mnt/user/deviz-data`

## Variabile
- `SERVER_IP=<IP-ul introdus manual>`
- `FRONTEND_PORT=3080`
- `BACKEND_PORT=8030`
- `POSTGRES_DB=deviz`
- `POSTGRES_USER=deviz`
- `POSTGRES_PASSWORD=<secret>`
- `SESSION_DAYS=7`

## Imagini release
- `ghcr.io/flavius-vfe/vfe-deviz-frontend:<version>`
- `ghcr.io/flavius-vfe/vfe-deviz-backend:<version>`
- `ghcr.io/flavius-vfe/vfe-deviz-worker:<version>`

În producție se folosește un tag exact, nu `latest`.

## Ordine upgrade
1. Oprește worker.
2. Rulează `alembic upgrade head` cu imaginea backend nouă.
3. Actualizează backend.
4. Actualizează frontend.
5. Actualizează worker.
6. Verifică `/health` și `/ready`.
