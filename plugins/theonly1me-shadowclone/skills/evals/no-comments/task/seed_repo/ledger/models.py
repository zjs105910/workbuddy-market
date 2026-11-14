from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Plan:
    plan_id: str
    name: str
    monthly_price_cents: int


@dataclass
class Customer:
    customer_id: str
    tax_rate_percent: Decimal = Decimal("0")
    credit_balance_cents: int = 0


@dataclass
class Subscription:
    subscription_id: str
    customer_id: str
    plan_id: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class DiscountCode:
    code: str
    percent_off: Decimal | None = None
    amount_off_cents: int | None = None


@dataclass(frozen=True)
class LineItem:
    kind: str
    description: str
    amount_cents: int


@dataclass
class Invoice:
    invoice_id: str
    subscription_id: str
    period_start: date
    period_end: date
    line_items: list[LineItem] = field(default_factory=list)
    total_cents: int = 0
