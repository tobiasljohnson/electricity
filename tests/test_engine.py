import datetime as dt
import unittest
from pathlib import Path

import pandas as pd

from conedrates.calendar import classify, holidays
from conedrates.demand import billable_demand
from conedrates.engine import price_period
from conedrates.loaders import Usage, load_msc, load_tariff, select_msc

ROOT = Path(__file__).resolve().parent.parent
D = dt.date


def usage_from(index, values):
    return Usage(pd.Series(values, index=index), 15, 0, 0)


def month_grid(y, m):
    s = pd.Timestamp(y, m, 1)
    e = s + pd.offsets.MonthBegin(1)
    return s, e, pd.date_range(s, e, freq="15min", inclusive="left")


def demand(kwh, s, e):
    return billable_demand(kwh, lambda i: classify(i).demand_period.values, 15, s, e)


class Holidays(unittest.TestCase):
    def test_2026(self):
        h = holidays(2026)
        self.assertIn(D(2026, 5, 25), h)
        self.assertIn(D(2026, 9, 7), h)
        self.assertIn(D(2026, 11, 26), h)
        self.assertEqual(len(h), 6)


class Demand(unittest.TestCase):
    def test_constant_load(self):
        s, e, g = month_grid(2026, 7)
        d = demand(pd.Series(0.25, index=g), s, e)
        self.assertAlmostEqual(d["on"]["kw"], 1.0)
        self.assertAlmostEqual(d["off"]["kw"], 1.0)

    def test_weekday_spike(self):
        s, e, g = month_grid(2026, 7)
        k = pd.Series(0.25, index=g)
        k[(g >= "2026-07-15 12:00") & (g < "2026-07-15 14:00")] = 1.25   # 5 kW
        self.assertAlmostEqual(demand(k, s, e)["on"]["kw"], 7 / 3)

    def test_saturday_spike_is_off_peak(self):
        s, e, g = month_grid(2026, 7)
        k = pd.Series(0.25, index=g)
        k[(g >= "2026-07-11 15:00") & (g < "2026-07-11 17:00")] = 1.25
        d = demand(k, s, e)
        self.assertAlmostEqual(d["off"]["kw"], 7 / 3)
        self.assertAlmostEqual(d["on"]["kw"], 1.0)

    def test_july_4_weekday(self):
        idx = pd.DatetimeIndex(["2025-07-04 15:00"])        # a Friday
        c = classify(idx).iloc[0]
        self.assertEqual(c.demand_period, "off")
        self.assertEqual(c.r3_msc, "super")
        self.assertEqual(c.r3_delivery, "on")

    def test_missing_interval_breaks_window(self):
        s, e, g = month_grid(2026, 7)
        k = pd.Series(0.25, index=g)
        k[(g >= "2026-07-15 12:00") & (g < "2026-07-15 13:00")] = 1.25   # 5 kW for one hour
        self.assertAlmostEqual(demand(k, s, e)["on"]["kw"], 7 / 3)
        # dropping 12:30 invalidates every window that contained the full spike hour;
        # the best remaining is 12:45-13:30 = 1.25 + 3 x 0.25 = 2.0 kW
        k = k.drop(pd.Timestamp("2026-07-15 12:30"))
        self.assertAlmostEqual(demand(k, s, e)["on"]["kw"], (2.0 + 1 + 1) / 3)


@unittest.skipUnless((ROOT / "LDS_APPND.csv").exists(), "raw MSC file not present")
class Msc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.msc = load_msc(ROOT / "LDS_APPND.csv", "J", "low")

    def test_july_2026(self):
        s, e = D(2026, 7, 1), D(2026, 8, 1)
        r1 = select_msc(self.msc, "RATE1", s, e)
        r3 = select_msc(self.msc, "001VTO", s, e)
        r4 = select_msc(self.msc, "001IPP", s, e)
        self.assertAlmostEqual(r1["all"], 0.144326)
        self.assertEqual((r3["all"], r3["on"], r3["off"]), (0.897796, 0.084043, 0.065453))
        self.assertEqual((r4["on"], r4["off"]), (0.353062, 0.074175))

    def test_super_peak_presence(self):
        m = self.msc[self.msc.code == "001VTO"]
        a = m[(m.start == D(2026, 4, 30)) & (m.end == D(2026, 5, 31))]
        b = m[(m.start == D(2026, 4, 30)) & (m.end == D(2026, 6, 1))]
        self.assertEqual(a["all"].iloc[0], 0)
        self.assertAlmostEqual(b["all"].iloc[0], 0.878514)

    def test_no_duplicates_no_long_cycles(self):
        self.assertFalse(self.msc.duplicated().any())
        self.assertTrue(((self.msc.end - self.msc.start).map(lambda x: x.days) <= 35).all())


@unittest.skipUnless((ROOT / "LDS_APPND.csv").exists(), "raw MSC file not present")
class BillReproduction(unittest.TestCase):
    def test_rate1_aug_sep_bill(self):
        s, e = D(2026, 8, 7), D(2026, 9, 8)
        g = pd.date_range(s, e, freq="15min", inclusive="left")
        u = usage_from(g, 308 / len(g))
        msc = load_msc(ROOT / "LDS_APPND.csv")
        r = price_period(u, (s, e), load_tariff(ROOT / "data" / "tariff.toml"), msc)
        items = {i["component"].split("] ")[-1]: i for i in r["plans"]["sc1_rate1"]["items"]}
        self.assertAlmostEqual(items["customer_charge"]["amount"], 22.40)
        self.assertAlmostEqual(items["billing_payment_processing"]["amount"], 1.80)
        self.assertAlmostEqual(items["customer_charge"]["amount"] + 1.80, 24.20)
        delivery = items["delivery.summer_first_tier"]["amount"] + items["delivery.summer_over_tier"]["amount"]
        self.assertAlmostEqual(delivery, 51.53, places=2)


if __name__ == "__main__":
    unittest.main()
