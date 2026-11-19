# Contributing

Thanks for helping improve Fire SimpleFIN. Keep changes focused and practical.

## Development setup

From the repository root:

```bash
cp env.example .env
# Set ENCRYPTION_KEY (required to store connections). Optionally set FIREFLY_* for sync/push.
make install
make run          # http://localhost:8080
```

Optional: `make frontend-run` for Vite hot reload on port 5173 while `make backend-run` serves the API.

## Checks

```bash
make lint          # ruff (backend) + TypeScript check (frontend)
make test          # backend unit tests (pytest)
make e2e           # Playwright (starts the app)
```

## Pull requests

- Prefer small PRs with a clear purpose.
- Match existing style: minimal comments, imports at the top of the file.
- Do not commit `.env`, databases under `backend/data/`, or any secrets.
- Update `env.example` if you add configuration knobs.
- Describe what you changed and how you tested it.

## Scope

Bug fixes, docs, tests, and small features that fit the SimpleFIN → Firefly bridge are welcome. Large redesigns: open an issue first.
