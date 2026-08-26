"""The invisible layer the interactive page hit-tests against.

``webpage.outlines`` turns each feature into an SVG path in percent-of-image
coordinates. Nothing here is drawn — the picture is a PNG underneath — so the
only way this layer is ever wrong is that the pointer lands on the wrong name,
and the only way anyone finds out is by hovering.

It had no test. What is pinned here is the invariant that makes hovering
trustworthy: the emitted shapes tile the map the way the real units do. Two
units that share a border must share one line in the overlay too. Thinning each
outline on its own does not give that — each side drops a different subset of
its points, the two edges cross, and along the sliver between them the pointer
either finds a neighbour or finds nothing.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)

try:
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import MultiPolygon, Point, Polygon
    from shapely.ops import unary_union
except Exception:                                   # pragma: no cover
    gpd = None


#: Distance between vertices along a wobbly edge. A *spacing* rather than a
#: count, so a border of half the length gets half as many points at the same
#: places — which is what makes two neighbours meet vertex for vertex.
STEP = 1.0


def wobbly_edge(x, y0, y1, amp=0.0):
    """A shared border with many vertices, so thinning has something to remove.

    The wobble is a function of ``y`` alone, never of position along this
    particular edge. Otherwise the same stretch of border wobbles differently
    depending on which unit is drawing it, the two sides do not coincide, and
    the fixture stops being a coverage before any code under test has run.
    """
    import math

    n = max(1, int(round(abs(y1 - y0) / STEP)))
    ys = [y0 + (y1 - y0) * i / n for i in range(n + 1)]
    return [(x + amp * math.sin(y / 7.0), y) for y in ys]


def tile(x0, x1, y0, y1, amp=0.0):
    """A square whose left and right edges carry the wobble, so neighbouring
    tiles share an identical dense boundary."""
    left = wobbly_edge(x0, y0, y1, amp=amp)
    right = list(reversed(wobbly_edge(x1, y0, y1, amp=amp)))
    return Polygon(left + right)


@unittest.skipIf(gpd is None, "geopandas/matplotlib not installed")
class OutlineCase(unittest.TestCase):
    def axes(self, width_in=7.0, height_in=7.0, dpi=100, span=(0.0, 100.0)):
        fig = plt.figure(figsize=(width_in, height_in), dpi=dpi)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_xlim(*span)
        ax.set_ylim(*span)
        ax.set_axis_off()
        fig.canvas.draw()
        self.addCleanup(plt.close, fig)
        return ax

    def rows(self, geoms, names=None):
        names = names or [f"Đơn vị {i}" for i in range(len(geoms))]
        return gpd.GeoDataFrame(
            {"__shape_id": list(range(len(geoms))), "ten": names},
            geometry=list(geoms), crs=None)

    def shapes(self, geoms, names=None, **kw):
        from emap import webpage

        return webpage.outlines(self.axes(**kw), self.rows(geoms, names), "ten")

    def in_percent(self, ax, geom):
        """The true geometry in the page's own units, for comparing against."""
        from shapely.ops import transform

        fig = ax.figure
        w_px, h_px = fig.get_size_inches() * fig.dpi

        def fn(x, y):
            pts = ax.transData.transform(list(zip(x, y)))
            return ([q[0] / w_px * 100 for q in pts],
                    [(h_px - q[1]) / h_px * 100 for q in pts])

        return transform(fn, geom)

    def as_polygon(self, shape):
        """Read one emitted path back as geometry, in the page's own units."""
        rings = []
        for chunk in shape["d"].split("M")[1:]:
            pts = [tuple(float(v) for v in p.split(","))
                   for p in chunk.rstrip("Z ").split("L") if "," in p]
            if len(pts) >= 3:
                rings.append(Polygon(pts).buffer(0))
        return unary_union(rings)


