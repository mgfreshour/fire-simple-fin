# Fire SimpleFIN — common commands
# Run app: make run (single server at http://localhost:8080)
# Tests: make test (all unit tests)
# Lint: make lint

PYTHON   ?= python3
UV       ?= uv
BACKEND  = backend
FRONTEND = frontend
E2E      = e2e

.PHONY: backend-venv backend-install backend-run backend-test backend-lint frontend-install frontend-run frontend-build frontend-lint install dev health clean e2e-install e2e e2e-report test run lint env-encrypt env-decrypt

# --- Backend ---

backend-venv:
	@test -d $(BACKEND)/.venv || (cd $(BACKEND) && $(UV) venv)

backend-install: backend-venv
	cd $(BACKEND) && . .venv/bin/activate && $(UV) pip install -e .

backend-run:
	cd $(BACKEND) && . .venv/bin/activate && uvicorn firesimplefin.main:app --reload --host 0.0.0.0 --port 8080

backend-test: backend-install
	cd $(BACKEND) && . .venv/bin/activate && $(UV) pip install -e ".[dev]" && $(UV) run pytest tests -v

# --- Frontend ---

frontend-install:
	cd $(FRONTEND) && npm install

frontend-run:
	cd $(FRONTEND) && npm run dev

frontend-build:
	cd $(FRONTEND) && npm run build

frontend-check:
	cd $(FRONTEND) && npm run check

# --- E2E (Playwright) ---

e2e-install: install
	cd $(E2E) && npm install && npx playwright install chromium

e2e: e2e-install
	cd $(E2E) && npm test

e2e-report:
	cd $(E2E) && npx playwright show-report

# --- Convenience ---

# Run all unit tests (backend pytest)
test: backend-test

# Run app locally: backend serves API + static frontend on http://localhost:8080
run: backend-install frontend-build
	@echo "Starting app at http://localhost:8080 ..."
	cd $(BACKEND) && . .venv/bin/activate && FRONTEND_DIST=$(CURDIR)/$(FRONTEND)/dist uvicorn firesimplefin.main:app --reload --host 0.0.0.0 --port 8080

# Lint backend (ruff) and frontend (tsc)
lint: backend-lint frontend-lint

backend-lint: backend-install
	cd $(BACKEND) && . .venv/bin/activate && $(UV) pip install -e ".[dev]" && $(UV) run ruff check src tests

frontend-lint: frontend-install
	cd $(FRONTEND) && npm run check

install: backend-install frontend-install

# Hit backend health (requires backend running)
health:
	@curl -s http://localhost:8080/api/health && echo ""
	@curl -s http://localhost:8080/api/ready && echo ""

# --- Env (SOPS) ---
# One-time: put your age public key in .sops.yaml (replace REPLACE_WITH_YOUR_AGE_PUBLIC_KEY).
# Generate with: age-keygen -o age-key.txt; use the public key in .sops.yaml, SOPS_AGE_KEY for the private key.
# Encrypt root .env to .env.enc for private deploy only; decrypt for local use or CI.
# Do not publish .env.enc or age private keys.
env-encrypt:
	@test -f .env || (echo "Create .env from env.example first." && exit 1)
	@grep -q 'REPLACE_WITH_YOUR_AGE_PUBLIC_KEY' .sops.yaml 2>/dev/null && (echo "Edit .sops.yaml: replace REPLACE_WITH_YOUR_AGE_PUBLIC_KEY with your age public key (age-keygen -o age-key.txt)." && exit 1) || true
	sops --input-type dotenv --output-type dotenv --encrypt .env > .env.enc
	@echo "Wrote .env.enc (private deploy only; do not commit .env or publish .env.enc)."

env-decrypt:
	@test -f .env.enc || (echo "No .env.enc found." && exit 1)
	@test -n "$$SOPS_AGE_KEY" || (echo "Set SOPS_AGE_KEY to your age private key for decryption." && exit 1)
	sops --input-type dotenv --output-type dotenv --decrypt .env.enc > .env
	@echo "Wrote .env (gitignored)."

clean:
	rm -rf $(BACKEND)/.venv $(BACKEND)/*.egg-info $(BACKEND)/dist $(BACKEND)/build
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/dist
	rm -rf $(E2E)/node_modules $(E2E)/test-results $(E2E)/playwright-report $(E2E)/blob-report $(E2E)/.cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
