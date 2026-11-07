from decimal import Decimal

from ledger.discounts import compute_discount_cents
from ledger.models import DiscountCode


def test_no_code_gives_no_discount():
    assert compute_discount_cents(1000, None) == 0


def test_percent_discount():
    code = DiscountCode(code="TEN", percent_off=Decimal("10"))
    assert compute_discount_cents(3250, code) == 325


def test_percent_discount_rounds_half_up():
    code = DiscountCode(code="HALF", percent_off=Decimal("12.5"))
    assert compute_discount_cents(1004, code) == 126


def test_fixed_discount_is_capped_at_subtotal():
    code = DiscountCode(code="BIG", amount_off_cents=9000)
    assert compute_discount_cents(3000, code) == 3000
