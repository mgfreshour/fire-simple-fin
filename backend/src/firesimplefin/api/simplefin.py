"""SimpleFIN claim, connection, link, and sync endpoints."""

import asyncio
import logging
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from firesimplefin.background import (
    create_job,
    get_job,
    set_job_completed,
    set_job_failed,
    set_job_progress,
    set_job_running,
)
from pydantic import BaseModel, Field

from firesimplefin.config import settings
from firesimplefin.firefly_client import FireflyClient
from firesimplefin.merge import merge_transactions
from firesimplefin.model.api import DisplayTransaction, DisplayTransactionType, TransactionState
from firesimplefin.model.firefly import Transaction, TransactionType
from firesimplefin.simplefin_client import (
    SimpleFINClaimError,
    SimpleFINFetchError,
    claim as client_claim,
    fetch_accounts,
)
from firesimplefin.storage import ConnectionStore, LinkStore
from firesimplefin.sync_service import fetch_statement_transactions

logger = logging.getLogger("firesimplefin.api.simplefin")

router = APIRouter()


def _connection_store() -> ConnectionStore:
    if not settings.encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SimpleFIN connection storage is not configured (ENCRYPTION_KEY missing).",
        )
    return ConnectionStore(encryption_key=settings.encryption_key)


def _link_store() -> LinkStore:
    return LinkStore()


def _sanitize_errors(errors: list[str]) -> list[str]:
    """Remove internal URLs or secrets from SimpleFIN errors before returning to client."""
    sanitized: list[str] = []
    for msg in errors:
        # Avoid leaking URLs that might contain credentials or internal paths
        if "http://" in msg.lower() or "https://" in msg.lower():
            sanitized.append("A server error was reported. Please try again or reconnect.")
        else:
            sanitized.append(msg)
    return sanitized


class ClaimRequest(BaseModel):
    setup_token: str = Field(..., min_length=1, description="Base64-encoded Setup Token from SimpleFIN")


class AccountSummary(BaseModel):
    """SimpleFIN account for linking; no Access URL or credentials."""

    id: str
    name: str = ""
    currency: str = ""
    org_name: str | None = None


class ClaimResponse(BaseModel):
    connection_id: str
    accounts: list[AccountSummary] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ConnectionSummary(BaseModel):
    id: str
    label: str | None = None
    created_at: str
    link_count: int = 0


class LinkCreateRequest(BaseModel):
    connection_id: str
    simplefin_account_id: str = Field(..., min_length=1)
    firefly_account_id: int


class LinkResponse(BaseModel):
    id: str
    connection_id: str
    simplefin_account_id: str
    firefly_account_id: int
    created_at: str
    last_sync_at: str | None = None
    last_push_at: str | None = None


class SyncRequest(BaseModel):
    firefly_account_id: int
    start_date: date
    end_date: date


class PushRequest(BaseModel):
    firefly_account_id: int
    transactions: list[DisplayTransaction] = Field(..., max_length=500)


class PushError(BaseModel):
    index: int
    message: str


class PushResponse(BaseModel):
    pushed: int = 0
    errors: list[PushError] = Field(default_factory=list)


class PushJobResponse(BaseModel):
    job_id: str


class PushStatusResponse(BaseModel):
    status: str
    processed: int | None = None
    pushed: int | None = None
    errors: list[PushError] = Field(default_factory=list)
    message: str | None = None


def _display_to_firefly_transaction(
    account_id: int,
    account_currency_id: int,
    account_name: str,
    transaction: DisplayTransaction,
) -> Transaction:
    """Map DisplayTransaction to Firefly Transaction (reuse Firemerge logic)."""
    if transaction.type is DisplayTransactionType.Withdrawal:
        tr_type = TransactionType.Withdrawal
        source_id = account_id
        source_name = account_name
        destination_id = transaction.account_id
        destination_name = transaction.account_name
    elif transaction.type is DisplayTransactionType.TransferOut:
        tr_type = TransactionType.Transfer
        source_id = account_id
        source_name = account_name
        destination_id = transaction.account_id or 0
        destination_name = transaction.account_name
    elif transaction.type is DisplayTransactionType.TransferIn:
        tr_type = TransactionType.Transfer
        source_id = transaction.account_id or 0
        source_name = transaction.account_name
        destination_id = account_id
        destination_name = account_name
    elif transaction.type is DisplayTransactionType.Deposit:
        tr_type = TransactionType.Deposit
        source_id = transaction.account_id
        source_name = transaction.account_name
        destination_id = account_id
        destination_name = account_name
    else:
        raise ValueError(f"Invalid transaction type: {transaction.type!r}")

    tid: int | None = None
    if transaction.state is not TransactionState.New and transaction.id:
        try:
            tid = int(transaction.id)
        except ValueError:
            pass

    t = Transaction(
        id=tid,
        type=tr_type,
        date=transaction.date,
        amount=transaction.amount,
        description=transaction.description,
        currency_id=account_currency_id,
        foreign_amount=transaction.foreign_amount,
        foreign_currency_id=transaction.foreign_currency_id,
        category_id=transaction.category_id,
        source_id=source_id,
        source_name=source_name if source_id is None else None,
        destination_id=destination_id,
        destination_name=destination_name if destination_id is None else None,
        notes=transaction.notes,
    )

    if (
        transaction.type is DisplayTransactionType.TransferIn
        and transaction.foreign_amount is not None
    ):
        assert t.foreign_currency_id is not None
        t.amount, t.foreign_amount = t.foreign_amount, t.amount
        t.currency_id, t.foreign_currency_id = t.foreign_currency_id, t.currency_id

    return t


