"""Real bills: load the transcribed line items, and scale usage to a bill's billed kWh.

Bills are the ground truth the statement model is tested against (tests/test_bills.py);
they are private and never part of the engine's inputs.
"""
import pandas as pd

from .engine import Period
from .loaders import Usage


def load_bills(path):
    """bills.csv with the line items transcribed from each bill."""
    return pd.read_csv(path, parse_dates=["from", "to"])


def scale_usage_to_kwh(usage, period, target_kwh):
    """Copy of `usage` with the period's intervals scaled so they total `target_kwh`.

    Interval data and billed kWh differ by a few kWh (rounding, estimated reads);
    scaling lets a bill be reproduced to the cent without changing load shape."""
    period = Period.coerce(period)
    k = usage.kwh.copy()
    sel = (k.index >= pd.Timestamp(period.start)) & (k.index < pd.Timestamp(period.end))
    k[sel] *= target_kwh / k[sel].sum()
    return Usage(k, usage.interval_minutes, usage.n_estimated, usage.n_duplicate_starts)
