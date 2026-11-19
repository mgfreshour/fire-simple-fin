# Fire SimpleFIN

Bridge between [SimpleFIN](https://www.simplefin.org/) and [Firefly III](https://www.firefly-iii.org/): claim a bank connection via SimpleFIN (no bank passwords in this app), link accounts, pull transactions, review matches, and push selected ones into Firefly III.

## Features

- Claim a SimpleFIN connection with a Setup Token; Access URL stored encrypted at rest
- Link SimpleFIN accounts to Firefly III asset accounts
- Pull (sync) transactions for a date range; see last pull / last push per linked account
- Review match status and push **New**, **Annotated**, and **Unmatched** transactions to Firefly (Matched are skipped); push runs as a background job and the UI polls status
- Single process serves API + built frontend (no separate nginx)

## Architecture

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12+, FastAPI, Pydantic Settings, httpx, uvicorn |
| Frontend | React 19, TypeScript, Vite |
| Persistence | SQLite (`DATABASE_PATH` / default under `backend/data/`) |
| Auth | None in-app — put a reverse proxy or trusted network in front |

Config is loaded from the environment and an optional root `.env` (see [env.example](env.example)). The frontend does not read secrets from `.env`.

```
Browser → FastAPI (/api/… + static UI)
              ├─ SimpleFIN Bridge (HTTPS)
              ├─ Firefly III API
              └─ SQLite (encrypted Access URL, links, sync state)
```

## Security

- **No bank credentials** in this app — only SimpleFIN Setup Token → Access URL.
- **Do not expose** the app unauthenticated on the public internet; use OAuth2 Proxy, SSO, VPN, or an allowlist.
- **Never commit** `.env`, ciphertext env files, age keys, or real tokens. See [SECURITY.md](SECURITY.md).

## Running locally

### Prerequisites

- Python 3.12+
- Node.js 18+
- Optional: [uv](https://docs.astral.sh/uv/)

### Makefile (from repo root)

```bash
cp env.example .env
# Edit .env: set ENCRYPTION_KEY; set FIREFLY_BASE_URL + FIREFLY_TOKEN for sync/push

make install          # backend venv + frontend npm install
make run              # build frontend + serve API+UI at http://localhost:8080
make health           # curl /api/health and /api/ready
make test             # backend unit tests
make lint             # ruff + TypeScript check
make e2e              # Playwright (starts the app)
make clean
```

`make run` rebuilds the frontend then starts one server. Backend reloads on code changes; for frontend changes run `make frontend-build` and refresh (or use `make frontend-run` + `make backend-run`).

### Manual

```bash
cp env.example .env
cd backend
uv pip install -e .   # or: pip install -e .
uvicorn firesimplefin.main:app --reload --host 0.0.0.0 --port 8080
```

Without `FRONTEND_DIST`, only the API is served.

## Docker

```bash
cp env.example .env   # set ENCRYPTION_KEY and optional FIREFLY_*
docker compose up --build
```

App: [http://localhost:8080](http://localhost:8080). Data lives in the `app-data` volume.

## Project layout

```
fire-simple-fin/
├── env.example           # Safe template → copy to .env
├── backend/              # FastAPI app
├── frontend/             # React + Vite UI
├── e2e/                  # Playwright tests
├── scripts/              # Optional helpers (e.g. Portainer env JSON)
├── docker-compose.yml
└── Makefile
```

## Maintainer deploy notes

Forgejo Actions, SOPS-encrypted env, and Portainer stack updates are used for the **maintainer’s private deploy**. They are not required for local use or typical forks. If those files appear in a private mirror, treat hostnames, registry defaults, and encrypted env as private; do not publish `.env.enc` or age private keys.

## License

[MIT](LICENSE) © 2026 Morgan Freshour
