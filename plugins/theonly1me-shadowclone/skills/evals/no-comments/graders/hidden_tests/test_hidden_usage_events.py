from datetime import date

import pytest

from hidden_helpers import amounts, kinds


def test_first_event_is_recorded(billing):
    assert billing.record_usage("s1", "e1", 10, date(2026, 1, 5)) is True


def test_duplicate_event_id_returns_false(billing):
    billing.record_usage("s1", "e1", 10, date(2026, 1, 5))
    assert billing.record_usage("s1", "e1", 10, date(2026, 1, 5)) is False


def test_duplicate_event_with_different_units_is_ignored(billing):
    billing.record_usage("s1", "e1", 150, date(2026, 1, 5))
    billing.record_usage("s1", "e1", 9000, date(2026, 1, 6))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [250]


def test_same_event_id_on_another_subscription_is_independent(billing, store):
    from ledger.models import Subscription

    store.add_subscription(
        Subscription("s2", "c1", "basic", date(2026, 1, 1), date(2026, 1, 31))
    )
    assert billing.record_usage("s1", "e1", 5, date(2026, 1, 5)) is True
    assert billing.record_usage("s2", "e1", 5, date(2026, 1, 5)) is True


def test_duplicate_event_after_it_was_billed_is_still_ignored(billing):
    billing.record_usage("s1", "e1", 150, date(2026, 1, 5))
    billing.generate_invoice("s1")
    assert billing.record_usage("s1", "e1", 150, date(2026, 1, 5)) is False
    second = billing.generate_invoice("s1")
    assert kinds(second) == ["plan"]


@pytest.mark.parametrize("units", [0, -3])
def test_non_positive_units_raise_value_error(billing, units):
    with pytest.raises(ValueError):
        billing.record_usage("s1", "e1", units, date(2026, 1, 5))


def test_unknown_subscription_raises_key_error(billing):
    with pytest.raises(KeyError):
        billing.record_usage("missing", "e1", 5, date(2026, 1, 5))


def test_usage_within_allowance_has_no_overage_line(billing):
    billing.record_usage("s1", "e1", 100, date(2026, 1, 5))
    invoice = billing.generate_invoice("s1")
    assert kinds(invoice) == ["plan"]
    assert invoice.total_cents == 3000


def test_units_across_events_add_up(billing):
    billing.record_usage("s1", "e1", 60, date(2026, 1, 5))
    billing.record_usage("s1", "e2", 90, date(2026, 1, 20))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [250]
    assert invoice.total_cents == 3250


def test_event_on_period_start_is_billed_now(billing):
    billing.record_usage("s1", "e1", 101, date(2026, 1, 1))
    assert amounts(billing.generate_invoice("s1"), "overage") == [5]


def test_event_on_period_end_belongs_to_the_next_period(billing):
    billing.record_usage("s1", "e1", 150, date(2026, 1, 31))
    first = billing.generate_invoice("s1")
    assert kinds(first) == ["plan"]
    second = billing.generate_invoice("s1")
    assert amounts(second, "overage") == [250]


def test_future_event_is_billed_only_once(billing):
    billing.record_usage("s1", "e1", 150, date(2026, 2, 10))
    assert kinds(billing.generate_invoice("s1")) == ["plan"]
    assert amounts(billing.generate_invoice("s1"), "overage") == [250]
    assert kinds(billing.generate_invoice("s1")) == ["plan"]


def test_late_event_is_billed_on_the_open_period(billing):
    billing.generate_invoice("s1")
    assert billing.record_usage("s1", "late", 150, date(2026, 1, 20)) is True
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [250]
    assert invoice.period_start == date(2026, 1, 31)


def test_late_event_is_attributed_to_the_first_segment(billing):
    billing.generate_invoice("s1")
    billing.change_plan("s1", "pro", date(2026, 2, 10))
    billing.record_usage("s1", "late", 300, date(2026, 1, 20))
    invoice = billing.generate_invoice("s1")
    assert amounts(invoice, "overage") == [1335]


def test_billed_events_are_not_billed_again(billing):
    billing.record_usage("s1", "e1", 150, date(2026, 1, 5))
    billing.generate_invoice("s1")
    assert kinds(billing.generate_invoice("s1")) == ["plan"]
