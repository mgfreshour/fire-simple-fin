# Agent memory

## Learned User Preferences

- When an operation fails (e.g. push to Firefly), the server should log the real error so it's visible in logs; return a safe message to the client.
- Prefer minimal comments and no inline imports; avoid IIFEs for simple variable computation.

## Learned Workspace Facts

- Backend loads config from environment and root `.env` (Pydantic Settings); frontend does not read .env for config (Vite can use VITE_* if needed).
- Make targets (e2e, install, run, etc.) are intended to be run from the repository root.
- When an external service (e.g. Firefly) is configured but unreachable, return 502 with a clear user-facing message instead of 500.
- Push to Firefly runs as a background job; the frontend polls for status; only New, Annotated, and Unmatched transactions are pushed (Matched are skipped).
- The app persists and displays last pull (sync) and last push timestamps per linked account on the index and sync pages.
- Docker runs a single container; the backend serves both the API and the static frontend (no nginx).
- Private deploy (maintainer only): SOPS-encrypted `.env.enc` + Forgejo/Portainer workflow; never publish ciphertext or age keys. Public GitHub history should not contain `.env.enc`.
