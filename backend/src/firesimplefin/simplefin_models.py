"""Internal types for SimpleFIN protocol (PRD §3.2)."""

from pydantic import BaseModel, Field


class SimpleFINOrg(BaseModel):
    """Organization from SimpleFIN account set."""

    domain: str | None = None
    name: str | None = None
    sfin_url: str | None = Field(None, alias="sfin-url")

    model_config = {"populate_by_name": True}


class SimpleFINTransaction(BaseModel):
    """Single transaction from SimpleFIN."""

    id: str
    posted: int  # Unix timestamp
    amount: str  # positive = deposit, negative = withdrawal
    description: str = ""
    transacted_at: int | None = None
    pending: bool = False
    extra: dict[str, object] = Field(default_factory=dict)


class SimpleFINAccount(BaseModel):
    """Single account from SimpleFIN account set."""

    id: str
    name: str = ""
    currency: str = ""
    org: SimpleFINOrg | None = None
    balance: str | None = None
    available_balance: str | None = Field(None, alias="available-balance")
    balance_date: int | None = Field(None, alias="balance-date")
    transactions: list[SimpleFINTransaction] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class SimpleFINAccountSet(BaseModel):
    """Response from GET .../accounts (PRD §3.2)."""

    accounts: list[SimpleFINAccount] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