class TestWhatEachShapeCarries(OutlineCase):
    def test_one_entry_per_feature_with_its_id_and_name(self):
        out = self.shapes([tile(0, 40, 0, 100), tile(40, 100, 0, 100)],
                          names=["Hà Nội", "Bắc Ninh"])
        self.assertEqual([s["id"] for s in out], ["0", "1"])
        self.assertEqual([s["name"] for s in out], ["Hà Nội", "Bắc Ninh"])

    def test_coordinates_are_percentages_of_the_image(self):
        """The overlay is stretched over the PNG by CSS, so it can only be
        written in units that do not depend on how large the page is drawn."""
        out = self.shapes([tile(0, 100, 0, 100)])
        numbers = [float(v) for pair in out[0]["d"].replace("M", "").replace("Z", "")
                   .split("L") for v in pair.split(",") if pair.strip()]
        self.assertGreaterEqual(min(numbers), -0.01)
        self.assertLessEqual(max(numbers), 100.01)

    def test_the_vertical_axis_is_flipped_for_svg(self):
        """Data grows upward; SVG grows downward. A shape in the top half of
        the map must come out in the top half of the overlay."""
        out = self.shapes([tile(0, 100, 80, 100)])
        ys = [float(p.split(",")[1]) for p in
              out[0]["d"].replace("M", "").rstrip("Z ").split("L") if "," in p]
        self.assertLess(max(ys), 30.0)

    def test_a_mainland_with_islands_becomes_several_subpaths(self):
        big = tile(0, 60, 0, 100)
        islands = MultiPolygon([big, Point(80, 20).buffer(3),
                                Point(85, 30).buffer(3)])
        out = self.shapes([islands])
        self.assertEqual(out[0]["d"].count("M"), 3)

    def test_the_main_landmass_is_named_when_it_is_not_everything(self):
        """Far enough out to be an archipelago rather than an offshore rock:
        ``main_parts`` reaches 0.75 of the mainland's own scale, so a small
        mainland with a distant island is the case that separates."""
        mainland = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
        far = Point(90, 95).buffer(1)
        out = self.shapes([MultiPolygon([mainland, far])])
        self.assertEqual(out[0]["main"], [0])

    def test_a_single_piece_needs_no_main_list(self):
        """``main`` is only worth its bytes when it excludes something."""
        out = self.shapes([tile(0, 100, 0, 100)])
        self.assertNotIn("main", out[0])

    def test_the_box_frames_the_main_landmass_not_the_far_islands(self):
        """The detail panel zooms to this box. Including a distant archipelago
        would zoom to the sea between them."""
        mainland = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
        far = Point(90, 95).buffer(1)
        out = self.shapes([MultiPolygon([mainland, far])])
        x, y, w, h = out[0]["box"]
        self.assertLess(x + w, 40.0)

    def test_missing_and_empty_geometry_are_left_out_entirely(self):
        """An entry with no path would be a name the pointer can never reach,
        and a row in the page's data that nothing indexes."""
        out = self.shapes([None, Polygon(), tile(0, 100, 0, 100)])
        self.assertEqual([s["id"] for s in out], ["2"])


