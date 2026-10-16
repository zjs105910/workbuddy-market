from decimal import Decimal

from ledger.money import round_half_up_cents


def compute_tax_cents(taxable_cents: int, rate_percent: Decimal) -> int:
    if taxable_cents <= 0:
        return 0
    return round_half_up_cents(Decimal(taxable_cents) * rate_percent / Decimal(100))
