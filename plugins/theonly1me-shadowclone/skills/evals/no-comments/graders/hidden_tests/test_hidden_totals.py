from datetime import date
from decimal import Decimal

from hidden_helpers import amounts, kinds


def seed_usage(billing):
    billing.record_usage("s1", "e1", 150, date(2026, 1, 5))


def test_percent_discount_applies_to_plan_and_overage(billing):
    seed_usage(billing)
    invoice = billing.generate_invoice("s1", discount_code="TEN")
    assert amounts(invoice, "discount") == [-325]
    assert invoice.total_cents == 2925


def test_discount_credit_tax_order_and_rounding(billing, store):
    customer = store.get_customer("c1")
    customer.tax_rate_percent = Decimal("10")
    customer.credit_balance_cents = 500
    seed_usage(billing)
    invoice = billing.generate_invoice("s1", discount_code="TEN")
    assert kinds(invoice) == ["plan", "overage", "discount", "credit", "tax"]
    assert amounts(invoice, "credit") == [-500]
    assert amounts(invoice, "tax") == [243]
    assert invoice.total_cents == 2668
    assert customer.credit_balance_cents == 0


def test_credit_larger_than_amount_leaves_a_balance(billing, store):
    customer = store.get_customer("c1")
    customer.credit_balance_cents = 5000
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "credit") == [-3000]
    assert kinds(invoice) == ["plan", "credit"]
    assert invoice.total_cents == 0
    assert customer.credit_balance_cents == 2000


def test_credit_covers_overage_too(billing, store):
    customer = store.get_customer("c1")
    customer.credit_balance_cents = 3100
    seed_usage(billing)
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "credit") == [-3100]
    assert invoice.total_cents == 150
    assert customer.credit_balance_cents == 0


def test_fixed_discount_is_capped_at_the_subtotal(billing):
    invoice = billing.generate_invoice("s1", discount_code="BIG")
    assert amounts(invoice, "discount") == [-3000]
    assert invoice.total_cents == 0


def test_zero_value_lines_are_omitted(billing):
    invoice = billing.generate_invoice("s1")
    assert kinds(invoice) == ["plan"]


def test_total_is_the_sum_of_lines(billing, store):
    store.get_customer("c1").tax_rate_percent = Decimal("7.5")
    store.get_customer("c1").credit_balance_cents = 123
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.record_usage("s1", "e1", 120, date(2026, 1, 5))
    billing.record_usage("s1", "e2", 500, date(2026, 1, 20))
    invoice = billing.generate_invoice("s1", discount_code="TEN")
    assert invoice.total_cents == sum(item.amount_cents for item in invoice.line_items)


def test_invoice_is_saved_with_usage_lines(billing, store):
    seed_usage(billing)
    invoice = billing.generate_invoice("s1")
    assert store.get_invoice(invoice.invoice_id) == invoice


def test_credit_is_spent_on_the_first_invoice_only(billing, store):
    customer = store.get_customer("c1")
    customer.credit_balance_cents = 1000
    billing.generate_invoice("s1")
    second = billing.generate_invoice("s1")
    assert kinds(second) == ["plan"]
    assert second.total_cents == 3000


def test_prorated_invoice_with_discount_and_tax(billing, store):
    store.get_customer("c1").tax_rate_percent = Decimal("20")
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    invoice = billing.generate_invoice("s1", discount_code="TEN")
    assert amounts(invoice, "discount") == [-700]
    assert amounts(invoice, "tax") == [1260]
    assert invoice.total_cents == 7560