@router.post("/simplefin/sync", response_model=list[DisplayTransaction])
async def sync(request: SyncRequest) -> list[DisplayTransaction]:
    """
    Sync: resolve Firefly account → link → SimpleFIN; fetch in 60-day chunks;
    merge with Firefly transactions; return display list for review UI.
    """
    link_store = _link_store()
    link = link_store.get_by_firefly_account_id(request.firefly_account_id)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This Firefly account is not linked to a SimpleFIN account.",
        )
    store = _connection_store()
    conn = store.get_connection(link.connection_id)
    if not conn:
        # Orphan link (e.g. connection deleted without removing links). Clean up and tell user to reconnect.
        link_store.delete_by_connection_id(link.connection_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection was removed. Please connect with SimpleFIN again from the home page and re-link this account.",
        )
    access_url = store.get_access_url(link.connection_id)
    if not access_url:
        link_store.delete_by_connection_id(link.connection_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection was removed. Please connect with SimpleFIN again from the home page and re-link this account.",
        )

    try:
        statement = fetch_statement_transactions(
            access_url,
            request.start_date,
            request.end_date,
            simplefin_account_id=link.simplefin_account_id,
            timeout=settings.simplefin_timeout_seconds,
            verify_tls=settings.simplefin_verify_tls,
        )
    except SimpleFINFetchError as e:
        if e.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your SimpleFIN connection may have been disabled. If you revoked the token at the Bridge, create a new one and reconnect.",
            ) from e
        errors = _sanitize_errors(e.errors) if e.errors else [str(e)]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=errors[0] if errors else "Failed to fetch from SimpleFIN.",
        ) from e

    if not settings.firefly_base_url or not settings.firefly_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firefly III is not configured (FIREFLY_BASE_URL and FIREFLY_TOKEN required for sync).",
        )

    start = request.start_date - timedelta(days=1)
    end = request.end_date + timedelta(days=1)
    async with httpx.AsyncClient(timeout=300) as http_client:
        firefly = FireflyClient(
            settings.firefly_base_url,
            settings.firefly_token,
            http_client,
        )
        raw_transactions = await firefly.get_transactions(
            request.firefly_account_id, start, end
        )
        currencies = await firefly.get_currencies()

    transactions = []
    for tr in raw_transactions:
        if tr.type in (TransactionType.Reconciliation, TransactionType.OpeningBalance):
            continue
        if (
            tr.type == TransactionType.Transfer
            and tr.destination_id == request.firefly_account_id
            and tr.foreign_amount is not None
        ):
            tr = tr.model_copy(
                update={
                    "amount": tr.foreign_amount,
                    "foreign_amount": tr.amount,
                    "currency_id": tr.foreign_currency_id or tr.currency_id,
                    "foreign_currency_id": tr.currency_id,
                }
            )
        transactions.append(tr)

    result = merge_transactions(
        transactions,
        statement,
        currencies,
        request.firefly_account_id,
    )
    link_store.set_last_sync(request.firefly_account_id)
    return result


@router.get("/simplefin/connections", response_model=list[ConnectionSummary])
async def list_connections() -> list[ConnectionSummary]:
    """List all connections (no Access URL). Includes link count per connection."""
    store = _connection_store()
    link_store = _link_store()
    connections = store.list_connections()
    return [
        ConnectionSummary(
            id=c.id,
            label=c.label,
            created_at=c.created_at,
            link_count=link_store.count_links_for_connection(c.id),
        )
        for c in connections
    ]


