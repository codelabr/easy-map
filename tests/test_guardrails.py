"""The warnings, and the arithmetic that decides whether each one fires.

Six of the fifteen checks were covered, spread across other files that happened
to need them. The nine here had none, which for this module is the worst place
to have none: a guardrail nobody exercises is indistinguishable from a guardrail
that never fires, and the whole agreed behaviour — warn, propose, then do what
the user decides — rests on the first word.

Each test names the decision, not the function. What is pinned is the boundary:
the share at which coverage becomes critical rather than a warning, the number
of units that makes a class count too many, the ratio at which circles stop
being marks on a map and start being the map.
"""

from __future__ import annotations

import pathlib
import unittest

import context  # noqa: F401  (path bootstrap)
from emap import guardrails as g
from emap import messages as msg
from emap import semantics as sem


class TestHowMuchOfTheMapHasNumbers(unittest.TestCase):
    """``check_coverage``: a map drawn from a third of its units is a map of
    where the reporting is, not of what it claims to show."""

    def test_a_full_map_says_nothing(self):
        self.assertEqual(g.check_coverage(34, 34), [])

    def test_just_above_the_line_says_nothing(self):
        """35% is the line, and the line itself is quiet."""
        self.assertEqual(g.check_coverage(35, 100), [])

    def test_just_below_the_line_is_a_warning(self):
        found = g.check_coverage(34, 100)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], g.WARNING)
        self.assertEqual(found[0]["share"], 0.34)

    def test_below_fifteen_percent_is_critical(self):
        """The two thresholds are different judgements, not one with a margin:
        a third of the units missing is a caveat, six sevenths is a different
        map."""
        self.assertEqual(g.check_coverage(14, 100)[0]["severity"], g.CRITICAL)
        self.assertEqual(g.check_coverage(15, 100)[0]["severity"], g.WARNING)

    def test_an_empty_frame_is_not_a_division_by_zero(self):
        self.assertEqual(g.check_coverage(0, 0), [])

    def test_the_sentence_carries_both_counts_and_the_share(self):
        """"Coverage is low" is not actionable; "12 of 100" is."""
        found = g.check_coverage(12, 100)[0]
        self.assertIn("12", found["problem"])
        self.assertIn("100", found["problem"])
        self.assertIn("12%", found["problem"])


class TestWhenRowsShareAPlaceName(unittest.TestCase):
    """``check_aggregation``: which combining rule is safe for which column."""

    RATE = {"column": "Tỷ lệ dương tính", "semantic": sem.PERCENT}
    COUNT = {"column": "Số ca", "semantic": sem.COUNT}

    def test_nothing_to_combine_means_nothing_to_warn_about(self):
        self.assertEqual(g.check_aggregation(self.RATE, "sum", 0), [])

    def test_summing_a_rate_is_critical(self):
        """Two communes at 10% do not make a district at 20%."""
        found = g.check_aggregation(self.RATE, "sum", 3)
        self.assertEqual(found[0]["id"], "summing-a-rate")
        self.assertEqual(found[0]["severity"], g.CRITICAL)

    def test_summing_a_count_is_fine(self):
        self.assertEqual(g.check_aggregation(self.COUNT, "sum", 3), [])

    def test_averaging_a_rate_without_weights_is_a_warning(self):
        found = g.check_aggregation(self.RATE, "mean", 3)
        self.assertEqual(found[0]["id"], "unweighted-mean")
        self.assertEqual(found[0]["severity"], g.WARNING)

    def test_averaging_a_rate_with_weights_is_quiet(self):
        """The weighted mean is the right answer, so saying nothing is the
        right response — a warning here would train the reader to skip them."""
        weighted = dict(self.RATE, weight_column="Số xét nghiệm")
        self.assertEqual(g.check_aggregation(weighted, "mean", 3), [])


class TestColouringByASizeRatherThanARate(unittest.TestCase):
    """``check_colour_choice``: shading by a raw count draws the population."""

    COUNT = {"column": "Số ca HIV", "semantic": sem.COUNT}

    def test_shading_a_count_is_a_warning(self):
        found = g.check_colour_choice(self.COUNT, "choropleth")
        self.assertEqual(found[0]["id"], "colour-by-count")

    def test_a_count_in_the_circles_is_not(self):
        """Circle area for a count is the correct pairing; only the fill is
        wrong. A map keyed by both must warn about the fill alone."""
        self.assertEqual(g.check_colour_choice(self.COUNT, "graduated-symbol"), [])

    def test_a_rate_in_the_fill_is_what_the_fill_is_for(self):
        rate = {"column": "Tỷ lệ", "semantic": sem.PERCENT}
        self.assertEqual(g.check_colour_choice(rate, "choropleth"), [])

    def test_money_counts_as_a_size_too(self):
        money = {"column": "Kinh phí (triệu đồng)", "semantic": sem.MONEY}
        self.assertTrue(g.check_colour_choice(money, "choropleth"))


