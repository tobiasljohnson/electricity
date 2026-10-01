"""Command line: python -m conedrates --usage usage.csv --msc LDS_APPND.csv"""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path

from .engine import PLAN_NAMES, PLANS, calendar_months, run
from .loaders import load_msc, load_tariff, load_usage

ROOT = Path(__file__).resolve().parent.parent


def read_bills(path):
    """CSV with columns from,to (YYYY-MM-DD); `to` is exclusive (TO - FROM = days)."""
    with open(path, newline="") as f:
        return [(dt.date.fromisoformat(r["from"]), dt.date.fromisoformat(r["to"])) for r in csv.DictReader(f)]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--usage", default=ROOT / "usage.csv")
    p.add_argument("--msc", default=ROOT / "LDS_APPND.csv")
    p.add_argument("--tariff", default=ROOT / "data" / "tariff.toml")
    p.add_argument("--zone", default="J")
    p.add_argument("--tension", default="low", choices=["low", "high"])
    p.add_argument("--bills", help="CSV of actual bill periods (columns: from,to)")
    p.add_argument("--common-kwh", type=float, default=0.0, help="common per-kWh charges, $/kWh")
    p.add_argument("--grt", type=float, default=0.0, help="gross receipts tax, percent")
    p.add_argument("--out", help="write full itemized JSON here")
    a = p.parse_args(argv)

    usage = load_usage(a.usage)
    msc = load_msc(a.msc, a.zone, a.tension)
    tariff = load_tariff(a.tariff)
    if a.bills:
        periods = read_bills(a.bills)
    else:
        periods = calendar_months(usage.kwh.index.min().date(), usage.kwh.index.max().date())
    res = run(usage, periods, tariff, msc, a.common_kwh, a.grt)

    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2, default=str))
    print(f"interval: {usage.interval_minutes} min; zone {a.zone} {a.tension} tension")
    print(f"{'period':<23}{'kWh':>8}" + "".join(f"{PLAN_NAMES[k]:>16}" for k in PLANS) + "  notes")
    for r in res:
        if "skipped" in r:
            print(f"{r['start']}..{r['end']:<10}  skipped: {r['skipped']}")
            continue
        d = r["diagnostics"]
        notes = "; ".join(d["warnings"] + [w for pl in r["plans"].values() for w in pl["warnings"]])
        print(f"{d['start']}..{d['end']:<10}{d['total_kwh']:>8.1f}"
              + "".join(f"{r['plans'][k]['total']:>16.2f}" for k in PLANS) + f"  {notes}")
    return 0
