"""Health and readiness endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: is the process up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness: is the app ready to accept traffic (no secrets in response)."""
    return {"status": "ready"}
