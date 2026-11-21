from datetime import date
from decimal import Decimal

import pytest

from ledger.billing import BillingService
from ledger.models import Customer, Plan, Subscription
from ledger.storage import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    store = InMemoryStore()
    store.add_plan(Plan(plan_id="basic", name="Basic", monthly_price_cents=3000))
    store.add_customer(Customer(customer_id="c1", tax_rate_percent=Decimal("0")))
    store.add_subscription(
        Subscription(
            subscription_id="s1",
            customer_id="c1",
            plan_id="basic",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
    )
    return store


@pytest.fixture
def billing(store: InMemoryStore) -> BillingService:
    return BillingService(store)
