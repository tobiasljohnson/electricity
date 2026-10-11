"""Tests for load_usage. Public data only: the fixtures in tests/ are invented, not real meter data."""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from conedrates.loaders import load_usage

FIXTURES = Path(__file__).resolve().parent

HEADER = "TYPE,DATE,START TIME,END TIME,USAGE (kWh),NOTES\n"
ROWS = ("Electric usage,2026-01-01,00:00,00:14,0.10,\n"
        "Electric usage,2026-01-01,00:15,00:29,0.20,\n")
PREAMBLE = "NAME,JANE DOE\nADDRESS,\"1 Main St, Anytown\"\n\n"


class Fixtures(unittest.TestCase):
    """The two checked-in files: one starts at the header, one has a preamble."""

    def test_usage_trimmed(self):
        """A file that begins immediately with the CSV header (it also has a byte-order mark)."""
        usage = load_usage(FIXTURES / "usage_trimmed.csv")
        self.assertEqual(len(usage.kwh), 7)                    # 8 rows; two share the 00:45 timestamp
        self.assertEqual(usage.interval_minutes, 15)
        self.assertEqual(usage.n_duplicate_starts, 1)
        self.assertAlmostEqual(usage.kwh[pd.Timestamp("2021-03-01 01:15")], 0.09)
        self.assertAlmostEqual(usage.kwh[pd.Timestamp("2021-03-01 00:45")], 0.29)   # 0.19 + 0.10 summed

    def test_usage_with_junk(self):
        """A file with name, address etc. before the CSV header: only the 12 data rows come through."""
        usage = load_usage(FIXTURES / "usage_with_junk.csv")
        self.assertEqual(len(usage.kwh), 12)
        self.assertEqual(usage.n_duplicate_starts, 0)
        self.assertAlmostEqual(usage.kwh.sum(), 2.69)
        self.assertAlmostEqual(usage.kwh[pd.Timestamp("2024-05-06 02:45")], 0.03)
        self.assertAlmostEqual(usage.kwh[pd.Timestamp("2024-05-06 01:45")], 0.01)


class Generated(unittest.TestCase):
    """Edge cases built on the fly, so nothing depends on invisible characters in a checked-in file."""

    def write(self, text, encoding="utf-8", newline=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)                 # deleted after the test, pass or fail
        path = Path(tmp.name) / "usage.csv"
        with open(path, "w", encoding=encoding, newline=newline) as f:
            f.write(text)
        return path

    def check_loads(self, path):
        usage = load_usage(path)
        self.assertEqual(len(usage.kwh), 2)
        self.assertAlmostEqual(usage.kwh.sum(), 0.30)
        self.assertEqual(usage.interval_minutes, 15)

    def test_plain_file(self):
        self.check_loads(self.write(HEADER + ROWS))

    def test_byte_order_mark_on_header(self):
        """The real Con Ed export starts with a byte-order mark; utf-8-sig writes one."""
        self.check_loads(self.write(HEADER + ROWS, encoding="utf-8-sig"))

    def test_byte_order_mark_before_preamble(self):
        self.check_loads(self.write(PREAMBLE + HEADER + ROWS, encoding="utf-8-sig"))

    def test_windows_line_endings(self):
        text = (PREAMBLE + HEADER + ROWS).replace("\n", "\r\n")
        self.check_loads(self.write(text, newline=""))        # newline="" writes the \r\n untouched

    def test_preamble_line_starting_with_type_is_not_the_header(self):
        """Only a line starting with 'TYPE,DATE' counts as the header."""
        self.check_loads(self.write("TYPE,some account note\n" + HEADER + ROWS))

    def test_no_header_raises_value_error_without_leaking_contents(self):
        path = self.write(PREAMBLE + ROWS)
        with self.assertRaises(ValueError) as cm:
            load_usage(path)
        self.assertIn("TYPE,DATE", str(cm.exception))
        self.assertNotIn("JANE DOE", str(cm.exception))      # the preamble holds personal details

    def test_empty_file_raises_value_error(self):
        with self.assertRaises(ValueError):
            load_usage(self.write(""))


if __name__ == "__main__":
    unittest.main()
