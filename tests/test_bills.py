"""Reproduce real SC 1 Rate I bills from the published statements. Needs private files (bills/,
usage.csv, LDS_APPND.csv); skipped when they are absent, e.g. on a fresh public clone."""
import datetime as dt
import unittest
from pathlib import Path

from conedrates.bills import load_bills, scale_usage_to_kwh
from conedrates.engine import Period, price_period
from conedrates.loaders import load_msc, load_tariff, load_usage
from conedrates.statements import load_statements

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = [ROOT / "bills" / "bills.csv", ROOT / "usage.csv", ROOT / "LDS_APPND.csv"]


class PeriodConvention(unittest.TestCase):
    def test_from_bill(self):
        p = Period.from_bill(dt.date(2026, 2, 9), dt.date(2026, 3, 11))
        self.assertEqual((p.start, p.end), (dt.date(2026, 2, 10), dt.date(2026, 3, 12)))
        self.assertEqual((p.end - p.start).days, 30)            # days printed on the bill
        self.assertEqual((p.msc_start, p.msc_end), (dt.date(2026, 2, 9), dt.date(2026, 3, 12)))


@unittest.skipUnless(all(p.exists() for p in PRIVATE), "private bill/usage/MSC files not present")
class BillReproduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bills = load_bills(ROOT / "bills" / "bills.csv")
        cls.usage = load_usage(ROOT / "usage.csv")
        cls.msc = load_msc(ROOT / "LDS_APPND.csv")
        cls.tariff = load_tariff(ROOT / "data" / "tariff.toml")
        cls.st = load_statements(ROOT / "data" / "statements.toml")

    def price(self, frm, to, kwh):
        period = Period.from_bill(frm, to)
        u = scale_usage_to_kwh(self.usage, period, kwh) if kwh else self.usage
        return price_period(u, period, self.tariff, self.msc, self.st)

    @staticmethod
    def lines(plan):
        """Group a plan's items into the lines printed on a Con Ed bill."""
        out = dict(basic=0.0, delivery=0.0, sbc=0.0, supply=0.0, mfc=0.0, grt=0.0, tax=0.0)
        for i in plan["items"]:
            c, a = i["component"].split("] ")[-1], i["amount"]
            if c in ("customer_charge", "billing_payment_processing"):
                out["basic"] += a
            elif c.startswith("sbc."):
                out["sbc"] += a
            elif c == "adder.mfc":
                out["mfc"] += a
            elif c.startswith("supply.") or c in ("adder.afmsc", "adder.cess"):
                out["supply"] += a
            elif c.startswith("tax.grt"):
                out["grt"] += a
            elif c == "tax.sales_tax":
                out["tax"] += a
            else:
                out["delivery"] += a
        return out

    def test_every_line_of_every_bill(self):
        want = dict(basic="basic", delivery="delivery_amt", sbc="sbc_amt", supply="supply_amt", mfc="mfc")
        for _, b in self.bills.iterrows():
            r = self.price(b["from"].date(), b["to"].date(), b.kwh)["plans"]["sc1_rate1"]
            got = self.lines(r)
            with self.subTest(bill=f"{b['from']:%Y-%m-%d}"):
                for k, col in want.items():
                    self.assertAlmostEqual(got[k], b[col], delta=0.03, msg=k)
                self.assertAlmostEqual(got["grt"], b.d_grt + b.s_grt, delta=0.03, msg="grt")
                self.assertAlmostEqual(got["tax"], b.d_tax + b.s_tax, delta=0.03, msg="sales tax")
                self.assertAlmostEqual(r["total"], b.total, delta=0.06, msg="total")

    def test_unscaled_interval_data_within_two_percent(self):
        for _, b in self.bills.iterrows():
            with self.subTest(bill=f"{b['from']:%Y-%m-%d}"):
                r = self.price(b["from"].date(), b["to"].date(), None)
                self.assertAlmostEqual(r["diagnostics"]["total_kwh"], b.kwh, delta=4)
                self.assertLess(abs(r["plans"]["sc1_rate1"]["total"] - b.total) / b.total, 0.02)

    def test_missing_march_bill_predicted_from_statements_alone(self):
        # Mar 11 - Apr 9 bill could not be downloaded. Its kWh = Apr bill's prior read 15867 minus the
        # Mar bill's new read 15664; its total $97.66 is from the Apr bill's "previous charges" summary.
        r = self.price(dt.date(2026, 3, 11), dt.date(2026, 4, 9), 203)["plans"]["sc1_rate1"]
        self.assertAlmostEqual(r["total"], 97.66, delta=0.50)


if __name__ == "__main__":
    unittest.main()
