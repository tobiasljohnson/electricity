"""Statement lookup rules and the statement-priced engine, on public data only."""
import datetime as dt
import unittest
from pathlib import Path

import pandas as pd

from conedrates.engine import Period, price_period
from conedrates.loaders import TariffNotInEffect, Usage, load_tariff
from conedrates.statements import StatementNotInEffect, load_statements

ROOT = Path(__file__).resolve().parent.parent
D = dt.date


class Lookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = load_statements(ROOT / "data" / "statements.toml")

    def test_to_date_rule_uses_the_bills_to_date(self):
        # Aug 7 - Sep 8 bill: statement #179 (eff Aug 13) is in force on Sep 8; #180 starts Sep 14.
        v, used = self.st.value("afmsc", Period.from_bill(D(2026, 8, 7), D(2026, 9, 8)))
        self.assertEqual((v, used), (-0.005885, [179]))

    def test_to_date_rule_calendar_month_uses_last_day(self):
        v, used = self.st.value("afmsc", Period.calendar_month(D(2026, 9, 1), D(2026, 10, 1)))
        self.assertEqual((v, used), (-0.026229, [180]))          # Sep 30 is after the Sep 14 statement

    def test_day_weighted_blends_statements_by_days(self):
        # Jul 9 - Aug 7 bill: usage days Jul 10..Aug 7 = 29 days: 22 under RDM #37, 7 under #38.
        p = Period.from_bill(D(2026, 7, 9), D(2026, 8, 7))
        v, used = self.st.value("rdm", p)
        self.assertAlmostEqual(v, (22 * 0.00738 + 7 * -0.00815) / 29, places=9)
        self.assertEqual(used, [37, 38])
        v, used = self.st.value("mac", p)
        self.assertAlmostEqual(v, (22 * 0.00040 + 7 * 0.00236) / 29, places=9)

    def test_uncovered_day_raises(self):
        with self.assertRaises(StatementNotInEffect):
            self.st.value("afmsc", Period.from_bill(D(2026, 1, 12), D(2026, 2, 10)))   # first AF-MSC is Feb 13
        self.assertTrue(issubclass(StatementNotInEffect, TariffNotInEffect))           # run() skips such periods

    def test_scope_separates_demand_and_energy_plans(self):
        self.assertIn("sbc_company_kwh", self.st.keys("sc1_rate1", "delivery"))
        self.assertNotIn("sbc_company_kw", self.st.keys("sc1_rate1", "delivery"))
        self.assertIn("sbc_company_kw", self.st.keys("riderz_rate1", "delivery"))
        self.assertNotIn("sbc_company_kwh", self.st.keys("sc1_rate4", "delivery"))


class SyntheticEngine(unittest.TestCase):
    """Constant 0.25 kWh per 15 minutes = 1 kW all month, so demand and kWh are hand-checkable."""

    @classmethod
    def setUpClass(cls):
        cls.st = load_statements(ROOT / "data" / "statements.toml")
        cls.tariff = load_tariff(ROOT / "data" / "tariff.toml")
        s, e = D(2026, 7, 1), D(2026, 8, 1)
        idx = pd.date_range(s, e, freq="15min", inclusive="left")
        cls.usage = Usage(pd.Series(0.25, index=idx), 15, 0, 0)
        row = lambda code, a, on, off: dict(code=code, start=s, end=D(2026, 7, 31), all=a, on=on, off=off)
        cls.msc = pd.DataFrame([row("RATE1", 0.14, 0, 0), row("001VTO", 0.9, 0.08, 0.06), row("001IPP", 0.08, 0.35, 0.07)])
        cls.period = Period.calendar_month(s, e)

    def price(self, **kw):
        return price_period(self.usage, self.period, self.tariff, self.msc, self.st, **kw)

    def items(self, res, plan):
        return {i["component"].split("] ")[-1]: i for i in res["plans"][plan]["items"]}

    def test_sbc_structure_differs_by_plan(self):
        r = self.price()
        i1, i4 = self.items(r, "sc1_rate1"), self.items(r, "sc1_rate4")
        self.assertAlmostEqual(i1["sbc.sbc_company_kwh"]["amount"], 744 * 0.0039)
        self.assertNotIn("sbc.sbc_company_kw", i1)
        self.assertAlmostEqual(i4["sbc.sbc_company_kw"]["quantity"], 1.0)      # 1 kW in every window
        self.assertAlmostEqual(i4["sbc.sbc_company_kw"]["amount"], 0.85)
        self.assertNotIn("sbc.sbc_company_kwh", i4)
        self.assertAlmostEqual(i1["sbc.sbc_nyserda"]["amount"], i4["sbc.sbc_nyserda"]["amount"])

    def test_sbc_demand_basis_is_flagged_and_changes_only_demand_plans(self):
        a, b = self.price(sbc_demand_basis="max_billable"), self.price(sbc_demand_basis="sum_billable")
        self.assertAlmostEqual(self.items(b, "sc1_rate4")["sbc.sbc_company_kw"]["quantity"], 2.0)
        self.assertEqual(a["plans"]["sc1_rate1"]["total"], b["plans"]["sc1_rate1"]["total"])
        self.assertTrue(any("monthly maximum demand" in w for w in a["diagnostics"]["warnings"]))

    def test_taxes_follow_bill_structure(self):
        for plan in ("sc1_rate1", "sc1_rate3", "sc1_rate4", "riderz_rate1"):
            with self.subTest(plan=plan):
                items = self.items(self.price(), plan)
                pre = sum(i["amount"] for n, i in items.items() if not n.startswith("tax."))
                grt = items["tax.grt_delivery"]["amount"] + items["tax.grt_supply"]["amount"]
                self.assertAlmostEqual(items["tax.sales_tax"]["amount"], 0.045 * (pre + grt))
                sup = sum(i["amount"] for i in items.values() if i["group"] == "supply" and not i["component"].startswith("tax."))
                self.assertAlmostEqual(items["tax.grt_supply"]["amount"], 0.024066 * sup)

    def test_statements_used_are_reported(self):
        used = self.price()["diagnostics"]["statements_used"]
        self.assertEqual(used["afmsc"], [178])          # July 31 is after Jul 15, before Aug 13
        self.assertEqual(used["rdm"], [37])

    def test_without_statements_matches_tariff_plus_msc_only(self):
        r = price_period(self.usage, self.period, self.tariff, self.msc)
        self.assertFalse(any(i["component"].startswith(("adder.", "sbc.", "tax.")) for i in r["plans"]["sc1_rate1"]["items"]))


if __name__ == "__main__":
    unittest.main()
