"""Fitting what the user asked for into the channels a map has.

The request that prompted this: viral suppression (a rate) and patients on
treatment (a count) on one map. The engine could draw each alone but had no way
to say which variable belongs to which channel, so a second count silently took
whatever row survived a deduplication.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import layers, semantics as sem


def ask(name: str, semantic: str) -> dict:
    return {"name": name, "semantic": semantic}


RATE = ask("Tỷ lệ ức chế virus", sem.PERCENT)
COUNT = ask("TX_CURR", sem.COUNT)
COUNT2 = ask("Số ca đồng nhiễm", sem.COUNT)
RATE2 = ask("Tỷ suất/100.000", sem.RATE_PER)
GROUP = ask("Mức ưu tiên", sem.CATEGORY)


class TestOneMap(unittest.TestCase):
    def test_a_rate_and_a_count_share_one_map(self):
        plan = layers.allocate([RATE, COUNT])
        self.assertEqual(len(plan["maps"]), 1)
        one = plan["maps"][0]
        self.assertEqual(one["fill"], RATE)
        self.assertEqual(one["symbol"], COUNT)
        self.assertEqual(one["kind"], "choropleth-symbol")

    def test_the_order_asked_for_does_not_change_the_channels(self):
        """Semantic decides the channel, not the order of the request."""
        self.assertEqual(layers.allocate([COUNT, RATE])["maps"][0]["fill"], RATE)

    def test_a_rate_alone_is_a_choropleth(self):
        self.assertEqual(layers.allocate([RATE])["maps"][0]["kind"], "choropleth")

    def test_a_count_alone_gets_circles_not_fill(self):
        plan = layers.allocate([COUNT])["maps"][0]
        self.assertIsNone(plan["fill"])
        self.assertEqual(plan["kind"], "graduated-symbol")

    def test_a_category_fills_areas_with_its_own_map_type(self):
        self.assertEqual(layers.allocate([GROUP])["maps"][0]["kind"], "categorized")

    def test_every_placement_explains_itself(self):
        why = " ".join(layers.allocate([RATE, COUNT])["maps"][0]["reason"])
        self.assertIn("chuẩn hoá", why)
        self.assertIn("diện tích và dân số", why)


class TestSpillingToASecondMap(unittest.TestCase):
    def test_two_counts_cannot_share_the_circle_channel(self):
        plan = layers.allocate([RATE, COUNT, COUNT2])
        self.assertEqual(len(plan["maps"]), 2)
        self.assertEqual(plan["maps"][0]["symbol"], COUNT)
        self.assertEqual(plan["maps"][1]["symbol"], COUNT2)

    def test_the_first_named_variable_keeps_the_channel(self):
        plan = layers.allocate([COUNT2, COUNT])
        self.assertEqual(plan["maps"][0]["symbol"], COUNT2)

    def test_two_rates_split_across_two_maps(self):
        plan = layers.allocate([RATE, RATE2])
        self.assertEqual([m["fill"] for m in plan["maps"]], [RATE, RATE2])

    def test_the_split_is_explained_rather_than_just_done(self):
        plan = layers.allocate([RATE, COUNT, COUNT2])
        self.assertIn("hai kênh", plan["why_split"])
        self.assertIn("hộp chọn", plan["why_split"])

    def test_a_single_map_needs_no_explanation_of_splitting(self):
        self.assertNotIn("why_split", layers.allocate([RATE, COUNT]))

    def test_four_variables_pair_up_two_and_two(self):
        plan = layers.allocate([RATE, COUNT, RATE2, COUNT2])
        self.assertEqual(len(plan["maps"]), 2)
        self.assertEqual(plan["maps"][1]["kind"], "choropleth-symbol")


class TestWhatCannotBeDrawn(unittest.TestCase):
    def test_a_time_column_is_refused_with_a_reason(self):
        plan = layers.allocate([ask("Quarter", sem.TIME)])
        self.assertEqual(plan["maps"], [])
        self.assertIn("lọc kỳ", plan["unplaced"][0]["why"])

    def test_coordinates_are_pointed_at_the_point_map(self):
        plan = layers.allocate([ask("Kinh độ", sem.COORDINATE)])
        self.assertIn("--map-type point", plan["unplaced"][0]["why"])

    def test_a_refused_column_does_not_stop_the_others(self):
        plan = layers.allocate([RATE, ask("Site Name", sem.TEXT), COUNT])
        self.assertEqual(len(plan["maps"]), 1)
        self.assertEqual(len(plan["unplaced"]), 1)


class TestConflictWarnings(unittest.TestCase):
    def test_two_counts_are_warned_about_before_the_split(self):
        text = " ".join(layers.conflicts([RATE, COUNT, COUNT2]))
        self.assertIn("vòng tròn", text)
        self.assertIn("chồng lên nhau", text)

    def test_two_fills_are_warned_about(self):
        self.assertIn("một thang màu", " ".join(layers.conflicts([RATE, RATE2])))

    def test_a_workable_pair_produces_no_warning(self):
        self.assertEqual(layers.conflicts([RATE, COUNT]), [])

    def test_mixing_a_category_with_a_rate_is_called_out(self):
        self.assertIn("hai loại thang màu", " ".join(layers.conflicts([GROUP, RATE])))


class TestSummaryLines(unittest.TestCase):
    def test_one_map_reads_without_a_number(self):
        lines = layers.summary_lines(layers.allocate([RATE, COUNT]))
        self.assertEqual(len(lines), 1)
        self.assertNotIn("Bản đồ 1", lines[0])
        self.assertIn("màu = Tỷ lệ ức chế virus", lines[0])
        self.assertIn("vòng tròn = TX_CURR", lines[0])

    def test_several_maps_are_numbered_for_the_confirmation_table(self):
        lines = layers.summary_lines(layers.allocate([RATE, COUNT, COUNT2]))
        self.assertTrue(lines[0].startswith("Bản đồ 1"))
        self.assertTrue(lines[1].startswith("Bản đồ 2"))



class TestUnitsShown(unittest.TestCase):
    """How much of the map carries data — on any channel, not just the fill.

    A proportional-symbol map drawing fourteen circles reported zero units with
    data, because the count looked only at the fill column. The map's own
    subtitle said 14/126 at the same time, so the two disagreed in print.
    """

    def setUp(self):
        self.cli = context.cli()

    def frame(self, values=None, symbols=None):
        """A stand-in for the pandas frame, exposing just what is read."""
        class Column(list):
            def notna(self):
                return Column(v is not None for v in self)

            def __or__(self, other):
                return Column(a or b for a, b in zip(self, other))

            def sum(self):
                return sum(1 for v in self if v)

        class Frame:
            def __init__(self, data):
                self._data = data
                self.columns = list(data)

            def __getitem__(self, key):
                return Column(self._data[key])

        data = {}
        if values is not None:
            data["__value"] = values
        if symbols is not None:
            data["__symbol"] = symbols
        return Frame(data)

    def test_a_symbol_only_map_counts_its_circles(self):
        frame = self.frame(symbols=[3, None, 7, 1, None])
        self.assertEqual(self.cli._units_shown(frame, False, True), 3)

    def test_a_fill_only_map_counts_its_colours(self):
        frame = self.frame(values=[51.3, None, 86.0])
        self.assertEqual(self.cli._units_shown(frame, True, False), 2)

    def test_a_unit_shown_on_both_channels_counts_once(self):
        frame = self.frame(values=[51.3, None, 86.0], symbols=[3, 4, None])
        self.assertEqual(self.cli._units_shown(frame, True, True), 3)

    def test_a_boundary_map_shows_no_data_at_all(self):
        self.assertEqual(self.cli._units_shown(self.frame(), False, False), 0)

    def test_a_channel_that_was_not_drawn_is_not_counted(self):
        """The column may exist on the frame without the map using it."""
        frame = self.frame(values=[1, 2, 3], symbols=[9, 9, 9])
        self.assertEqual(self.cli._units_shown(frame, True, False), 3)

class TestLongSheetLayers(unittest.TestCase):
    """--layer where every number lives in one column.

    On a PEPFAR extract "TX_CURR" is a value inside 'Indicator Code', not a
    heading, so asking --layer for a column name was a dead end: the allocation,
    the channel-conflict warnings and the automatic second map were all
    unreachable on exactly the kind of file this skill exists for.
    """

    def setUp(self):
        import argparse

        import pandas as pd

        self.cli = context.cli()
        self.deps = None                       # not needed on the long path
        # two provinces; TX_CURR carries a pre-computed Total beside its detail
        # rows, HTS_TST_POS has no Total at all — the pins cannot be the same
        rows = []
        for place, curr, num, den, pos in (("Hà Nội", 100, 97, 100, 7),
                                           ("Huế", 40, 39, 40, 3)):
            rows += [
                (place, "TX_CURR", "Total", curr),
                (place, "TX_CURR", "<03 months of ARVs", curr - 10),
                (place, "TX_CURR", "03-05 months of ARVs", 10),
                (place, "TX_PVLS Num", "Total", num),
                (place, "TX_PVLS Den", "Total", den),
                (place, "HTS_TST_POS", "Positive", pos),
            ]
        self.frame = pd.DataFrame(rows, columns=["SNU1", "Indicator Code",
                                                 "Status/Result", "Value"])
        self.args = argparse.Namespace(
            layer=[], indicator_column="Indicator Code", value_column="Value",
            fill_where=None, symbol_where=None, numerator=None, denominator=None,
            fill_indicator=None, symbol_indicator=None, symbol_column=None,
            ratio_column=None)

    def requests(self, *layers):
        self.args.layer = list(layers)
        return self.cli._layer_requests(self.args, self.deps, self.frame)

    def test_an_indicator_value_is_accepted_where_a_column_name_would_not_be(self):
        [one] = self.requests("TX_CURR")
        self.assertEqual(one["indicator"], "TX_CURR")
        self.assertEqual(one["semantic"], sem.COUNT)

    def test_a_pair_written_with_a_slash_becomes_a_rate(self):
        [one] = self.requests("TX_PVLS Num / TX_PVLS Den")
        self.assertEqual(one["semantic"], sem.PERCENT)
        self.assertEqual((one["numerator"], one["denominator"]), ("TX_PVLS Num", "TX_PVLS Den"))

    def test_a_pin_on_a_column_whose_name_contains_a_slash(self):
        """'Status/Result' must not be mistaken for a numerator and denominator."""
        [one] = self.requests("TX_CURR|Status/Result=Total")
        self.assertEqual(one["indicator"], "TX_CURR")
        self.assertEqual(one["slice"], ["Status/Result=Total"])

    def test_an_unknown_indicator_names_what_does_exist(self):
        with self.assertRaises(SystemExit) as caught:
            self.requests("TX_CUR")
        self.assertIn("TX_CURR", str(caught.exception))

    def test_three_indicators_lay_out_over_two_maps(self):
        plan = layers.allocate(self.requests(
            "TX_PVLS Num / TX_PVLS Den", "TX_CURR", "HTS_TST_POS"))
        self.assertEqual(len(plan["maps"]), 2)
        self.assertEqual(plan["maps"][0]["kind"], "choropleth-symbol")
        self.assertEqual(plan["maps"][1]["symbol"]["name"], "HTS_TST_POS")


class TestChannelsPinnedSeparately(unittest.TestCase):
    """Two indicators on one map, pinned differently on the same column.

    TX_CURR has to be pinned to its 'Total' rows or it counts every patient
    three times; HTS_TST_POS has no Total row, so the same pin would erase it.
    A single --where has to choose one and lose the other.
    """

    def setUp(self):
        import argparse

        import pandas as pd

        self.cli = context.cli()
        rows = [
            (1, "TX_CURR", "Total", 100),
            (1, "TX_CURR", "<03 months of ARVs", 90),
            (1, "TX_CURR", "03-05 months of ARVs", 10),
            (1, "HTS_TST_POS", "Positive", 7),
            (2, "TX_CURR", "Total", 40),
            (2, "TX_CURR", "<03 months of ARVs", 40),
            (2, "HTS_TST_POS", "Positive", 3),
        ]
        self.joined = pd.DataFrame(rows, columns=["__shape_id", "Indicator Code",
                                                  "Status/Result", "Value"])
        self.args = argparse.Namespace(
            indicator_column="Indicator Code", ratio_column=None, value_column="Value",
            numerator=None, denominator=None,
            # argparse always sets these two; a double that omits them would
            # pass while the real command line failed
            animate=False, period_column=None,
            fill_indicator="TX_CURR", fill_where=["Status/Result=Total"],
            symbol_indicator="HTS_TST_POS", symbol_where=None, symbol_column=None)

    def test_each_channel_keeps_its_own_pin(self):
        name, frame, note = self.cli._build_long_columns(self.args, self.joined, {})
        self.assertEqual(note["fill"]["total"], 140.0)     # not 280: detail excluded
        self.assertEqual(note["symbol"]["total"], 10.0)

    def test_a_pin_that_erases_the_other_channel_is_refused_loudly(self):
        self.args.symbol_where = ["Status/Result=Total"]
        with self.assertRaises(SystemExit) as caught:
            self.cli._build_long_columns(self.args, self.joined, {})
        self.assertIn("Positive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


class TestALongTableKeepsItsPeriodsForAFilm(unittest.TestCase):
    """``_build_long_columns`` reduced to one row per unit and summed every
    period into it, so a column of four quarters reached the animation as one —
    and the engine then reported that the *data* held a single period.

    Nothing caught it because no test drove a long table and ``--animate``
    together, and the sentence it failed with was plausible.
    """

    ROWS = [
        # unit, quarter, indicator, value
        (1, "Q1", "TX_CURR", 10), (1, "Q2", "TX_CURR", 20),
        (1, "Q3", "TX_CURR", 30), (1, "Q4", "TX_CURR", 40),
        (2, "Q1", "TX_CURR", 50), (2, "Q2", "TX_CURR", 60),
        (2, "Q3", "TX_CURR", 70), (2, "Q4", "TX_CURR", 80),
    ]

    def setUp(self):
        import argparse

        try:
            import pandas as pd
        except ImportError:                       # pragma: no cover
            self.skipTest("cần pandas")
        self.pd = pd
        self.cli = context.cli()
        self.joined = pd.DataFrame(
            [{"__shape_id": u, "Quarter": q, "Indicator Code": code, "Value": v}
             for u, q, code, v in self.ROWS])
        self.args = argparse.Namespace(
            indicator_column="Indicator Code", ratio_column=None,
            value_column="Value", numerator=None, denominator=None,
            fill_indicator="TX_CURR", fill_where=None,
            symbol_indicator=None, symbol_where=None, symbol_column=None,
            animate=True, period_column="Quarter")

    def build(self):
        return self.cli._build_long_columns(self.args, self.joined, {})

    def test_one_row_per_unit_per_period(self):
        _, frame, _ = self.build()
        self.assertEqual(len(frame), 8)
        self.assertEqual(sorted(frame["Quarter"].unique()),
                         ["Q1", "Q2", "Q3", "Q4"])

    def test_each_period_keeps_its_own_value(self):
        """The bug summed them: every quarter of unit 1 would read 100."""
        name, frame, _ = self.build()
        got = dict(zip(frame.loc[frame["__shape_id"] == 1, "Quarter"],
                       frame.loc[frame["__shape_id"] == 1, name]))
        self.assertEqual(got, {"Q1": 10, "Q2": 20, "Q3": 30, "Q4": 40})

    def test_a_still_map_still_reduces_to_one_row_per_unit(self):
        """The old behaviour is the right one when no film is being made."""
        self.args.animate = False
        name, frame, _ = self.build()
        self.assertEqual(len(frame), 2)
        self.assertEqual(sorted(frame[name]), [100, 260])

    def test_the_note_says_the_frame_is_per_period(self):
        _, _, note = self.build()
        self.assertEqual(note.get("kept_per_period"), "Quarter")

    def test_the_unit_count_counts_units_not_rows(self):
        """Eight rows, two units. A count of rows would read the film's length
        as a number of places."""
        _, _, note = self.build()
        self.assertEqual(note["fill"]["unit_count"], 2)


class TestTheFilmSaysWhoTookItsPeriods(unittest.TestCase):
    """The stop used to name the column and blame the workbook.

    "Column 'Quarter' holds only 1 period" was printed against a file holding
    four, because a ``--where`` had pinned it. A message that is true of the
    data and false about the cause is worse than none: it sends the reader
    hunting through their own spreadsheet.
    """

    def args(self, **over):
        import argparse

        base = dict(period_column="Quarter", where=None)
        base.update(over)
        return argparse.Namespace(**base)

    def setUp(self):
        self.cli = context.cli()

    def test_a_pin_on_the_period_column_is_named(self):
        pins = self.cli._period_pins(
            self.args(where=["Result/Target=Result", "Quarter=Q1"]))
        self.assertEqual(pins, ["Quarter=Q1"])

    def test_filters_on_other_columns_are_not_blamed(self):
        self.assertEqual(
            self.cli._period_pins(self.args(where=["Result/Target=Result"])), [])

    def test_no_filters_at_all(self):
        self.assertEqual(self.cli._period_pins(self.args()), [])

    def test_no_period_column_means_nothing_to_pin(self):
        self.assertEqual(
            self.cli._period_pins(self.args(period_column=None,
                                            where=["Quarter=Q1"])), [])

    def test_the_sentence_exists_in_both_languages_and_names_the_filter(self):
        from emap import messages as msg

        for lang in msg.LANGUAGES:
            text = msg.text("error.animation-period-pinned", lang,
                            column="Quarter", filters="--where Quarter=Q1", count=4)
            with self.subTest(lang=lang):
                self.assertIn("Quarter", text)
                self.assertIn("--where Quarter=Q1", text)
                self.assertIn("4", text)


class TestAWideSheetCanAskForAQuotient(unittest.TestCase):
    """``--layer "A / B"`` worked only with ``--indicator-column``.

    A wide sheet with two count columns was refused outright, and the user had
    to add a rate column to their own workbook. SKILL.md said "A / B is a ratio"
    and did not mention the constraint.
    """

    def setUp(self):
        self.cli = context.cli()

    def test_a_spaced_slash_is_a_quotient(self):
        self.assertEqual(self.cli.split_wide_ratio("Cases / Population"),
                         ("Cases", "Population"))

    def test_a_slash_inside_a_column_name_is_not(self):
        """Real headings carry slashes — ``Tỷ suất ca mới/100.000 dân`` and
        ``Status/Result`` are both real. Splitting on a bare slash would cut a
        column in half and then report it missing."""
        for name in ("Tỷ suất ca mới/100.000 dân", "Status/Result",
                     "Xã/phường"):
            with self.subTest(name=name):
                self.assertEqual(self.cli.split_wide_ratio(name), (name, None))

    def test_an_empty_side_is_not_a_quotient(self):
        for name in ("A / ", " / B", " / "):
            with self.subTest(name=name):
                self.assertIsNone(self.cli.split_wide_ratio(name)[1])

    def test_the_column_is_summed_then_divided(self):
        """Per unit, not averaged from row-level ratios: a mean of ratios
        weights a commune of two hundred like a city of two million."""
        try:
            import pandas as pd
        except ImportError:                        # pragma: no cover
            self.skipTest("cần pandas")
        frame = pd.DataFrame({"Cases": [1.0, 3.0], "Population": [100.0, 100.0]})
        by_name = {}
        name = self.cli.build_wide_ratio(frame, by_name, "Cases / Population")
        self.assertEqual(name, "Cases ÷ Population (%)")
        self.assertEqual(list(frame[name]), [1.0, 3.0])
        self.assertEqual(by_name[name]["semantic"], "percent")

    def test_a_zero_denominator_is_no_data_rather_than_infinity(self):
        try:
            import pandas as pd
        except ImportError:                        # pragma: no cover
            self.skipTest("cần pandas")
        frame = pd.DataFrame({"Cases": [1.0], "Population": [0.0]})
        name = self.cli.build_wide_ratio(frame, {}, "Cases / Population")
        self.assertTrue(frame[name].isna().all())

    def test_a_plain_column_is_left_alone(self):
        try:
            import pandas as pd
        except ImportError:                        # pragma: no cover
            self.skipTest("cần pandas")
        frame = pd.DataFrame({"Cases": [1.0]})
        self.assertIsNone(self.cli.build_wide_ratio(frame, {}, "Cases"))
