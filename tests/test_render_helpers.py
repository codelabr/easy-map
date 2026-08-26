"""The arithmetic between the data and the page.

These are the functions that decide what rectangle the map looks at, how wide a
typical unit is, how many drawn paths a feature turns into, how long a scale bar
should be, and how big a locator box may grow before it lands on the footer.
None of them had a test. Each is small, and each has already caused a visible
fault at least once: the colour list that was cycled across 2,703 paths, the
locator that overlapped the source line, the map framed to the right shape with
the wrong crop.
"""

from __future__ import annotations

import math
import unittest

import context  # noqa: F401  (path bootstrap)

try:
    import geopandas as gpd
    from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon
except Exception:                                   # pragma: no cover
    gpd = None


def box(minx, miny, maxx, maxy):
    return Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])


@unittest.skipIf(gpd is None, "geopandas not installed")
class TestTheRectangleTheMapLooksAt(unittest.TestCase):
    """``view_bounds`` and ``geometry_aspect``.

    Both come from one place on purpose: computing the page's shape and the
    axes' crop separately is how a map ends up correctly proportioned and
    showing the wrong part of the country.
    """

    def frame(self, *boxes):
        return gpd.GeoDataFrame(geometry=[box(*b) for b in boxes], crs="EPSG:3857")

    def test_with_no_declared_meridian_the_frame_is_the_geometry(self):
        from emap import render

        f = self.frame((0, 0, 10, 20))
        bounds, plan = render.view_bounds(f, None)
        self.assertEqual(bounds, (0.0, 0.0, 10.0, 20.0))
        self.assertIsNone(plan)

    def test_the_aspect_is_width_over_height_of_that_same_rectangle(self):
        from emap import render

        self.assertAlmostEqual(
            render.geometry_aspect(self.frame((0, 0, 10, 20)), None), 0.5)
        self.assertAlmostEqual(
            render.geometry_aspect(self.frame((0, 0, 30, 10)), None), 3.0)

    def test_a_frame_with_nothing_in_it_falls_back_instead_of_returning_nan(self):
        """``if height`` was written as this fallback and was not one: bounds
        of an empty frame are NaN, NaN is truthy, and the division returned NaN
        — which sized a figure and was then written into the metadata, where a
        NaN is not valid JSON. Defensive; no run has been seen to reach it."""
        from emap import render

        for f in (gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
                  gpd.GeoDataFrame(geometry=[Point(0, 0).buffer(0)],
                                   crs="EPSG:3857")):
            with self.subTest(rows=len(f)):
                self.assertEqual(render.geometry_aspect(f, None), 1.0)

    def test_a_frame_with_no_height_does_not_divide_by_zero(self):
        """One feature on a horizontal line. A crash here would take a map down
        for a degenerate boundary file rather than drawing something."""
        from emap import render
        from shapely.geometry import LineString

        f = gpd.GeoDataFrame(geometry=[LineString([(0, 5), (10, 5)])],
                             crs="EPSG:3857")
        self.assertEqual(render.geometry_aspect(f, None), 1.0)

    def test_the_bounds_are_plain_floats_not_numpy_scalars(self):
        """They are written into JSON. A numpy float64 there raises at dump
        time, a long way from here."""
        from emap import render

        for value in render.view_bounds(self.frame((0, 0, 10, 20)), None)[0]:
            self.assertIs(type(value), float)


@unittest.skipIf(gpd is None, "geopandas not installed")
class TestHowWideATypicalUnitIs(unittest.TestCase):
    """``median_feature_width``: the yardstick the circle-occlusion warning is
    measured against."""

    def frame(self, widths):
        return gpd.GeoDataFrame(
            geometry=[box(0, 0, w, 10) for w in widths], crs="EPSG:3857")

    def test_the_median_and_not_the_mean(self):
        """One enormous province would drag a mean far past anything typical,
        and the warning built on it would stop firing."""
        from emap import render

        self.assertEqual(render.median_feature_width(self.frame([1, 2, 3, 4, 900])), 3.0)

    def test_empty_geometry_is_skipped_rather_than_counted_as_zero(self):
        from emap import render

        self.assertEqual(render.median_feature_width(self.frame([2, 4, 6])), 4.0)

    def test_a_frame_with_nothing_measurable_gives_zero(self):
        """Zero is the value the occlusion check reads as "do not measure"."""
        from emap import render

        empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:3857")
        self.assertEqual(render.median_feature_width(empty), 0.0)


@unittest.skipIf(gpd is None, "geopandas not installed")
class TestHowManyPathsAFeatureDraws(unittest.TestCase):
    """``part_counts``.

    This exists because of a defect that made every video the wrong colour: a
    province is a MultiPolygon, so 34 features became 2,703 drawn paths, and
    matplotlib cycled the 34-colour list across all of them.
    """

    def counts(self, geoms):
        from emap import render

        return render.part_counts(gpd.GeoDataFrame(geometry=geoms, crs="EPSG:3857"))

    def test_a_single_polygon_draws_one_path(self):
        self.assertEqual(self.counts([box(0, 0, 1, 1)]), [1])

    def test_a_mainland_with_islands_draws_one_path_per_piece(self):
        many = MultiPolygon([box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)])
        self.assertEqual(self.counts([many]), [3])

    def test_a_geometry_collection_is_counted_the_same_way(self):
        mixed = GeometryCollection([box(0, 0, 1, 1), box(2, 0, 3, 1)])
        self.assertEqual(self.counts([mixed]), [2])

    def test_missing_and_empty_geometry_count_as_no_paths(self):
        """Counting a blank as one would shift every later colour by a place,
        which is the same silent failure in a smaller disguise."""
        self.assertEqual(self.counts([None, Polygon(), box(0, 0, 1, 1)]), [0, 0, 1])

    def test_the_total_is_what_a_colour_list_has_to_be_expanded_to(self):
        rows = [box(0, 0, 1, 1),
                MultiPolygon([box(2, 0, 3, 1), box(4, 0, 5, 1)]),
                None]
        counts = self.counts(rows)
        self.assertEqual(len(counts), len(rows))       # one entry per feature
        self.assertEqual(sum(counts), 3)               # three paths in total


