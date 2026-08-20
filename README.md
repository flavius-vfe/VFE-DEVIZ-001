# VFE-DEVIZ-001

Aplicație locală, în limba română, pentru devize de construcții, liste de cantități (BOQ),
costuri, achiziții și urmărirea execuției.

## Stadiu
Increment funcțional inițial (`0.1.0`):
- API FastAPI
- PostgreSQL + Alembic
- configurare inițială administrator
- autentificare cu sesiune 7 zile
- proiecte
- motor de calcul BOQ de bază
- calcul TVA, pachete, fier beton, geometrie cameră/acoperiș
- comparație furnizori după cost livrat
- frontend Next.js în română
- worker separat
- Docker / Unraid
- CI + release GHCR

## Porturi
- Frontend host: `3080`
- Backend host: `8030`
- PostgreSQL: numai rețeaua Docker

## Pornire dezvoltare
1. Copiază `.env.example` în `.env`.
2. Pornește PostgreSQL.
3. Rulează migrațiile din `backend`:
   `alembic upgrade head`
4. Pornește backend:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000`
5. Pornește frontend:
   `npm run dev -- --hostname 0.0.0.0 --port 3000`

Pe Unraid se folosesc porturile host 3080/8030.

## Securitate
- un singur cont `administrator` în MVP;
- parola este hash-uită Argon2id;
- sesiunea este stocată prin token aleator, în cookie HttpOnly;
- PostgreSQL nu se publică în LAN;
- acces remote numai prin VPN existent.

Consultați `docs/SPEC-001-DEVIZ-CONSTRUCTII.md`.
