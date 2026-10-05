"""Real bills: load them, and derive the common-charge factors they imply.

A bill's line items split into tariff + MSC (which the engine prices) and
everything else (delivery adjustments, System Benefit Charge, MSC adjustment,
Merchant Function Charge, GRT, sales tax). `derive_common` measures the
"everything else" per bill so the engine can reproduce it.
"""
import pandas as pd

from .engine import Period, price_period
from .loaders import COMMON_FIELDS, Usage

SALES_TAX_PCT = 4.5   # NYC local sales tax, applied to everything on the bill incl. GRT


def load_bills(path):
    """bills.csv with the line items transcribed from each bill (see bills/ README in SPEC)."""
    return pd.read_csv(path, parse_dates=["from", "to"])


def scale_usage_to_kwh(usage, period, target_kwh):
    """Copy of `usage` with the period's intervals scaled so they total `target_kwh`.

    Interval data and billed kWh differ by a few kWh (rounding, estimated reads);
    scaling lets a bill be reproduced to the cent without changing load shape."""
    k = usage.kwh.copy()
    sel = (k.index >= pd.Timestamp(period.start)) & (k.index < pd.Timestamp(period.end))
    k[sel] *= target_kwh / k[sel].sum()
    return Usage(k, usage.interval_minutes, usage.n_estimated, usage.n_duplicate_starts)


def derive_common(bill, usage, tariff, msc):
    """Common-charge factors implied by one bill row (SC 1 Rate I)."""
    period = Period.from_bill(bill["from"].date(), bill["to"].date())
    u = scale_usage_to_kwh(usage, period, bill.kwh)
    items = price_period(u, period, tariff, msc)["plans"]["sc1_rate1"]["items"]
    eng = lambda key: sum(i["amount"] for i in items if key in i["component"])
    kwh = bill.kwh
    return {
        "from": bill["from"].date(),
        "to": bill["to"].date(),
        "delivery_adj_c": round((bill.delivery_amt - eng("delivery.")) / kwh * 100, 3),
        "sbc_c": bill.sbc_rate_c,
        "supply_adj_c": round((bill.supply_amt - eng("supply.")) / kwh * 100, 3),
        "mfc_c": round(bill.mfc / kwh * 100, 3),
        "grt_delivery_pct": round(bill.d_grt / (bill.basic + bill.delivery_amt + bill.sbc_amt) * 100, 3),
        "grt_supply_pct": round(bill.s_grt / (bill.supply_amt + bill.mfc) * 100, 3),
    }


def derive_all(bills, usage, tariff, msc):
    periods = [derive_common(r, usage, tariff, msc) for _, r in bills.iterrows()]
    default = {f: round(sum(p[f] for p in periods) / len(periods), 3) for f in COMMON_FIELDS}
    return {"global": {"sales_tax_pct": SALES_TAX_PCT}, "default": default, "period": periods}


def to_toml(common):
    """Minimal TOML writer for the common-charges structure."""
    lines = [
        "# Factors that sit on top of tariff delivery and MSC supply, measured from real",
        "# SC 1 Rate I bills by scripts/derive_common_charges.py. Re-run it after adding bills.",
        "# *_c = cents per kWh; *_pct = percent. [default] is a plain average of the periods,",
        "# used only where no bill is within 15 days -- treat those months as estimates.",
        "# ASSUMPTION: the same per-kWh values apply to all four plans (SPEC: unverified).",
        "",
        "[global]",
        f"sales_tax_pct = {common['global']['sales_tax_pct']}",
        "",
        "[default]",
        *[f"{f} = {v}" for f, v in common["default"].items()],
    ]
    for p in common["period"]:
        lines += ["", "[[period]]", f"from = {p['from']}", f"to = {p['to']}",
                  *[f"{f} = {p[f]}" for f in COMMON_FIELDS]]
    return "\n".join(lines) + "\n"
