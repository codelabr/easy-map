"""Combining several rows that describe one place.

The choice of method is not cosmetic. Two districts reporting 60% and 90%
coverage do not make a province 75% unless they are the same size — and a
province's case count is the sum of theirs, never their average. Getting this
wrong produces a number that is plausible, printed, and false.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import aggregate, semantics as sem


def frame(rows, columns):
    import pandas as pd

    return pd.DataFrame(rows, columns=columns)


class TestResolvingTheMethod(unittest.TestCase):
    def test_an_explicit_choice_always_wins(self):
        info = sem.infer("Số ca", [1, 2], True)
        self.assertEqual(aggregate.resolve("median", info), "median")

    def test_a_count_defaults_to_adding_up(self):
        info = sem.infer("Số ca phát hiện 2026", [12, 40], True)
        self.assertEqual(aggregate.resolve("auto", info), "sum")

    def test_a_share_is_recomputed_by_weight_when_there_is_one(self):
        info = sem.infer("Tỷ lệ bao phủ (%)", [51.3, 86.0], True)
        info["weight_column"] = "Dân số"
        self.assertEqual(aggregate.resolve("auto", info), "weighted-mean")

    def test_a_share_asks_for_a_weighted_mean_even_before_a_weight_is_found(self):
        """``resolve`` names the method the measure deserves; whether a weight
        column actually exists is settled later, in ``combine``. Keeping the two
        apart is what lets the footer say "trung bình có trọng số theo Dân số"
        on one map and plain "trung bình" on another."""
        info = sem.infer("Tỷ lệ bao phủ (%)", [51.3, 86.0], True)
        self.assertEqual(aggregate.resolve("auto", info), "weighted-mean")


class TestCombining(unittest.TestCase):
    COLUMNS = ["province", "ca", "tỷ_lệ", "dân_số"]
    ROWS = [["Hà Nội", 100, 60.0, 900_000],
            ["Hà Nội", 40, 90.0, 100_000],
            ["Huế", 25, 80.0, 500_000]]

    def setUp(self):
        self.df = frame(self.ROWS, self.COLUMNS)
        self.count = sem.infer("Số ca", [100, 40], True)
        self.share = sem.infer("Tỷ lệ (%)", [60.0, 90.0], True)

    def combine(self, column, info, method, weight=None):
        return aggregate.combine(None, self.df, "province", column, info, method,
                                 weight_column=weight)

    def test_counts_are_added(self):
        out = self.combine("ca", self.count, "sum")
        self.assertEqual(out["Hà Nội"], 140)
        self.assertEqual(out["Huế"], 25)

    def test_a_weighted_mean_follows_the_population_not_the_row_count(self):
        """The plain mean of 60 and 90 is 75; weighted by 900k and 100k it is
        63 — and 63 is the province's actual coverage."""
        out = self.combine("tỷ_lệ", self.share, "weighted-mean", weight="dân_số")
        self.assertAlmostEqual(out["Hà Nội"], 63.0, places=6)

    def test_an_unweighted_mean_is_the_other_answer(self):
        self.assertAlmostEqual(self.combine("tỷ_lệ", self.share, "mean")["Hà Nội"],
                               75.0, places=6)

    def test_a_weight_column_that_is_not_there_degrades_to_a_mean(self):
        out = self.combine("tỷ_lệ", self.share, "weighted-mean", weight="không_có")
        self.assertAlmostEqual(out["Hà Nội"], 75.0, places=6)

    def test_a_single_row_is_returned_unchanged_by_every_method(self):
        for method in ("sum", "mean", "median", "max", "min", "first"):
            self.assertEqual(self.combine("ca", self.count, method)["Huế"], 25,
                             f"method={method}")

    def test_all_missing_stays_missing_rather_than_becoming_zero(self):
        """``sum`` on an all-empty group returns 0 unless told otherwise, and a
        zero on a map reads as "none reported", not as "not reported" — grey and
        the lightest class are different claims. The engine passes min_count=1
        for exactly this; the value comes back empty, as None or NaN depending
        on the column's dtype, and what matters is that it is not 0."""
        import pandas as pd

        self.df = frame([["Hà Nội", None], ["Hà Nội", None]], ["province", "ca"])
        out = aggregate.combine(None, self.df, "province", "ca", self.count, "sum")
        self.assertTrue(pd.isna(out["Hà Nội"]))
        self.assertNotEqual(out["Hà Nội"], 0)

    def test_a_category_takes_the_most_frequent_group(self):
        self.df = frame([["Hà Nội", "Cao"], ["Hà Nội", "Cao"], ["Hà Nội", "Thấp"]],
                        ["province", "mức"])
        info = sem.infer("Mức ưu tiên", ["Cao", "Thấp"], False)
        self.assertEqual(aggregate.combine(None, self.df, "province", "mức", info,
                                           "mode")["Hà Nội"], "Cao")


class TestReporting(unittest.TestCase):
    def test_the_method_is_named_in_the_readers_language(self):
        info = sem.infer("Số ca", [1, 2], True)
        self.assertEqual(aggregate.describe("sum", info, None, "vi"), "cộng tổng")
        self.assertEqual(aggregate.describe("sum", info, None, "en"), "a sum")

    def test_a_weighted_mean_names_the_column_it_weighted_by(self):
        info = sem.infer("Tỷ lệ (%)", [51.3], True)
        text = aggregate.describe("weighted-mean", info, "Dân số", "vi")
        self.assertIn("Dân số", text)
        self.assertIn("trọng số", text)

    def test_an_unknown_method_is_shown_verbatim_rather_than_as_a_key(self):
        info = sem.infer("Số ca", [1, 2], True)
        self.assertEqual(aggregate.describe("kỳ_lạ", info, None, "vi"), "kỳ_lạ")

    def test_duplicates_are_counted_so_the_user_can_be_told(self):
        df = frame([["Hà Nội", 1], ["Hà Nội", 2], ["Huế", 3]], ["province", "ca"])
        self.assertEqual(aggregate.duplicate_count(df, "province"), 1)

    def test_a_tidy_table_reports_no_duplicates(self):
        df = frame([["Hà Nội", 1], ["Huế", 3]], ["province", "ca"])
        self.assertEqual(aggregate.duplicate_count(df, "province"), 0)


if __name__ == "__main__":
    unittest.main()
