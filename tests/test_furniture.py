"""The blocks stacked down the side column, and the marks on the map itself.

Every block returns the vertical cursor it finished at. That is the whole
contract, and it is what stopped the legend, the circle key and the locator from
landing on each other in an earlier build — the alternative was hand-tuned
offsets, which held until the day a legend had one more class than the day
before.

Nothing tested it. These draw into a real figure and read the artists back,
because the question each block answers is where its ink ended up.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:                                   # pragma: no cover
    plt = None


@unittest.skipIf(plt is None, "matplotlib not installed")
class PanelCase(unittest.TestCase):
    def axes(self, w=2.4, h=8.0, dpi=100):
        fig = plt.figure(figsize=(w, h), dpi=dpi)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_axis_off()
        fig.canvas.draw()
        self.addCleanup(plt.close, fig)
        return ax

    def ink_span(self, ax):
        """Top and bottom of everything drawn, in axes fractions."""
        fig = ax.figure
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        boxes = []
        for artist in list(ax.texts) + list(ax.patches) + list(ax.collections):
            try:
                b = artist.get_window_extent(renderer=r)
            except Exception:                        # pragma: no cover
                continue
            if b.width > 0 and b.height > 0:
                boxes.append(b)
        self.assertTrue(boxes, "nothing was drawn")
        frame = ax.bbox
        tops = [(b.y1 - frame.y0) / frame.height for b in boxes]
        bottoms = [(b.y0 - frame.y0) / frame.height for b in boxes]
        return max(tops), min(bottoms)


class TestTheColourLegend(PanelCase):
    COLOURS = ["#eef", "#99c", "#369"]
    LABELS = ["0 – 10", "10 – 20", "20 – 30"]

    def draw(self, ax, y=0.985, **kw):
        from emap import furniture as furn

        return furn.colour_legend(ax, 0.0, y, self.COLOURS, self.LABELS,
                                  "Tỷ lệ (%)", **kw)

    def test_the_cursor_comes_back_below_everything_it_drew(self):
        """A caller stacks the next block at this number. Returning anything
        above the last swatch puts the circle key through the legend."""
        ax = self.axes()
        end = self.draw(ax)
        _, bottom = self.ink_span(ax)
        self.assertLessEqual(end, bottom + 1e-6)

    def test_it_draws_downward_from_where_it_was_told_to_start(self):
        ax = self.axes()
        end = self.draw(ax, y=0.9)
        top, _ = self.ink_span(ax)
        self.assertLessEqual(top, 0.9 + 0.02)
        self.assertLess(end, 0.9)

    def test_one_swatch_per_class_plus_the_no_data_box(self):
        ax = self.axes()
        self.draw(ax)
        self.assertEqual(len(ax.patches), len(self.COLOURS) + 1)

    def test_the_no_data_row_can_be_left_out(self):
        """A map where every unit has a value should not carry a key for a
        colour it never used."""
        ax = self.axes()
        self.draw(ax, no_data_label=None)
        self.assertEqual(len(ax.patches), len(self.COLOURS))

    def test_the_no_data_wording_is_the_caller_s(self):
        """It comes from the language table. Hard-coding it here is how an
        English map ended up with a Vietnamese caption once already."""
        ax = self.axes()
        self.draw(ax, no_data_label="No data")
        self.assertIn("No data", [t.get_text() for t in ax.texts])

    def test_the_low_class_is_at_the_top(self):
        """A legend read top to bottom must run low to high, or it reverses
        the reader's sense of the colour ramp without saying so."""
        ax = self.axes()
        self.draw(ax)
        rows = [(t.get_position()[1], t.get_text()) for t in ax.texts
                if t.get_text() in self.LABELS]
        self.assertEqual([text for _, text in sorted(rows, reverse=True)],
                         self.LABELS)

    def test_more_classes_take_more_room(self):
        """The reason the cursor is returned rather than assumed."""
        from emap import furniture as furn

        short = furn.colour_legend(self.axes(), 0.0, 0.985, self.COLOURS,
                                   self.LABELS, "T")
        long = furn.colour_legend(self.axes(), 0.0, 0.985, self.COLOURS * 3,
                                  self.LABELS * 3, "T")
        self.assertLess(long, short)


