You are working in the `ledger` Python package in the current directory. It is a small subscription billing library. All money is integer cents. Read the code first, then implement the feature below.

# Feature: usage-based billing with mid-cycle plan changes

## Public API (hidden tests call exactly this)

- `ledger.models.Plan` gains two keyword fields with default `0`: `included_units: int` and `overage_unit_price_cents: int`.
- `BillingService.record_usage(subscription_id, event_id, units, occurred_on) -> bool`
- `BillingService.change_plan(subscription_id, new_plan_id, effective_on) -> None`
- `BillingService.generate_invoice(subscription_id, discount_code=None) -> Invoice` keeps its signature and now bills usage and plan changes.
- Keep `ledger.models`, `ledger.storage.InMemoryStore` and `ledger.billing.BillingService` at their current import paths. You may add modules and fields.

## Rules

Billing periods are half-open: `[period_start, period_end)`. `period_days = (period_end - period_start).days`.

### Usage events

1. `record_usage` stores one usage event. `units` must be greater than 0, otherwise raise `ValueError`. An unknown subscription raises `KeyError`.
2. Events are idempotent per subscription by `event_id`. If the `event_id` was already recorded for that subscription, ignore the new call completely (even if `units` or `occurred_on` differ) and return `False`. Otherwise record it and return `True`.
3. An event is billed on the next invoice generated for the subscription whose `period_end` is later than the event's `occurred_on`, and it is billed only once. So an event with `occurred_on >= period_end` of the open period is not billed yet. An event with `occurred_on < period_start` (a late event for a closed period) is billed on the invoice for the currently open period.

### Plan changes

4. `change_plan` switches the subscription to `new_plan_id` from `effective_on` onward within the open period. The old plan applies on days `[segment_start, effective_on)` and the new plan on `[effective_on, ...)`.
5. Several changes may happen in one period. Each `effective_on` must be strictly after `period_start`, strictly before `period_end`, and strictly after the previous change in this period. Otherwise raise `ValueError`. Changing to the plan that is already current raises `ValueError`. An unknown plan raises `KeyError`. A rejected change must leave all state unchanged.
6. The period is split into segments by the changes. `segment_days` is the number of days in a segment.

### Invoice

7. For each segment in chronological order, add a line item `kind="plan"`, `description="Plan: <plan name>"`, with `amount_cents = round_half_up_cents(Decimal(monthly_price_cents) * segment_days / period_days)`. Use the existing `round_half_up_cents`. A period with no change has one segment and bills the full price.
8. Each usage event is attributed to the segment that contains its `occurred_on`. Late events (`occurred_on < period_start`) are attributed to the first segment.
9. For each segment, `included = floor(plan.included_units * segment_days / period_days)` using integer floor division. `overage_units = max(0, segment_units - included)`. If `overage_units > 0`, add a line item `kind="overage"`, `description="Overage: <plan name>"`, `amount_cents = overage_units * plan.overage_unit_price_cents`. Overage lines come after all plan lines, in chronological order.
10. `subtotal = sum of plan and overage lines`. After the overage lines, add these lines in this order, each only when its amount is not 0: `discount` (negative, from the existing `compute_discount_cents` on the subtotal), `credit` (negative, the customer's credit balance capped at the amount left after the discount), `tax` (from the existing `compute_tax_cents` on the amount left after discount and credit).
11. `total_cents` is the sum of all line items. The customer's `credit_balance_cents` drops by the credit used. The invoice is saved in the store, as today.
12. After the invoice: the subscription's `plan_id` becomes the plan in effect at the end of the period, its recorded plan changes are cleared, and the period advances by the same length as today.

# Also do

- Keep all existing tests passing.
- Add tests for the new behavior.
- Run the test suite before you finish.
