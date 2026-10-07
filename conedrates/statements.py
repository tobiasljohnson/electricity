"""Con Edison statements: per-kWh adders, SBC and tax percentages, each with an effective date.

`data/statements.toml` holds the series. This module answers one question: what value of a
series applies to a given billing period, and which statements did it come from.
"""
import datetime as dt
import tomllib
from dataclasses import dataclass

from .loaders import TariffNotInEffect

ONE_DAY = dt.timedelta(days=1)


class StatementNotInEffect(TariffNotInEffect):
    """No statement of a series covers some day of the period."""


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    rule: str              # "to_date" or "day_weighted"
    scope: tuple           # plan keys, or ("all",)
    group: str             # "delivery" or "supply" ("" for tax percentages)
    unit: str
    entries: tuple         # ((effective date, value, statement number), ...) sorted by date

    def applies_to(self, plan):
        return "all" in self.scope or plan in self.scope

    def on(self, day):
        """(value, stmt) in effect on `day`: the latest entry whose effective date is <= day."""
        best = None
        for e in self.entries:
            if e[0] <= day:
                best = e
        if best is None:
            raise StatementNotInEffect(f"{self.key}: no statement in effect on {day}")
        return best[1], best[2]


class Statements:
    def __init__(self, meta, series):
        self.meta = meta
        self.series = series

    @property
    def sales_tax_pct(self):
        return self.meta["sales_tax_pct"]

    @property
    def as_of(self):
        return self.meta["as_of"]

    def keys(self, plan, group):
        """Series keys of `group` that apply to `plan`, in file order."""
        return [k for k, s in self.series.items() if s.group == group and s.applies_to(plan)]

    def value(self, key, period):
        """Value of series `key` for `period` (a Period: usage window [start, end), TO date = end - 1).

        Returns (value, sorted statement numbers used)."""
        s = self.series[key]
        if s.rule == "to_date":
            v, n = s.on(period.end - ONE_DAY)
            return v, [n]
        if s.rule == "day_weighted":
            days = (period.end - period.start).days
            vals = [s.on(period.start + i * ONE_DAY) for i in range(days)]
            return sum(v for v, _ in vals) / days, sorted({n for _, n in vals})
        raise ValueError(f"{key}: unknown rule {s.rule!r}")


def load_statements(path):
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    series = {}
    for key, s in raw["series"].items():
        scope = tuple(x.strip() for x in s.get("scope", "all").split(","))
        entries = tuple(sorted(((e["effective"], e["value"], e["stmt"]) for e in s["entries"]), key=lambda e: e[0]))
        series[key] = Series(key, s["name"], s["rule"], scope, s.get("group", ""), s.get("unit", "$/kWh"), entries)
    return Statements(raw["meta"], series)
