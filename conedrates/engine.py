"""Pricing engine: itemized cost of a usage record under each of the four plans."""
import datetime as dt

import pandas as pd

from .calendar import classify, is_summer
from .demand import billable_demand
from .loaders import TariffNotInEffect, effective_dates, select_msc, tariff_entry

PLANS = ("sc1_rate1", "sc1_rate3", "sc1_rate4", "riderz_rate1")
PLAN_NAMES = {
    "sc1_rate1": "SC 1 Rate I",
    "sc1_rate3": "SC 1 Rate III",
    "sc1_rate4": "SC 1 Rate IV",
    "riderz_rate1": "Rider Z Rate I",
}
PRORATION_DAYS = 30


def _item(component, quantity, unit, rate, amount=None):
    return {
        "component": component, "quantity": quantity, "unit": unit, "rate": rate,
        "amount": quantity * rate if amount is None else amount,
    }


def segments(start, end, plan_effective):
    """Split [start, end) by day at season boundaries and tariff effective dates."""
    cuts = {start, end}
    d = start
    while d < end:
        if d.day == 1 and d.month in (6, 10):
            cuts.add(d)
        d += dt.timedelta(days=1)
    cuts |= {e for e in plan_effective if start < e < end}
    pts = sorted(cuts)
    return list(zip(pts[:-1], pts[1:]))


def _kwh_by(df, mask_col_vals, s, e):
    """Total kWh for rows in [s, e) grouped by the given label series."""
    sel = (df.index >= pd.Timestamp(s)) & (df.index < pd.Timestamp(e))
    return df.loc[sel].groupby(mask_col_vals[sel]).kwh.sum()


