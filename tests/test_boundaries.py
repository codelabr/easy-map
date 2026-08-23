"""The safety net for the multi-country work: what is true of Vietnam, what is
true of a country that is not Vietnam, and where the engine tells the two apart.

Five hundred and seventy-one tests stand behind this project and every one of
them is built on Vietnam. Generalise the engine and they all stay green — which
proves the engine still draws Vietnam and says nothing whatever about any other
country. That is the exact failure mode the handbook has recorded three times:
a change passing the whole suite while being wrong, because the suite rests on
the assumption being changed.

So this file does three separate jobs, and it is worth being clear about which
is which, because they will not all age the same way.

**Pinned facts.** Measurements of the real Vietnamese boundary files. If one of
these changes, the boundary data changed, and the change has to be explained.

**Pinned behaviour.** What the engine does with Vietnam today. These must go on
holding after the multi-country waves land: Vietnam is the regression case, and
"the new code draws Vietnam the same way" is the whole claim.

**Recorded assumptions.** Places where the engine is pinned to Vietnam and a
second country therefore comes out wrong. *These tests are meant to fail* when
the corresponding wave lands. A red line here is the signal that the wave
worked; update it deliberately, with the new number written down. What must not
happen is the wave landing while these stay green — that would mean the
generalisation never reached the constant it was supposed to reach.

Every number below was measured, not assumed. The commands that produced them
are in the plan; the values are repeated here so a failure says what it broke.
"""

from __future__ import annotations

import glob
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import dataio, furniture, insets, matching, semantics

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "countries"

#: Where the real Vietnamese boundaries live once unpacked. They ship as zips
#: and are not in the repository, so a fresh clone has none and the Vietnam
#: measurements skip rather than fail — a missing 135 MB download is not a bug
#: in the engine.
VN_TIERS = {"province": ROOT / "shapefiles" / "provinces",
            "commune": ROOT / "shapefiles" / "communes"}


def geopandas_or_skip():
    try:
        import geopandas  # noqa: F401
    except ImportError:  # pragma: no cover - depends on the machine
        raise unittest.SkipTest("cần geopandas")
    return geopandas


def vietnam(tier: str):
    """The real boundary file for one tier, or a skip."""
    gpd = geopandas_or_skip()
    folder = VN_TIERS[tier]
    found = sorted(glob.glob(str(folder / "*.shp")))
    if not found:
        raise unittest.SkipTest(f"chưa giải nén {folder.name}/")
    return gpd.read_file(found[0])


def fixture(kind: str, tier: str):
    gpd = geopandas_or_skip()
    suffix = {"shp": "shp", "geojson": "geojson", "kml": "kml"}[kind]
    found = sorted(glob.glob(str(FIXTURES / kind / "fictavia" / tier / f"*.{suffix}")))
    if not found:
        raise unittest.SkipTest("chưa dựng fixture: tools/generate_fixture_country.py")
    return gpd.read_file(found[0])


def mainland(gdf, meridian: float):
    """The frame with its detached territory dropped, by bounding box only.

    Nothing is clipped and nothing is redrawn. Whole parts east of the meridian
    are set aside, which is what ``insets.py`` does to decide where to look and
    what a projection has to do before inferring a central meridian.
    """
    parts = gdf.explode(index_parts=False, ignore_index=True)
    return parts[parts.geometry.bounds["minx"] < meridian]


def centre_lon(gdf) -> float:
    b = gdf.total_bounds
    return float((b[0] + b[2]) / 2)


def aspect(gdf) -> float:
    """Height over width, in whatever units the frame is already in."""
    b = gdf.total_bounds
    return float((b[3] - b[1]) / (b[2] - b[0]))


# --------------------------------------------------------------------------
# Pinned facts: the real Vietnamese boundary files
# --------------------------------------------------------------------------

