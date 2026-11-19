"""Tests for SimpleFIN → StatementTransaction mapping."""

from datetime import datetime, timezone
from decimal import Decimal

from firesimplefin.simplefin_mapper import (
    account_set_to_statement_list,
    simplefin_transaction_to_statement,
)
from firesimplefin.simplefin_models import SimpleFINAccount, SimpleFINAccountSet, SimpleFINTransaction


def test_simplefin_transaction_to_statement() -> None:
    t = SimpleFINTransaction(
        id="tx1",
        posted=1704067200,  # 2024-01-01 00:00 UTC
        amount="-50.25",
        description="Coffee Shop",
        transacted_at=1704067200,
        pending=False,
        extra={},
    )
    st = simplefin_transaction_to_statement(t)
    assert st.name == "Coffee Shop"
    assert st.amount == Decimal("-50.25")
    assert st.date == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert st.foreign_amount is None
    assert st.foreign_currency_code is None


def test_simplefin_transaction_with_extra() -> None:
    t = SimpleFINTransaction(
        id="tx2",
        posted=1704153600,
        amount="100.00",
        description="Deposit",
        extra={"foreign_amount": "85.50", "foreign_currency_code": "EUR"},
    )
    st = simplefin_transaction_to_statement(t)
    assert st.amount == Decimal("100.00")
    assert st.foreign_amount == Decimal("85.50")
    assert st.foreign_currency_code == "EUR"


def test_account_set_to_statement_list() -> None:
    account_set = SimpleFINAccountSet(
        accounts=[
            SimpleFINAccount(
                id="acc1",
                name="Checking",
                currency="USD",
                transactions=[
                    SimpleFINTransaction(
                        id="t1",
                        posted=1704067200,
                        amount="-10.00",
                        description="Payee",
                    ),
                ],
            ),
            SimpleFINAccount(
                id="acc2",
                name="Savings",
                currency="USD",
                transactions=[
                    SimpleFINTransaction(
                        id="t2",
                        posted=1704153600,
                        amount="50.00",
                        description="Transfer",
                    ),
                ],
            ),
        ],
        errors=[],
    )
    all_pairs = account_set_to_statement_list(account_set)
    assert len(all_pairs) == 2
    ids = [tid for tid, _ in all_pairs]
    assert "t1" in ids
    assert "t2" in ids

    one_account = account_set_to_statement_list(account_set, simplefin_account_id="acc1")
    assert len(one_account) == 1
    assert one_account[0][0] == "t1"
    assert one_account[0][1].name == "Payee"
