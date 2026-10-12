"""Tax engine. Rules are data with effective dates, never hard-coded rates.

All amounts are integer LKR cents. Each rule's total is computed exactly and rounded
once (half up), so the result does not depend on how many lines the order has.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Line:
    amount: int
    tax_category: str


@dataclass(frozen=True)
class Rule:
    code: str
    name: dict[str, str]
    rate_bp: int
    applies_to: Sequence[str]
    compound: bool
    sequence: int
    effective_from: datetime
    effective_to: datetime | None = None

    def is_effective(self, at: datetime) -> bool:
        return self.effective_from <= at and (self.effective_to is None or at < self.effective_to)

    def applies(self, category: str) -> bool:
        return "*" in self.applies_to or category in self.applies_to


@dataclass(frozen=True)
class TaxLine:
    code: str
    name: dict[str, str]
    rate_bp: int
    base: int
    amount: int


@dataclass(frozen=True)
class Totals:
    subtotal: int
    tax_lines: list[TaxLine]
    tax_total: int
    total: int


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def calculate(lines: Sequence[Line], rules: Sequence[Rule], at: datetime) -> Totals:
    subtotal = sum(line.amount for line in lines)
    active = sorted((r for r in rules if r.is_effective(at)), key=lambda r: (r.sequence, r.code))
    prior = [Decimal(0)] * len(lines)  # exact charges already applied to each line
    tax_lines: list[TaxLine] = []

    for rule in active:
        rate = Decimal(rule.rate_bp) / Decimal(10_000)
        base = Decimal(0)
        exact = Decimal(0)
        for i, line in enumerate(lines):
            if not rule.applies(line.tax_category):
                continue
            line_base = Decimal(line.amount) + (prior[i] if rule.compound else 0)
            charge = line_base * rate
            base += line_base
            exact += charge
            prior[i] += charge
        if base == 0:
            continue
        tax_lines.append(TaxLine(rule.code, rule.name, rule.rate_bp, base=_round(base), amount=_round(exact)))

    tax_total = sum(t.amount for t in tax_lines)
    return Totals(subtotal, tax_lines, tax_total, subtotal + tax_total)