class TestVietnamBoundaryFacts(unittest.TestCase):
    """Measurements of the shipped data. A failure here means the data moved."""

    def test_the_province_tier_holds_the_thirty_four_post_reform_units(self):
        self.assertEqual(len(vietnam("province")), 34)

    def test_the_commune_tier_holds_3321_units(self):
        self.assertEqual(len(vietnam("commune")), 3321)

    def test_tier_order_comes_from_the_feature_count_not_the_folder_name(self):
        """The rule that has to survive generalisation.

        ``provinces`` and ``communes`` happen to sort the right way in English;
        ``region`` before ``district`` does too, and ``comuna`` before
        ``judet`` does not. Counting features works for every country there is.
        """
        self.assertLess(len(vietnam("province")), len(vietnam("commune")))

    def test_every_commune_names_a_province_the_province_tier_knows(self):
        provinces = set(vietnam("province")["ten_tinh"].astype(str).str.strip())
        parents = set(vietnam("commune")["ten_tinh"].astype(str).str.strip())
        self.assertEqual(parents - provinces, set())
        self.assertEqual(len(parents), 34)

    def test_sap_nhap_is_carried_by_both_tiers(self):
        """The merger history, and the reason the crosswalk belongs to the
        Vietnam detector rather than to a tier: no other boundary source
        carries a column like it."""
        self.assertIn("sap_nhap", vietnam("province").columns)
        self.assertIn("sap_nhap", vietnam("commune").columns)

    def test_the_name_column_cannot_be_found_by_counting_distinct_values(self):
        """2,849 distinct commune names over 3,321 communes.

        The obvious heuristic — the text column with the most distinct values
        is the name — picks ``ma_xa`` here, because codes are unique and names
        are not. Anyone who reaches for that heuristic during the detector work
        should be stopped by this line.
        """
        communes = vietnam("commune")
        self.assertEqual(communes["ten_xa"].nunique(), 2849)
        self.assertEqual(communes["ma_xa"].nunique(), 3321)
        self.assertLess(communes["ten_xa"].nunique(), communes["ma_xa"].nunique())

    def test_the_whole_bounding_box_puts_the_central_meridian_out_at_sea(self):
        """109.77°E, which is past the east coast. Hoàng Sa and Trường Sa reach
        117.39°E and drag the midpoint with them."""
        self.assertAlmostEqual(centre_lon(vietnam("province")), 109.7686, places=3)

    def test_the_mainland_alone_puts_it_at_106_39(self):
        land = mainland(vietnam("province"), insets.ARCHIPELAGO_LON)
        self.assertAlmostEqual(centre_lon(land), 106.3919, places=3)
        self.assertAlmostEqual(land.total_bounds[0], 102.1439, places=3)
        self.assertAlmostEqual(land.total_bounds[2], 110.6398, places=3)

    def test_the_mainland_is_portrait(self):
        """1.90 tall to wide. Half of why a locator box sized for Vietnam
        cannot be reused unchanged for a country shaped differently."""
        self.assertAlmostEqual(aspect(mainland(vietnam("province"),
                                               insets.ARCHIPELAGO_LON)),
                               1.9032, places=3)


# --------------------------------------------------------------------------
# Pinned behaviour: what the engine does with Vietnam today
# --------------------------------------------------------------------------

class TestVietnamStaysDrawnTheSameWay(unittest.TestCase):
    """The regression case. These have to hold after every wave."""

    def test_the_two_folder_layout_still_resolves(self):
        for tier, folder in VN_TIERS.items():
            if not sorted(glob.glob(str(folder / "*.shp"))):
                self.skipTest(f"chưa giải nén {folder.name}/")
            found = dataio.find_shapefile(ROOT, tier)
            self.assertEqual(found.parent.name, folder.name)
            self.assertEqual(found.suffix, ".shp")

    def test_the_vietnamese_name_columns_are_the_ones_found(self):
        self.assertEqual(dataio.shape_fields(vietnam("province"), "province"),
                         {"province": "ten_tinh", "commune": None})
        self.assertEqual(dataio.shape_fields(vietnam("commune"), "commune"),
                         {"province": "ten_tinh", "commune": "ten_xa"})

    def test_the_thematic_projection_is_the_pinned_string(self):
        """Written out in full rather than compared to the constant, so that
        editing the constant fails here and has to be meant."""
        self.assertEqual(
            dataio.VIETNAM_EQUAL_AREA,
            "+proj=aea +lat_1=10 +lat_2=22 +lat_0=16 +lon_0=106 "
            "+datum=WGS84 +units=m +no_defs")

    def test_the_pinned_meridian_is_0_39_degrees_off_the_measured_one(self):
        """The plan allows Vietnam's projection to change, from 106.00 to
        106.39. Until it does, the gap is recorded here so that it is a
        decision and not a drift; when it changes, this is where the new
        number gets written down.
        """
        pinned = 106.0
        measured = centre_lon(mainland(vietnam("province"), insets.ARCHIPELAGO_LON))
        self.assertIn("+lon_0=106 ", dataio.VIETNAM_EQUAL_AREA)
        self.assertAlmostEqual(measured - pinned, 0.3919, places=3)


# --------------------------------------------------------------------------
# The fixture itself
# --------------------------------------------------------------------------

