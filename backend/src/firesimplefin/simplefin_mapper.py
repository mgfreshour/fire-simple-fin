"""Map SimpleFIN data to StatementTransaction (PRD §4.1)."""

from datetime import datetime, timezone
from decimal import Decimal

from firesimplefin.model.api import StatementTransaction
from firesimplefin.simplefin_models import SimpleFINAccountSet, SimpleFINTransaction


def simplefin_transaction_to_statement(t: SimpleFINTransaction) -> StatementTransaction:
    """Map one SimpleFIN transaction to StatementTransaction."""
    amount = Decimal(t.amount)
    notes = t.description.strip() or None
    if t.extra and isinstance(t.extra, dict):
        extra_notes = t.extra.get("notes") or t.extra.get("memo")
        if extra_notes:
            notes = f"{t.description}; {extra_notes}" if t.description else str(extra_notes)
    foreign_amount = None
    foreign_currency_code = None
    if t.extra and isinstance(t.extra, dict):
        foreign_amount = t.extra.get("foreign_amount")
        foreign_currency_code = t.extra.get("foreign_currency_code")
        if foreign_amount is not None:
            foreign_amount = Decimal(str(foreign_amount))
    return StatementTransaction(
        name=t.description or "",
        date=datetime.fromtimestamp(t.posted, tz=timezone.utc),
        amount=amount,
        foreign_amount=foreign_amount,
        foreign_currency_code=foreign_currency_code,
        notes=notes,
        fee=None,
    )


def account_set_to_statement_list(
    account_set: SimpleFINAccountSet,
    simplefin_account_id: str | None = None,
) -> list[tuple[str, StatementTransaction]]:
    """
    Map SimpleFIN account set to (transaction_id, StatementTransaction) list.
    If simplefin_account_id is set, only include transactions from that account.
    Transaction id is used for deduplication across chunked fetches.
    """
    result: list[tuple[str, StatementTransaction]] = []
    for account in account_set.accounts:
        if simplefin_account_id is not None and account.id != simplefin_account_id:
            continue
        for t in account.transactions:
            result.append((t.id, simplefin_transaction_to_statement(t)))
    return result
