from decimal import ROUND_HALF_UP, Decimal


def round_half_up_cents(value: Decimal) -> int:
    # Billing rounds exact halves up, never to even.
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