class TestHowManyClassesTheDataCanCarry(unittest.TestCase):
    """``most_classes`` and ``check_classes``."""

    def test_roughly_three_units_to_a_class(self):
        self.assertEqual(g.most_classes(30), 10)
        self.assertEqual(g.most_classes(34), 11)

    def test_never_fewer_than_two(self):
        """A one-class map is a single flat colour, which is not a map."""
        self.assertEqual(g.most_classes(0), 2)
        self.assertEqual(g.most_classes(3), 2)

    def test_the_advice_names_the_ceiling_for_this_map(self):
        """A reader of eight communes was once told to reduce to three classes
        while using three. The suggestion has to be computed from their own
        unit count, not from a constant."""
        found = g.check_classes({"classes": 5, "edges": [0, 1, 2, 3, 4, 5]}, 8)
        warning = next(i for i in found if i["id"] == "too-many-classes")
        joined = " ".join(str(v) for v in warning.values())
        self.assertIn("2", joined)

    def test_a_class_count_within_reach_is_quiet(self):
        found = g.check_classes({"classes": 5, "edges": [0, 1, 2, 3, 4, 5]}, 34)
        self.assertEqual([i for i in found if i["id"] == "too-many-classes"], [])

    def test_notes_from_the_classifier_are_passed_through_as_information(self):
        """``classify`` merges classes it could not fill. That is not a fault
        to be warned about, but the reader has to be told the legend they are
        looking at is not the one they asked for."""
        found = g.check_classes({"classes": 3, "notes": ["gộp hai nhóm hẹp"]}, 34)
        self.assertEqual(found[0]["id"], "classes-adjusted")
        self.assertEqual(found[0]["severity"], g.INFO)


class TestAPercentageThatIsNotOne(unittest.TestCase):
    """``check_percent_range``: values outside 0–100 in a column read as one."""

    PCT = {"column": "Tỷ lệ dương tính", "semantic": sem.PERCENT}

    def test_an_ordinary_range_is_quiet(self):
        self.assertEqual(g.check_percent_range([0.0, 12.5, 100.0], self.PCT), [])

    def test_over_a_hundred_is_a_warning(self):
        found = g.check_percent_range([12.0, 140.0], self.PCT)
        self.assertEqual([i["id"] for i in found], ["percent-over-100"])

    def test_a_half_point_of_rounding_is_not_a_fault(self):
        """100.4 is a rounded 100. Reporting it would fire on real data that
        is merely displayed to one decimal."""
        self.assertEqual(g.check_percent_range([100.4], self.PCT), [])

    def test_a_negative_percentage_is_its_own_warning(self):
        found = g.check_percent_range([-3.0, 40.0], self.PCT)
        self.assertEqual([i["id"] for i in found], ["percent-negative"])

    def test_both_ends_can_be_wrong_at_once(self):
        found = g.check_percent_range([-3.0, 140.0], self.PCT)
        self.assertEqual([i["id"] for i in found],
                         ["percent-over-100", "percent-negative"])

    def test_a_column_stored_as_a_fraction_is_scaled_before_judging(self):
        """0.85 in a unit-scaled column is 85%, not a violation; 1.4 is 140%
        and is one. Judging the raw number would get both backwards."""
        unit = dict(self.PCT, scale="unit")
        self.assertEqual(g.check_percent_range([0.85], unit), [])
        self.assertEqual([i["id"] for i in g.check_percent_range([1.4], unit)],
                         ["percent-over-100"])

    def test_a_column_that_is_not_a_percentage_is_not_checked(self):
        count = {"column": "Số ca", "semantic": sem.COUNT}
        self.assertEqual(g.check_percent_range([-3.0, 5000.0], count), [])

    def test_a_column_of_blanks_is_not_a_fault(self):
        self.assertEqual(g.check_percent_range([None, None], self.PCT), [])


