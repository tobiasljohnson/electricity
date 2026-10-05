"""Regenerate data/common_charges.toml from bills/bills.csv.

Usage: python3 scripts/derive_common_charges.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conedrates.bills import derive_all, load_bills, to_toml  # noqa: E402
from conedrates.loaders import load_msc, load_tariff, load_usage  # noqa: E402

common = derive_all(
    load_bills(ROOT / "bills" / "bills.csv"),
    load_usage(ROOT / "usage.csv"),
    load_tariff(ROOT / "data" / "tariff.toml"),
    load_msc(ROOT / "LDS_APPND.csv"),
)
out = ROOT / "data" / "common_charges.toml"
out.write_text(to_toml(common))
print(f"wrote {out} ({len(common['period'])} periods)")
