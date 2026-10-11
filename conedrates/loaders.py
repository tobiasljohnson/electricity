"""Loaders for usage, MSC and tariff files."""
import csv
import datetime as dt
import tomllib
from dataclasses import dataclass

import pandas as pd


# ---------- usage ----------

@dataclass
class Usage:
    kwh: pd.Series            # index = interval start (local wall clock, naive)
    interval_minutes: int
    n_estimated: int          # rows with a non-empty NOTES field
    n_duplicate_starts: int   # duplicate timestamps (summed), e.g. DST fall-back


def load_usage(path):
    """Read a Con Ed 'Download My Data' interval CSV.

    Columns: TYPE, DATE, START TIME, END TIME, USAGE (kWh), NOTES. Times are
    local wall-clock; END TIME is the last minute of the interval (00:14 for a
    00:00 start), so interval length = END - START + 1 minute.

    Anything before the header line ("TYPE,DATE,START TIME,...") is skipped.
    """
    with open(path, 'r', encoding="utf-8-sig") as processed_file:
        current_pos = processed_file.tell()
        line = processed_file.readline()
        while line and not line.lstrip().startswith("TYPE,DATE"):
            current_pos = processed_file.tell()
            line = processed_file.readline()
        if not line:
            raise ValueError(f"no header line starting with 'TYPE,DATE' found in {path}")
        processed_file.seek(current_pos)
        df = pd.read_csv(processed_file, dtype={"NOTES": "string"})

    df.columns = [c.strip() for c in df.columns]
    start = pd.to_datetime(df["DATE"] + " " + df["START TIME"])
    end = pd.to_datetime(df["DATE"] + " " + df["END TIME"])
    minutes = ((end - start).dt.total_seconds() / 60 + 1).round().astype(int)
    interval = int(minutes.mode().iloc[0])
    kwh = pd.Series(df["USAGE (kWh)"].astype(float).values, index=pd.DatetimeIndex(start))
    dups = int(kwh.index.duplicated().sum())
    kwh = kwh.groupby(level=0).sum().sort_index()
    return Usage(kwh, interval, int(df["NOTES"].notna().sum()), dups)


# ---------- MSC ----------

MSC_CODES = {"RATE1": "SC1 Rate I / Rider Z", "001VTO": "SC1 Rate III", "001IPP": "Rider Z Rate IV / SC1 Rate IV"}
MAX_CYCLE_DAYS = 35


def _norm_code(c):
    c = c.strip()
    return "RATE1" if c.lstrip("0") == "1" else c   # raw file says '001'; pandas mangles it to '1'


def _ymd(s):
    s = s.strip()
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def load_msc(path, zone="J", tension="low"):
    """Load LDS_APPND.csv (raw, two header rows) or the filtered 7-column version.

    Returns DataFrame[code, start, end (inclusive), all, on, off], deduplicated,
    limited to the three codes used and to regular (<= 35 day) cycles.
    """
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    head = [h.strip() for h in rows[0]]
    if head[:3] == ["SC AND", "FROM DT", "TO  DT"] and "ON PEAK" in head and rows[1][4].strip() != "LT-ZONE H":
        cols = {"all": head.index("ALL HOURS"), "on": head.index("ON PEAK"), "off": head.index("OFF PEAK")}
        body = rows[1:]
    else:
        loc = f"{'LT' if tension.lower().startswith('l') else 'HT'}-ZONE {zone.upper()}"
        sub = [h.strip() for h in rows[1]]
        cols = {}
        for key, kind in (("all", "ALL HOURS"), ("on", "ON PEAK"), ("off", "OFF PEAK")):
            idx = [i for i in range(4, len(head)) if head[i] == kind and sub[i] == loc]
            if len(idx) != 1:
                raise ValueError(f"MSC column {kind}/{loc} not found in {path}")
            cols[key] = idx[0]
        body = rows[2:]
    out = []
    for r in body:
        if len(r) < 4:
            continue
        code = _norm_code(r[0])
        if code not in MSC_CODES:
            continue
        s, e = _ymd(r[1]), _ymd(r[2])
        if (e - s).days > MAX_CYCLE_DAYS:
            continue
        out.append((code, s, e, *(float(r[cols[k]]) for k in ("all", "on", "off"))))
    df = pd.DataFrame(out, columns=["code", "start", "end", "all", "on", "off"])
    return df.drop_duplicates().reset_index(drop=True)


def select_msc(msc, code, start, end):
    """Row for `code` best matching [start, end) (end exclusive): exact match
    first, else FROM closest to period start, ties by TO closeness."""
    sub = msc[msc.code == code]
    if sub.empty:
        raise ValueError(f"no MSC rows for {code}")
    last = end - dt.timedelta(days=1)
    key = pd.DataFrame({
        "a": sub.start.map(lambda d: abs((d - start).days)),
        "b": sub.end.map(lambda d: abs((d - last).days)),
    })
    best = key.sort_values(["a", "b"]).index[0]
    return sub.loc[best]


# ---------- tariff ----------

def load_tariff(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


class TariffNotInEffect(ValueError):
    pass


def tariff_entry(tariff, plan, on):
    """Entry of `plan` in effect on date `on` (latest effective <= on)."""
    ok = [e for e in tariff[plan] if e["effective"] <= on]
    if not ok:
        raise TariffNotInEffect(f"no {plan} tariff in effect on {on}")
    return max(ok, key=lambda e: e["effective"])


def effective_dates(tariff, plan):
    return sorted(e["effective"] for e in tariff[plan])
