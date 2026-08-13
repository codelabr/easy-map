"""Reading a table where one row is one observation.

Every rule here was written against a real PEPFAR MER export: 70.080 rows, 23
indicators and one ``Value`` column. The failure mode it guards against is not a
crash — it is a total that is silently several times too large because the same
people were counted once per disaggregation.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import longform


def col(name: str, semantic: str, **extra) -> dict:
    return {"column": name, "semantic": semantic, **extra}


WIDE = [col("Tỉnh/thành phố", "category"), col("Xã/phường", "text"),
        col("Dân số", "count"), col("Bao phủ (%)", "percent")]

LONG = [col("SNU1", "category"), col("Indicator Code", "category"),
        col("Quarter", "category"), col("Disaggregate", "category"),
        col("Value", "count")]


class TestLooksLong(unittest.TestCase):
    def test_a_wide_sheet_is_not_mistaken_for_a_long_one(self):
        self.assertIsNone(longform.looks_long(WIDE, row_count=42, distinct_places=42))

    def test_many_rows_per_place_over_one_measure_is_long(self):
        found = longform.looks_long(LONG, row_count=70080, distinct_places=13)
        self.assertIsNotNone(found)
        self.assertEqual(found["cột_giá_trị"], "Value")
        self.assertGreater(found["dòng_trên_mỗi_đơn_vị"], 100)

    def test_two_measures_mean_it_is_not_the_single_value_shape(self):
        two = LONG + [col("Target", "count")]
        self.assertIsNone(longform.looks_long(two, 70080, 13))

    def test_a_handful_of_extra_rows_is_not_enough_to_call_it_long(self):
        """Duplicate place names in a wide sheet must not trip the detector."""
        self.assertIsNone(longform.looks_long(LONG, row_count=50, distinct_places=42))

    def test_the_verdict_explains_itself(self):
        found = longform.looks_long(LONG, 70080, 13)
        self.assertIn("Value", found["vì_sao"])
        self.assertIn("quan sát", found["vì_sao"])


class TestMeasureColumn(unittest.TestCase):
    def test_a_column_that_names_itself_wins(self):
        self.assertEqual(longform.measure_column(LONG), "Value")

    def test_a_lone_numeric_column_is_taken_even_when_oddly_named(self):
        cols = [col("SNU1", "category"), col("Số ca ghi nhận", "count")]
        self.assertEqual(longform.measure_column(cols), "Số ca ghi nhận")

    def test_two_unnamed_numeric_columns_are_left_to_the_user(self):
        cols = [col("A", "count"), col("B", "count")]
        self.assertIsNone(longform.measure_column(cols))


class TestIndicatorAxis(unittest.TestCase):
    def test_the_column_named_for_it_is_found(self):
        samples = {"Indicator Code": ["TX_CURR", "HTS_TST", "TX_PVLS Num"],
                   "SNU1": ["Ha Noi", "Ha Noi", "Hai Phong"],
                   "Quarter": ["Q1", "Q2", "Q1"], "Disaggregate": ["(total)"] * 3}
        self.assertEqual(longform.indicator_axis(LONG, samples), "Indicator Code")

    def test_code_shaped_values_give_it_away_without_the_name(self):
        cols = [col("SNU1", "category"), col("Thước đo", "category"),
                col("Value", "count")]
        samples = {"Thước đo": ["TX_CURR", "TX_NEW", "HTS_TST", "PREP_NEW"],
                   "SNU1": ["Ha Noi"] * 4}
        self.assertEqual(longform.indicator_axis(cols, samples), "Thước đo")

    def test_a_place_column_is_not_an_indicator_axis(self):
        cols = [col("SNU1", "category"), col("Value", "count")]
        self.assertIsNone(longform.indicator_axis(
            cols, {"SNU1": ["Ha Noi", "Hai Phong", "Hue"]}))


class TestVaryingAxes(unittest.TestCase):
    """The double-counting detector."""

    def setUp(self):
        # Hà Nội appears four times: two age bands × two sexes
        self.places = ["Ha Noi", "Ha Noi", "Ha Noi", "Ha Noi", "Hue"]
        self.axes = {
            "Age": ["20-24", "20-24", "25-29", "25-29", "20-24"],
            "Sex": ["Male", "Female", "Male", "Female", "Male"],
            "Quarter": ["Q2", "Q2", "Q2", "Q2", "Q2"],
        }

    def test_a_column_that_is_constant_within_a_place_is_not_reported(self):
        names = [a["cột"] for a in longform.varying_axes(self.places, self.axes)]
        self.assertNotIn("Quarter", names)

    def test_the_columns_that_split_a_place_are_named(self):
        names = [a["cột"] for a in longform.varying_axes(self.places, self.axes)]
        self.assertEqual(sorted(names), ["Age", "Sex"])

    def test_one_row_per_place_raises_nothing(self):
        self.assertEqual(longform.varying_axes(["Ha Noi", "Hue"],
                                               {"Age": ["20-24", "25-29"]}), [])

    def test_the_warning_names_the_columns_and_the_damage(self):
        axes = longform.varying_axes(self.places, self.axes)
        text = longform.pin_warning(axes, place_count=2)
        self.assertIn("Age", text)
        self.assertIn("đếm trùng", text)

    def test_nothing_to_pin_means_no_warning(self):
        self.assertIsNone(longform.pin_warning([], place_count=2))


class TestIndicatorSlices(unittest.TestCase):
    def setUp(self):
        self.indicators = ["TX_CURR", "TX_CURR", "HTS_TST", "TX_CURR", "HTS_TST"]
        self.places = ["Ha Noi", "Hue", "Ha Noi", "Can Tho", "Ha Noi"]
        self.values = [10, 20, 5, 30, 7]
        self.periods = ["Q1", "Q1", "Q2", "Q2", "Q2"]

    def test_the_indicator_covering_most_places_comes_first(self):
        out = longform.indicator_slices(self.indicators, self.places, self.values,
                                        self.periods)
        self.assertEqual(out[0]["chỉ_số"], "TX_CURR")
        self.assertEqual(out[0]["số_đơn_vị_có_mặt"], 3)

    def test_a_place_counted_twice_still_counts_once_as_coverage(self):
        out = {d["chỉ_số"]: d for d in longform.indicator_slices(
            self.indicators, self.places, self.values, self.periods)}
        self.assertEqual(out["HTS_TST"]["số_dòng"], 2)
        self.assertEqual(out["HTS_TST"]["số_đơn_vị_có_mặt"], 1)

    def test_the_periods_each_indicator_actually_has_are_listed(self):
        out = {d["chỉ_số"]: d for d in longform.indicator_slices(
            self.indicators, self.places, self.values, self.periods)}
        self.assertEqual(out["TX_CURR"]["kỳ_có_sẵn"], ["Q1", "Q2"])
        self.assertEqual(out["HTS_TST"]["kỳ_có_sẵn"], ["Q2"])

    def test_text_in_the_value_column_does_not_take_the_run_down(self):
        out = longform.indicator_slices(["A", "A"], ["Ha Noi", "Hue"],
                                        [5, "không có"])
        self.assertEqual(out[0]["tổng_thô"], 5.0)


class TestRatioPairs(unittest.TestCase):
    def test_a_num_den_pair_is_recognised(self):
        pairs = longform.ratio_pairs(["TX_PVLS Num", "TX_PVLS Den", "TX_CURR"])
        self.assertEqual(pairs, [{"tên": "TX_PVLS", "tử_số": "TX_PVLS Num",
                                  "mẫu_số": "TX_PVLS Den"}])

    def test_a_numerator_with_no_denominator_is_not_a_pair(self):
        self.assertEqual(longform.ratio_pairs(["TX_PVLS Num", "TX_CURR"]), [])

    def test_underscore_and_vietnamese_spellings_work_too(self):
        self.assertEqual(
            [p["tên"] for p in longform.ratio_pairs(
                ["TX_TB_Num", "TX_TB_Den", "Sàng lọc tử số", "Sàng lọc mẫu số"])],
            ["Sàng lọc", "TX_TB"])

    def test_an_indicator_that_merely_ends_in_n_is_not_split(self):
        self.assertEqual(longform.ratio_pairs(["PREP_NEW", "PREP_CT"]), [])


class TestWhereFilters(unittest.TestCase):
    def test_a_filter_is_split_on_the_first_equals_only(self):
        self.assertEqual(longform.parse_where(["Disaggregate=By Age - Sex"]),
                         [("Disaggregate", "By Age - Sex")])

    def test_several_filters_are_kept_in_order(self):
        self.assertEqual(longform.parse_where(["Quarter=Q2", "Fiscal Year=2026"]),
                         [("Quarter", "Q2"), ("Fiscal Year", "2026")])

    def test_a_malformed_filter_is_refused_rather_than_ignored(self):
        with self.assertRaises(ValueError):
            longform.parse_where(["Quarter Q2"])
        with self.assertRaises(ValueError):
            longform.parse_where(["=Q2"])

    def test_a_typo_is_answered_with_the_values_that_do_exist(self):
        present = ["Q1", "Q2", "Q3", "Q4"]
        self.assertIsNone(longform.unknown_values("Quarter", "Q2", present))
        self.assertEqual(longform.unknown_values("Quarter", "Q5", present), present)

    def test_a_near_miss_is_offered_first(self):
        present = ["By Age - Sex", "By Age - Sex - Outcome", "(total)"]
        found = longform.unknown_values("Disaggregate", "age", present)
        self.assertEqual(sorted(found), ["By Age - Sex", "By Age - Sex - Outcome"])


if __name__ == "__main__":
    unittest.main()


class TestDoubleCountingAxes(unittest.TestCase):
    """Not every axis that splits a place is a hazard.

    Sites within a province, or age bands within one disaggregation, are parts
    of a whole: adding them is the correct thing to do. A column that carries a
    pre-computed total *alongside* its detail is the dangerous one, and it is
    dangerous precisely because the inflated result stays believable.
    """

    def setUp(self):
        self.places = ["Ha Noi"] * 4 + ["Hue"] * 2

    def test_a_clean_partition_is_not_flagged(self):
        axes = {"Age": ["20-24", "25-29", "30-34", "35-39", "20-24", "25-29"]}
        self.assertEqual(longform.double_counting_axes(self.places, axes), [])

    def test_a_total_row_sitting_beside_detail_rows_is_flagged(self):
        axes = {"Disaggregate": ["(total)", "By Age", "By Age", "By Age",
                                 "(total)", "By Age"]}
        found = longform.double_counting_axes(self.places, axes)
        self.assertEqual([a["cột"] for a in found], ["Disaggregate"])
        self.assertEqual(found[0]["giá_trị_tổng"], ["(total)"])

    def test_a_column_of_nothing_but_totals_is_not_a_hazard(self):
        axes = {"Disaggregate": ["(total)"] * 6}
        self.assertEqual(longform.double_counting_axes(self.places, axes), [])

    def test_the_vietnamese_spellings_are_recognised(self):
        for word in ("Tổng", "tất cả", "Total", "(All)"):
            self.assertTrue(longform.is_total_like(word), word)
        for word in ("By Age - Sex", "Male", "Q2"):
            self.assertFalse(longform.is_total_like(word), word)

    def test_the_warning_says_why_the_column_is_dangerous(self):
        axes = {"Disaggregate": ["(total)", "By Age", "By Age", "By Age",
                                 "(total)", "By Age"]}
        text = longform.pin_warning(
            longform.double_counting_axes(self.places, axes), place_count=2)
        self.assertIn("dòng tổng", text)
        self.assertIn("Disaggregate", text)


class TestChoosingTheSlice(unittest.TestCase):
    """Naming the dangerous column is only half the job.

    An agent that is told "pin Disaggregate" still has to know *which* value,
    and getting that wrong empties the map or triples the total. These rules
    measure the candidates instead of guessing at their names.
    """

    def setUp(self):
        # '(total)' and 'By Age - Sex' describe the same people; 'By CD4' is a
        # narrower subset that only two provinces report
        self.values = (["(total)"] * 3 + ["By Age - Sex"] * 6 + ["By CD4"] * 2)
        self.places = (["Ha Noi", "Hue", "Can Tho"]
                       + ["Ha Noi", "Ha Noi", "Hue", "Hue", "Can Tho", "Can Tho"]
                       + ["Ha Noi", "Hue"])
        self.amounts = [100, 60, 40] + [50, 50, 30, 30, 20, 20] + [10, 5]

    def options(self):
        return longform.pin_options(self.values, self.places, self.amounts)

    def test_each_candidate_is_measured_not_assumed(self):
        by_value = {o["giá_trị"]: o for o in self.options()}
        self.assertEqual(by_value["(total)"]["số_đơn_vị"], 3)
        self.assertEqual(by_value["(total)"]["tổng"], 200.0)
        self.assertEqual(by_value["By Age - Sex"]["số_đơn_vị"], 3)
        self.assertEqual(by_value["By CD4"]["số_đơn_vị"], 2)

    def test_values_adding_up_to_the_same_thing_are_reported_together(self):
        found = longform.duplicated_totals(self.options())
        self.assertEqual([sorted(g) for g in found], [["(total)", "By Age - Sex"]])

    def test_a_narrower_subset_is_not_called_a_duplicate(self):
        self.assertNotIn("By CD4", sum(longform.duplicated_totals(self.options()), []))

    def test_the_publishers_own_total_wins_a_tie_on_coverage(self):
        pick = longform.recommend_pin(self.options())
        self.assertEqual(pick["giá_trị"], "(total)")
        self.assertIn("dòng tổng", pick["vì_sao"])

    def test_without_a_total_row_the_widest_coverage_wins(self):
        values = ["By Age - Sex"] * 3 + ["By CD4"] * 2
        places = ["Ha Noi", "Hue", "Can Tho", "Ha Noi", "Hue"]
        pick = longform.recommend_pin(longform.pin_options(values, places, [1] * 5))
        self.assertEqual(pick["giá_trị"], "By Age - Sex")
        self.assertIn("phủ nhiều đơn vị nhất", pick["vì_sao"])

    def test_the_alternatives_are_offered_rather_than_hidden(self):
        pick = longform.recommend_pin(self.options())
        self.assertIn("By Age - Sex", pick["phương_án_khác"])

    def test_a_single_candidate_needs_no_justification(self):
        pick = longform.recommend_pin(
            longform.pin_options(["(total)"] * 2, ["Ha Noi", "Hue"], [5, 5]))
        self.assertIn("chỉ có một giá trị", pick["vì_sao"])

    def test_nothing_to_pin_returns_nothing(self):
        self.assertIsNone(longform.recommend_pin([]))
        self.assertEqual(longform.pin_options([None, "", "nan"], [], []), [])
