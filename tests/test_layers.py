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
    return {"tên": name, "semantic": semantic}


RATE = ask("Tỷ lệ ức chế virus", sem.PERCENT)
COUNT = ask("TX_CURR", sem.COUNT)
COUNT2 = ask("Số ca đồng nhiễm", sem.COUNT)
RATE2 = ask("Tỷ suất/100.000", sem.RATE_PER)
GROUP = ask("Mức ưu tiên", sem.CATEGORY)


class TestOneMap(unittest.TestCase):
    def test_a_rate_and_a_count_share_one_map(self):
        plan = layers.allocate([RATE, COUNT])
        self.assertEqual(len(plan["bản_đồ"]), 1)
        one = plan["bản_đồ"][0]
        self.assertEqual(one["màu_vùng"], RATE)
        self.assertEqual(one["vòng_tròn"], COUNT)
        self.assertEqual(one["loại"], "choropleth-symbol")

    def test_the_order_asked_for_does_not_change_the_channels(self):
        """Semantic decides the channel, not the order of the request."""
        self.assertEqual(layers.allocate([COUNT, RATE])["bản_đồ"][0]["màu_vùng"], RATE)

    def test_a_rate_alone_is_a_choropleth(self):
        self.assertEqual(layers.allocate([RATE])["bản_đồ"][0]["loại"], "choropleth")

    def test_a_count_alone_gets_circles_not_fill(self):
        plan = layers.allocate([COUNT])["bản_đồ"][0]
        self.assertIsNone(plan["màu_vùng"])
        self.assertEqual(plan["loại"], "graduated-symbol")

    def test_a_category_fills_areas_with_its_own_map_type(self):
        self.assertEqual(layers.allocate([GROUP])["bản_đồ"][0]["loại"], "categorized")

    def test_every_placement_explains_itself(self):
        why = " ".join(layers.allocate([RATE, COUNT])["bản_đồ"][0]["lý_do"])
        self.assertIn("chuẩn hoá", why)
        self.assertIn("diện tích và dân số", why)


class TestSpillingToASecondMap(unittest.TestCase):
    def test_two_counts_cannot_share_the_circle_channel(self):
        plan = layers.allocate([RATE, COUNT, COUNT2])
        self.assertEqual(len(plan["bản_đồ"]), 2)
        self.assertEqual(plan["bản_đồ"][0]["vòng_tròn"], COUNT)
        self.assertEqual(plan["bản_đồ"][1]["vòng_tròn"], COUNT2)

    def test_the_first_named_variable_keeps_the_channel(self):
        plan = layers.allocate([COUNT2, COUNT])
        self.assertEqual(plan["bản_đồ"][0]["vòng_tròn"], COUNT2)

    def test_two_rates_split_across_two_maps(self):
        plan = layers.allocate([RATE, RATE2])
        self.assertEqual([m["màu_vùng"] for m in plan["bản_đồ"]], [RATE, RATE2])

    def test_the_split_is_explained_rather_than_just_done(self):
        plan = layers.allocate([RATE, COUNT, COUNT2])
        self.assertIn("hai kênh", plan["vì_sao_tách"])
        self.assertIn("hộp chọn", plan["vì_sao_tách"])

    def test_a_single_map_needs_no_explanation_of_splitting(self):
        self.assertNotIn("vì_sao_tách", layers.allocate([RATE, COUNT]))

    def test_four_variables_pair_up_two_and_two(self):
        plan = layers.allocate([RATE, COUNT, RATE2, COUNT2])
        self.assertEqual(len(plan["bản_đồ"]), 2)
        self.assertEqual(plan["bản_đồ"][1]["loại"], "choropleth-symbol")


class TestWhatCannotBeDrawn(unittest.TestCase):
    def test_a_time_column_is_refused_with_a_reason(self):
        plan = layers.allocate([ask("Quarter", sem.TIME)])
        self.assertEqual(plan["bản_đồ"], [])
        self.assertIn("lọc kỳ", plan["không_xếp_được"][0]["vì_sao"])

    def test_coordinates_are_pointed_at_the_point_map(self):
        plan = layers.allocate([ask("Kinh độ", sem.COORDINATE)])
        self.assertIn("--map-type point", plan["không_xếp_được"][0]["vì_sao"])

    def test_a_refused_column_does_not_stop_the_others(self):
        plan = layers.allocate([RATE, ask("Site Name", sem.TEXT), COUNT])
        self.assertEqual(len(plan["bản_đồ"]), 1)
        self.assertEqual(len(plan["không_xếp_được"]), 1)


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
        self.assertEqual(one["chỉ_số"], "TX_CURR")
        self.assertEqual(one["semantic"], sem.COUNT)

    def test_a_pair_written_with_a_slash_becomes_a_rate(self):
        [one] = self.requests("TX_PVLS Num / TX_PVLS Den")
        self.assertEqual(one["semantic"], sem.PERCENT)
        self.assertEqual((one["tử_số"], one["mẫu_số"]), ("TX_PVLS Num", "TX_PVLS Den"))

    def test_a_pin_on_a_column_whose_name_contains_a_slash(self):
        """'Status/Result' must not be mistaken for a numerator and denominator."""
        [one] = self.requests("TX_CURR|Status/Result=Total")
        self.assertEqual(one["chỉ_số"], "TX_CURR")
        self.assertEqual(one["lát"], ["Status/Result=Total"])

    def test_an_unknown_indicator_names_what_does_exist(self):
        with self.assertRaises(SystemExit) as caught:
            self.requests("TX_CUR")
        self.assertIn("TX_CURR", str(caught.exception))

    def test_three_indicators_lay_out_over_two_maps(self):
        plan = layers.allocate(self.requests(
            "TX_PVLS Num / TX_PVLS Den", "TX_CURR", "HTS_TST_POS"))
        self.assertEqual(len(plan["bản_đồ"]), 2)
        self.assertEqual(plan["bản_đồ"][0]["loại"], "choropleth-symbol")
        self.assertEqual(plan["bản_đồ"][1]["vòng_tròn"]["tên"], "HTS_TST_POS")


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
            fill_indicator="TX_CURR", fill_where=["Status/Result=Total"],
            symbol_indicator="HTS_TST_POS", symbol_where=None, symbol_column=None)

    def test_each_channel_keeps_its_own_pin(self):
        name, frame, note = self.cli._build_long_columns(self.args, self.joined, {})
        self.assertEqual(note["màu_vùng"]["tổng"], 140.0)     # not 280: detail excluded
        self.assertEqual(note["vòng_tròn"]["tổng"], 10.0)

    def test_a_pin_that_erases_the_other_channel_is_refused_loudly(self):
        self.args.symbol_where = ["Status/Result=Total"]
        with self.assertRaises(SystemExit) as caught:
            self.cli._build_long_columns(self.args, self.joined, {})
        self.assertIn("Positive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