class TestDrawingMoreThanOnePeriodAtOnce(unittest.TestCase):
    """``check_periods``: one plate showing 2024 and 2025 stacked together."""

    def test_one_period_is_the_normal_case(self):
        self.assertEqual(g.check_periods(["Năm 2025"] * 34), [])

    def test_two_periods_on_one_plate_is_critical(self):
        found = g.check_periods(["Năm 2024", "Năm 2025", "Năm 2025"])
        self.assertEqual(found[0]["severity"], g.CRITICAL)

    def test_the_periods_are_named_so_the_reader_can_pick_one(self):
        found = g.check_periods(["Quý I/2025", "Quý II/2025"])
        self.assertEqual(found[0]["periods"], ["Quý I/2025", "Quý II/2025"])

    def test_blanks_are_not_a_period_of_their_own(self):
        """A column with one real period and some empty cells is one period."""
        self.assertEqual(g.check_periods(["Năm 2025", None, "Năm 2025"]), [])

    def test_the_list_of_periods_is_capped(self):
        """A daily column would otherwise put a year of dates into the JSON the
        agent has to read back to the user."""
        found = g.check_periods([f"2025-{d:03d}" for d in range(300)])
        self.assertEqual(len(found[0]["periods"]), 24)


class TestCirclesLargeEnoughToBeTheMap(unittest.TestCase):
    """``check_symbol_occlusion``: a mark wider than the unit it sits on."""

    def test_a_mark_well_inside_its_unit_is_quiet(self):
        self.assertEqual(g.check_symbol_occlusion(1_000.0, 20_000.0), [])

    def test_a_mark_wider_than_its_unit_is_a_warning(self):
        self.assertTrue(g.check_symbol_occlusion(20_000.0, 10_000.0))

    def test_the_line_is_drawn_on_diameter_against_unit_width(self):
        """Radius 8 is diameter 16, which is 1.6 units wide — the boundary, and
        the boundary is quiet. A hair more is not."""
        self.assertEqual(g.check_symbol_occlusion(8.0, 10.0), [])
        self.assertTrue(g.check_symbol_occlusion(8.1, 10.0))

    def test_a_map_with_no_circles_is_not_measured(self):
        self.assertEqual(g.check_symbol_occlusion(0.0, 10_000.0), [])
        self.assertEqual(g.check_symbol_occlusion(1_000.0, 0.0), [])


class TestDataThatCrossesZero(unittest.TestCase):
    """``check_diverging``: percentage-point change wants a two-ended ramp."""

    POINTS = {"column": "Thay đổi", "semantic": sem.POINT}

    def test_values_on_both_sides_of_zero_suggest_a_diverging_scale(self):
        found = g.check_diverging([-4.0, 2.0], self.POINTS)
        self.assertEqual(found[0]["id"], "needs-diverging-scale")
        self.assertEqual(found[0]["severity"], g.INFO)

    def test_all_negative_does_not(self):
        """A sequential ramp is right when every unit moved the same way."""
        self.assertEqual(g.check_diverging([-4.0, -1.0], self.POINTS), [])

    def test_all_positive_does_not(self):
        self.assertEqual(g.check_diverging([1.0, 4.0], self.POINTS), [])

    def test_a_column_that_is_not_a_change_is_not_asked(self):
        pct = {"column": "Tỷ lệ", "semantic": sem.PERCENT}
        self.assertEqual(g.check_diverging([-4.0, 2.0], pct), [])


class TestPuttingTheWarningsInOrder(unittest.TestCase):
    """``summarize``: what the agent reads out, and in what order."""

    def _issues(self):
        return [{"severity": g.INFO, "id": "c"},
                {"severity": g.WARNING, "id": "b"},
                {"severity": g.CRITICAL, "id": "a"}]

    def test_the_most_serious_comes_first(self):
        out = g.summarize(self._issues())
        self.assertEqual([i["id"] for i in out["items"]], ["a", "b", "c"])

    def test_the_counts_are_by_severity_not_a_total_restated(self):
        out = g.summarize(self._issues())
        self.assertEqual((out["total"], out["critical"], out["warnings"]),
                         (3, 1, 1))

    def test_information_is_counted_in_the_total_and_in_neither_tally(self):
        """It is still something the reader is told; it is not something that
        should make a run look risky."""
        out = g.summarize([{"severity": g.INFO, "id": "c"}])
        self.assertEqual((out["total"], out["critical"], out["warnings"]),
                         (1, 0, 0))

    def test_a_clean_run_summarises_to_zero_rather_than_to_nothing(self):
        out = g.summarize([])
        self.assertEqual(out, {"total": 0, "critical": 0, "warnings": 0,
                               "items": []})

    def test_an_unknown_severity_sorts_last_instead_of_raising(self):
        """Nothing produces one today. If something does, the run should still
        finish and the reader should still see the warnings that are real."""
        out = g.summarize([{"severity": "novel", "id": "z"},
                           {"severity": g.CRITICAL, "id": "a"}])
        self.assertEqual([i["id"] for i in out["items"]], ["a", "z"])


