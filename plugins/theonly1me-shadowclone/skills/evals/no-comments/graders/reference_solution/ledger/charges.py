from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger.models import LineItem, Plan, Subscription, UsageEvent
from ledger.money import round_half_up_cents
from ledger.storage import InMemoryStore


@dataclass
class Segment:
    plan: Plan
    start: date
    end: date
    units: int = 0

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def build_segments(store: InMemoryStore, subscription: Subscription) -> list[Segment]:
    plan_ids = [subscription.plan_id] + [change.plan_id for change in subscription.plan_changes]
    starts = [subscription.period_start] + [
        change.effective_on for change in subscription.plan_changes
    ]
    ends = starts[1:] + [subscription.period_end]
    return [
        Segment(store.get_plan(plan_id), start, end)
        for plan_id, start, end in zip(plan_ids, starts, ends)
    ]


def attribute_usage(segments: list[Segment], events: list[UsageEvent]) -> None:
    for event in events:
        target = segments[0]
        for segment in segments:
            if segment.start <= event.occurred_on < segment.end:
                target = segment
        target.units += event.units


def plan_line(segment: Segment, period_days: int) -> LineItem:
    amount = round_half_up_cents(
        Decimal(segment.plan.monthly_price_cents) * segment.days / period_days
    )
    return LineItem("plan", f"Plan: {segment.plan.name}", amount)


def overage_line(segment: Segment, period_days: int) -> LineItem | None:
    included = segment.plan.included_units * segment.days // period_days
    overage_units = max(0, segment.units - included)
    if not overage_units:
        return None
    amount = overage_units * segment.plan.overage_unit_price_cents
    return LineItem("overage", f"Overage: {segment.plan.name}", amount)
