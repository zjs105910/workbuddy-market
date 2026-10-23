from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Plan:
    plan_id: str
    name: str
    monthly_price_cents: int
    included_units: int = 0
    overage_unit_price_cents: int = 0


@dataclass
class Customer:
    customer_id: str
    tax_rate_percent: Decimal = Decimal("0")
    credit_balance_cents: int = 0


@dataclass
class UsageEvent:
    event_id: str
    units: int
    occurred_on: date
    billed: bool = False


@dataclass(frozen=True)
class PlanChange:
    plan_id: str
    effective_on: date


@dataclass
class Subscription:
    subscription_id: str
    customer_id: str
    plan_id: str
    period_start: date
    period_end: date
    usage_events: list[UsageEvent] = field(default_factory=list)
    plan_changes: list[PlanChange] = field(default_factory=list)


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
