"""Which part of a feature the detail panel shows.

The answer is decided at render time, so a wrong one ships inside the page and
cannot be corrected by the reader. The cases that matter are the ones Vietnam
actually contains: a province whose territory reaches 400 km offshore, a bay made
of hundreds of islands that belong together, and a commune that is an archipelago
and nothing else.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import spotlight

try:
    from shapely.geometry import MultiPolygon, Polygon, box
except ImportError:                                    # pragma: no cover
    Polygon = None


def square(x: float, y: float, side: float = 1.0):
    return box(x, y, x + side, y + side)


@unittest.skipIf(Polygon is None, "cần shapely")
class TestWhichPartsAreTheMainland(unittest.TestCase):
    def test_a_single_polygon_is_all_of_itself(self):
        keep, share = spotlight.main_parts(square(0, 0, 10))
        self.assertEqual(keep, [0])
        self.assertEqual(share, 1.0)

    def test_an_island_just_offshore_belongs_to_the_mainland(self):
        """Hạ Long's bay is 848 fragments and every one of them is the unit."""
        mainland = square(0, 0, 10)
        nearby = square(11, 4, 1)          # a gap of 1 against a width of 10
        keep, share = spotlight.main_parts(MultiPolygon([mainland, nearby]))
        self.assertEqual(keep, [0, 1])
        self.assertEqual(share, 1.0)

    def test_an_archipelago_far_offshore_is_dropped(self):
        """Khánh Hòa carries Trường Sa; enlarging both gives a frame of sea."""
        mainland = square(0, 0, 10)
        far = square(400, 0, 1)
        keep, _ = spotlight.main_parts(MultiPolygon([mainland, far]))
        self.assertEqual(keep, [0])

    def test_a_chain_of_islands_joins_through_its_neighbours(self):
        """Each hop is short even though the last island is far from the first."""
        pieces = [square(0, 0, 10)] + [square(11 + 2 * i, 4, 1) for i in range(4)]
        keep, _ = spotlight.main_parts(MultiPolygon(pieces))
        self.assertEqual(keep, list(range(len(pieces))))

    def test_a_unit_that_is_only_islands_keeps_all_of_them(self):
        """Trường Sa is itself a commune. "Keep the biggest part" would reduce it
        to one islet and throw away most of the unit, which is not a main part —
        it is a lost feature."""
        scattered = MultiPolygon([square(0, 0, 1), square(60, 0, 1),
                                  square(120, 0, 1), square(180, 0, 1)])
        keep, share = spotlight.main_parts(scattered)
        self.assertEqual(keep, [0, 1, 2, 3])
        self.assertEqual(share, 1.0)

    def test_indices_are_positions_in_the_geometry_and_come_back_sorted(self):
        """The page slices its own subpath list with these, so an index that
        does not line up with the geometry draws the wrong island."""
        pieces = [square(400, 0, 1), square(0, 0, 10), square(11, 4, 1)]
        keep, _ = spotlight.main_parts(MultiPolygon(pieces))
        self.assertEqual(keep, [1, 2])
        self.assertEqual(keep, sorted(keep))

    def test_the_share_reports_how_much_of_the_area_survived(self):
        keep, share = spotlight.main_parts(
            MultiPolygon([square(0, 0, 10), square(400, 0, 5)]))
        self.assertEqual(keep, [0])
        self.assertAlmostEqual(share, 100 / 125, places=6)


@unittest.skipIf(Polygon is None, "cần shapely")
class TestBoundingBoxGap(unittest.TestCase):
    def test_overlapping_boxes_have_no_gap(self):
        self.assertEqual(spotlight._gap((0, 0, 10, 10), (5, 5, 15, 15)), 0.0)

    def test_a_gap_on_one_axis_only(self):
        self.assertEqual(spotlight._gap((0, 0, 10, 10), (13, 0, 20, 10)), 3.0)

    def test_a_diagonal_gap_is_the_straight_line_distance(self):
        self.assertAlmostEqual(spotlight._gap((0, 0, 1, 1), (4, 5, 6, 7)), 5.0)


@unittest.skipIf(Polygon is None, "cần shapely")
class TestTheThresholdsAreDeliberate(unittest.TestCase):
    """These two numbers were chosen against the real shapefile, not by taste.

    Locking them here means a future edit has to argue with the measurement:
    at REACH below 0.35 Hạ Long's bay breaks into pieces, and at AREA_FLOOR
    above 0.35 Khánh Hòa (which keeps 67%) would stop dropping Trường Sa.
    """

    def test_reach_is_wide_enough_for_a_bay(self):
        self.assertGreaterEqual(spotlight.REACH, 0.35)

    def test_the_floor_sits_below_the_share_a_real_mainland_keeps(self):
        self.assertLess(spotlight.AREA_FLOOR, 0.67)
        self.assertGreater(spotlight.AREA_FLOOR, 0.22)   # above Hoàng Sa's share


if __name__ == "__main__":
    unittest.main()
