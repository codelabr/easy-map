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


#: These squares stand in for Vietnam, so the meridian that splits them is
#: Vietnam's own — read from the declaration table rather than written here a
#: second time. Every one of these calls used to leave the argument out and let
#: a default fill it in; the default is gone, because it filled itself in for
#: every other country too.
VN_LON = insets.declared("Việt Nam")["meridian"]

MAINLAND = [(105.0, 21.0), (106.5, 16.0), (106.0, 10.5)]
ISLANDS = [(112.0, 16.5), (114.0, 9.0), (116.5, 8.0)]


class TestWhenAnInsetIsWorthIt(unittest.TestCase):
    def test_a_mainland_only_frame_is_framed_the_ordinary_way(self):
        self.assertIsNone(insets.view(frame(MAINLAND), VN_LON))

    def test_offshore_fragments_trigger_the_inset(self):
        self.assertIsNotNone(insets.view(frame(MAINLAND + ISLANDS), VN_LON))

    def test_a_single_province_out_at_sea_gets_no_inset(self):
        """Asked for Khánh Hòa alone, the reader wants Khánh Hòa — there is no
        mainland-versus-islands story to tell."""
        self.assertIsNone(insets.view(frame(ISLANDS), VN_LON))

    def test_an_island_barely_off_the_coast_is_not_worth_a_box(self):
        near = frame(MAINLAND + [(107.4, 16.0)])
        self.assertIsNone(insets.view(near, VN_LON))


class TestFramingNumbers(unittest.TestCase):
    def setUp(self):
        self.plan = insets.view(frame(MAINLAND + ISLANDS), VN_LON)

    def test_the_mainland_gains_width_it_did_not_have(self):
        """The share depends on the shape of the country, so compare it against
        the framing it replaces rather than against a number picked by hand.
        On the real 34-province shapefile this moves 55.7% to 69.4%."""
        rows = frame(MAINLAND + ISLANDS)
        whole = rows.total_bounds[2] - rows.total_bounds[0]
        land = rows.iloc[:len(MAINLAND)]
        land_w = land.total_bounds[2] - land.total_bounds[0]
        before = land_w / whole * 100
        self.assertGreater(self.plan["mainland_width_pct"], before * 1.5)

    def test_the_view_stops_short_of_the_islands(self):
        _, _, view_maxx, _ = self.plan["view_bounds"]
        island_minx, _, _, _ = self.plan["archipelago_bounds"]
        self.assertLess(view_maxx, island_minx)

    def test_the_inset_box_sits_inside_the_view(self):
        vminx, vminy, vmaxx, vmaxy = self.plan["view_bounds"]
        x0, y0, w, h = self.plan["inset_box"]
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
        plan = insets.view(rows, VN_LON)
        self.assertIsNotNone(plan)
        # the drawn map stops well short of the islands, in metres
        self.assertLess(plan["view_bounds"][2], plan["archipelago_bounds"][0])

    def test_the_split_is_in_the_frames_own_units(self):
        """Metres, so the numbers are large — a plan still in degrees would
        report a view a few hundred units wide."""
        plan = insets.view(frame(MAINLAND + ISLANDS, crs=self.METRIC), VN_LON)
        minx, _, maxx, _ = plan["view_bounds"]
        self.assertGreater(maxx - minx, 100_000)

    def test_both_coordinate_systems_split_the_same_units(self):
        """Same three squares each side, whichever units the frame is in."""
        for crs in ("EPSG:4326", self.METRIC):
            rows = frame(MAINLAND + ISLANDS, crs=crs)
            drawn = insets.clip_for_drawing(rows, insets.view(rows, VN_LON))
            kept = [i for i, g in enumerate(drawn.geometry) if not g.is_empty]
            self.assertEqual(kept, list(range(len(MAINLAND))), f"crs={crs}")


#: A country the built-in table has never heard of, with its own detached
#: territory in its own part of the world. Nothing about it resembles Vietnam.
ELSEWHERE = [(12.0, 47.0), (25.0, 46.0), (38.0, 48.0)]
ELSEWHERE_ISLANDS = [(45.7, 46.6), (46.4, 47.4)]