class TestTheCircleKey(PanelCase):
    def test_the_key_and_the_map_read_off_one_number(self):
        """A key built to one scale beside a map drawn to another is a key that
        is wrong for its own map. That happened here once."""
        import inspect

        from emap import furniture as furn, render

        self.assertIs(
            inspect.signature(furn.symbol_legend).parameters["max_points"].default,
            furn.SYMBOL_MAX_PT)
        self.assertIn("SYMBOL_MAX_PT", inspect.getsource(render.draw)
                      + inspect.getsource(furn.symbol_legend))

    def test_circle_area_follows_the_value(self):
        """Radius by the square root, so twelve times the caseload is twelve
        times the ink — not a circle barely twice as wide."""
        from emap import furniture as furn

        ax = self.axes()
        furn.symbol_legend(ax, 0.0, 0.9, [25.0, 100.0], "Số ca",
                           format_value=lambda v: str(int(v)))
        sizes = list(ax.collections[0].get_sizes())
        self.assertAlmostEqual(sizes[1] / sizes[0], 4.0, places=6)

    def test_the_cursor_comes_back_below_everything_it_drew(self):
        from emap import furniture as furn

        ax = self.axes()
        end = furn.symbol_legend(ax, 0.0, 0.9, [1.0, 10.0], "Số ca",
                                 format_value=lambda v: str(int(v)))
        _, bottom = self.ink_span(ax)
        self.assertLessEqual(end, bottom + 1e-6)

    def test_a_key_with_no_values_still_moves_the_cursor(self):
        """It has drawn its heading, so the next block must start below it.
        Returning the same y would stack the next block on the title."""
        from emap import furniture as furn

        ax = self.axes()
        end = furn.symbol_legend(ax, 0.0, 0.9, [], "Số ca",
                                 format_value=str)
        self.assertLess(end, 0.9)
        self.assertEqual(len(ax.collections), 0)

    def test_each_circle_is_labelled_with_its_own_value(self):
        from emap import furniture as furn

        ax = self.axes()
        furn.symbol_legend(ax, 0.0, 0.9, [10.0, 50.0], "Số ca",
                           format_value=lambda v: f"{int(v)} ca")
        drawn = [t.get_text() for t in ax.texts]
        self.assertIn("10 ca", drawn)
        self.assertIn("50 ca", drawn)


class TestTheScaleBar(unittest.TestCase):
    """The bar is drawn in data coordinates on the map itself."""

    def map_axes(self, span_m=800_000.0):
        fig = plt.figure(figsize=(6.0, 6.0), dpi=100)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_xlim(0.0, span_m)
        ax.set_ylim(0.0, span_m)
        fig.canvas.draw()
        self.addCleanup(plt.close, fig)
        return ax

    @unittest.skipIf(plt is None, "matplotlib not installed")
    def test_the_printed_number_is_the_length_actually_drawn(self):
        """A bar labelled 200 km that measures 250 is worse than no bar."""
        from emap import furniture as furn

        ax = self.map_axes()
        furn.scale_bar(ax, lang="en")
        drawn = sum(p.get_width() for p in ax.patches)
        labels = [t.get_text() for t in ax.texts if t.get_text() != "0"]
        self.assertEqual(labels, [furn._km(drawn, "en")])

    @unittest.skipIf(plt is None, "matplotlib not installed")
    def test_the_two_halves_are_equal_and_meet(self):
        from emap import furniture as furn

        ax = self.map_axes()
        furn.scale_bar(ax)
        left, right = sorted(ax.patches, key=lambda p: p.get_x())
        self.assertAlmostEqual(left.get_width(), right.get_width())
        self.assertAlmostEqual(left.get_x() + left.get_width(), right.get_x())

    def test_the_number_is_grouped_the_way_the_rest_of_the_map_is(self):
        """It was hard-wired to the Vietnamese convention, so a 1,000 km bar on
        an English map read as one kilometre."""
        from emap import furniture as furn

        self.assertEqual(furn._km(1_000_000.0, "vi"), "1.000 km")
        self.assertEqual(furn._km(1_000_000.0, "en"), "1,000 km")

    def test_a_distance_under_a_kilometre_is_given_in_metres(self):
        from emap import furniture as furn

        self.assertTrue(furn._km(500.0, "en").endswith(" m"))
        self.assertTrue(furn._km(5_000.0, "en").endswith(" km"))

    def test_the_metre_form_follows_the_language_too(self):
        """Only visible at the rounding boundary, because everything below a
        kilometre is under four digits and has nothing to separate. 999.5 m
        rounds up to a thousand *metres* rather than switching to kilometres —
        a real inconsistency, and one no caller can reach: the bar's length
        always comes from ``nice_length``, which returns 1, 2 or 5 times a
        power of ten and never a value in between. Pinned, not fixed."""
        from emap import furniture as furn

        self.assertEqual(furn._km(999.5, "vi"), "1.000 m")
        self.assertEqual(furn._km(999.5, "en"), "1,000 m")
        self.assertNotIn(furn.nice_length(2_000_000.0), (999.5,))


