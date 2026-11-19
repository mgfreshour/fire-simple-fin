"""Firefly III HTTP client (adapted from Firemerge). Get transactions, currencies, account."""

import logging
from datetime import date
from itertools import count
from time import monotonic
from typing import AsyncIterable, Optional
from uuid import uuid4

import httpx
from httpx import HTTPStatusError

from firesimplefin.model.common import Account, AccountType, Currency
from firesimplefin.model.firefly import Transaction
from firesimplefin.util import async_collect

logger = logging.getLogger("firesimplefin.firefly")

TIMEOUT = 300


class FireflyClient:
    """Firefly III API client: Bearer auth, get transactions/currencies/account."""

    def __init__(self, base_url: str, token: str, client: httpx.AsyncClient):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client

    async def _request(
        self,
        path: str,
        params: Optional[dict] = None,
        method: str = "GET",
        json: Optional[dict] = None,
    ) -> httpx.Response:
        headers = {
            "accept": "application/json",
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
            "X-Trace-Id": str(uuid4()),
        }
        url = f"{self.base_url}/api/{path}"
        started_at = monotonic()
        resp = await self._client.request(
            method, url, headers=headers, params=params, json=json
        )
        if not resp.is_success:
            raise HTTPStatusError(request=resp.request, response=resp, message=resp.text)
        logger.debug("Firefly %s in %.2fs", path, monotonic() - started_at)
        return resp

    async def _json_request(
        self,
        path: str,
        params: Optional[dict] = None,
        method: str = "GET",
        json: Optional[dict] = None,
    ) -> dict:
        resp = await self._request(path, params, method, json)
        return resp.json()

    async def _paging_get(
        self, path: str, params: Optional[dict] = None
    ) -> AsyncIterable[dict]:
        params = params or {}
        page = 1
        for _ in count(1):
            resp = await self._json_request(path, {**params, "page": page})
            for row in resp["data"]:
                yield row
            if resp["meta"]["pagination"]["total_pages"] <= page:
                break
            page += 1

    @async_collect
    async def get_transactions(
        self, account_id: int, start: date, end: date
    ) -> AsyncIterable[Transaction]:
        """Get transactions for an account in date range (Firefly III v1 API)."""
        async for row in self._paging_get(
            f"v1/accounts/{account_id}/transactions",
            {
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
                "limit": 2000,
            },
        ):
            for trans in row["attributes"]["transactions"]:
                yield Transaction.model_validate({**trans, "id": row["id"]})

    @async_collect
    async def get_accounts(self) -> AsyncIterable[Account]:
        """Get all Firefly accounts (for link dropdown). Paginated; type inferred from attributes."""
        async for row in self._paging_get("v1/accounts", {"limit": 500}):
            attrs = row["attributes"]
            type_str = attrs.get("type", "asset")
            try:
                account_type = AccountType(type_str)
            except ValueError:
                account_type = AccountType.Asset
            yield Account(
                id=row["id"],
                type=account_type,
                currency_id=attrs.get("currency_id"),
                name=attrs.get("name", ""),
                iban=attrs.get("iban"),
                current_balance=None,
            )

    @async_collect
    async def get_currencies(self) -> AsyncIterable[Currency]:
        """Get all currencies (for resolving code → currency_id)."""
        async for row in self._paging_get("v1/currencies"):
            yield Currency.model_validate({**row["attributes"], "id": row["id"]})

    async def store_transaction(self, transaction: Transaction) -> Transaction:
        """Create or update a transaction in Firefly III (POST or PUT)."""
        data = transaction.model_dump(mode="json", exclude_none=True)
        if transaction.id is None:
            data.pop("id", None)
        if transaction.id is None:
            resp = await self._json_request(
                "v1/transactions",
                method="POST",
                json={"transactions": [data]},
            )
        else:
            resp = await self._json_request(
                f"v1/transactions/{transaction.id}",
                method="PUT",
                json={"transactions": [data]},
            )
        resp_transactions = resp["data"]["attributes"]["transactions"]
        if len(resp_transactions) != 1:
            raise RuntimeError(f"Expected 1 transaction, got {len(resp_transactions)}")
        attrs = resp_transactions[0]
        return Transaction.model_validate(
            {**attrs, "id": resp["data"]["id"]}
        )

    async def get_account(self, account_id: int) -> Account:
        """Get single account (for currency_id and name)."""
        resp = await self._json_request(f"v1/accounts/{account_id}")
        attrs = resp["data"]["attributes"]
        # Firefly returns type as string; map to AccountType
        type_str = attrs.get("type", "asset")
        try:
            account_type = AccountType(type_str)
        except ValueError:
            account_type = AccountType.Asset
        return Account(
            id=resp["data"]["id"],
            type=account_type,
            currency_id=attrs.get("currency_id"),
            name=attrs.get("name", ""),
            iban=attrs.get("iban"),
            current_balance=None,
        )
