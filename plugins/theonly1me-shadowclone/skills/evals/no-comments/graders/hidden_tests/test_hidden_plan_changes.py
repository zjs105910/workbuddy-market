from datetime import date

import pytest

from hidden_helpers import amounts, kinds


def plan_lines(invoice):
    return [(item.description, item.amount_cents) for item in invoice.line_items if item.kind == "plan"]


def test_mid_cycle_change_prorates_both_plans(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    invoice = billing.generate_invoice("s1")
    assert plan_lines(invoice) == [("Plan: Basic", 1000), ("Plan: Pro", 6000)]
    assert invoice.total_cents == 7000


def test_proration_rounds_each_segment_half_up(long_period_store, billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "plan") == [968, 6097]


def test_exact_half_cent_rounds_up(billing, store):
    store.get_subscription("s1").plan_id = "odd"
    billing.change_plan("s1", "flat", date(2026, 1, 16))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "plan") == [501, 1000]


def test_several_changes_in_one_period(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.change_plan("s1", "basic", date(2026, 1, 21))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "plan") == [1000, 3000, 1000]
    assert invoice.total_cents == 5000


def test_change_recorded_after_the_usage_events(billing):
    billing.record_usage("s1", "e1", 120, date(2026, 1, 5))
    billing.record_usage("s1", "e2", 500, date(2026, 1, 20))
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [435, 702]
    assert invoice.total_cents == 8137


def test_usage_is_attributed_by_occurrence_date_not_record_time(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.record_usage("s1", "e1", 120, date(2026, 1, 5))
    billing.record_usage("s1", "e2", 500, date(2026, 1, 20))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [435, 702]


def test_overage_descriptions_name_the_plan(billing):
    billing.record_usage("s1", "e1", 120, date(2026, 1, 5))
    billing.record_usage("s1", "e2", 500, date(2026, 1, 20))
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    invoice = billing.generate_invoice("s1")
    descriptions = [item.description for item in invoice.line_items if item.kind == "overage"]
    assert descriptions == ["Overage: Basic", "Overage: Pro"]


def test_included_units_are_floored_per_segment(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.record_usage("s1", "e1", 34, date(2026, 1, 5))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [5]


def test_segment_without_overage_has_no_overage_line(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.record_usage("s1", "e1", 500, date(2026, 1, 20))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [702]


def test_plan_lines_come_before_overage_lines(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.record_usage("s1", "e1", 120, date(2026, 1, 5))
    billing.record_usage("s1", "e2", 500, date(2026, 1, 20))
    assert kinds(billing.generate_invoice("s1")) == ["plan", "plan", "overage", "overage"]


def test_plan_after_invoice_is_the_last_plan(billing, store):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.generate_invoice("s1")
    subscription = store.get_subscription("s1")
    assert subscription.plan_id == "pro"
    assert subscription.period_start == date(2026, 1, 31)
    assert subscription.period_end == date(2026, 3, 2)


def test_next_invoice_has_a_single_segment_on_the_new_plan(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    billing.generate_invoice("s1")
    second = billing.generate_invoice("s1")
    assert amounts(second, "plan") == [9000]


def test_late_event_goes_to_first_segment_plan_rates(billing):
    billing.generate_invoice("s1")
    billing.change_plan("s1", "pro", date(2026, 2, 10))
    billing.record_usage("s1", "late", 300, date(2026, 1, 20))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "plan") == [1000, 6000]
    assert amounts(invoice, "overage") == [1335]


@pytest.mark.parametrize(
    "effective_on",
    [date(2026, 1, 1), date(2025, 12, 20), date(2026, 1, 31), date(2026, 3, 1)],
)
def test_effective_date_must_be_strictly_inside_the_period(billing, effective_on):
    with pytest.raises(ValueError):
        billing.change_plan("s1", "pro", effective_on)


def test_change_must_be_after_the_previous_change(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    with pytest.raises(ValueError):
        billing.change_plan("s1", "basic", date(2026, 1, 5))


def test_change_on_the_same_day_as_the_previous_change_is_rejected(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    with pytest.raises(ValueError):
        billing.change_plan("s1", "basic", date(2026, 1, 11))


def test_changing_to_the_current_plan_is_rejected(billing):
    with pytest.raises(ValueError):
        billing.change_plan("s1", "basic", date(2026, 1, 11))


def test_changing_to_the_plan_from_the_last_change_is_rejected(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    with pytest.raises(ValueError):
        billing.change_plan("s1", "pro", date(2026, 1, 21))


def test_unknown_plan_raises_key_error(billing):
    with pytest.raises(KeyError):
        billing.change_plan("s1", "missing", date(2026, 1, 11))


def test_unknown_subscription_raises_key_error(billing):
    with pytest.raises(KeyError):
        billing.change_plan("missing", "pro", date(2026, 1, 11))


def test_rejected_change_leaves_state_unchanged(billing):
    billing.change_plan("s1", "pro", date(2026, 1, 11))
    with pytest.raises(ValueError):
        billing.change_plan("s1", "basic", date(2026, 1, 11))
    with pytest.raises(KeyError):
        billing.change_plan("s1", "missing", date(2026, 1, 21))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "plan") == [1000, 6000]
