"""Reading and ordering reporting periods.

Sorting periods as plain text puts "Tháng 10" before "Tháng 2" and breaks a year
boundary silently. In an animation that produces a video that runs backwards in
places, with nothing on screen to reveal it.
"""

from __future__ import annotations

import unittest
from datetime import date

import context  # noqa: F401  (path bootstrap)
from emap import periods


class TestParse(unittest.TestCase):
    def test_plain_year(self):
        self.assertEqual(periods.parse("2020")[:3], (2020, 1, 1))
        self.assertEqual(periods.parse("Năm 2020")[:3], (2020, 1, 1))
        self.assertEqual(periods.parse(2020)[:3], (2020, 1, 1))

    def test_quarter_in_roman_and_digits(self):
        self.assertEqual(periods.parse("Quý I/2026")[:3], (2026, 1, 1))
        self.assertEqual(periods.parse("Quý IV/2025")[:3], (2025, 10, 1))
        self.assertEqual(periods.parse("Quy 2/2026")[:3], (2026, 4, 1))

    def test_month(self):
        self.assertEqual(periods.parse("Tháng 3/2026")[:3], (2026, 3, 1))
        self.assertEqual(periods.parse("T12/2025")[:3], (2025, 12, 1))
        self.assertEqual(periods.parse("03/2026")[:3], (2026, 3, 1))
        self.assertEqual(periods.parse("2026-03")[:3], (2026, 3, 1))

    def test_full_date(self):
        self.assertEqual(periods.parse("2026-03-15")[:3], (2026, 3, 15))
        self.assertEqual(periods.parse(date(2026, 3, 15))[:3], (2026, 3, 15))

    def test_granularity_is_reported(self):
        self.assertEqual(periods.parse("2020")[3], periods.YEAR)
        self.assertEqual(periods.parse("Quý I/2026")[3], periods.QUARTER)
        self.assertEqual(periods.parse("Tháng 3/2026")[3], periods.MONTH)
        self.assertEqual(periods.parse("2026-03-15")[3], periods.DAY)

    def test_unreadable_values(self):
        for value in (None, "", "chưa rõ", "kỳ báo cáo"):
            self.assertIsNone(periods.parse(value), value)

    def test_impossible_month_is_not_a_month(self):
        self.assertNotEqual(periods.parse("Tháng 19/2026"), (2026, 19, 1, periods.MONTH))


class TestOrdering(unittest.TestCase):
    def test_months_sort_numerically_not_alphabetically(self):
        given = ["Tháng 10/2025", "Tháng 2/2025", "Tháng 1/2025"]
        self.assertEqual(periods.ordered(given),
                         ["Tháng 1/2025", "Tháng 2/2025", "Tháng 10/2025"])

    def test_quarters_cross_the_year_boundary(self):
        given = ["Quý I/2026", "Quý IV/2025", "Quý III/2025"]
        self.assertEqual(periods.ordered(given),
                         ["Quý III/2025", "Quý IV/2025", "Quý I/2026"])

    def test_years_sort_chronologically(self):
        self.assertEqual(periods.ordered([2021, 2019, 2026, 2020]),
                         [2019, 2020, 2021, 2026])

    def test_duplicates_collapse(self):
        self.assertEqual(periods.ordered(["2020", "2020", "2021"]), ["2020", "2021"])

    def test_blank_values_are_dropped(self):
        self.assertEqual(periods.ordered(["2020", "", None, "nan"]), ["2020"])

    def test_unreadable_values_sort_last_and_are_reported(self):
        given = ["chưa rõ", "2020", "2019"]
        self.assertEqual(periods.ordered(given), ["2019", "2020", "chưa rõ"])
        self.assertEqual(periods.unreadable(given), ["chưa rõ"])


class TestGranularity(unittest.TestCase):
    def test_finest_granularity_wins(self):
        self.assertEqual(periods.granularity(["2020", "Tháng 3/2020"]), periods.MONTH)
        self.assertEqual(periods.granularity(["2019", "2020"]), periods.YEAR)

    def test_nothing_readable(self):
        self.assertEqual(periods.granularity(["chưa rõ"]), periods.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
