"""App configuration from environment."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env (so backend loads it regardless of cwd)
_ROOT_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Load from env / .env; no secrets in defaults."""

    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV) if _ROOT_ENV.is_file() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    listen_url: str = "0.0.0.0:8080"
    # When set, serve static frontend from this directory (e.g. in Docker)
    frontend_dist: str | None = None

    # Firefly III (required when using Firefly features)
    firefly_base_url: str | None = None
    firefly_token: str | None = None

    # Encryption key for stored SimpleFIN Access URL (required for persistence)
    # Must be set before enabling SimpleFIN connection storage.
    encryption_key: str | None = None

    # SimpleFIN client
    simplefin_timeout_seconds: float = 30.0
    simplefin_verify_tls: bool = True
    # Optional: Bridge URL for documentation only (e.g. https://bridge.simplefin.org)
    simplefin_bridge_url: str | None = None


settings = Settings()