class TestTheFixtureIsWhatItClaims(unittest.TestCase):

    def test_both_tiers_are_the_size_they_should_be(self):
        self.assertEqual(len(fixture("shp", "region")), 8)
        self.assertEqual(len(fixture("shp", "district")), 40)

    def test_tier_order_comes_from_the_feature_count_here_too(self):
        self.assertLess(len(fixture("shp", "region")),
                        len(fixture("shp", "district")))

    def test_every_district_names_a_region_the_region_tier_knows(self):
        regions = set(fixture("shp", "region")["NAME_1"])
        parents = set(fixture("shp", "district")["NAME_1"])
        self.assertEqual(parents, regions)
        self.assertEqual(len(regions), 8)

    def test_district_names_repeat_across_regions(self):
        """34 distinct over 40, so the fixture carries Vietnam's naming trap
        as well. Without it, a detector that counts distinct values would pass
        on the fixture and fail on real data."""
        districts = fixture("shp", "district")
        self.assertEqual(districts["NAME_2"].nunique(), 34)
        self.assertEqual(districts["GID_2"].nunique(), 40)

    def test_the_whole_bounding_box_puts_the_meridian_3_70_degrees_wrong(self):
        """Vietnam's version of this error is 0.39°. Fictavia's is nearly ten
        times larger, which is the point of having it: a projection inferred
        the naive way is unmistakable rather than arguable."""
        whole = fixture("shp", "region")
        land = mainland(whole, 42.0)
        self.assertAlmostEqual(centre_lon(whole), 29.20, places=2)
        self.assertAlmostEqual(centre_lon(land), 25.50, places=2)
        self.assertAlmostEqual(centre_lon(whole) - centre_lon(land), 3.70, places=2)

    def test_the_mainland_is_landscape(self):
        land = mainland(fixture("shp", "region"), 42.0)
        self.assertAlmostEqual(aspect(land), 0.2593, places=3)


class TestTheThreeFormatsAgree(unittest.TestCase):
    """Wave 1 has to make these three interchangeable. Here is what is already
    the same between them, and what is not."""

    def test_geometry_and_bounds_are_identical(self):
        """Count and bounds, and then the shapes themselves.

        Bounds alone would not notice an interior boundary moving, which is
        exactly the kind of difference a format conversion can introduce and
        the kind nobody sees on a printed map until a figure is questioned.
        """
        for tier, count in (("region", 8), ("district", 40)):
            reference = fixture("shp", tier)
            for kind in ("shp", "geojson", "kml"):
                frame = fixture(kind, tier)
                self.assertEqual(len(frame), count, kind)
                self.assertEqual([round(float(v), 6) for v in frame.total_bounds],
                                 [round(float(v), 6) for v in reference.total_bounds],
                                 kind)
                self.assertEqual(sorted(round(float(a), 9) for a in frame.geometry.area),
                                 sorted(round(float(a), 9) for a in reference.geometry.area),
                                 kind)

    def test_shapefile_and_geojson_carry_the_same_attribute_table(self):
        for tier in ("region", "district"):
            shp, geojson = fixture("shp", tier), fixture("geojson", tier)
            self.assertEqual(list(shp.columns), list(geojson.columns))

    def test_an_empty_string_survives_as_none_in_a_shapefile_and_as_text_in_geojson(self):
        """Measured, and a trap worth naming: the same absent value reads back
        as two different things depending on which file the user dropped in, so
        ``if value:`` and ``if value is not None:`` disagree by format."""
        self.assertIsNone(fixture("shp", "region")["VARNAME_1"].iloc[0])
        self.assertEqual(fixture("geojson", "region")["VARNAME_1"].iloc[0], "")

    def test_kml_keeps_the_name_and_throws_the_table_away(self):
        """Of eleven columns, one survives as content. What comes back instead
        is KML's own presentation vocabulary. There is nowhere in KML to put a
        population column, so a map drawn from KML cannot show one — the detail
        panel has to omit the row rather than print a zero."""
        region = fixture("kml", "region")
        self.assertIn("Name", region.columns)
        self.assertEqual(region["Name"].iloc[0], "Ardenne")
        for gone in ("GID_1", "COUNTRY", "NAME_1", "TYPE_1", "HASC_1"):
            self.assertNotIn(gone, region.columns)
        for presentation in ("tessellate", "extrude", "visibility"):
            self.assertIn(presentation, region.columns)


# --------------------------------------------------------------------------
# Recorded assumptions: these are meant to go red when a wave lands
# --------------------------------------------------------------------------