@router.get("/simplefin/connections/{connection_id}/accounts", response_model=list[AccountSummary])
async def list_connection_accounts(connection_id: str) -> list[AccountSummary]:
    """
    List SimpleFIN accounts for this connection (fetched with balances-only).
    On 403 or errors from SimpleFIN, returns clear message; connection may need re-auth or disconnect.
    """
    store = _connection_store()
    conn_record = store.get_connection(connection_id)
    if not conn_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    access_url = store.get_access_url(connection_id)
    if not access_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        account_set = fetch_accounts(
            access_url,
            balances_only=True,
            timeout=settings.simplefin_timeout_seconds,
            verify_tls=settings.simplefin_verify_tls,
        )
    except SimpleFINFetchError as e:
        if e.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your SimpleFIN connection may have been disabled. If you revoked the token at the Bridge, create a new one and reconnect.",
            ) from e
        errors = _sanitize_errors(e.errors) if e.errors else [str(e)]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=errors[0] if errors else "Failed to fetch accounts from SimpleFIN.",
        ) from e
    return [
        AccountSummary(
            id=a.id,
            name=a.name or "",
            currency=a.currency or "",
            org_name=a.org.name if (a.org and a.org.name) else None,
        )
        for a in account_set.accounts
    ]


@router.delete("/simplefin/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(connection_id: str) -> None:
    """Disconnect: delete stored Access URL and all links for this connection."""
    store = _connection_store()
    if not store.delete(connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")


@router.post("/simplefin/links", response_model=LinkResponse)
async def create_or_replace_link(request: LinkCreateRequest) -> LinkResponse:
    """Create or replace an account link. One Firefly account at most one SimpleFIN link."""
    store = _connection_store()
    conn_record = store.get_connection(request.connection_id)
    if not conn_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    link_store = _link_store()
    record = link_store.create_or_replace(
        connection_id=request.connection_id,
        simplefin_account_id=request.simplefin_account_id,
        firefly_account_id=request.firefly_account_id,
    )
    return LinkResponse(
        id=record.id,
        connection_id=record.connection_id,
        simplefin_account_id=record.simplefin_account_id,
        firefly_account_id=record.firefly_account_id,
        created_at=record.created_at,
    )


@router.get("/simplefin/links", response_model=list[LinkResponse])
async def list_links(
    connection_id: str | None = None,
    firefly_account_id: int | None = None,
) -> list[LinkResponse]:
    """List account links, optionally filtered by connection_id and/or firefly_account_id."""
    link_store = _link_store()
    links = link_store.list_links(connection_id=connection_id, firefly_account_id=firefly_account_id)
    return [
        LinkResponse(
            id=link.id,
            connection_id=link.connection_id,
            simplefin_account_id=link.simplefin_account_id,
            firefly_account_id=link.firefly_account_id,
            created_at=link.created_at,
            last_sync_at=link.last_sync_at,
            last_push_at=link.last_push_at,
        )
        for link in links
    ]


@router.delete("/simplefin/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: str) -> None:
    """Remove one account link."""
    link_store = _link_store()
    if not link_store.delete(link_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")


def _sanitize_firefly_error(e: Exception) -> str:
    """Return a safe message for Firefly API errors."""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
            if isinstance(body, dict) and "message" in body:
                return str(body["message"])[:200]
        except Exception:
            pass
        if e.response.status_code == 422:
            return "Firefly rejected the transaction (validation error). Check payee and amount."
        if e.response.status_code >= 500:
            return "Firefly III server error. Try again later."
    return "Failed to save transaction. Try again or check Firefly."


async def _execute_push(request: PushRequest, job_id: str | None = None) -> PushResponse:
    """Run the push logic (background job). Updates job progress when job_id is set."""
    link_store = _link_store()
    link = link_store.get_by_firefly_account_id(request.firefly_account_id)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This Firefly account is not linked to a SimpleFIN account.",
        )
    if not settings.firefly_base_url or not settings.firefly_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firefly III is not configured.",
        )
    async with httpx.AsyncClient(timeout=300) as http_client:
        firefly_client = FireflyClient(
            settings.firefly_base_url,
            settings.firefly_token,
            http_client,
        )
        account = await firefly_client.get_account(request.firefly_account_id)
        if not account.currency_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Firefly account has no currency; cannot push.",
            )
        pushed = 0
        errors: list[PushError] = []
        for idx, display_tr in enumerate(request.transactions):
            if display_tr.state is TransactionState.Matched:
                continue
            try:
                ff_tr = _display_to_firefly_transaction(
                    request.firefly_account_id,
                    account.currency_id,
                    account.name,
                    display_tr,
                )
                await firefly_client.store_transaction(ff_tr)
                pushed += 1
                if job_id:
                    set_job_progress(job_id, pushed)
            except Exception as e:  # noqa: BLE001
                logger.warning("Push transaction %s failed: %s", idx + 1, e)
                errors.append(
                    PushError(index=idx, message=_sanitize_firefly_error(e))
                )
        if pushed > 0:
            link_store.set_last_push(request.firefly_account_id)
        return PushResponse(pushed=pushed, errors=errors)


def _run_push_job(job_id: str, request: PushRequest) -> None:
    """Background task: run push and update job state."""

    async def _run() -> None:
        set_job_running(job_id)
        try:
            result = await _execute_push(request, job_id=job_id)
            set_job_completed(job_id, result)
        except HTTPException as e:
            set_job_failed(job_id, e.detail)
        except Exception as e:  # noqa: BLE001
            logger.exception("Push job %s failed", job_id)
            set_job_failed(job_id, str(e))

    asyncio.create_task(_run())


@router.post("/simplefin/push", status_code=status.HTTP_202_ACCEPTED)
async def push(request: PushRequest) -> JSONResponse:
    """
    Start a background push to Firefly III. Returns 202 with job_id.
    Poll GET /api/simplefin/push/status/{job_id} until status is completed or failed.
    """
    link_store = _link_store()
    link = link_store.get_by_firefly_account_id(request.firefly_account_id)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This Firefly account is not linked to a SimpleFIN account.",
        )
    if not settings.firefly_base_url or not settings.firefly_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firefly III is not configured.",
        )
    job_id = create_job()
    _run_push_job(job_id, request)
    return JSONResponse(status_code=202, content={"job_id": job_id})


