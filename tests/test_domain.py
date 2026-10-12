from datetime import UTC, datetime

import pytest

from kiosk.domain import tax
from kiosk.domain.menu import in_windows
from kiosk.domain.orders import Status, TransitionError, all_items_done, check_transition

T0 = datetime(2024, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 6, 1, tzinfo=UTC)

SC = tax.Rule("SC", {"en": "Service"}, 1000, ["*"], compound=False, sequence=1, effective_from=T0)
VAT = tax.Rule("VAT", {"en": "VAT"}, 1800, ["*"], compound=True, sequence=2, effective_from=T0)


def test_service_charge_then_compound_vat() -> None:
    result = tax.calculate([tax.Line(100_000, "food")], [VAT, SC], NOW)
    # 1000.00 + 10% SC = 100.00, VAT 18% on 1100.00 = 198.00
    assert [(t.code, t.amount) for t in result.tax_lines] == [("SC", 10_000), ("VAT", 19_800)]
    assert result.total == 129_800


def test_rule_only_applies_to_its_categories() -> None:
    bev_only = tax.Rule("BEV", {"en": "Bev levy"}, 500, ["beverage"], False, 1, T0)
    result = tax.calculate([tax.Line(10_000, "food"), tax.Line(4_000, "beverage")], [bev_only], NOW)
    assert result.tax_lines[0].base == 4_000
    assert result.tax_total == 200


def test_effective_dates() -> None:
    old = tax.Rule(
        "VAT", {"en": "VAT"}, 1500, ["*"], False, 1, T0, effective_to=datetime(2025, 1, 1, tzinfo=UTC)
    )
    new = tax.Rule("VAT", {"en": "VAT"}, 1800, ["*"], False, 1, datetime(2025, 1, 1, tzinfo=UTC))
    line = [tax.Line(10_000, "food")]
    assert tax.calculate(line, [old, new], datetime(2024, 6, 1, tzinfo=UTC)).tax_total == 1_500
    assert tax.calculate(line, [old, new], NOW).tax_total == 1_800


def test_rounding_is_per_rule_not_per_line() -> None:
    rule = tax.Rule("X", {"en": "X"}, 1000, ["*"], False, 1, T0)
    # three lines of 0.05 -> exact 0.015 total -> 2 cents (per-line rounding would give 3)
    result = tax.calculate([tax.Line(5, "food")] * 3, [rule], NOW)
    assert result.tax_total == 2


def test_transitions() -> None:
    check_transition(Status.PLACED, Status.IN_KITCHEN)
    with pytest.raises(TransitionError):
        check_transition(Status.PLACED, Status.COMPLETED)
    with pytest.raises(TransitionError):
        check_transition(Status.COMPLETED, Status.VOIDED)


def test_all_items_done_ignores_voided() -> None:
    assert all_items_done(["done", "voided"])
    assert not all_items_done(["done", "queued"])
    assert not all_items_done(["voided"])


def test_time_windows() -> None:
    breakfast = [{"days": [0, 1, 2, 3, 4], "start": "06:00", "end": "11:00"}]
    monday_8 = datetime(2026, 9, 28, 8, 0)
    assert in_windows(breakfast, monday_8)
    assert not in_windows(breakfast, monday_8.replace(hour=12))
    assert not in_windows(breakfast, datetime(2026, 9, 27, 8, 0))  # Sunday
    late = [{"days": [4], "start": "22:00", "end": "02:00"}]  # Friday night
    assert in_windows(late, datetime(2026, 10, 2, 23, 0))
    assert in_windows(late, datetime(2026, 10, 3, 1, 0))  # Saturday 01:00 counts for Friday
    assert not in_windows(late, datetime(2026, 10, 4, 1, 0))
    assert in_windows([], monday_8)
