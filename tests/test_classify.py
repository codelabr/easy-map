"""Class breaks, palettes and legend labels.

The rules under test are the ones that make two maps comparable and a legend
honest: counts break on whole numbers, meaningless slivers get merged, a series
shares one set of breaks, and a diverging ramp is anchored on zero.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import classify, semantics as sem

COUNT = sem.infer("Số ca phát hiện 2026", [1], True)
PERCENT = sem.infer("Bao phủ 2026 (%)", [51.3, 86.0], True)
POINT = sem.infer("Thay đổi (điểm %)", [-6.3, 15.2], True)


class TestComputeBins(unittest.TestCase):
    def test_count_breaks_are_whole_numbers(self):
        """A count legend showing 46.5 was the original defect."""
        bins = classify.compute_bins([7, 9, 13, 46, 47, 240], "quantile", 3, COUNT)
        for edge in bins["edges"]:
            self.assertEqual(edge, int(edge), f"{edge} is not a whole number")

    def test_edges_are_sorted_and_span_the_data(self):
        values = [51.3, 62.0, 66.1, 73.4, 86.0]
        bins = classify.compute_bins(values, "quantile", 4, PERCENT)
        edges = bins["edges"]
        self.assertEqual(edges, sorted(edges))
        self.assertLessEqual(edges[0], min(values))
        self.assertGreaterEqual(edges[-1], max(values))

    def test_classes_reduced_when_values_are_few(self):
        bins = classify.compute_bins([10.0, 20.0], "quantile", 5, PERCENT)
        self.assertLessEqual(bins["classes"], 2)
        self.assertTrue(bins["notes"], "an automatic reduction must be reported")

    def test_slivers_are_merged(self):
        """Quantiles on a clustered sample produced classes like 66–67%."""
        values = [10.0, 66.0, 66.2, 66.4, 66.6, 100.0]
        bins = classify.compute_bins(values, "quantile", 5, PERCENT)
        span = bins["edges"][-1] - bins["edges"][0]
        widths = [b - a for a, b in zip(bins["edges"], bins["edges"][1:])]
        self.assertTrue(all(w >= span * 0.03 for w in widths), widths)

    def test_equal_interval_produces_even_widths(self):
        bins = classify.compute_bins([0.0, 100.0], "equal-interval", 2, PERCENT)
        widths = [b - a for a, b in zip(bins["edges"], bins["edges"][1:])]
        self.assertAlmostEqual(widths[0], widths[-1], places=6)

    def test_identical_values_do_not_crash(self):
        bins = classify.compute_bins([5.0, 5.0, 5.0], "quantile", 4, PERCENT)
        self.assertGreaterEqual(len(bins["edges"]), 2)

    def test_empty_input_is_rejected(self):
        with self.assertRaises(ValueError):
            classify.compute_bins([], "quantile", 5, PERCENT)


class TestDivergingBins(unittest.TestCase):
    def test_zero_is_a_break(self):
        """Otherwise the neutral colour sits somewhere other than 'no change'."""
        bins = classify.compute_bins([-7.0, -3.0, -1.0, 2.0, 5.0, 15.0],
                                     "quantile", 6, POINT, center_zero=True)
        self.assertIn(0.0, bins["edges"])

    def test_one_sided_data_falls_back_to_a_single_ramp(self):
        bins = classify.compute_bins([1.0, 4.0, 9.0], "quantile", 4, POINT,
                                     center_zero=True)
        self.assertNotIn(0.0, bins["edges"][1:-1])
        self.assertTrue(any("một chiều" in n for n in bins["notes"]))

    def test_diverging_palette_has_a_colour_per_class(self):
        bins = classify.compute_bins([-5.0, -1.0, 3.0, 8.0], "quantile", 4, POINT,
                                     center_zero=True)
        colours = classify.palette(bins["classes"], diverging=True)
        self.assertEqual(len(colours), bins["classes"])


class TestSharedBins(unittest.TestCase):
    def test_one_set_of_breaks_covers_every_group(self):
        """Per-province breaks made the same blue mean different things."""
        groups = {"Hà Nội": [51.3, 66.0, 86.0],
                  "Huế": [58.0, 68.0, 96.9],
                  "Cần Thơ": [62.9, 79.0, 92.9]}
        bins = classify.shared_bins(groups, "quantile", 5, PERCENT)
        pooled = [v for values in groups.values() for v in values]
        self.assertLessEqual(bins["edges"][0], min(pooled))
        self.assertGreaterEqual(bins["edges"][-1], max(pooled))
        self.assertEqual(sorted(bins["shared_across"]), sorted(groups))
        self.assertTrue(any("dùng chung" in n.lower() for n in bins["notes"]),
                        bins["notes"])

    def test_every_group_value_lands_in_a_class(self):
        groups = {"A": [1.0, 5.0], "B": [50.0, 99.0]}
        bins = classify.shared_bins(groups, "quantile", 4, PERCENT)
        for values in groups.values():
            for v in values:
                idx = classify.class_index(v, bins["edges"])
                self.assertGreaterEqual(idx, 0)
                self.assertLess(idx, bins["classes"])


class TestClassIndex(unittest.TestCase):
    def setUp(self):
        self.edges = [0.0, 10.0, 20.0, 30.0]

    def test_lower_bound(self):
        self.assertEqual(classify.class_index(0.0, self.edges), 0)

    def test_upper_bound_stays_in_the_last_class(self):
        self.assertEqual(classify.class_index(30.0, self.edges), 2)

    def test_break_belongs_to_the_lower_class(self):
        self.assertEqual(classify.class_index(10.0, self.edges), 0)
        self.assertEqual(classify.class_index(10.001, self.edges), 1)

    def test_values_beyond_the_top_are_clamped(self):
        self.assertEqual(classify.class_index(999.0, self.edges), 2)


class TestBinLabels(unittest.TestCase):
    def test_count_ranges_do_not_overlap(self):
        labels = classify.bin_labels([0.0, 24.0, 107.0, 240.0], COUNT)
        self.assertEqual(labels, ["0–24", "25–107", "108–240"])

    def test_percent_labels_carry_the_sign(self):
        labels = classify.bin_labels([51.0, 64.0, 86.0], PERCENT)
        self.assertTrue(all("%" in label for label in labels))

    def test_point_labels_are_signed_and_have_no_minus_zero(self):
        labels = classify.bin_labels([-7.0, -2.0, 0.0, 5.0, 15.0], POINT)
        joined = " ".join(labels)
        self.assertIn("-7", joined)
        self.assertIn("+5", joined)
        self.assertNotIn("-0 ", joined)

    def test_point_labels_do_not_repeat_the_unit(self):
        """The unit belongs in the legend heading, not on both endpoints."""
        labels = classify.bin_labels([-7.0, 0.0, 15.0], POINT)
        self.assertTrue(all("điểm %" not in label for label in labels))


class TestPalette(unittest.TestCase):
    def test_length_matches_requested_classes(self):
        for k in range(3, 8):
            self.assertEqual(len(classify.palette(k)), k)

    def test_out_of_range_requests_are_clamped(self):
        self.assertEqual(len(classify.palette(2)), 3)
        self.assertEqual(len(classify.palette(99)), 7)

    def test_sequential_ramp_is_monotone_in_darkness(self):
        """The old palette ran blue -> teal -> blue, which reads as a hue change."""
        def luminance(hex_colour: str) -> float:
            r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        lums = [luminance(c) for c in classify.palette(5)]
        self.assertEqual(lums, sorted(lums, reverse=True), lums)


class TestSymbolScale(unittest.TestCase):
    def test_scale_reports_the_pooled_extremes(self):
        scale = classify.symbol_scale([7, 240, 72, None, 0])
        self.assertEqual(scale["max_value"], 240)
        self.assertEqual(scale["min_value"], 7)

    def test_empty_scale_is_safe_to_divide_by(self):
        self.assertEqual(classify.symbol_scale([])["max_value"], 1.0)

    def test_symbol_legend_values_are_whole_numbers(self):
        picks = classify.symbol_legend_values(240, integer=True)
        self.assertTrue(all(float(p).is_integer() for p in picks), picks)
        self.assertEqual(picks[-1], 240)

    def test_symbol_legend_values_are_deduplicated(self):
        picks = classify.symbol_legend_values(2, integer=True)
        self.assertEqual(len(picks), len(set(picks)))


if __name__ == "__main__":
    unittest.main()


class TestFlatSpreadWarning(unittest.TestCase):
    """A ramp stretched across a difference that is not there.

    Viral suppression from a real PEPFAR extract came back as 99.20% to 99.74%
    across five provinces. Quantiles gave each its own shade and the map then
    claimed the provinces differ.
    """

    def test_half_a_point_across_a_ninety_nine_percent_indicator_is_flagged(self):
        from emap import guardrails

        found = guardrails.check_spread({"edges": [99.20, 99.25, 99.32, 99.46, 99.74]})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], guardrails.WARNING)
        self.assertIn("gần như bằng nhau", found[0]["why"])

    def test_a_real_spread_says_nothing(self):
        from emap import guardrails

        self.assertEqual(guardrails.check_spread({"edges": [26.0, 41.0, 54.0, 88.0]}), [])

    def test_counts_starting_at_zero_are_not_mistaken_for_flat(self):
        from emap import guardrails

        self.assertEqual(guardrails.check_spread({"edges": [0, 5, 40, 240]}), [])

    def test_no_edges_no_opinion(self):
        from emap import guardrails

        self.assertEqual(guardrails.check_spread({}), [])


class TestLabelDecimals(unittest.TestCase):
    def test_the_map_labels_follow_the_legend(self):
        self.assertEqual(
            classify.label_decimals({"edges": [99.20, 99.25, 99.32, 99.46, 99.74]}), 2)

    def test_a_count_legend_leaves_the_labels_alone(self):
        self.assertIsNone(classify.label_decimals({"edges": [7, 46, 240],
                                                   "integer": True}))

    def test_no_bins_no_opinion(self):
        self.assertIsNone(classify.label_decimals(None))


class TestSymbolsAgreeWithTheirLegend(unittest.TestCase):
    """The key has to describe the map it sits beside.

    The legend sizes its circles by true area (scatter `s` is area). The map
    used to interpolate radius between a floor and a ceiling, so a province with
    twelve times the caseload drew a circle roughly twice as wide — and the key
    said something else.
    """

    def radii(self, values, vmax):
        from emap import render

        return render.symbol_radii(values, {"max_value": vmax}, span_y=100.0)

    def test_four_times_the_value_is_twice_the_radius(self):
        small, big = self.radii([2500, 10000], 10000)
        self.assertAlmostEqual(big / small, 2.0, places=6)

    def test_the_real_pepfar_spread_is_not_flattened(self):
        """2.941 against 35.156 is a 3.46x radius, not 2x."""
        small, big = self.radii([2941, 35156], 35156)
        self.assertAlmostEqual(big / small, (35156 / 2941) ** 0.5, places=6)

    def test_the_largest_value_fills_the_scale(self):
        self.assertAlmostEqual(self.radii([35156], 35156)[0], 100.0 * 0.021, places=9)

    def test_a_tiny_value_stays_visible_without_bending_the_scale(self):
        """A floor is a distortion; it only has to be small and to exist.

        Big enough to see on a printed page, small enough that it cannot be
        mistaken for a real quantity beside the other circles.
        """
        rmax = 100.0 * 0.021
        floor = self.radii([1], 1_000_000)[0]
        self.assertGreater(floor, 0)
        self.assertLess(floor, rmax * 0.15)

    def test_the_floor_only_catches_values_that_would_vanish(self):
        """Anything with real weight is sized by the scale, not the floor."""
        floor = self.radii([1], 1_000_000)[0]
        self.assertGreater(self.radii([250_000], 1_000_000)[0], floor * 4)

    def test_missing_and_zero_draw_nothing(self):
        self.assertEqual(self.radii([None, 0, -5], 100), [0.0, 0.0, 0.0])