class TestTwoUnitsThatShareABorder(OutlineCase):
    """The invariant the hover depends on, and the reason for coverage
    simplification.

    Measured on the 34 provinces before the change: every wrong hover sat
    within 0.35 px of the true border — inside the 1.5 px thinning tolerance,
    so no reader could hit one on purpose. The reason to fix it anyway is that
    "sub-pixel" was a property of that one boundary file, not of the method: a
    file with sparser vertices fails by more, and nothing would say so.
    """

    def pair(self):
        """A T-junction: one tall unit against two stacked neighbours.

        Two *equal* neighbours are no test at all. Douglas-Peucker walks a whole
        ring from its corners inward, so where both sides of a border have their
        corners in the same places, both drop the same points and the edge
        survives by luck. It takes a third unit to break the symmetry: the tall
        one anchors the border at its two ends, the short ones anchor it at the
        midpoint too, and the two thinnings diverge. Measured on this fixture,
        thinning each part on its own overlaps by 0.24 square units out of
        10,000 and loses one of the two contacts altogether.
        """
        return [tile(0, 50, 0, 100, amp=1.5),
                tile(50, 100, 0, 50, amp=1.5),
                tile(50, 100, 50, 100, amp=1.5)]

    def test_no_two_outlines_overlap(self):
        """Where they overlap, the pointer goes to whichever path the document
        happens to list second."""
        drawn = [self.as_polygon(s) for s in self.shapes(self.pair())]
        for i, a in enumerate(drawn):
            for b in drawn[i + 1:]:
                self.assertLess(a.intersection(b).area, 1e-6)

    def test_the_outlines_leave_no_strip_between_them(self):
        """Where they part, the pointer lands on neither and the tooltip does
        not appear at all — which reads as a broken page rather than a near
        miss."""
        drawn = [self.as_polygon(s) for s in self.shapes(self.pair())]
        merged = unary_union(drawn)
        self.assertEqual(len(getattr(merged, "geoms", [merged])), 1)
        self.assertAlmostEqual(merged.area, sum(d.area for d in drawn), places=4)

    def test_the_shared_border_survives_as_one_line(self):
        """Both sides must drop the same vertices. If they drop different ones
        the edge becomes two lines and everything above follows from it."""
        a, b, c = (self.as_polygon(s) for s in self.shapes(self.pair()))
        self.assertTrue(a.touches(b), "the tall unit no longer meets the lower")
        self.assertTrue(a.touches(c), "the tall unit no longer meets the upper")

    def test_the_outlines_are_thinner_than_the_geometry_they_came_from(self):
        """The whole point of the layer is that it is small. Every test above
        would pass on the untouched geometry, and the page would quietly carry
        every vertex of the boundary file.

        Counted on the points actually written, not on ``L`` commands — the
        first point of a subpath is an ``M``, so a count of ``L`` is one short
        of the truth and "fewer than the input" comes out true even when
        nothing was removed. That is how the first version of this test passed
        against a build that simplified nothing at all.
        """
        dense = self.pair()
        out = self.shapes(dense)
        drawn = sum(s["d"].count(",") for s in out)
        original = sum(len(p.exterior.coords) for p in dense)
        self.assertLess(drawn, original * 0.75,
                        f"{drawn} points written from {original}")


    def test_the_outlines_stay_close_to_the_geometry_they_came_from(self):
        """Thin, but not to the point of being a different map.

        Every other test here is satisfied by outlines thinned until each unit
        is a triangle: they would still tile without overlap, still touch, and
        still be smaller. Injecting a 40x tolerance proved exactly that — no
        test moved. So bound the error directly.

        The budget is half the pixel the thinning is allowed to move, which
        sounds tight and is not: measured on this fixture, the real outlines
        drift 0.14 of it, so there is three and a half times the headroom. Half
        a pixel is what makes the bound bite — at a full pixel a fourfold
        tolerance still slips through (it drifts 0.84), and at two pixels even
        an eightfold one does.
        """
        from emap import webpage

        ax = self.axes()
        tiles = self.pair()
        out = webpage.outlines(ax, self.rows(tiles), "ten")
        # SIMPLIFY_PIXELS is stated in screen pixels; the outline is written in
        # percent of image width, so the budget has to be converted the same way
        w_px = ax.figure.get_size_inches()[0] * ax.figure.dpi
        budget = webpage.SIMPLIFY_PIXELS / w_px * 100 * 0.5
        for shape, geom in zip(out, tiles):
            with self.subTest(name=shape["name"]):
                self.assertLess(
                    self.as_polygon(shape).hausdorff_distance(
                        self.in_percent(ax, geom)),
                    budget)


class TestWhenTheInputIsNotACoverage(OutlineCase):
    """Overlapping features are not a coverage, and must still get outlines.

    Real files do contain them — two versions of one unit, a district drawn
    over its province. Coverage simplification is not defined there, so the
    fallback thins each part on its own, exactly as this did before. The page
    is then no better than it was, and no worse.
    """

    def overlapping(self):
        return [tile(0, 60, 0, 100, amp=1.5), tile(40, 100, 0, 100, amp=1.5)]

    def test_every_feature_still_gets_a_path(self):
        out = self.shapes(self.overlapping())
        self.assertEqual(len(out), 2)
        self.assertTrue(all(s["d"].startswith("M") for s in out))

    def test_the_fallback_is_taken_rather_than_an_error_raised(self):
        from emap import webpage

        parts = {0: [self.overlapping()[0]], 1: [self.overlapping()[1]]}
        thinned = webpage._simplify_together(parts, 0.5)
        self.assertEqual(set(thinned), {(0, 0), (1, 0)})
        self.assertTrue(all(not g.is_empty for g in thinned.values()))

    def test_nothing_to_simplify_is_not_an_error(self):
        from emap import webpage

        self.assertEqual(webpage._simplify_together({}, 0.5), {})


if __name__ == "__main__":
    unittest.main()
