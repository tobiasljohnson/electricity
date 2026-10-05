"""Pricing engine: itemized cost of a usage record under each of the four plans."""
import datetime as dt
from typing import NamedTuple, Optional

import pandas as pd

from .calendar import classify, is_summer
from .demand import billable_demand
from .loaders import TariffNotInEffect, effective_dates, select_common, select_msc, tariff_entry

PLANS = ("sc1_rate1", "sc1_rate3", "sc1_rate4", "riderz_rate1")
PLAN_NAMES = {
    "sc1_rate1": "SC 1 Rate I",
    "sc1_rate3": "SC 1 Rate III",
    "sc1_rate4": "SC 1 Rate IV",
    "riderz_rate1": "Rider Z Rate I",
}
PRORATION_DAYS = 30


class Period(NamedTuple):
    """A billing period.

    start, end: the usage window, end exclusive (end - start = days billed).
    msc_start, msc_end: the dates used to look up MSC / common-charge rows,
    in the same convention as Con Ed's files (cycle FROM and TO, TO exclusive
    here). They equal start/end for calendar months.
    """
    start: dt.date
    end: dt.date
    msc_start: Optional[dt.date] = None
    msc_end: Optional[dt.date] = None

    @classmethod
    def calendar_month(cls, start, end):
        return cls(start, end, start, end)

    @classmethod
    def from_bill(cls, from_date, to_date):
        """Bill dates are meter-read dates: a bill 'Feb 9 to Mar 11' covers usage
        from Feb 10 through Mar 11 inclusive (verified against kWh on six bills),
        while Con Ed's MSC file rows carry the bill dates themselves."""
        one = dt.timedelta(days=1)
        return cls(from_date + one, to_date + one, from_date, to_date + one)

    @classmethod
    def coerce(cls, p):
        if isinstance(p, cls):
            return cls(p.start, p.end, p.msc_start or p.start, p.msc_end or p.end)
        return cls.calendar_month(*p)


def _item(component, quantity, unit, rate, amount=None, group="delivery"):
    return {
        "component": component, "quantity": quantity, "unit": unit, "rate": rate,
        "amount": quantity * rate if amount is None else amount, "group": group,
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


def price_period(usage, period, tariff, msc, common=None):
    """Price one billing period under all four plans.

    `period` is a Period (or a (start, end) tuple, treated as a calendar month).
    `common` is a CommonCharges (see loaders.load_common) or None for tariff +
    MSC only.
    """
    period = Period.coerce(period)
    start, end = period.start, period.end
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

    ms, me = period.msc_start, period.msc_end
    m1 = select_msc(msc, "RATE1", ms, me)
    m3 = select_msc(msc, "001VTO", ms, me)
    m4 = select_msc(msc, "001IPP", ms, me)
    diag["msc_rows"] = {
        n: {"from": r.start.isoformat(), "to": r.end.isoformat()}
        for n, r in (("rate1", m1), ("rate3", m3), ("rate4", m4))
    }

    cc = None
    if common is not None:
        cc, estimated = select_common(common, ms, me)
        diag["common_charges"] = {"source": "default estimate" if estimated else f"{cc['from']}..{cc['to']}"}
        if estimated:
            diag["warnings"].append("no bill-based common charges near this period; using default estimate")

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
            items.append(_item("supply.flat", total_kwh, "kWh", m1["all"], group="supply"))
        elif plan == "sc1_rate3":
            by = df.groupby("r3_msc").kwh.sum()
            for label, price in (("super", m3["all"]), ("on", m3["on"]), ("off", m3["off"])):
                q = float(by.get(label, 0))
                if label == "super" and q > 0 and price == 0:
                    warns.append("super-peak kWh present but MSC super-peak price is 0")
                items.append(_item(f"supply.{label}_peak", q, "kWh", price, group="supply"))
        else:
            by = df.groupby("demand_period").kwh.sum()
            items.append(_item("supply.on_peak", float(by.get("on", 0)), "kWh", m4["on"], group="supply"))
            items.append(_item("supply.off_peak", float(by.get("off", 0)), "kWh", m4["off"], group="supply"))

        bpp = tariff_entry(tariff, "bpp", start)["amount"]
        items.append(_item("billing_payment_processing", 1, "bill", bpp))
        if cc is not None:
            items += _common_items(items, cc, total_kwh)
        results[plan] = {
            "plan": PLAN_NAMES[plan], "items": items, "warnings": warns,
            "total": sum(i["amount"] for i in items),
        }
    return {"diagnostics": diag, "plans": results}


def _common_items(items, cc, kwh):
    """Charges and taxes that sit on top of tariff delivery and MSC supply.

    Modeled on the structure of a real Con Ed bill: delivery side = basic
    service + delivery + adjustments + System Benefit Charge; supply side =
    supply + MSC adjustment + Merchant Function Charge. GRT is applied to each
    side, then sales tax to everything including GRT. Per-kWh adjustments are
    assumed identical for all four plans (SPEC: unverified for demand plans).
    """
    cents = lambda c: c / 100
    out = [
        _item("common.delivery_adjustments", kwh, "kWh", cents(cc["delivery_adj_c"])),
        _item("common.system_benefit_charge", kwh, "kWh", cents(cc["sbc_c"])),
        _item("common.supply_adjustment", kwh, "kWh", cents(cc["supply_adj_c"]), group="supply"),
        _item("common.merchant_function_charge", kwh, "kWh", cents(cc["mfc_c"]), group="supply"),
    ]
    side = {"delivery": 0.0, "supply": 0.0}
    for i in items + out:
        side[i["group"]] += i["amount"]
    grt_d = _item("tax.grt_delivery", side["delivery"], "$", cc["grt_delivery_pct"] / 100)
    grt_s = _item("tax.grt_supply", side["supply"], "$", cc["grt_supply_pct"] / 100, group="supply")
    out += [grt_d, grt_s]
    taxable = side["delivery"] + side["supply"] + grt_d["amount"] + grt_s["amount"]
    out.append(_item("tax.sales_tax", taxable, "$", cc["sales_tax_pct"] / 100))
    return out


def calendar_months(first, last):
    """Month [start, next-month-start) periods covering dates first..last."""
    out, d = [], dt.date(first.year, first.month, 1)
    while d <= last:
        n = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append(Period.calendar_month(d, n))
        d = n
    return out


def run(usage, periods, tariff, msc, common=None):
    """Price each period; periods with no tariff in effect come back as {"skipped": reason}."""
    out = []
    for p in map(Period.coerce, periods):
        try:
            out.append(price_period(usage, p, tariff, msc, common))
        except TariffNotInEffect as ex:
            out.append({"skipped": str(ex), "start": p.start.isoformat(), "end": p.end.isoformat()})
    return out