@router.get("/simplefin/push/status/{job_id}", response_model=PushStatusResponse)
async def push_status(job_id: str) -> PushStatusResponse:
    """Poll for push job completion. Returns status and result when completed or failed."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status == "completed":
        result = job.result
        return PushStatusResponse(
            status="completed",
            processed=result.pushed if result else 0,
            pushed=result.pushed if result else 0,
            errors=result.errors if result else [],
        )
    if job.status == "failed":
        return PushStatusResponse(
            status="failed",
            message=job.result if isinstance(job.result, str) else None,
        )
    return PushStatusResponse(status=job.status, processed=job.processed)


@router.post("/simplefin/claim", response_model=ClaimResponse)
async def claim(request: ClaimRequest) -> ClaimResponse:
    """
    Exchange Setup Token for Access URL, store it encrypted, and return account list.

    On success: connection is stored; returns connection_id and list of accounts (id, name, currency, org).
    On failure: no persistence; returns appropriate HTTP status and sanitized error message.
    Access URL is never returned or logged.
    """
    try:
        access_url = client_claim(
            request.setup_token,
            timeout=settings.simplefin_timeout_seconds,
            verify_tls=settings.simplefin_verify_tls,
        )
    except SimpleFINClaimError as e:
        logger.warning("Claim failed: %s", e.args[0] if e.args else "unknown")
        status_code = status.HTTP_400_BAD_REQUEST
        if e.status_code == 403:
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=e.safe_message) from e

    store = _connection_store()
    record = store.create(access_url, label=None)

    # Fetch accounts (balances-only to get list without large transaction payload)
    try:
        account_set = fetch_accounts(
            access_url,
            balances_only=True,
            timeout=settings.simplefin_timeout_seconds,
            verify_tls=settings.simplefin_verify_tls,
        )
    except SimpleFINFetchError as e:
        # Connection stored but fetch failed: still return connection_id, empty accounts, sanitized errors
        errors = _sanitize_errors(e.errors) if e.errors else [e.args[0] if e.args else "Failed to fetch accounts."]
        if e.status_code == 403:
            errors = ["Your SimpleFIN connection may have been disabled. If you revoked the token at the Bridge, create a new one and reconnect."]
        return ClaimResponse(
            connection_id=record.id,
            accounts=[],
            errors=errors,
        )

    accounts = [
        AccountSummary(
            id=a.id,
            name=a.name or "",
            currency=a.currency or "",
            org_name=a.org.name if (a.org and a.org.name) else None,
        )
        for a in account_set.accounts
    ]
    return ClaimResponse(
        connection_id=record.id,
        accounts=accounts,
        errors=_sanitize_errors(account_set.errors),
    )