class TestWhatIsStillPinnedToVietnam(unittest.TestCase):
    """Seven places the plan says must change. Each one is measured here
    against the fixture, so that "it works for another country now" is a claim
    with a number behind it.

    A failure in this class is not a regression. It means the constant it names
    was generalised, and the line should be rewritten to state the new
    behaviour — never deleted, because the fixture is the only thing standing
    between a generalisation and a silent return to Vietnam-only.
    """

    def test_the_name_columns_do_not_recognise_gadm(self):
        """``dataio.shape_fields`` looks for ``ten_tinh`` and four other
        Vietnamese spellings, so a GADM frame raises. Wave 3."""
        with self.assertRaises(SystemExit):
            dataio.shape_fields(fixture("shp", "region"), "province")
        with self.assertRaises(SystemExit):
            dataio.shape_fields(fixture("shp", "district"), "commune")

    def test_name_matched_by_accident_would_have_been_worse_than_raising(self):
        """``name`` is in both lists, and KML gives every feature a ``Name``.

        So the KML fixture does not raise — it matches, on a column that is
        the right one here purely by luck. Loud failure on the shapefile and
        quiet success on the KML is the shape of the risk in wave 1.
        """
        found = dataio.shape_fields(fixture("kml", "region"), "province")
        self.assertEqual(found["province"], "Name")

    def test_there_is_no_way_to_ask_for_a_country(self):
        """``find_shapefile`` takes a tier and nothing else, and turns anything
        that is not ``province`` into ``communes``. Wave 2 and 3."""
        root = str(FIXTURES / "shp")
        with self.assertRaises(SystemExit):
            dataio.find_shapefile(ROOT, "province", override=root)
        with self.assertRaises(SystemExit):
            dataio.find_shapefile(ROOT, "region", override=root)

    def test_the_locator_box_would_squash_the_fixture_eightfold(self):
        """``LOCATOR_ASPECT`` is Vietnam's 2.2 tall to wide. Fictavia is 0.26.
        A country drawn into a box eight times the wrong shape is not a subtle
        error, and nothing in the code notices it. Wave 4."""
        land = mainland(fixture("shp", "region"), 42.0)
        self.assertEqual(furniture.LOCATOR_ASPECT, 2.2)
        self.assertGreater(furniture.LOCATOR_ASPECT / aspect(land), 8.0)

    def test_the_archipelago_meridian_is_vietnams_and_misses_the_islands(self):
        """111.0°E sits east of everything Fictavia has, so its two island
        groups are read as mainland and the frame stretches to hold them.
        Wave 4."""
        self.assertEqual(insets.ARCHIPELAGO_LON, 111.0)
        whole = fixture("shp", "region")
        self.assertEqual(len(mainland(whole, insets.ARCHIPELAGO_LON)),
                         len(whole.explode(index_parts=False, ignore_index=True)))

    def test_the_coordinate_rule_only_recognises_vietnamese_coordinates(self):
        """A longitude column of Fictavian values is classified as a count, so
        a point map is never offered. Nothing warns; the column simply stops
        being a coordinate. Wave 4."""
        vn = semantics.infer("longitude", [105.8, 106.7, 108.2], True)
        self.assertEqual(vn["semantic"], semantics.COORDINATE)

        fictavia = semantics.infer("longitude", [12.5, 25.5, 38.9], True)
        self.assertNotEqual(fictavia["semantic"], semantics.COORDINATE)

    def test_latitude_too(self):
        vn = semantics.infer("latitude", [10.8, 16.5, 21.0], True)
        self.assertEqual(vn["semantic"], semantics.COORDINATE)

        fictavia = semantics.infer("latitude", [44.5, 47.5, 50.5], True)
        self.assertNotEqual(fictavia["semantic"], semantics.COORDINATE)

    def test_english_administrative_words_are_left_on_the_name(self):
        """``matching._PREFIXES`` is Vietnamese, and the plan keeps it that
        way — deriving prefixes from the data is outside this round. So this
        line is a record of a known cost, not a target: the user's table says
        "Alder District" and the boundary file says "Alder", and the two do
        not normalise to the same string.
        """
        self.assertEqual(matching.normalize("Xã Alder"), "alder")
        self.assertEqual(matching.normalize("Alder District"), "alder district")
        self.assertEqual(matching.normalize("Region of Ardenne"), "region of ardenne")
        self.assertNotEqual(matching.normalize("Alder District"),
                            matching.normalize("Alder"))

    def test_the_users_table_joins_to_nothing_and_says_so(self):
        """The cost above, counted.

        Forty rows, forty misses. The best fuzzy score any of them reaches is
        60.9, well under the floor of 82, so nothing is quietly accepted — and
        every row comes back ``unmatched`` rather than matched-with-a-caveat.
        That last part is the one thing here that is already right, and it is
        worth a line of its own: the module the plan calls the worst risk is
        the module that currently fails loudest.
        """
        rows = (FIXTURES / "fictavia_testing.csv").read_text(
            encoding="utf-8").splitlines()[1:]
        names = [line.split(",")[1] for line in rows]
        index = matching.build_index(
            [{"name": n, "shape_id": i}
             for i, n in enumerate(fixture("shp", "district")["NAME_2"])])

        outcomes, best = [], 0.0
        for name in names:
            feature, score, method = matching.match_one(name, index)
            outcomes.append((feature, matching.status_for(method, score)))
            best = max(best, score)

        self.assertEqual(len(names), 40)
        self.assertEqual({status for _, status in outcomes}, {"unmatched"})
        self.assertEqual([f for f, _ in outcomes if f is not None], [])
        self.assertLess(best, 82.0)


if __name__ == "__main__":
    unittest.main()
