# VFE-DEVIZ-001

Aplicație locală, în limba română, pentru devize de construcții, liste de cantități (BOQ),
costuri, achiziții și urmărirea execuției.

## Stadiu
Increment funcțional instalabil pe Unraid (`0.1.8`):
- API FastAPI
- PostgreSQL + Alembic
- configurare inițială administrator
- autentificare cu sesiune 7 zile
- proiecte
- motor de calcul BOQ de bază
- calcul TVA, pachete, fier beton, geometrie cameră/acoperiș
- comparație furnizori după cost livrat
- frontend Next.js în română
- editor frontend complet pentru Proiect → Corp → Nivel → Capitol → Articol de deviz
- creare, editare, ștergere și subtotaluri cantitative pe unități
- cataloage generice pentru materiale, manoperă, utilaje și alte resurse
- rețete STANDARD → COMPANY OVERRIDE → PROJECT OVERRIDE, fără modificarea rețetei master
- linii de resurse generate și manuale, prețuri specifice proiectului și totaluri net/TVA/brut
- calcule exclusiv Decimal/Numeric și conversii reutilizabile de unități
- modele de versiuni și snapshot-uri pentru păstrarea calculelor istorice
- motor geometric Decimal pentru încăperi, structură, armături, plasă sudată și acoperiș în două ape
- sincronizare automată geometrie → cantitate articol → resurse rețetă → total deviz
- catalog standard românesc versionat: 20 categorii, lucrări, materiale generice și manoperă
- rețete standard editabile, override-uri, versiuni fixate în deviz și import/export JSON
- oferte Dedeman și MatHaus din pagini publice, import URL, istoric de preț și asociere la materiale generice
- optimizare landed-cost pe furnizor unic/mix, transport manual, planuri blocabile și liste PDF/XLSX
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

Pentru instalarea de producție consultați [`docs/UNRAID-INSTALL.md`](docs/UNRAID-INSTALL.md).