class TestDeclaringWhereTheSplitIs(unittest.TestCase):
    """The meridian is declared, not measured, and any country can declare one.

    Until wave 4 it was ``insets.ARCHIPELAGO_LON = 111.0``, a module constant.
    That is the same as ruling that every country on earth splits at 111°E — and
    since no other country has anything either side of it, the same as ruling
    that no other country ever gets an inset. Nothing said so anywhere.
    """

    def test_vietnams_number_is_unchanged_and_says_where_it_came_from(self):
        found = insets.declared("Việt Nam")
        self.assertEqual(found["meridian"], 111.0)
        self.assertIn("110,64", found["evidence"])

    def test_the_name_may_arrive_as_the_folder_it_sits_in(self):
        """``tên_quốc_gia`` is what the file reports; the fallback is the folder
        name, and those are spelled differently."""
        for spelling in ("Việt Nam", "viet nam", "viet-nam", "VNM", " vietnam "):
            self.assertEqual(insets.declared(spelling)["meridian"], 111.0,
                             spelling)

    def test_a_country_nobody_declared_gets_told_how_to_declare_one(self):
        found = insets.declaration("Fictavia", where="ho_so.json")
        self.assertIsNone(found["meridian"])
        self.assertEqual(found["source"], "undeclared")
        self.assertIn(insets.HAND_KEY, found["how_to_declare"])
        self.assertIn("ho_so.json", found["how_to_declare"])

    def test_a_hand_written_declaration_beats_the_table(self):
        found = insets.declaration("Việt Nam", {insets.HAND_KEY: 120.0})
        self.assertEqual(found["meridian"], 120.0)
        self.assertEqual(found["source"], "declared_by_user")

    def test_null_is_how_a_country_says_it_wants_no_inset(self):
        """Turning Vietnam's own inset off is a decision somebody is allowed to
        make, so it has to be expressible — and it must not read the same as
        having said nothing."""
        found = insets.declaration("Việt Nam", {insets.HAND_KEY: None})
        self.assertIsNone(found["meridian"])
        self.assertNotEqual(found["source"], "undeclared")

    def test_an_unusable_declaration_stops_with_the_key_named(self):
        for bad in ("111", 400.0, True, [111]):
            with self.assertRaises(SystemExit) as stop:
                insets.declaration("Atlantis", {insets.HAND_KEY: bad})
            self.assertIn(insets.HAND_KEY, str(stop.exception), bad)

    def test_the_caption_is_declared_with_the_meridian(self):
        """Nothing in the data says "Hoàng Sa" — the shapefile carries province
        names and the islands are fragments of two of them — so the caption is
        declared too. It used to be a default argument, which is how the first
        map ever drawn with a second country's inset captioned that country's
        islands with Vietnam's."""
        self.assertEqual(insets.declared("Việt Nam")["label"], "Hoàng Sa · Trường Sa")

        bare = insets.declaration("Atlantis", {insets.HAND_KEY: 42.0})
        self.assertIsNone(bare["label"])

        named = insets.declaration("Atlantis", {insets.HAND_KEY: 42.0,
                                                insets.HAND_LABEL_KEY: "Eastern Isles"})
        self.assertEqual(named["label"], "Eastern Isles")

    def test_the_caption_is_read_from_the_profile_too(self):
        self.assertEqual(insets.inset_label({"inset": {"label": "Isles"}}), "Isles")
        for empty in (None, {}, {"inset": {"meridian": 42.0}}):
            self.assertIsNone(insets.inset_label(empty), empty)

    def test_the_meridian_is_read_from_a_profile_not_worked_out_again(self):
        self.assertEqual(insets.meridian({"inset": {"meridian": 42.0}}), 42.0)
        for empty in (None, {}, {"inset": None}, {"inset": {}}):
            self.assertIsNone(insets.meridian(empty), empty)

    def test_no_declaration_means_no_inset_however_scattered_the_land_is(self):
        """The frame splits perfectly at 42°E and still gets no box, because
        nobody said 42. This is the safe half of the change: a country with an
        undeclared meridian is framed the ordinary way and warned about it,
        never framed against another country's number."""
        rows = frame(ELSEWHERE + ELSEWHERE_ISLANDS)
        self.assertIsNone(insets.view(rows, None))
        self.assertIsNone(insets.view(rows, VN_LON))

    def test_a_second_country_declaring_its_own_gets_its_own_inset(self):
        """And this is the half that did not exist at all."""
        rows = frame(ELSEWHERE + ELSEWHERE_ISLANDS)
        plan = insets.view(rows, 42.0)
        self.assertIsNotNone(plan)
        self.assertLess(plan["view_bounds"][2], plan["archipelago_bounds"][0])
        drawn = insets.clip_for_drawing(rows, plan)
        kept = [i for i, g in enumerate(drawn.geometry) if not g.is_empty]
        self.assertEqual(kept, list(range(len(ELSEWHERE))))

    def test_the_split_works_anywhere_on_earth(self):
        """The mask polygons used to be fixed at lat 0–30, lon 95–130 — "wide
        enough for Vietnam and its seas", and nowhere near anywhere else. A
        country outside that window put both halves of the mask where its
        geometry is not, both came back empty, and the split declined without a
        word. A declaration would have been read, honoured and thrown away.

        Same three-plus-two arrangement, carried around the world — but not
        across the antimeridian, which this does not handle and does not claim
        to: see ``_extent``.
        """
        for shift, flip in ((0, 1), (-140, 1), (130, 1), (-25, -1), (60, -1)):
            land = [(x + shift, y * flip) for x, y in ELSEWHERE]
            isles = [(x + shift, y * flip) for x, y in ELSEWHERE_ISLANDS]
            plan = insets.view(frame(land + isles), 42.0 + shift)
            self.assertIsNotNone(plan, (shift, flip))
            self.assertLess(plan["view_bounds"][2], plan["archipelago_bounds"][0],
                            (shift, flip))


