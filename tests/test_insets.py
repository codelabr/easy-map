"""Framing the mainland and carrying the archipelagos in a corner box.

Vietnam's national map must show Hoàng Sa and Trường Sa, which in the shapefile
are fragments of Đà Nẵng and Khánh Hòa rather than features of their own.
Framing the whole geometry leaves the mainland with 56% of the width.
"""

from __future__ import annotations

import json
import unittest

import context  # noqa: F401  (path bootstrap)
from emap import insets


def frame(pairs, crs="EPSG:4326"):
    """A tiny GeoDataFrame of squares at the given lon/lat centres."""
    import geopandas as gpd
    import shapely.geometry as sg

    boxes = [sg.box(x - 0.2, y - 0.2, x + 0.2, y + 0.2) for x, y in pairs]
    return gpd.GeoDataFrame({"ten": [f"u{i}" for i in range(len(boxes))]},
                            geometry=boxes, crs="EPSG:4326").to_crs(crs)


MAINLAND = [(105.0, 21.0), (106.5, 16.0), (106.0, 10.5)]
ISLANDS = [(112.0, 16.5), (114.0, 9.0), (116.5, 8.0)]


class TestWhenAnInsetIsWorthIt(unittest.TestCase):
    def test_a_mainland_only_frame_is_framed_the_ordinary_way(self):
        self.assertIsNone(insets.view(frame(MAINLAND)))

    def test_offshore_fragments_trigger_the_inset(self):
        self.assertIsNotNone(insets.view(frame(MAINLAND + ISLANDS)))

    def test_a_single_province_out_at_sea_gets_no_inset(self):
        """Asked for Khánh Hòa alone, the reader wants Khánh Hòa — there is no
        mainland-versus-islands story to tell."""
        self.assertIsNone(insets.view(frame(ISLANDS)))

    def test_an_island_barely_off_the_coast_is_not_worth_a_box(self):
        near = frame(MAINLAND + [(107.4, 16.0)])
        self.assertIsNone(insets.view(near))


class TestFramingNumbers(unittest.TestCase):
    def setUp(self):
        self.plan = insets.view(frame(MAINLAND + ISLANDS))

    def test_the_mainland_gains_width_it_did_not_have(self):
        """The share depends on the shape of the country, so compare it against
        the framing it replaces rather than against a number picked by hand.
        On the real 34-province shapefile this moves 55.7% to 69.4%."""
        rows = frame(MAINLAND + ISLANDS)
        whole = rows.total_bounds[2] - rows.total_bounds[0]
        land = rows.iloc[:len(MAINLAND)]
        land_w = land.total_bounds[2] - land.total_bounds[0]
        before = land_w / whole * 100
        self.assertGreater(self.plan["phần_trăm_bề_ngang_đất_liền"], before * 1.5)

    def test_the_view_stops_short_of_the_islands(self):
        _, _, view_maxx, _ = self.plan["khung_nhìn"]
        island_minx, _, _, _ = self.plan["vùng_quần_đảo"]
        self.assertLess(view_maxx, island_minx)

    def test_the_inset_box_sits_inside_the_view(self):
        vminx, vminy, vmaxx, vmaxy = self.plan["khung_nhìn"]
        x0, y0, w, h = self.plan["ô_khung_phụ"]
        self.assertGreaterEqual(x0, vminx)
        self.assertLessEqual(x0 + w, vmaxx + 1e-6)
        self.assertGreaterEqual(y0, vminy)
        self.assertLessEqual(y0 + h, vmaxy)

    def test_the_summary_can_be_written_to_the_run_folder(self):
        """The plan carries a shapely mask; the report must not."""
        json.dumps(insets.summary(self.plan), ensure_ascii=False)

    def test_no_plan_summarises_to_nothing(self):
        self.assertIsNone(insets.summary(None))


class TestProjectedCoordinates(unittest.TestCase):
    """The frame that reaches this module is in metres, not degrees.

    Maps are drawn in an equal-area projection so province areas stay
    comparable. A meridian written as the number 111 is meaningless there:
    clipping at "x = 111 metres" erased the middle of the country and left the
    mainland sitting inside the box meant for the islands — and nothing raised.
    """

    METRIC = ("+proj=aea +lat_1=10 +lat_2=22 +lat_0=16 +lon_0=106 "
              "+datum=WGS84 +units=m +no_defs")

    def test_the_split_works_on_a_projected_frame(self):
        rows = frame(MAINLAND + ISLANDS, crs=self.METRIC)
        plan = insets.view(rows)
        self.assertIsNotNone(plan)
        # the drawn map stops well short of the islands, in metres
        self.assertLess(plan["khung_nhìn"][2], plan["vùng_quần_đảo"][0])

    def test_the_split_is_in_the_frames_own_units(self):
        """Metres, so the numbers are large — a plan still in degrees would
        report a view a few hundred units wide."""
        plan = insets.view(frame(MAINLAND + ISLANDS, crs=self.METRIC))
        minx, _, maxx, _ = plan["khung_nhìn"]
        self.assertGreater(maxx - minx, 100_000)

    def test_both_coordinate_systems_split_the_same_units(self):
        """Same three squares each side, whichever units the frame is in."""
        for crs in ("EPSG:4326", self.METRIC):
            rows = frame(MAINLAND + ISLANDS, crs=crs)
            drawn = insets.clip_for_drawing(rows, insets.view(rows))
            kept = [i for i, g in enumerate(drawn.geometry) if not g.is_empty]
            self.assertEqual(kept, list(range(len(MAINLAND))), f"crs={crs}")


class TestClippingForDrawing(unittest.TestCase):
    def setUp(self):
        self.rows = frame(MAINLAND + ISLANDS)
        self.plan = insets.view(self.rows)

    def test_every_row_survives_in_its_original_order(self):
        """The caller draws with a positional colour list: a reordered or
        shortened frame paints each unit in another unit's colour."""
        out = insets.clip_for_drawing(self.rows, self.plan)
        self.assertEqual(len(out), len(self.rows))
        self.assertEqual(list(out["ten"]), list(self.rows["ten"]))

    def test_the_islands_are_gone_from_what_is_drawn(self):
        out = insets.clip_for_drawing(self.rows, self.plan)
        self.assertLess(out.total_bounds[2], self.rows.total_bounds[2])

    def test_the_mainland_keeps_its_full_area(self):
        out = insets.clip_for_drawing(self.rows, self.plan)
        self.assertAlmostEqual(out.geometry.iloc[0].area,
                               self.rows.geometry.iloc[0].area, places=9)

    def test_without_a_plan_nothing_is_touched(self):
        self.assertIs(insets.clip_for_drawing(self.rows, None), self.rows)


if __name__ == "__main__":
    unittest.main()
