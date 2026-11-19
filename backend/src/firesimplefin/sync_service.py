"""Sync: chunked SimpleFIN fetch → StatementTransaction list (60-day limit, dedupe)."""

from datetime import date, datetime, timedelta, timezone

from firesimplefin.model.api import StatementTransaction
from firesimplefin.simplefin_client import fetch_accounts
from firesimplefin.simplefin_mapper import account_set_to_statement_list

DAYS_PER_CHUNK = 60


def _date_to_ts(d: date, end_of_day: bool = False) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())


def fetch_statement_transactions(
    access_url: str,
    start_date: date,
    end_date: date,
    simplefin_account_id: str | None = None,
    *,
    timeout: float = 30.0,
    verify_tls: bool = True,
) -> list[StatementTransaction]:
    """
    Fetch SimpleFIN data in 60-day chunks and return deduplicated StatementTransaction list.
    Respects 60-day limit per request; dedupes by SimpleFIN transaction id.
    """
    if start_date > end_date:
        return []
    seen_ids: set[str] = set()
    result: list[StatementTransaction] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=DAYS_PER_CHUNK - 1), end_date)
        start_ts = _date_to_ts(current)
        end_ts = _date_to_ts(chunk_end, end_of_day=True)

        account_ids = [simplefin_account_id] if simplefin_account_id else None
        account_set = fetch_accounts(
            access_url,
            start_date=start_ts,
            end_date=end_ts,
            account_ids=account_ids,
            timeout=timeout,
            verify_tls=verify_tls,
        )
        for tx_id, st in account_set_to_statement_list(account_set, simplefin_account_id):
            if tx_id not in seen_ids:
                seen_ids.add(tx_id)
                result.append(st)
        current = chunk_end + timedelta(days=1)
    result.sort(key=lambda s: s.date)
    return result
