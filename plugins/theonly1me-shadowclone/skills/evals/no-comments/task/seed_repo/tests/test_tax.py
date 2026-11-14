from decimal import Decimal

from ledger.tax import compute_tax_cents


def test_tax_rounds_half_up():
    assert compute_tax_cents(2425, Decimal("10")) == 243


def test_zero_rate_gives_no_tax():
    assert compute_tax_cents(5000, Decimal("0")) == 0


def test_nothing_taxable_gives_no_tax():
    assert compute_tax_cents(0, Decimal("20")) == 0
