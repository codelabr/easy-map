"""Which column holds the commune names, when two columns both look like it.

A commune-level report written by one province repeats that province's name on
every row. Many province names are also the name of a commune somewhere else, so
that column can score a *perfect* commune match rate while holding one value.

Measured on the 2026 boundary set while building the eleven training workbooks:
three of them were profiled with the province column proposed as the commune
column, and two of those three went on to draw a map. An image built from a
column of one repeated value is worse than a refusal, because nothing about it
looks wrong to the person holding it.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)

from emap import matching, profile


def frame(rows: list[dict], deps=None):
    import pandas as pd

    return pd.DataFrame(rows)


def described(columns: list[str]) -> list[dict]:
    """The shape ``location_candidates`` wants, without running the profiler.

    Only the two keys it reads are supplied. Building the real description would
    drag in the dependency loader and measure nothing extra.
    """
    return [{"column": c, "semantic": "text"} for c in columns]


PROVINCES = ["Quảng Trị", "Thanh Hóa", "Hà Nội"]
COMMUNES = ["Quảng Trị", "Đông Hà", "Cam Lộ", "Gio Linh", "Vĩnh Linh"]


class TestARepeatedProvinceIsNotTheCommuneColumn(unittest.TestCase):
    def candidates(self, rows: list[dict]):
        table = frame(rows)
        return profile.location_candidates(
            table, described(list(table.columns)), PROVINCES, COMMUNES,
            matching.NOTHING)

    def test_the_varied_column_is_proposed_first(self):
        rows = [{"Tỉnh/thành phố": "Quảng Trị", "Xã/phường": c}
                for c in ("Đông Hà", "Cam Lộ", "Gio Linh", "Vĩnh Linh")]
        found = self.candidates(rows)
        self.assertEqual(found["commune"][0]["column"], "Xã/phường")

    def test_even_when_the_province_column_matches_more_often(self):
        """The case that survived the first fix.

        Quang Tri's own file: the province column matched 1.0 and the commune
        column 0.987, because one commune name is spelled unusually. Ranking on
        hit rate with the count only as a tie-break still chose the province.
        """
        rows = [{"Tỉnh/thành phố": "Quảng Trị", "Xã/phường": c}
                for c in ("Đông Hà", "Cam Lộ", "Gio Linh", "Không Có Thật")]
        found = self.candidates(rows)
        best = found["commune"][0]
        self.assertEqual(best["column"], "Xã/phường")
        self.assertLess(best["match_rate"], 1.0,
                        "the test no longer exercises the losing-on-rate case")

    def test_the_single_valued_column_is_still_offered_second(self):
        """Demoted, not discarded. It is a real candidate for a one-commune
        table, and the agent may still show it as an alternative."""
        rows = [{"Tỉnh/thành phố": "Quảng Trị", "Xã/phường": c}
                for c in ("Đông Hà", "Cam Lộ")]
        columns = [d["column"] for d in self.candidates(rows)["commune"]]
        self.assertEqual(columns, ["Xã/phường", "Tỉnh/thành phố"])

    def test_a_one_row_table_is_not_broken_by_the_rule(self):
        """One row means every column holds one value, so the rule cannot
        separate them and must not throw them away."""
        rows = [{"Tỉnh/thành phố": "Quảng Trị", "Xã/phường": "Đông Hà"}]
        found = self.candidates(rows)
        self.assertTrue(found["commune"], "every candidate was discarded")

    def test_provinces_are_not_demoted_for_holding_one_value(self):
        """A commune-level table for one province legitimately names that
        province and nothing else; the province column must still be found."""
        rows = [{"Tỉnh/thành phố": "Quảng Trị", "Xã/phường": c}
                for c in ("Đông Hà", "Cam Lộ", "Gio Linh")]
        found = self.candidates(rows)
        self.assertEqual(found["province"][0]["column"], "Tỉnh/thành phố")

    def test_the_count_is_reported_so_the_choice_can_be_explained(self):
        """The agent tells the user which column it picked and why. A rank with
        no visible reason is a rank the user cannot check."""
        rows = [{"Tỉnh/thành phố": "Quảng Trị", "Xã/phường": c}
                for c in ("Đông Hà", "Cam Lộ", "Gio Linh")]
        for kind in ("province", "commune"):
            for candidate in self.candidates(rows)[kind]:
                with self.subTest(kind=kind, column=candidate["column"]):
                    self.assertIn("distinct_values", candidate)


if __name__ == "__main__":
    unittest.main()
