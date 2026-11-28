from datetime import date
from decimal import Decimal

import pytest

from ledger.billing import BillingService
from ledger.models import Customer, DiscountCode, Plan, Subscription
from ledger.storage import InMemoryStore


@pytest.fixture
def store():
    store = InMemoryStore()
    store.add_plan(Plan(plan_id="basic", name="Basic", monthly_price_cents=3000, included_units=100, overage_unit_price_cents=5))
    store.add_plan(Plan(plan_id="pro", name="Pro", monthly_price_cents=9000, included_units=400, overage_unit_price_cents=3))
    store.add_plan(Plan(plan_id="odd", name="Odd", monthly_price_cents=1001))
    store.add_plan(Plan(plan_id="flat", name="Flat", monthly_price_cents=2000))
    store.add_customer(Customer(customer_id="c1"))
    store.add_subscription(
        Subscription(
            subscription_id="s1",
            customer_id="c1",
            plan_id="basic",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
    )
    store.add_discount_code(DiscountCode(code="TEN", percent_off=Decimal("10")))
    store.add_discount_code(DiscountCode(code="BIG", amount_off_cents=99999))
    return store


@pytest.fixture
def billing(store):
    return BillingService(store)


@pytest.fixture
def long_period_store(store):
    subscription = store.get_subscription("s1")
    subscription.period_end = date(2026, 2, 1)
    return store

