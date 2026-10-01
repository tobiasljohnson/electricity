"""Holidays, seasons and time-period classification."""
import datetime as dt

import numpy as np
import pandas as pd

SUMMER_MONTHS = (6, 7, 8, 9)


def _nth_weekday(year, month, weekday, n):
    """n-th (1-based) given weekday of a month; n=-1 means last."""
    if n > 0:
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
        return d
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def holidays(year):
    """Tariff holidays for Rate IV / Rider Z on-peak exclusion (no observed-day shifts)."""
    return {
        dt.date(year, 1, 1),
        _nth_weekday(year, 5, 0, -1),   # Memorial Day
        dt.date(year, 7, 4),
        _nth_weekday(year, 9, 0, 1),    # Labor Day
        _nth_weekday(year, 11, 3, 4),   # Thanksgiving
        dt.date(year, 12, 25),
    }


def is_summer(month):
    return month in SUMMER_MONTHS


def classify(starts):
    """Classify interval start timestamps (local, naive DatetimeIndex).

    Returns a DataFrame of boolean/str columns:
      demand_period : 'on' / 'off'  (Rate IV and Rider Z)
      r3_delivery   : 'on' / 'off'  (Rate III delivery)
      r3_msc        : 'super' / 'on' / 'off'  (Rate III supply)
    """
    hour = starts.hour + starts.minute / 60
    weekday = starts.dayofweek < 5
    dates = starts.normalize()
    years = sorted(set(starts.year))
    hol = np.isin(dates.date, [d for y in years for d in holidays(y)])
    summer = starts.month.isin(SUMMER_MONTHS)

    dem_on = weekday & ~hol & (hour >= 12) & (hour < 20)
    r3_on = hour >= 8
    r3_super = summer & weekday & (hour >= 14) & (hour < 18)
    return pd.DataFrame({
        "demand_period": np.where(dem_on, "on", "off"),
        "r3_delivery": np.where(r3_on, "on", "off"),
        "r3_msc": np.where(r3_super, "super", np.where(r3_on, "on", "off")),
    }, index=starts)