class TestClippingForDrawing(unittest.TestCase):
    def setUp(self):
        self.rows = frame(MAINLAND + ISLANDS)
        self.plan = insets.view(self.rows, VN_LON)

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


class TestTheBoxOnThePage(unittest.TestCase):
    """What the corner box is captioned, drawn rather than described."""

    #: Two islands stacked one above the other, so the box that holds them is
    #: tall and narrow — the shape Fictavia's turned out to be, and the shape
    #: Vietnam's is not.
    NARROW = [(112.0, 8.0), (112.2, 20.0)]

    def box(self, label, islands=None):
        try:
            import matplotlib
        except ImportError:                      # pragma: no cover
            raise unittest.SkipTest("cần matplotlib")
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from emap import furniture

        rows = frame(MAINLAND + (islands or ISLANDS))
        plan = insets.view(rows, VN_LON)
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        minx, miny, maxx, maxy = plan["view_bounds"]
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        painted = [(insets.clip_for_drawing(rows, plan), {"color": "#cccccc"})]
        return furniture.archipelago_inset(ax, plan, painted, label=label)

    def test_a_declared_caption_is_written_on_the_box(self):
        self.assertEqual([t.get_text() for t in self.box("Eastern Isles").texts],
                         ["Eastern Isles"])

    def test_no_declaration_means_no_caption_rather_than_vietnams(self):
        self.assertEqual(list(self.box(None).texts), [])

    def test_a_caption_too_wide_for_its_box_is_shrunk_to_fit(self):
        """The box is as wide as the islands are, so a country whose offshore
        territory is tall and narrow gets a narrow box. Vietnam's is wide enough
        that a fixed caption size never showed; the first map drawn for another
        country had its caption running out both sides."""
        from emap import furniture

        wide = self.box("The Far Eastern Island Groups of Atlantis").texts[0]
        self.assertEqual(wide.get_fontsize(), furniture.CAPTION_PT)

        short = self.box("Isles", self.NARROW).texts[0]
        long = self.box("The Far Eastern Island Groups of Atlantis",
                        self.NARROW).texts[0]
        self.assertEqual(short.get_fontsize(), furniture.CAPTION_PT)
        self.assertLess(long.get_fontsize(), furniture.CAPTION_PT)
        self.assertGreaterEqual(long.get_fontsize(), furniture.CAPTION_MIN_PT)


if __name__ == "__main__":
    unittest.main()
