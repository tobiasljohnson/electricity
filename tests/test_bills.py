"""Reproduce real SC 1 Rate I bills. Needs private files (bills/, usage.csv,
LDS_APPND.csv); skipped when they are absent, e.g. on a fresh public clone."""
import datetime as dt
import unittest
from pathlib import Path

from conedrates.bills import load_bills, scale_usage_to_kwh
from conedrates.engine import Period, price_period
from conedrates.loaders import load_common, load_msc, load_tariff, load_usage, select_common

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = [ROOT / "bills" / "bills.csv", ROOT / "usage.csv", ROOT / "LDS_APPND.csv"]


class PeriodConvention(unittest.TestCase):
    def test_from_bill(self):
        p = Period.from_bill(dt.date(2026, 2, 9), dt.date(2026, 3, 11))
        self.assertEqual((p.start, p.end), (dt.date(2026, 2, 10), dt.date(2026, 3, 12)))
        self.assertEqual((p.end - p.start).days, 30)            # days printed on the bill
        self.assertEqual((p.msc_start, p.msc_end), (dt.date(2026, 2, 9), dt.date(2026, 3, 12)))

    def test_common_nearest_period_and_default(self):
        c = load_common(ROOT / "data" / "common_charges.toml")
        near, est = select_common(c, dt.date(2026, 7, 1), dt.date(2026, 8, 1))
        self.assertFalse(est)
        self.assertEqual(near["from"], dt.date(2026, 7, 9))
        far, est = select_common(c, dt.date(2026, 3, 1), dt.date(2026, 4, 1))   # March: no bill
        self.assertTrue(est)


@unittest.skipUnless(all(p.exists() for p in PRIVATE), "private bill/usage/MSC files not present")
class BillReproduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bills = load_bills(ROOT / "bills" / "bills.csv")
        cls.usage = load_usage(ROOT / "usage.csv")
        cls.msc = load_msc(ROOT / "LDS_APPND.csv")
        cls.tariff = load_tariff(ROOT / "data" / "tariff.toml")
        cls.common = load_common(ROOT / "data" / "common_charges.toml")

    def price(self, bill, scaled):
        period = Period.from_bill(bill["from"].date(), bill["to"].date())
        u = scale_usage_to_kwh(self.usage, period, bill.kwh) if scaled else self.usage
        r = price_period(u, period, self.tariff, self.msc, self.common)
        return r, r["plans"]["sc1_rate1"]

    def test_total_and_components_to_the_cent(self):
        for _, b in self.bills.iterrows():
            with self.subTest(bill=f"{b['from']:%Y-%m-%d}"):
                _, plan = self.price(b, scaled=True)
                it = {}
                for i in plan["items"]:   # segments (season/rate changes) repeat a component: sum them
                    name = i["component"].split("] ")[-1]
                    it[name] = it.get(name, 0) + i["amount"]
                basic = it["customer_charge"] + it["billing_payment_processing"]
                self.assertAlmostEqual(basic, b.basic, places=2)
                self.assertAlmostEqual(it["tax.grt_delivery"] + it["tax.grt_supply"], b.d_grt + b.s_grt, delta=0.06)
                self.assertAlmostEqual(it["tax.sales_tax"], b.d_tax + b.s_tax, delta=0.06)
                self.assertAlmostEqual(plan["total"], b.total, delta=0.10)

    def test_unscaled_interval_data_within_two_percent(self):
        for _, b in self.bills.iterrows():
            with self.subTest(bill=f"{b['from']:%Y-%m-%d}"):
                r, plan = self.price(b, scaled=False)
                self.assertAlmostEqual(r["diagnostics"]["total_kwh"], b.kwh, delta=4)
                self.assertLess(abs(plan["total"] - b.total) / b.total, 0.02)

    def test_sum_of_six_bills(self):
        total = sum(self.price(b, scaled=False)[1]["total"] for _, b in self.bills.iterrows())
        self.assertAlmostEqual(total, self.bills.total.sum(), delta=0.01 * self.bills.total.sum())


if __name__ == "__main__":
    unittest.main()