class TestEveryWarningSpeaksBothLanguages(unittest.TestCase):
    """The module holds no sentences, and this is what makes that true.

    Each check is fired here in both languages and the two are required to
    differ — a key missing from one table falls back to the other, which would
    otherwise ship a Vietnamese warning into an English conversation without
    anything raising.
    """

    CASES = (
        ("low-coverage", lambda l: g.check_coverage(2, 100, lang=l)),
        ("summing-a-rate", lambda l: g.check_aggregation(
            {"column": "Tỷ lệ", "semantic": sem.PERCENT}, "sum", 3, lang=l)),
        ("unweighted-mean", lambda l: g.check_aggregation(
            {"column": "Tỷ lệ", "semantic": sem.PERCENT}, "mean", 3, lang=l)),
        ("colour-by-count", lambda l: g.check_colour_choice(
            {"column": "Số ca", "semantic": sem.COUNT}, "choropleth", lang=l)),
        ("percent-over-100", lambda l: g.check_percent_range(
            [140.0], {"column": "Tỷ lệ", "semantic": sem.PERCENT}, lang=l)),
        ("several-periods", lambda l: g.check_periods(["a", "b"], lang=l)),
        ("circles-hide-areas", lambda l: g.check_symbol_occlusion(
            20_000.0, 10_000.0, lang=l)),
        ("needs-diverging-scale", lambda l: g.check_diverging(
            [-1.0, 1.0], {"column": "Thay đổi", "semantic": sem.POINT}, lang=l)),
    )

    def test_each_check_speaks_both_languages(self):
        for key, fire in self.CASES:
            with self.subTest(key=key):
                vi = fire("vi")[0]
                en = fire("en")[0]
                self.assertEqual(vi["id"], key)
                self.assertNotEqual(vi["problem"], en["problem"],
                                    f"{key}: same sentence in both languages")

    def test_each_warning_says_what_is_wrong_why_it_matters_and_what_to_do(self):
        """Warn, propose, then do what the user decides. All three sentences
        have to be there: a warning with no ``fix`` leaves the reader holding a
        problem and no next move, and one with no ``why`` is a rule to obey
        rather than something they can weigh against what they know."""
        for key, fire in self.CASES:
            for lang in msg.LANGUAGES:
                issue = fire(lang)[0]
                for field in ("problem", "why", "fix"):
                    with self.subTest(key=key, lang=lang, field=field):
                        self.assertTrue(str(issue.get(field, "")).strip(),
                                        f"{key}/{lang}: no {field}")


class TestGroupsWhoseOrderNobodyKnows(unittest.TestCase):
    """``check_category_order``: say so rather than shipping the alphabet."""

    def test_an_unrecognised_scale_is_a_warning(self):
        found = g.check_category_order(["Vùng xanh", "Vùng đỏ", "Vùng cam"],
                                       recognised=False, stated=False)
        self.assertEqual(found[0]["id"], "categories-not-ordered")
        self.assertEqual(found[0]["severity"], g.WARNING)

    def test_a_recognised_scale_is_quiet(self):
        self.assertEqual(
            g.check_category_order(["Thấp", "Trung bình", "Cao"],
                                   recognised=True, stated=False), [])

    def test_an_order_the_caller_stated_is_quiet(self):
        """They have answered the question; repeating it would train them to
        skip warnings."""
        self.assertEqual(
            g.check_category_order(["Vùng xanh", "Vùng đỏ", "Vùng cam"],
                                   recognised=False, stated=True), [])

    def test_two_groups_need_no_order(self):
        """Any order of two is a pair, and the legend shows which is which."""
        self.assertEqual(
            g.check_category_order(["Có", "Không"], recognised=False,
                                   stated=False), [])

    def test_the_groups_are_named_so_the_reader_can_rank_them(self):
        found = g.check_category_order(["Vùng xanh", "Vùng đỏ", "Vùng cam"],
                                       recognised=False, stated=False)
        self.assertEqual(found[0]["groups"],
                         ["Vùng xanh", "Vùng đỏ", "Vùng cam"])
        self.assertIn("Vùng xanh", found[0]["problem"])

    def test_the_remedy_names_the_flag_that_exists(self):
        for lang in msg.LANGUAGES:
            with self.subTest(lang=lang):
                found = g.check_category_order(["a", "b", "c"], recognised=False,
                                               stated=False, lang=lang)
                self.assertIn("--category-order", found[0]["fix"])

    def test_repeats_are_counted_once(self):
        found = g.check_category_order(["a", "b", "a", "c", "b"],
                                       recognised=False, stated=False)
        self.assertIn("3", found[0]["problem"])


