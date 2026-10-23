from decimal import Decimal

from ledger.money import round_half_up_cents


def test_exact_half_rounds_up():
    assert round_half_up_cents(Decimal("500.5")) == 501


def test_below_half_rounds_down():
    assert round_half_up_cents(Decimal("500.49")) == 500


def test_whole_value_is_unchanged():
    assert round_half_up_cents(Decimal("1200")) == 1200