class TestHowLongAScaleBarShouldBe(unittest.TestCase):
    """``nice_length``: a round number near a quarter of the map's width.

    A bar reading "127 km" is arithmetic showing through. The rule is 1, 2 or 5
    times a power of ten, and the point of the tests is that the chosen number
    stays in that family across three orders of magnitude.
    """

    def test_every_answer_is_one_two_or_five_times_a_power_of_ten(self):
        from emap import furniture as furn

        for span in (1_000, 12_345, 250_000, 1_600_000, 40_000_000):
            with self.subTest(span=span):
                length = furn.nice_length(float(span))
                mantissa = length / 10 ** math.floor(math.log10(length))
                self.assertIn(round(mantissa, 6), (1.0, 2.0, 5.0))

    def test_the_bar_is_a_useful_fraction_of_the_map(self):
        """Not so short it measures nothing, not so long it runs off the page.
        Between a tenth and half the width is the band that reads."""
        from emap import furniture as furn

        for span in (1_000, 12_345, 250_000, 1_600_000, 40_000_000):
            with self.subTest(span=span):
                share = furn.nice_length(float(span)) / span
                self.assertGreater(share, 0.10)
                self.assertLess(share, 0.50)

    def test_it_grows_with_the_map_and_never_shrinks(self):
        from emap import furniture as furn

        spans = [1_000, 5_000, 20_000, 100_000, 900_000, 5_000_000]
        lengths = [furn.nice_length(float(s)) for s in spans]
        self.assertEqual(lengths, sorted(lengths))

    def test_a_map_of_almost_no_width_still_returns_something_positive(self):
        """A one-province frame in a tiny country. Zero here would draw a bar
        of no length and label it 0 km."""
        from emap import furniture as furn

        self.assertGreater(furn.nice_length(1.0), 0)


class TestSizingTheLocatorBox(unittest.TestCase):
    """``locator_rect``: the small country-scale map, and the footer below it.

    It returns None rather than drawing when there is no room. That branch is
    the one that matters: the fault it replaced was a locator drawn across the
    source line, which looked deliberate.
    """

    def fig(self, w=8.0, h=10.0):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        f = plt.figure(figsize=(w, h), dpi=100)
        self.addCleanup(plt.close, f)
        return f

    def test_a_box_that_fits_keeps_the_width_it_was_asked_for(self):
        from emap import furniture as furn

        rect = furn.locator_rect(self.fig(), 0.05, 0.90, 0.20,
                                 aspect=0.5, floor=0.10)
        self.assertIsNotNone(rect)
        self.assertAlmostEqual(rect[2], 0.20)

    def test_the_box_hangs_from_its_top_edge(self):
        """Stacking is done downwards from a cursor, so the top is the fixed
        point and the height grows away from it."""
        from emap import furniture as furn

        x, y, w, h = furn.locator_rect(self.fig(), 0.05, 0.90, 0.20,
                                       aspect=0.5, floor=0.10)
        self.assertAlmostEqual(y + h, 0.90)
        self.assertAlmostEqual(x, 0.05)

    def test_a_tall_country_is_narrowed_rather_than_allowed_to_overrun(self):
        """Vietnam is far taller than it is wide. Asked for a width that would
        make it too tall, the box gives up width, not the floor."""
        from emap import furniture as furn

        floor = 0.10
        rect = furn.locator_rect(self.fig(), 0.05, 0.90, 0.60,
                                 aspect=3.0, floor=floor)
        self.assertIsNotNone(rect)
        self.assertLess(rect[2], 0.60)
        self.assertGreaterEqual(round(rect[1], 6), floor)

    def test_the_caption_underneath_is_left_room(self):
        from emap import furniture as furn

        floor, caption = 0.10, 0.05
        rect = furn.locator_rect(self.fig(), 0.05, 0.90, 0.60, aspect=3.0,
                                 floor=floor, caption_frac=caption)
        self.assertGreaterEqual(round(rect[1], 6), round(floor + caption, 6))

    def test_no_room_means_no_box_rather_than_a_box_over_the_footer(self):
        from emap import furniture as furn

        self.assertIsNone(furn.locator_rect(self.fig(), 0.05, 0.12, 0.20,
                                            aspect=0.5, floor=0.10))

    def test_the_shape_of_the_page_is_taken_into_account(self):
        """A fraction of the width and a fraction of the height are different
        lengths unless the page is square, and a locator that ignores that is
        stretched."""
        from emap import furniture as furn

        wide = furn.locator_rect(self.fig(16.0, 9.0), 0.05, 0.90, 0.20,
                                 aspect=1.0, floor=0.0)
        tall = furn.locator_rect(self.fig(9.0, 16.0), 0.05, 0.90, 0.20,
                                 aspect=1.0, floor=0.0)
        self.assertGreater(wide[3], tall[3])


if __name__ == "__main__":
    unittest.main()
