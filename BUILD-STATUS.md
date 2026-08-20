# BUILD STATUS — 2026-08-20

## Verificat local
- Python compileall: OK
- Pytest backend: 11/11 teste trecute
- Alembic `upgrade head` pe bază goală: OK
- Alembic `check`: OK, zero operații noi detectate
- Smoke API pe DB migrată: OK
  - `/health`
  - `/ready`
  - setup administrator
  - login
  - creare proiect
  - listare proiecte
- Sintaxă TypeScript/TSX: OK
- YAML: OK
- XML template-uri Unraid: OK
- `git diff --check`: OK

## Neexecutabil în mediul local curent
- Build-ul Docker complet: runtime Docker nu este disponibil în mediul de lucru.
- `npm install` / `next build`: accesul de rețea npm nu este disponibil în mediul de lucru.

Aceste două verificări sunt definite obligatoriu în GitHub Actions; release-ul GHCR nu se construiește
dacă testele backend, migrațiile, typecheck-ul sau build-ul Next.js eșuează.

## Scope implementat în 0.1.0
Nucleul M1 + începutul M2/M3:
- autentificare
- wizard inițial
- proiecte
- schemă BOQ/furnizori/prețuri/snapshot
- TVA
- pierderi
- pachete
- camere
- beton
- fier beton
- etrieri
- suprafață acoperiș
- cost livrat/furnizor unic și mix (motor pur)
- CI/release GHCR
- deployment Unraid

Adaptoarele reale Dedeman/MatHaus/Leroy/Hornbach și modulele operaționale complete urmează
în incrementurile M4–M8; worker-ul 0.1.0 verifică baza de date și este pregătit pentru aceste adaptoare.
