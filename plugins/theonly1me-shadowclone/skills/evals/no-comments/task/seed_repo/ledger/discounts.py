from decimal import Decimal

from ledger.models import DiscountCode
from ledger.money import round_half_up_cents


def compute_discount_cents(subtotal_cents: int, code: DiscountCode | None) -> int:
    if code is None or subtotal_cents <= 0:
        return 0
    if code.percent_off is not None:
        raw = Decimal(subtotal_cents) * code.percent_off / Decimal(100)
        return min(round_half_up_cents(raw), subtotal_cents)
    if code.amount_off_cents is not None:
        return min(code.amount_off_cents, subtotal_cents)
    return 0
