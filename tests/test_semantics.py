"""What a column means, and how its values are written out.

Every assertion here corresponds to a decision the map depends on: a rate per
100.000 must never be drawn as a percent, a count must never carry decimals, and
a rate must never be summed.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import semantics as sem


class TestInfer(unittest.TestCase):
    def test_counts_are_integers_and_summable(self):
        info = sem.infer("Số ca phát hiện 2026", [12, 40, 7], is_numeric=True)
        self.assertEqual(info["semantic"], sem.COUNT)
        self.assertTrue(info["integer"])
        self.assertTrue(info["safe_to_sum"])
        self.assertEqual(info["default_aggregation"], "sum")

    def test_population_is_a_count(self):
        info = sem.infer("Dân số", [48987, 105301], is_numeric=True)
        self.assertEqual(info["semantic"], sem.COUNT)

    def test_percent_detected_and_never_summed(self):
        info = sem.infer("Bao phủ 2026 (%)", [51.3, 86.0], is_numeric=True)
        self.assertEqual(info["semantic"], sem.PERCENT)
        self.assertEqual(info["scale"], "percent")
        self.assertFalse(info["safe_to_sum"])
        self.assertEqual(info["default_aggregation"], "weighted-mean")

    def test_percent_on_a_zero_to_one_scale(self):
        info = sem.infer("Tỷ lệ dương tính", [0.04, 0.31], is_numeric=True)
        self.assertEqual(info["semantic"], sem.PERCENT)
        self.assertEqual(info["scale"], "unit")

    def test_rate_per_capita_is_not_a_percent(self):
        """The original renderer labelled this '%', which overstated it 1000x."""
        info = sem.infer("Tỷ suất ca phát hiện/100.000 dân", [42.7, 310.5], is_numeric=True)
        self.assertEqual(info["semantic"], sem.RATE_PER)
        self.assertEqual(info["unit"], "trên 100.000 dân")
        self.assertFalse(info["safe_to_sum"])

    def test_percentage_point_beats_percent(self):
        info = sem.infer("Thay đổi bao phủ (điểm %)", [-6.3, 15.2], is_numeric=True)
        self.assertEqual(info["semantic"], sem.POINT)
        self.assertFalse(info["safe_to_sum"])

    def test_money(self):
        info = sem.infer("Ngân sách 2026 (VND)", [1.2e9], is_numeric=True)
        self.assertEqual(info["semantic"], sem.MONEY)
        self.assertEqual(info["unit"], "VND")
        self.assertTrue(info["safe_to_sum"])

    def test_money_written_only_as_a_unit(self):
        info = sem.infer("Chi phí điều trị (đồng)", [450_000], is_numeric=True)
        self.assertEqual(info["semantic"], sem.MONEY)

    def test_co_infection_is_a_count_not_money(self):
        """'đồng nhiễm' deaccents to 'dong nhiem'; 'đồng' is also the currency."""
        info = sem.infer("Số ca đồng nhiễm HIV/Lao", [3, 9, 21], is_numeric=True)
        self.assertEqual(info["semantic"], sem.COUNT)
        self.assertNotIn("đồng", sem.format_value(21, info))

    def test_a_name_containing_tien_is_not_money(self):
        info = sem.infer("Số ca tiến triển nặng", [4, 11], is_numeric=True)
        self.assertEqual(info["semantic"], sem.COUNT)

    def test_low_cardinality_text_is_a_category(self):
        info = sem.infer("Mức ưu tiên", ["Cao", "Thường quy", "Cao", "Rất cao"],
                         is_numeric=False)
        self.assertEqual(info["semantic"], sem.CATEGORY)
        self.assertEqual(info["levels"], 3)

    def test_free_text_is_not_mappable(self):
        notes = [f"ghi chú số {i}" for i in range(30)]
        info = sem.infer("Ghi chú chất lượng dữ liệu", notes, is_numeric=False)
        self.assertEqual(info["semantic"], sem.TEXT)
        self.assertFalse(info["mappable"])

    def test_reporting_period_is_time(self):
        info = sem.infer("Kỳ báo cáo", ["Quý I/2026"] * 5, is_numeric=False)
        self.assertEqual(info["semantic"], sem.TIME)

    def test_coordinates(self):
        lon = sem.infer("Kinh độ", [105.70841, 106.1], is_numeric=True)
        lat = sem.infer("Vĩ độ", [20.98317, 10.2], is_numeric=True)
        self.assertEqual((lon["semantic"], lon["axis"]), (sem.COORDINATE, "lon"))
        self.assertEqual((lat["semantic"], lat["axis"]), (sem.COORDINATE, "lat"))

    def test_a_longitude_anywhere_in_the_world_is_a_coordinate(self):
        """This test used to assert the opposite, and it was right to.

        The rule read ``100 <= abs(v) <= 115`` — Vietnam's own extent, written
        into the meaning of the word "longitude". A column of Ecuadorean
        longitudes was quietly reclassified as a count, so a point map was
        never offered and nothing said why.
        """
        for value in (3.0, -78.5, 179.9):
            info = sem.infer("Kinh độ", [value, value + 0.1], is_numeric=True)
            self.assertEqual(info["semantic"], sem.COORDINATE, value)

    def test_a_number_that_cannot_be_a_coordinate_still_is_not_one(self):
        """Widening the range loosened the second half of a two-part test. The
        first half — the column has to be *called* a longitude — still holds,
        and so does the ceiling."""
        self.assertNotEqual(
            sem.infer("Kinh độ", [190.0, 200.0], is_numeric=True)["semantic"],
            sem.COORDINATE)
        self.assertNotEqual(
            sem.infer("Vĩ độ", [95.0, 100.0], is_numeric=True)["semantic"],
            sem.COORDINATE)
        self.assertNotEqual(
            sem.infer("Số ca mắc", [10.5, 20.5], is_numeric=True)["semantic"],
            sem.COORDINATE)


class TestHelpers(unittest.TestCase):
    def test_deaccent_handles_d_stroke(self):
        self.assertEqual(sem.deaccent("Đắk Lắk"), "dak lak")

    def test_is_integer_like(self):
        self.assertTrue(sem.is_integer_like([1, 2, 3.0]))
        self.assertFalse(sem.is_integer_like([1, 2.5]))
        self.assertFalse(sem.is_integer_like([]))

    def test_find_denominator_for_coverage(self):
        columns = [
            sem.infer("Dân số", [1], True),
            sem.infer("Dân số mục tiêu", [1], True),
            sem.infer("Bao phủ 2026 (%)", [50.0], True),
        ]
        self.assertEqual(sem.find_denominator("Bao phủ 2026 (%)", columns),
                         "Dân số mục tiêu")

    def test_find_denominator_returns_none_without_counts(self):
        columns = [sem.infer("Bao phủ 2026 (%)", [50.0], True)]
        self.assertIsNone(sem.find_denominator("Bao phủ 2026 (%)", columns))

    # the stat keys come from the module itself, so a rename in
    # describe_columns cannot silently disable the arithmetic check again
    @staticmethod
    def _count(name: str, total: float) -> dict:
        return dict(sem.infer(name, [1], True), **{sem.STAT_SUM: total})

    @staticmethod
    def _rate(name: str, median: float) -> dict:
        return dict(sem.infer(name, [median], True), **{sem.STAT_MEDIAN: median})

    @staticmethod
    def _series(**columns):
        return {name.replace("__", " "): values for name, values in columns.items()}

    def test_arithmetic_beats_naming(self):
        """A rate is named after its numerator, so words alone pick the wrong column."""
        managed = [900, 400, 1200]
        screened = [600, 260, 900]
        rate = [round(s / m * 100, 1) for s, m in zip(screened, managed)]
        columns = [
            self._count("Số người nhiễm HIV được sàng lọc lao", sum(screened)),
            self._count("Số người nhiễm HIV đang quản lý", sum(managed)),
            self._rate("Tỷ lệ sàng lọc lao (%)", rate[0]),
        ]
        series = {"Số người nhiễm HIV được sàng lọc lao": screened,
                  "Số người nhiễm HIV đang quản lý": managed,
                  "Tỷ lệ sàng lọc lao (%)": rate}
        self.assertEqual(
            sem.find_denominator("Tỷ lệ sàng lọc lao (%)", columns, series),
            "Số người nhiễm HIV đang quản lý")

    def test_target_not_uptake_weights_a_coverage_rate(self):
        users, target = [4000, 1500, 900], [9000, 2500, 3000]
        rate = [round(u / t * 100, 1) for u, t in zip(users, target)]
        columns = [
            self._count("Số người dùng PrEP 2026", sum(users)),
            self._count("Chỉ tiêu PrEP 2026", sum(target)),
            self._rate("Tỷ lệ bao phủ PrEP (%)", rate[0]),
        ]
        series = {"Số người dùng PrEP 2026": users, "Chỉ tiêu PrEP 2026": target,
                  "Tỷ lệ bao phủ PrEP (%)": rate}
        self.assertEqual(sem.find_denominator("Tỷ lệ bao phủ PrEP (%)", columns, series),
                         "Chỉ tiêu PrEP 2026")

    def test_a_rate_per_100000_uses_its_own_multiplier(self):
        cases, population = [12, 40, 7], [120_000, 260_000, 80_000]
        rate = [round(c / p * 100_000, 1) for c, p in zip(cases, population)]
        columns = [
            self._count("Số ca HIV mới phát hiện 2026", sum(cases)),
            self._count("Dân số", sum(population)),
            self._rate("Tỷ suất ca mới/100.000 dân", rate[0]),
        ]
        series = {"Số ca HIV mới phát hiện 2026": cases, "Dân số": population,
                  "Tỷ suất ca mới/100.000 dân": rate}
        self.assertEqual(sem.find_denominator("Tỷ suất ca mới/100.000 dân", columns, series),
                         "Dân số")

    def test_no_pair_reproduces_the_rate_so_naming_decides(self):
        """The real denominator of the ART cascade is simply not a column here."""
        on_art, estimated = [800, 300], [1000, 420]
        rate = [93.1, 88.4]          # denominator is 'people who know their status'
        columns = [
            self._count("Số người đang điều trị ARV", sum(on_art)),
            self._count("Số người nhiễm HIV ước tính", sum(estimated)),
            self._rate("Tỷ lệ điều trị ARV (%)", rate[0]),
        ]
        series = {"Số người đang điều trị ARV": on_art,
                  "Số người nhiễm HIV ước tính": estimated,
                  "Tỷ lệ điều trị ARV (%)": rate}
        chosen = sem.find_denominator("Tỷ lệ điều trị ARV (%)", columns, series)
        self.assertIn(chosen, {"Số người đang điều trị ARV", "Số người nhiễm HIV ước tính"})

    def test_falls_back_to_the_curated_hint_without_any_data(self):
        columns = [
            sem.infer("Dân số", [1], True),
            sem.infer("Số người xét nghiệm HIV 2026", [1], True),
        ]
        self.assertEqual(sem.find_denominator("Tỷ lệ dương tính (%)", columns),
                         "Số người xét nghiệm HIV 2026")

    def test_rate_multiplier(self):
        percent = sem.infer("Bao phủ (%)", [50.0], True)
        unit = sem.infer("Tỷ lệ dương tính", [0.05], True)
        per_100k = sem.infer("Tỷ suất/100.000 dân", [42.0], True)
        self.assertEqual(sem.rate_multiplier(percent), 100.0)
        self.assertEqual(sem.rate_multiplier(unit), 1.0)
        self.assertEqual(sem.rate_multiplier(per_100k), 100_000.0)


class TestOrderCategories(unittest.TestCase):
    def test_priority_scale_is_ordered_by_meaning(self):
        """Alphabetical order would read 'Cao, Rất cao, Thường quy'."""
        self.assertEqual(sem.order_categories(["Cao", "Rất cao", "Thường quy"]),
                         ["Thường quy", "Cao", "Rất cao"])

    def test_pass_fail_scale(self):
        self.assertEqual(sem.order_categories(["Vượt", "Chưa đạt", "Đạt"]),
                         ["Chưa đạt", "Đạt", "Vượt"])

    def test_unordered_categories_return_none(self):
        self.assertIsNone(sem.order_categories(["Đơn vị A", "Đơn vị B", "Đơn vị C"]))

    def test_single_category_is_not_a_scale(self):
        self.assertIsNone(sem.order_categories(["Cao"]))


class TestFormatValue(unittest.TestCase):
    def setUp(self):
        self.count = sem.infer("Số ca phát hiện 2026", [1, 2], True)
        self.percent = sem.infer("Bao phủ 2026 (%)", [51.3, 86.0], True)
        self.unit_percent = sem.infer("Tỷ lệ dương tính", [0.04], True)
        self.rate = sem.infer("Tỷ suất/100.000 dân", [42.7], True)
        self.point = sem.infer("Thay đổi (điểm %)", [-6.3], True)

    def test_counts_group_digits_and_drop_decimals(self):
        self.assertEqual(sem.format_value(1234, self.count), "1.234")
        self.assertEqual(sem.format_value(46.5, self.count), "46")

    def test_percent_carries_a_sign(self):
        self.assertEqual(sem.format_value(86.0, self.percent), "86%")
        self.assertEqual(sem.format_value(51.34, self.percent), "51,3%")

    def test_unit_scale_percent_is_multiplied(self):
        self.assertEqual(sem.format_value(0.04, self.unit_percent), "4%")

    def test_rate_per_capita_never_gets_a_percent_sign(self):
        self.assertNotIn("%", sem.format_value(310.5, self.rate))

    def test_percentage_point_is_signed(self):
        self.assertEqual(sem.format_value(15.2, self.point), "+15,2 điểm %")
        self.assertEqual(sem.format_value(-6.3, self.point), "-6,3 điểm %")

    def test_percentage_point_never_prints_minus_zero(self):
        """-0.4 rounded to whole points used to render as '-0 điểm %'."""
        self.assertEqual(sem.format_value(-0.4, self.point, decimals=0), "0 điểm %")

    def test_english_unit_for_percentage_point(self):
        self.assertEqual(sem.format_value(15.2, self.point, lang="en"), "+15.2 pp")

    def test_missing_value(self):
        self.assertEqual(sem.format_value(None, self.count), "–")

    def test_category_string_passes_through(self):
        """Formatting a category used to raise ValueError and kill the render."""
        category = sem.infer("Mức ưu tiên", ["Cao", "Thấp"], False)
        self.assertEqual(sem.format_value("Rất cao", category), "Rất cao")


class TestDigitSeparators(unittest.TestCase):
    """One page, one meaning per character.

    The Vietnamese edition printed "5.576" in the circle legend and "89.9%" in
    the colour legend of the same plate, so a dot grouped thousands in one place
    and marked the decimal in the other, with nothing on the page to say which.
    The cause was a half-finished fix: an earlier pass localised the thousands
    separator and left every decimal in the C convention.
    """

    def setUp(self):
        self.count = sem.infer("Số người đang điều trị ARV", [669, 5576], True)
        self.percent = sem.infer("Tỷ lệ ức chế (%)", [88.0, 89.9], True)
        self.rate = sem.infer("Tỷ suất ca mới/100.000 dân", [1234.5], True)

    def test_vietnamese_groups_with_a_dot_and_marks_decimals_with_a_comma(self):
        self.assertEqual(sem.format_value(5576, self.count, lang="vi"), "5.576")
        self.assertEqual(sem.format_value(89.94, self.percent, lang="vi"), "89,9%")

    def test_english_is_the_other_way_round(self):
        self.assertEqual(sem.format_value(5576, self.count, lang="en"), "5,576")
        self.assertEqual(sem.format_value(89.94, self.percent, lang="en"), "89.9%")

    def test_one_number_carrying_both_separators(self):
        self.assertEqual(sem.format_value(1234.5, self.rate, lang="vi"), "1.234,5")
        self.assertEqual(sem.format_value(1234.5, self.rate, lang="en"), "1,234.5")

    def test_a_grouped_whole_number_keeps_its_zeros(self):
        """Stripping trailing zeros off "1,200" used to leave "1,2"."""
        unknown = sem._pack(sem.UNKNOWN, "Chỉ số không rõ", "")
        self.assertEqual(sem.format_value(1200, unknown, decimals=0, lang="vi"), "1.200")

    def test_the_scale_bar_follows_the_same_convention(self):
        """It was hard-wired to Vietnamese, so an English map read 1.000 km."""
        from emap import furniture

        self.assertEqual(furniture._km(1_000_000, "vi"), "1.000 km")
        self.assertEqual(furniture._km(1_000_000, "en"), "1,000 km")
class TestADiacriticIsTheOnlyDifference(unittest.TestCase):
    """Vietnamese period words that collide with ordinary words once stripped.

    The name matching runs on the deaccented heading, because exports are
    inconsistent about diacritics. That is right for `period`, `fiscal` and
    `kỳ báo cáo`, and wrong for five words where the accent carries the whole
    meaning:

        năm year    · nam   male, south
        quý quarter · quy   rule, scale
        tháng month · thang ladder, scale
        ngày day    · ngay  straight
        tuần week   · tuấn  a given name

    Measured before the fix: six of seventeen headings came back as periods,
    among them a province-name column. The whole suite was green throughout —
    nothing here had ever been asked.
    """

    def semantic(self, column, values, numeric=True):
        return sem.infer(column, values, numeric)["semantic"]

    def test_a_column_of_men_is_not_a_column_of_years(self):
        """The heading that started this: `Số ca phát hiện - Nam`."""
        self.assertEqual(self.semantic("Số ca phát hiện - Nam", [128, 141, 76]), sem.COUNT)
        self.assertEqual(self.semantic("Số ca phát hiện - Nữ", [94, 88, 52]), sem.COUNT)

    def test_a_province_name_column_is_not_a_period(self):
        """`Tỉnh Nam Định` read as a period is a place column lost."""
        self.assertNotEqual(self.semantic("Tỉnh Nam Định", ["x", "y"], numeric=False),
                            sem.TIME)
        self.assertNotEqual(self.semantic("Miền Nam", ["có", "không"], numeric=False),
                            sem.TIME)

    def test_the_other_three_collisions(self):
        for column, values in (("Quy mô dân số", [4995214, 3619443]),
                               ("Thang điểm đánh giá", [4, 5, 3]),
                               ("Tuấn Anh phụ trách", [1, 2])):
            with self.subTest(column=column):
                self.assertNotEqual(self.semantic(column, values), sem.TIME)

    def test_the_accented_spelling_is_still_a_period(self):
        for column, values in (("Năm", [2019, 2020, 2021]),
                               ("Năm báo cáo", [2025, 2026]),
                               ("Tuần dịch tễ", [1, 2, 3])):
            with self.subTest(column=column):
                self.assertEqual(self.semantic(column, values), sem.TIME)
        for column, values in (("Kỳ báo cáo", ["Năm 2026"]), ("Tháng", ["2025-10"]),
                               ("Quý", ["Quý I", "Quý II"])):
            with self.subTest(column=column):
                self.assertEqual(self.semantic(column, values, numeric=False), sem.TIME)

    def test_english_period_words_are_untouched(self):
        """The PEPFAR export names its periods in English and must keep working."""
        self.assertEqual(self.semantic("Fiscal Year", ["2025", "2026"], numeric=False),
                         sem.TIME)
        self.assertEqual(self.semantic("Quarter", ["Q1", "Q2"], numeric=False), sem.TIME)

    def test_a_heading_with_no_diacritics_at_all_still_matches(self):
        """Someone typing without accents means what they typed. The bare
        spelling counts when there is nothing else to go on."""
        self.assertEqual(self.semantic("Nam 2026", [2026]), sem.TIME)
        self.assertEqual(self.semantic("nam bao cao", [2019, 2020]), sem.TIME)

    def test_the_numbers_have_to_look_like_periods(self):
        """A heading is a hint; the values are the evidence. `Nam` with counts
        in it is not a year column however it was spelled."""
        self.assertEqual(self.semantic("Nam", [128, 141, 76]), sem.COUNT)
        self.assertEqual(self.semantic("Quy", [7, 9, 30]), sem.COUNT)

    def test_a_quantity_outranks_a_timeframe(self):
        """`Số ca mắc trong ngày` carries the word for day, but it counts cases."""
        self.assertEqual(self.semantic("Số ca mắc trong ngày", [12, 8, 5]), sem.COUNT)
        self.assertEqual(self.semantic("Số ngày điều trị", [30, 60]), sem.COUNT)

    def test_the_identifier_keywords_actually_fire(self):
        """`_has` matches whole words, so `"ma "` compiled to a pattern demanding
        a non-word character after the space — it could never match. Every
        Vietnamese code column fell through to `category`, and a category is
        mappable, so the skill would offer to colour a map by province code."""
        for column in ("Mã ĐV", "Mã tỉnh", "Mã", "ma tinh",
                       "Số hiệu", "Ký hiệu", "Code", "ID"):
            with self.subTest(column=column):
                self.assertEqual(self.semantic(column, ["A1", "B2"], numeric=False),
                                 sem.IDENTIFIER)

    def test_the_identifier_word_carries_its_diacritic_too(self):
        """mã (code) against má and mà — the same collision, the same rule."""
        for column in ("Má hồng", "Mà thôi"):
            with self.subTest(column=column):
                self.assertNotEqual(self.semantic(column, ["a", "b"], numeric=False),
                                    sem.IDENTIFIER)

    def test_no_keyword_ends_in_a_separator(self):
        """The defect above as a rule, so it cannot come back in another list.

        A keyword ending in a space or an underscore is dead on arrival, because
        the matcher requires a word boundary immediately after it.
        """
        lists = {"_TIME_WORDS": sem._TIME_WORDS, "_ID_WORDS": sem._ID_WORDS,
                 "_COUNT_WORDS": sem._COUNT_WORDS, "_PERCENT_WORDS": sem._PERCENT_WORDS,
                 "_RATE_WORDS": sem._RATE_WORDS, "_MONEY_WORDS": sem._MONEY_WORDS,
                 "_SCORE_WORDS": sem._SCORE_WORDS, "_LON_WORDS": sem._LON_WORDS,
                 "_LAT_WORDS": sem._LAT_WORDS, "_POINT_WORDS": sem._POINT_WORDS}
        for name, words in lists.items():
            for word in words:
                with self.subTest(list=name, word=word):
                    self.assertEqual(word, word.strip(" _"),
                                     f"{name}: {word!r} can never match")


if __name__ == "__main__":
    unittest.main()


class TestPuttingGroupsInTheirOwnOrder(unittest.TestCase):
    """``order_categories``: a ranking the data has, not one the alphabet has.

    The legend that prompted this read "Cao, Rất cao, Thường quy" - alphabetical
    order shown with a low-to-high colour ramp, which is a ranking the map
    invented. Recognising the scale is only half of it; the other half is
    admitting when it has not been recognised, which ``guardrails`` now does.
    """

    def test_a_known_vietnamese_scale_is_ordered_by_meaning(self):
        from emap import semantics as sem

        self.assertEqual(sem.order_categories(["Cao", "Rất cao", "Thường quy"]),
                         ["Thường quy", "Cao", "Rất cao"])

    def test_english_scales_are_known_too(self):
        """The map text can be either language, and "Good, High, Low, Medium"
        is exactly as wrong as its Vietnamese equivalent."""
        from emap import semantics as sem

        self.assertEqual(sem.order_categories(["High", "Low", "Medium"]),
                         ["Low", "Medium", "High"])
        self.assertEqual(sem.order_categories(["Agree", "Strongly agree",
                                               "Disagree"]),
                         ["Disagree", "Agree", "Strongly agree"])

    def test_accents_and_capitals_do_not_hide_a_known_scale(self):
        from emap import semantics as sem

        self.assertIsNotNone(sem.order_categories(["THẤP", "cao", "Trung Bình"]))

    def test_a_rank_written_into_the_label_is_read_off_it(self):
        """Whoever exported the column already stated the order. Reading it is
        more reliable than any table of words can be."""
        from emap import semantics as sem

        self.assertEqual(
            sem.order_categories(["3) Cao", "1. Thấp", "2 - Trung bình"]),
            ["1. Thấp", "2 - Trung bình", "3) Cao"])
        self.assertEqual(sem.order_categories(["C. Tốt", "A. Kém", "B. Khá"]),
                         ["A. Kém", "B. Khá", "C. Tốt"])

    def test_a_rank_that_repeats_is_not_a_rank(self):
        """Two groups both numbered 1 cannot be ordered by their numbers, and
        guessing which came first would be inventing the answer."""
        from emap import semantics as sem

        self.assertIsNone(sem.order_categories(["1. Thấp", "1. Cao"]))

    def test_the_written_rank_wins_over_the_words(self):
        """If the export says 1, 2, 3 and the words say otherwise, the export
        is the one that knows this dataset."""
        from emap import semantics as sem

        self.assertEqual(sem.order_categories(["1. Cao", "2. Thấp"]),
                         ["1. Cao", "2. Thấp"])

    def test_genuinely_unordered_groups_return_nothing(self):
        """Nothing, not a guess. The caller then uses the qualitative palette,
        which does not imply a ranking."""
        from emap import semantics as sem

        self.assertIsNone(sem.order_categories(["Hà Nội", "Đà Nẵng", "Cần Thơ"]))
        self.assertIsNone(sem.order_categories(["Vùng xanh", "Vùng đỏ",
                                                "Vùng cam"]))

    def test_one_group_is_not_a_scale(self):
        from emap import semantics as sem

        self.assertIsNone(sem.order_categories(["Cao"]))


class TestOnWhatGroundsAWeightingColumnWasChosen(unittest.TestCase):
    """``denominator``: the column, and whether it was proved or guessed.

    A rate's weighting column is its denominator. Where the numbers are at hand
    the engine reproduces the rate row by row and the answer is arithmetic;
    where they are not it matches column headings, and a heading match can pick
    the rate's own numerator. Measured on a real provincial HIV sheet: four of
    seven rates were named-matched, and two of those took their numerator.

    The grounds travel with the answer because the two are not interchangeable,
    and returning only the column made them look the same to every caller.
    """

    def columns(self):
        return [
            {"column": "Tỷ lệ điều trị ARV (%)", "semantic": sem.PERCENT},
            {"column": "Số người đang điều trị ARV", "semantic": sem.COUNT,
             "total": 900},
            {"column": "Số người nhiễm HIV ước tính", "semantic": sem.COUNT,
             "total": 1200},
            {"column": "Dân số", "semantic": sem.COUNT, "total": 100000},
        ]

    def test_arithmetic_that_reproduces_the_rate_is_proof(self):
        """Two counts whose quotient is the rate, row by row. Nothing about the
        headings enters into it."""
        found = sem.denominator(
            "Tỷ lệ điều trị ARV (%)", self.columns(),
            {"Tỷ lệ điều trị ARV (%)": [50.0, 25.0, 80.0],
             "Số người đang điều trị ARV": [50, 25, 80],
             "Số người nhiễm HIV ước tính": [100, 100, 100],
             "Dân số": [7, 13, 29]})
        self.assertEqual(found.column, "Số người nhiễm HIV ước tính")
        self.assertEqual(found.basis, sem.FITTED)
        self.assertIn(found.basis, sem.PROVEN)

    def test_without_the_numbers_it_falls_back_to_the_headings_and_says_so(self):
        found = sem.denominator("Tỷ lệ điều trị ARV (%)", self.columns())
        self.assertEqual(found.basis, sem.BY_NAME)
        self.assertNotIn(found.basis, sem.PROVEN)

    def test_the_named_match_can_pick_the_rates_own_numerator(self):
        """Not a hypothetical: this is the case that prompted the warning. The
        heading of a coverage rate shares its words with the count of people
        already covered."""
        found = sem.denominator("Tỷ lệ điều trị ARV (%)", self.columns())
        self.assertEqual(found.column, "Số người đang điều trị ARV")

    def test_a_sheet_with_no_counts_has_no_denominator_and_no_grounds(self):
        found = sem.denominator("Tỷ lệ (%)",
                                [{"column": "Tỷ lệ (%)", "semantic": sem.PERCENT}])
        self.assertEqual(found, (None, sem.NONE))

    def test_the_old_name_still_answers_with_the_column_alone(self):
        """Callers that have no use for the grounds keep working, and there is
        one implementation rather than two that can drift."""
        columns = self.columns()
        self.assertEqual(sem.find_denominator("Tỷ lệ điều trị ARV (%)", columns),
                         sem.denominator("Tỷ lệ điều trị ARV (%)", columns).column)


class TestTheHeadingAboveTheColourKey(unittest.TestCase):
    """Where a unit goes when the class labels have no room for one.

    ``axis_suffix`` was written and wired to nothing for a long time. Measured
    on real labels: a rate legend reads ``3–12``, ``12–25`` with no unit among
    the classes, while a percentage reads ``6%–10%`` and needs no help.

    Said plainly, because the first account of this overstated it: on both HIV
    workbooks every rate column is *named* after its unit, so the heading
    already carried it and this changes nothing there. It is a safety net for a
    column whose semantic comes from the workbook's data dictionary rather than
    from its own name.
    """

    def heading(self, column, info, stated=None, map_type="choropleth"):
        import argparse

        import easy_map

        args = argparse.Namespace(legend_title=stated, map_type=map_type)
        return easy_map._legend_heading(args, column, info, "vi")

    def rate(self, unit="trên 100.000 dân"):
        return {"semantic": sem.RATE_PER, "unit": unit}

    def test_a_rate_whose_name_omits_the_unit_gets_it_in_the_heading(self):
        self.assertEqual(self.heading("Số ca mới", self.rate()),
                         "Số ca mới (trên 100.000 dân)")

    def test_a_rate_already_named_after_its_unit_is_left_alone(self):
        """Compared word by word. Testing for the unit verbatim produced
        ``Tỷ suất ca mới/100.000 dân (trên 100.000 dân)`` on real data — the
        same fact twice, because one writes "/100.000 dân" and the other
        "trên 100.000 dân"."""
        self.assertEqual(self.heading("Tỷ suất ca mới/100.000 dân", self.rate()),
                         "Tỷ suất ca mới/100.000 dân")

    def test_a_different_denominator_is_still_worth_saying(self):
        """Per thousand and per hundred thousand differ by nothing but the
        digits, and ``_tokens`` drops digits — so they are compared apart."""
        self.assertEqual(
            self.heading("Tỷ suất ca mới/1.000 dân", self.rate()),
            "Tỷ suất ca mới/1.000 dân (trên 100.000 dân)")

    def test_a_heading_that_names_the_number_but_not_the_thing_counted(self):
        """The words matter on their own, not only the digits.

        Removing the word comparison left every test above green, because in
        each of them the digits already settled it. This is the case where they
        do not: the heading says 100.000 and never says of what.
        """
        self.assertEqual(self.heading("Chỉ số trên 100.000", self.rate()),
                         "Chỉ số trên 100.000 (trên 100.000 dân)")

    def test_a_percentage_is_left_as_it_was(self):
        """``6%–10%`` carries its own mark. Moving it would change every
        percentage map already in circulation for no gain."""
        pct = {"semantic": sem.PERCENT, "unit": "%"}
        self.assertEqual(self.heading("Tỷ lệ dương tính (%)", pct),
                         "Tỷ lệ dương tính (%)")

    def test_a_percentage_is_left_alone_even_when_its_name_omits_the_sign(self):
        """The one that separates "percentages are excluded" from "the sign
        happens to add nothing": with the exclusion removed, every test above
        still passed, because ``%`` has no words and no digits to compare."""
        pct = {"semantic": sem.PERCENT, "unit": "%"}
        self.assertEqual(self.heading("Tỷ lệ dương tính", pct),
                         "Tỷ lệ dương tính")

    def test_a_count_gets_nothing_added(self):
        self.assertEqual(self.heading("Dân số", {"semantic": sem.COUNT}),
                         "Dân số")

    def test_money_is_left_alone_although_it_has_a_unit(self):
        """This is what the rate-only rule is actually for.

        Removing it does not change a percentage — ``%`` has no words and no
        digits, so the duplicate check declines it anyway — but it does change
        money, whose unit is words. The scope agreed was rates; a money map
        gaining "(triệu đồng)" in its heading was not asked for.
        """
        money = {"semantic": sem.MONEY, "unit": "triệu đồng"}
        self.assertEqual(self.heading("Kinh phí chương trình", money),
                         "Kinh phí chương trình")

    def test_a_heading_the_caller_wrote_is_never_touched(self):
        """They have already said what they wanted. Appending to it is how a
        heading ends up reading "Cases per 100,000 (per 100,000)"."""
        self.assertEqual(self.heading("x", self.rate(), stated="Chữ của tôi"),
                         "Chữ của tôi")

    def test_a_change_map_keeps_its_own_wording(self):
        self.assertNotEqual(self.heading("x", self.rate(), map_type="change"), "x")

    def test_axis_suffix_is_no_longer_wired_to_nothing(self):
        """It sat unused long enough to look like working API. Whatever else
        changes, something has to call it."""
        import inspect

        import easy_map

        self.assertIn("heading_unit", inspect.getsource(easy_map._legend_heading))
        self.assertIn("axis_suffix", inspect.getsource(sem.heading_unit))
