"""SimpleFIN client: claim Setup Token and fetch accounts (PRD §3.1, §3.2)."""

import base64
import logging
from urllib.parse import urljoin, urlparse

import httpx

from firesimplefin.simplefin_models import SimpleFINAccountSet

logger = logging.getLogger("firesimplefin.simplefin")


class SimpleFINClaimError(Exception):
    """Claim failed (invalid token, 403, network)."""

    def __init__(self, message: str, status_code: int | None = None, safe_message: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.safe_message = safe_message or message


class SimpleFINFetchError(Exception):
    """Fetch accounts failed."""

    def __init__(self, message: str, status_code: int | None = None, errors: list[str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []


def _ensure_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() != "https":
        raise ValueError("SimpleFIN requires HTTPS")


def _accounts_url(access_url: str) -> str:
    """Base URL for /accounts: no trailing slash then add /accounts."""
    base = access_url.rstrip("/")
    return urljoin(base + "/", "accounts")


def claim(
    setup_token: str,
    *,
    timeout: float = 30.0,
    verify_tls: bool = True,
    client: httpx.Client | None = None,
) -> str:
    """
    Exchange Setup Token for Access URL.

    - Base64-decode token → claim URL.
    - POST with no body (Content-Length: 0).
    - Response body is the Access URL (plain text).
    - Raises SimpleFINClaimError on non-2xx (e.g. 403) or invalid token.
    - Uses HTTPS only; verifies TLS by default.
    """
    if not setup_token or not setup_token.strip():
        raise SimpleFINClaimError("Setup token is required", safe_message="Setup token is required")

    try:
        raw = base64.standard_b64decode(setup_token.strip())
        claim_url = raw.decode("utf-8").strip()
    except Exception as e:
        logger.warning("Invalid setup token (decode failed)")
        raise SimpleFINClaimError(
            f"Invalid setup token: {e!s}",
            safe_message="Invalid setup token. Please copy the full token from SimpleFIN.",
        ) from e

    try:
        _ensure_https(claim_url)
    except ValueError as e:
        raise SimpleFINClaimError(str(e), safe_message="SimpleFIN requires a secure connection (HTTPS).") from e

    own_client = client is None
    if client is None:
        client = httpx.Client(timeout=timeout, verify=verify_tls)

    try:
        resp = client.post(claim_url, content=b"")
        body = resp.text.strip() if resp.content else ""

        if resp.status_code == 403:
            safe = (
                "This token was rejected or has already been used. "
                "If you did not use it here, disable it at the SimpleFIN Bridge and create a new one."
            )
            logger.warning("SimpleFIN claim returned 403")
            raise SimpleFINClaimError(
                f"Claim rejected: {body or resp.reason_phrase}",
                status_code=403,
                safe_message=safe,
            )

        if resp.status_code < 200 or resp.status_code >= 300:
            safe = "Could not connect your account. Please check the token and try again."
            raise SimpleFINClaimError(
                f"Claim failed {resp.status_code}: {body or resp.reason_phrase}",
                status_code=resp.status_code,
                safe_message=safe,
            )

        if not body:
            raise SimpleFINClaimError(
                "Empty response from SimpleFIN",
                status_code=resp.status_code,
                safe_message="Invalid response from SimpleFIN. Please try again.",
            )

        _ensure_https(body)
        return body
    finally:
        if own_client:
            client.close()


def fetch_accounts(
    access_url: str,
    *,
    start_date: int | None = None,
    end_date: int | None = None,
    account_ids: list[str] | None = None,
    balances_only: bool = False,
    pending: bool = False,
    timeout: float = 30.0,
    verify_tls: bool = True,
    client: httpx.Client | None = None,
) -> SimpleFINAccountSet:
    """
    GET {ACCESS_URL}/accounts with Basic Auth (from Access URL).

    Query params: start-date, end-date (Unix), account (repeatable), balances-only, pending.
    Returns parsed Account Set (accounts + errors). Raises SimpleFINFetchError on HTTP errors.
    """
    _ensure_https(access_url)
    url = _accounts_url(access_url)

    params: list[tuple[str, str]] = []
    if start_date is not None:
        params.append(("start-date", str(start_date)))
    if end_date is not None:
        params.append(("end-date", str(end_date)))
    if account_ids:
        for aid in account_ids:
            params.append(("account", aid))
    if balances_only:
        params.append(("balances-only", "1"))
    if pending:
        params.append(("pending", "1"))

    own_client = client is None
    if client is None:
        client = httpx.Client(timeout=timeout, verify=verify_tls)

    try:
        resp = client.get(url, params=params if params else None)

        if resp.status_code == 403:
            raise SimpleFINFetchError(
                "Access revoked or invalid",
                status_code=403,
                errors=["Your SimpleFIN connection may have been disabled. Please reconnect."],
            )

        if resp.status_code < 200 or resp.status_code >= 300:
            raise SimpleFINFetchError(
                f"Fetch failed {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )

        data = resp.json()
        return SimpleFINAccountSet.model_validate(data)
    finally:
        if own_client:
            client.close()
