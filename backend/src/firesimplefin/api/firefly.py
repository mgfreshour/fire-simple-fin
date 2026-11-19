"""Firefly III proxy endpoints (accounts list for link UI)."""

import logging

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from firesimplefin.config import settings
from firesimplefin.firefly_client import FireflyClient

logger = logging.getLogger("firesimplefin.api.firefly")

router = APIRouter()


class FireflyAccountSummary(BaseModel):
    id: int
    name: str
    type: str


@router.get("/firefly/accounts", response_model=list[FireflyAccountSummary])
async def list_firefly_accounts() -> list[FireflyAccountSummary]:
    """List Firefly accounts for the link dropdown (id, name, type)."""
    if not settings.firefly_base_url or not settings.firefly_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firefly III is not configured.",
        )
    try:
        async with httpx.AsyncClient(timeout=300) as http_client:
            client = FireflyClient(
                settings.firefly_base_url,
                settings.firefly_token,
                http_client,
            )
            accounts = await client.get_accounts()
    except httpx.ConnectError as e:
        logger.warning("Could not reach Firefly III: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Firefly III. Check that the URL is correct and the server is running.",
        ) from e
    except httpx.HTTPStatusError as e:
        logger.warning("Firefly III returned error: %s", e.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Firefly III returned an error. Check your token and try again.",
        ) from e
    except httpx.RequestError as e:
        logger.warning("Firefly III request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not communicate with Firefly III. Please try again.",
        ) from e
    return [
        FireflyAccountSummary(id=a.id, name=a.name, type=a.type.value)
        for a in accounts
    ]
