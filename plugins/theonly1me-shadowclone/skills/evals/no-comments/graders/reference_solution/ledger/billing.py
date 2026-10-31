from datetime import date

from ledger.charges import attribute_usage, build_segments, overage_line, plan_line
from ledger.invoices import build_invoice
from ledger.models import Invoice, PlanChange, UsageEvent
from ledger.storage import InMemoryStore


class BillingService:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def record_usage(
        self, subscription_id: str, event_id: str, units: int, occurred_on: date
    ) -> bool:
        subscription = self._store.get_subscription(subscription_id)
        if units <= 0:
            raise ValueError("units must be positive")
        if any(event.event_id == event_id for event in subscription.usage_events):
            return False
        subscription.usage_events.append(UsageEvent(event_id, units, occurred_on))
        return True

    def change_plan(self, subscription_id: str, new_plan_id: str, effective_on: date) -> None:
        subscription = self._store.get_subscription(subscription_id)
        self._store.get_plan(new_plan_id)
        current_plan_id = (
            subscription.plan_changes[-1].plan_id
            if subscription.plan_changes
            else subscription.plan_id
        )
        previous_boundary = (
            subscription.plan_changes[-1].effective_on
            if subscription.plan_changes
            else subscription.period_start
        )
        if not previous_boundary < effective_on < subscription.period_end:
            raise ValueError("effective_on is outside the open segment")
        if new_plan_id == current_plan_id:
            raise ValueError("plan is already current")
        subscription.plan_changes.append(PlanChange(new_plan_id, effective_on))

    def generate_invoice(
        self, subscription_id: str, discount_code: str | None = None
    ) -> Invoice:
        subscription = self._store.get_subscription(subscription_id)
        customer = self._store.get_customer(subscription.customer_id)
        discount = self._store.get_discount_code(discount_code) if discount_code else None

        segments = build_segments(self._store, subscription)
        billable = [
            event
            for event in subscription.usage_events
            if not event.billed and event.occurred_on < subscription.period_end
        ]
        attribute_usage(segments, billable)
        period_days = (subscription.period_end - subscription.period_start).days
        charge_lines = [plan_line(segment, period_days) for segment in segments]
        overage_lines = [overage_line(segment, period_days) for segment in segments]
        charge_lines += [line for line in overage_lines if line]

        invoice = build_invoice(
            self._store.next_invoice_id(), subscription, charge_lines, customer, discount
        )

        credit_spent = sum(
            -item.amount_cents for item in invoice.line_items if item.kind == "credit"
        )
        customer.credit_balance_cents -= credit_spent

        for event in billable:
            event.billed = True
        subscription.plan_id = segments[-1].plan.plan_id
        subscription.plan_changes = []
        length = subscription.period_end - subscription.period_start
        subscription.period_start = subscription.period_end
        subscription.period_end = subscription.period_end + length

        self._store.save_invoice(invoice)
        return invoice
