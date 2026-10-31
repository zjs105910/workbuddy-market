from datetime import date
from decimal import Decimal

from ledger.models import DiscountCode


def test_flat_invoice_has_one_plan_line(billing):
    invoice = billing.generate_invoice("s1")

    assert [item.kind for item in invoice.line_items] == ["plan"]
    assert invoice.total_cents == 3000


def test_invoice_is_saved(billing, store):
    invoice = billing.generate_invoice("s1")

    assert store.get_invoice(invoice.invoice_id) == invoice


def test_period_advances_by_the_same_length(billing, store):
    billing.generate_invoice("s1")

    subscription = store.get_subscription("s1")
    assert subscription.period_start == date(2026, 1, 31)
    assert subscription.period_end == date(2026, 3, 2)


def test_discount_credit_and_tax_order(billing, store):
    store.add_discount_code(DiscountCode(code="TEN", percent_off=Decimal("10")))
    customer = store.get_customer("c1")
    customer.tax_rate_percent = Decimal("10")
    customer.credit_balance_cents = 500

    invoice = billing.generate_invoice("s1", discount_code="TEN")

    assert [(item.kind, item.amount_cents) for item in invoice.line_items] == [
        ("plan", 3000),
        ("discount", -300),
        ("credit", -500),
        ("tax", 220),
    ]
    assert invoice.total_cents == 2420
    assert customer.credit_balance_cents == 0


def test_credit_larger_than_invoice_leaves_a_balance(billing, store):
    customer = store.get_customer("c1")
    customer.credit_balance_cents = 5000

    invoice = billing.generate_invoice("s1")

    assert invoice.total_cents == 0
    assert customer.credit_balance_cents == 2000