@unittest.skipIf(plt is None, "matplotlib not installed")
class TestTheNorthArrow(unittest.TestCase):
    def map_axes(self):
        fig = plt.figure(figsize=(6.0, 6.0), dpi=100)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_xlim(0.0, 100.0)
        ax.set_ylim(0.0, 100.0)
        fig.canvas.draw()
        self.addCleanup(plt.close, fig)
        return ax

    def test_the_letter_is_the_caller_s_not_this_module_s(self):
        """North is B in Vietnamese and N in English, and this module holds no
        sentences — the letter arrives with the call."""
        from emap import furniture as furn

        for letter in ("B", "N"):
            ax = self.map_axes()
            furn.north_arrow(ax, letter=letter)
            self.assertEqual([t.get_text() for t in ax.texts], [letter])

    def test_the_letter_sits_above_the_arrow_head(self):
        from emap import furniture as furn

        ax = self.map_axes()
        furn.north_arrow(ax)
        label = ax.texts[0].get_position()[1]
        top = max(y for _, y in ax.patches[0].get_xy())
        self.assertGreaterEqual(label, top)


class TestHowTallTheLocatorBoxShouldBe(unittest.TestCase):
    """``locator_aspect``: read from the country, not from a constant.

    It *was* a constant, 2.2, described as Vietnam's bounding box. It was not:
    Vietnam in the projection it is drawn in, archipelagos included, is 1.10
    tall to wide. The box was twice as tall as its contents for the one country
    it was measured for, and four to seven times too tall for anywhere else.
    """

    def frame(self, w, h):
        import geopandas as gpd
        from shapely.geometry import Polygon

        return gpd.GeoDataFrame(
            geometry=[Polygon([(0, 0), (w, 0), (w, h), (0, h)])], crs="EPSG:3857")

    def test_the_ratio_comes_from_the_geometry(self):
        from emap import furniture as furn

        self.assertAlmostEqual(furn.locator_aspect(self.frame(10, 22)), 2.2)
        self.assertAlmostEqual(furn.locator_aspect(self.frame(30, 10)), 1 / 3)

    def test_an_extreme_country_is_clamped_to_a_box_that_still_reads(self):
        """Past five to one the box is a line and the caption under it is wider
        than the map above."""
        from emap import furniture as furn

        low, high = furn.LOCATOR_LIMITS
        self.assertEqual(furn.locator_aspect(self.frame(1, 500)), high)
        self.assertEqual(furn.locator_aspect(self.frame(500, 1)), low)

    def test_a_frame_with_no_width_does_not_divide_by_zero(self):
        from emap import furniture as furn

        self.assertEqual(furn.locator_aspect(self.frame(0, 10)), 1.0)


if __name__ == "__main__":
    unittest.main()