class TestAMapThatCouldNotNameItsUnits(unittest.TestCase):
    """``check_labels``: the reader cannot see the ceiling, so say where it fell.

    Measured on 126 Hà Nội communes: 35 lettered, 81 never reached placement
    because of the label ceiling, 10 more found nowhere to sit — and the only
    warning on that run was about colouring by a count. A reader gets a commune
    map with three quarters of the units unnamed and nothing saying so, which
    makes the named quarter look chosen.
    """

    def report(self, drawn, crowded=0):
        return {"drawn": drawn, "moved": 0, "skipped": [],
                "dropped_no_room": ["x"] * crowded, "name_only": []}

    def test_a_fully_lettered_map_says_nothing(self):
        self.assertEqual(g.check_labels(self.report(34), 34), [])

    def test_a_map_naming_most_of_its_units_says_nothing(self):
        """Some gaps are normal and the reader can see the map is crowded. The
        line is where the named units stop looking like the rule and start
        looking like a selection."""
        self.assertEqual(g.check_labels(self.report(21), 34), [])

    def test_naming_a_quarter_of_them_is_a_warning(self):
        found = g.check_labels(self.report(35, crowded=10), 126)
        self.assertEqual(found[0]["id"], "few-labels")
        self.assertEqual(found[0]["severity"], g.WARNING)
        self.assertEqual(found[0]["share_named"], round(35 / 126, 4))

    def test_naming_almost_none_of_them_is_critical(self):
        """Two different judgements, not one with a margin: a partly labelled
        map is a caveat, a map with five names on two hundred units is a
        different map."""
        self.assertEqual(g.check_labels(self.report(5), 200)[0]["severity"],
                         g.CRITICAL)
        self.assertEqual(g.check_labels(self.report(50), 200)[0]["severity"],
                         g.WARNING)

    def test_the_sentence_carries_both_counts_and_the_share(self):
        found = g.check_labels(self.report(35, crowded=10), 126)[0]
        self.assertIn("35", found["problem"])
        self.assertIn("126", found["problem"])
        self.assertIn("28%", found["problem"])

    def test_the_ones_that_found_nowhere_are_counted_separately(self):
        """Hitting the ceiling and finding no room are different faults with
        different answers: one wants fewer names, the other smaller type."""
        found = g.check_labels(self.report(35, crowded=10), 126)[0]
        self.assertEqual(found["crowded_out"], 10)

    def test_an_empty_frame_is_not_a_division_by_zero(self):
        """No separate guard for it: nothing can be drawn from no units, so
        ``drawn >= in_frame`` returns before the division. Pinned because the
        arithmetic is easy to rearrange into a crash."""
        self.assertEqual(g.check_labels(self.report(0), 0), [])

    def test_the_remedies_are_flags_that_exist(self):
        """A warning proposing a flag the command does not accept is worse than
        no warning: the reader tries it and the run stops."""
        for lang in msg.LANGUAGES:
            with self.subTest(lang=lang):
                fix = g.check_labels(self.report(35, crowded=10), 126,
                                     lang=lang)[0]["fix"]
                for flag in ("--labels off", "--label-fontsize", "--map-scope"):
                    self.assertIn(flag, fix)


class TestEveryCheckIsActuallyCalled(unittest.TestCase):
    """A guardrail nobody calls is a guardrail that never fires.

    Every test above proves a check *would* fire. None of them proves the
    command asks it to. Deleting the call site of ``check_labels`` left the
    whole suite green — the same shape of hole as a test that restates a rule
    and then checks only itself.
    """

    def _called(self) -> set:
        """Every ``check_*`` called anywhere in the engine.

        Not just from ``easy_map``: the first version of this looked there
        alone and reported ``check_periods`` as dead, when it is called from
        ``profile`` — the warning belongs to reading the workbook, not to
        drawing. ``check_spread`` is called from inside ``guardrails`` itself.
        A check is wired if *something* calls it.
        """
        import ast

        root = pathlib.Path(g.__file__).resolve().parent
        names = set()
        for path in list(root.glob("*.py")) + [root.parent / "easy_map.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute):
                    names.add(func.attr)
                elif isinstance(func, ast.Name):
                    names.add(func.id)
        return names

    def test_no_check_is_written_and_left_unwired(self):
        """A guardrail nobody calls is indistinguishable from one that never
        fires, and it passes every test above."""
        written = {name for name in dir(g) if name.startswith("check_")}
        self.assertTrue(written)
        missing = sorted(written - self._called())
        self.assertEqual(missing, [], f"never called anywhere: {missing}")

    def test_the_summary_is_what_the_run_reports_through(self):
        self.assertIn("summarize", self._called())


if __name__ == "__main__":
    unittest.main()