def price_period(usage, start, end, tariff, msc, common_per_kwh=0.0, grt_pct=0.0):
    """Price [start, end) (dates, end exclusive) under all four plans."""
    ts, te = pd.Timestamp(start), pd.Timestamp(end)
    kwh = usage.kwh[(usage.kwh.index >= ts) & (usage.kwh.index < te)]
    cls = classify(kwh.index)
    df = pd.DataFrame({"kwh": kwh.values}, index=kwh.index).join(cls)
    df["season"] = ["summer" if is_summer(m) else "non" for m in df.index.month]
    total_kwh = float(kwh.sum())

    days = (end - start).days
    grid = pd.date_range(ts, te, freq=f"{usage.interval_minutes}min", inclusive="left")
    nonexistent = grid.tz_localize("America/New_York", ambiguous=True, nonexistent="NaT").isna().sum()
    expected = len(grid) - int(nonexistent)
    diag = {
        "start": start.isoformat(), "end": end.isoformat(), "days": days,
        "proration_factor": days / PRORATION_DAYS,
        "interval_minutes": usage.interval_minutes,
        "intervals_expected": expected, "intervals_present": len(kwh),
        "intervals_missing": expected - len(kwh),
        "estimated_intervals": usage.n_estimated,
        "partial_period": len(kwh) < expected,
        "total_kwh": total_kwh,
        "warnings": [],
    }
    if usage.interval_minutes != 15:
        diag["warnings"].append(
            f"interval is {usage.interval_minutes} min, not 15: 60-minute demand is computed from "
            f"{60 // usage.interval_minutes} interval(s)")
    if diag["partial_period"]:
        diag["warnings"].append(f"{diag['intervals_missing']} intervals missing")

    m1 = select_msc(msc, "RATE1", start, end)
    m3 = select_msc(msc, "001VTO", start, end)
    m4 = select_msc(msc, "001IPP", start, end)
    diag["msc_rows"] = {
        n: {"from": r.start.isoformat(), "to": r.end.isoformat()}
        for n, r in (("rate1", m1), ("rate3", m3), ("rate4", m4))
    }

    dem = billable_demand(
        usage.kwh, lambda idx: classify(idx).demand_period.values,
        usage.interval_minutes, ts, te)
    diag["demand"] = dem
    for k, v in dem.items():
        if v["low_data"]:
            diag["warnings"].append(f"only {v['days']} qualifying day(s) for {k}-peak demand")

    results = {}
    for plan in PLANS:
        items, warns = [], []
        segs = segments(start, end, effective_dates(tariff, plan))
        for s, e in segs:
            t = tariff_entry(tariff, plan, s)
            f = (e - s).days / PRORATION_DAYS
            summer = is_summer(s.month)
            season = "summer" if summer else "non-summer"
            tag = f"[{s}..{e}] "
            items.append(_item(tag + "customer_charge", f, "months", t["customer_charge"]))

            if plan == "sc1_rate1":
                seg_kwh = float(_kwh_by(df, df.season, s, e).sum())
                if summer:
                    tier = t["summer_tier_kwh"] * f
                    first = min(seg_kwh, tier)
                    items.append(_item(tag + "delivery.summer_first_tier", first, "kWh", t["summer_first"]))
                    items.append(_item(tag + "delivery.summer_over_tier", seg_kwh - first, "kWh", t["summer_over"]))
                else:
                    items.append(_item(tag + "delivery.non_summer", seg_kwh, "kWh", t["nonsummer"]))
            elif plan == "sc1_rate3":
                by = _kwh_by(df, df.r3_delivery, s, e)
                on_rate = t["onpeak_summer"] if summer else t["onpeak_nonsummer"]
                items.append(_item(tag + f"delivery.on_peak ({season})", float(by.get("on", 0)), "kWh", on_rate))
                items.append(_item(tag + "delivery.off_peak", float(by.get("off", 0)), "kWh", t["offpeak"]))
            else:
                on_rate = t["onpeak_kw_summer"] if summer else t["onpeak_kw_nonsummer"]
                items.append(_item(tag + f"delivery.on_peak_demand ({season})", dem["on"]["kw"] * f, "kW-months", on_rate))
                items.append(_item(tag + "delivery.off_peak_demand", dem["off"]["kw"] * f, "kW-months", t["offpeak_kw"]))

        # supply (per interval labels, so segmentation is unnecessary)
        if plan in ("sc1_rate1", "riderz_rate1"):
            items.append(_item("supply.flat", total_kwh, "kWh", m1["all"]))
        elif plan == "sc1_rate3":
            by = df.groupby("r3_msc").kwh.sum()
            for label, price in (("super", m3["all"]), ("on", m3["on"]), ("off", m3["off"])):
                q = float(by.get(label, 0))
                if label == "super" and q > 0 and price == 0:
                    warns.append("super-peak kWh present but MSC super-peak price is 0")
                items.append(_item(f"supply.{label}_peak", q, "kWh", price))
        else:
            by = df.groupby("demand_period").kwh.sum()
            items.append(_item("supply.on_peak", float(by.get("on", 0)), "kWh", m4["on"]))
            items.append(_item("supply.off_peak", float(by.get("off", 0)), "kWh", m4["off"]))

        bpp = tariff_entry(tariff, "bpp", start)["amount"]
        items.append(_item("billing_payment_processing", 1, "bill", bpp))
        if common_per_kwh:
            items.append(_item("common_charges", total_kwh, "kWh", common_per_kwh))
        subtotal = sum(i["amount"] for i in items)
        if grt_pct:
            items.append(_item("gross_receipts_tax", subtotal, "$", grt_pct / 100))
        results[plan] = {
            "plan": PLAN_NAMES[plan], "items": items, "warnings": warns,
            "total": sum(i["amount"] for i in items),
        }
    return {"diagnostics": diag, "plans": results}


def calendar_months(first, last):
    """Month [start, next-month-start) periods covering dates first..last."""
    out, d = [], dt.date(first.year, first.month, 1)
    while d <= last:
        n = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append((d, n))
        d = n
    return out


def run(usage, periods, tariff, msc, common_per_kwh=0.0, grt_pct=0.0):
    """Price each period; periods with no tariff in effect come back as {"skipped": reason}."""
    out = []
    for s, e in periods:
        try:
            out.append(price_period(usage, s, e, tariff, msc, common_per_kwh, grt_pct))
        except TariffNotInEffect as ex:
            out.append({"skipped": str(ex), "start": s.isoformat(), "end": e.isoformat()})
    return out
