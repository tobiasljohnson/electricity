"""Billable demand: average of the 3 highest daily maxima of integrated 60-minute demand."""
import numpy as np
import pandas as pd


def billable_demand(kwh, labels, interval_minutes, start, end, top_n=3):
    """kwh: Series indexed by interval start. labels: callable(DatetimeIndex) -> array of
    period labels for those starts. Period is [start, end) (Timestamps).

    A window is n consecutive intervals (n = 60/interval) all present, all in the
    same period and all starting on the same calendar day. Returns
    {label: {"kw", "days", "top", "low_data"}}.
    """
    n = 60 // interval_minutes
    grid = pd.date_range(start, end, freq=f"{interval_minutes}min", inclusive="left")
    vals = kwh.reindex(grid)
    lab = pd.Series(pd.factorize(pd.Series(labels(grid)))[0], index=grid)
    names = pd.Series(labels(grid), index=grid)
    day = pd.Series(grid.normalize().astype("int64"), index=grid)

    roll = lambda s: s.rolling(n)
    total = roll(vals).sum()                       # NaN if any interval missing
    same = (roll(lab).min() == roll(lab).max()) & (roll(day).min() == roll(day).max())
    ok = total.notna() & same
    win = pd.DataFrame({"kw": total[ok], "label": names[ok], "day": day[ok]})

    out = {}
    for label in sorted(set(names)):
        w = win[win.label == label]
        daily = w.groupby("day").kw.max().sort_values(ascending=False)
        top = daily.head(top_n)
        out[label] = {
            "kw": float(top.mean()) if len(top) else 0.0,
            "days": int(len(daily)),
            "top": [round(float(x), 4) for x in top],
            "low_data": len(daily) < top_n,
        }
    return out
