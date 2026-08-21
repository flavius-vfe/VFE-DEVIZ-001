# Instalare VFE Deviz pe Unraid

Versiune recomandată: `0.1.7`. Instalarea nu folosește reverse proxy; accesul este direct prin IP-ul LAN sau prin VPN-ul existent.

## 1. Pregătire

1. Notează IP-ul LAN fix al serverului Unraid (exemplu: `192.168.0.50`).
2. Alege o parolă PostgreSQL puternică, fără caractere care trebuie codificate într-un URL.
3. În terminalul Unraid rulează o singură dată:

   ```bash
   docker network inspect vfe-deviz >/dev/null 2>&1 || docker network create vfe-deviz
   mkdir -p /mnt/user/appdata/vfe-deviz/postgres
   mkdir -p /mnt/user/appdata/vfe-deviz/backend
   mkdir -p /mnt/user/deviz-data
   ```

## 2. Instalează PostgreSQL

Importă `unraid/templates/deviz-postgres.xml` sau creează containerul cu:

- nume: `vfe-deviz-postgres`;
- imagine: `postgres:18.6`;
- rețea: `vfe-deviz`;
- `POSTGRES_DB=deviz`;
- `POSTGRES_USER=deviz`;
- `POSTGRES_PASSWORD=<PAROLA_ALEASĂ>`;
- `/mnt/user/appdata/vfe-deviz/postgres` → `/var/lib/postgresql` (read/write; ținta necesară pentru PostgreSQL 18+);
- niciun port publicat. Nu adăuga mapare pentru `5432`.

Pornește containerul și așteaptă starea `healthy`.

## 3. Instalează backend-ul

Importă `unraid/templates/deviz-backend.xml` și setează:

- imagine: `ghcr.io/flavius-vfe/vfe-deviz-backend:0.1.7`;
- rețea: `vfe-deviz`;
- port host `8030` → container `8000`;
- `DATABASE_URL=postgresql+psycopg://deviz:<PAROLA_ALEASĂ>@vfe-deviz-postgres:5432/deviz`;
- `SERVER_IP=<IP_UNRAID>`;
- `FRONTEND_PORT=3080`;
- `SESSION_DAYS=7`;
- `/mnt/user/appdata/vfe-deviz/backend` → `/appdata` (read/write);
- `/mnt/user/deviz-data` → `/data` (read/write).

La fiecare pornire, backend-ul așteaptă PostgreSQL și rulează idempotent `alembic upgrade head` înainte de API. Verifică:

```text
http://<IP_UNRAID>:8030/health
http://<IP_UNRAID>:8030/ready
```

Ambele trebuie să răspundă cu status HTTP `200`.

## 4. Instalează worker-ul

Importă `unraid/templates/deviz-worker.xml` și setează:

- imagine: `ghcr.io/flavius-vfe/vfe-deviz-worker:0.1.7`;
- rețea: `vfe-deviz`;
- același `DATABASE_URL` ca la backend;
- `REFRESH_INTERVAL_SECONDS=86400`;
- niciun port publicat.

Worker-ul reîncearcă automat conexiunea la PostgreSQL și devine `healthy` după prima conexiune reușită.

## 5. Instalează frontend-ul

Importă `unraid/templates/deviz-frontend.xml` și setează:

- imagine: `ghcr.io/flavius-vfe/vfe-deviz-frontend:0.1.7`;
- rețea: `vfe-deviz`;
- port host `3080` → container `3000`;
- `API_BASE_URL` gol pentru configurația recomandată.

Cu `API_BASE_URL` gol, browserul folosește automat hostname-ul paginii și portul `8030`. Pentru o adresă API explicită, setează la runtime, de exemplu `http://192.168.0.50:8030`; valoarea nu este inclusă în imagine.

## 6. Configurare inițială

1. Deschide `http://<IP_UNRAID>:3080`.
2. Introdu manual IP-ul serverului Unraid.
3. Confirmă localitatea `Ceahlău`, județul `Neamț`, moneda `RON` și TVA-ul curent configurabil (implicit `21%`).
4. Alege parola administratorului (minimum 10 caractere).
5. Autentifică-te și creează primul proiect.

Sesiunea administratorului este păstrată 7 zile. Nu expune aplicația direct la Internet; folosește numai LAN sau VPN.

## 7. Verificare și diagnostic

Deschide `http://<SERVER_IP>:3080/suppliers` pentru furnizori. Importă numai URL-uri publice Dedeman sau MatHaus; fiecare produs rămâne o ofertă asociată unui material generic. Stocul local neconfirmat este `UNKNOWN`, transportul se introduce manual, iar actualizarea automată vizează doar produsele folosite în proiecte active, o dată la 24 de ore.

- `docker ps` trebuie să arate toate cele patru containere ca `healthy`;
- numai porturile LAN `3080` și `8030` trebuie publicate;
- `vfe-deviz-postgres` și `vfe-deviz-worker` nu trebuie să aibă porturi publicate;
- toate containerele trebuie să fie conectate la rețeaua `vfe-deviz`;
- logurile backend trebuie să conțină finalizarea migrației Alembic înainte de pornirea Uvicorn.

Pentru upgrade, oprește worker-ul, actualizează mai întâi backend-ul (migrațiile rulează automat), apoi frontend-ul și worker-ul. Folosește întotdeauna tag-ul exact al versiunii, nu `latest`.
