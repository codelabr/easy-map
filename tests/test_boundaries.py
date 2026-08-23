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
import shutil
import tempfile
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
VN_TIERS = {"province": ROOT / "shapefiles" / "viet-nam" / "province",
            "commune": ROOT / "shapefiles" / "viet-nam" / "commune"}


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
        raise unittest.SkipTest(f"chưa giải nén viet-nam/{folder.name}/")
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

    def test_both_tiers_still_resolve_after_the_move(self):
        """The layout changed under Vietnam and Vietnam still resolves.

        ``provinces/`` and ``communes/`` became ``viet-nam/province/`` and
        ``viet-nam/commune/``, by rename rather than by copy — 135 MB is not a
        thing to duplicate in order to reshape a folder. The role names the
        request uses did not change.
        """
        for tier, folder in VN_TIERS.items():
            if not sorted(glob.glob(str(folder / "*.shp"))):
                self.skipTest(f"chưa giải nén viet-nam/{folder.name}/")
            found = dataio.find_boundaries(ROOT, tier, country="viet-nam")
            self.assertEqual(found.parent.name, folder.name)
            self.assertEqual(found.parent.parent.name, "viet-nam")
            self.assertEqual(found.suffix, ".shp")

    def test_the_vietnamese_name_columns_are_the_ones_found(self):
        self.assertEqual(dataio.shape_fields(vietnam("province"), "province"),
                         {"province": "ten_tinh", "commune": None})
        self.assertEqual(dataio.shape_fields(vietnam("commune"), "commune"),
                         {"province": "ten_tinh", "commune": "ten_xa"})

    def test_the_thematic_projection_is_now_derived_and_lands_here(self):
        """Vietnam's projection is no longer written down anywhere.

        It used to be the constant ``VIETNAM_EQUAL_AREA``, at
        ``lat_1=10 lat_2=22 lat_0=16 lon_0=106``, chosen by hand. It is now
        inferred by the same code every country goes through, and the plan
        allowed it to move. Where it moved to is written out in full here, so
        that any further drift is a decision rather than a discovery.

        The hand-picked parallels turn out to have been the two-sixths rule all
        along, rounded: 9.67 and 20.65 against 10 and 22.
        """
        self.assertEqual(
            dataio.thematic_crs(vietnam("province")),
            "+proj=aea +lat_1=9.6747 +lat_2=20.6490 +lat_0=15.1619 "
            "+lon_0=106.4149 +datum=WGS84 +units=m +no_defs")

    def test_the_meridian_moved_by_0_41_degrees_and_no_further(self):
        """What the change to Vietnam actually cost, in one number.

        The old value was 106.00, hand-picked. The plan measured 106.39 by
        dropping everything east of 111 and taking the midpoint of what was
        left. The rule that shipped is neither: it is an area-weighted mean of
        directions, because no meridian separates the mainland United States
        from Alaska and a rule that only works for Vietnam is not a rule. It
        lands at 106.4149 — 0.02 degrees from the plan's figure and 0.41 from
        where Vietnam used to be.
        """
        old = 106.0
        by_the_plans_rule = centre_lon(mainland(vietnam("province"),
                                                insets.ARCHIPELAGO_LON))
        now = float(dataio.thematic_crs(vietnam("province"))
                    .split("+lon_0=")[1].split()[0])

        self.assertAlmostEqual(by_the_plans_rule, 106.3919, places=3)
        self.assertAlmostEqual(now, 106.4149, places=3)
        self.assertAlmostEqual(now - old, 0.4149, places=3)
        self.assertLess(abs(now - by_the_plans_rule), 0.03)

    def test_both_vietnamese_tiers_are_drawn_on_one_projection(self):
        """The two tiers infer meridians 0.0023 degrees apart — small enough to
        look like nothing, and wrong all the same, because the national locator
        sits beside a commune map and the two must share a frame. The run
        resolves one projection from the province tier and reuses it."""
        province = dataio.thematic_crs(vietnam("province"))
        commune = dataio.thematic_crs(vietnam("commune"))
        self.assertNotEqual(province, commune)

        deps = dataio.load(require_geo=True)
        self.assertEqual(dataio.run_thematic_crs(deps, ROOT, country="viet-nam"),
                         province)


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
        """The same absent value reads back as two different things depending
        on which file the user dropped in, so ``if value:`` and
        ``if value is not None:`` disagree by format.

        Written here rather than read from the fixture, because the fixture no
        longer has an empty cell to read: a real GADM download writes the
        string ``"NA"`` where it has nothing, and the fixture was corrected to
        match. The format difference is still real — it shows on a genuine US
        state file as a column with 12 distinct values read one way and 13 the
        other — so it is kept, on data built to have the gap.
        """
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        frame = gpd.GeoDataFrame({"note": ["", "here"]},
                                 geometry=[sg.box(0, 0, 1, 1), sg.box(1, 0, 2, 1)],
                                 crs="EPSG:4326")
        with tempfile.TemporaryDirectory() as folder:
            shp, geojson = Path(folder) / "a.shp", Path(folder) / "a.geojson"
            frame.to_file(shp)
            frame.to_file(geojson, driver="GeoJSON")
            back_shp = gpd.read_file(shp)["note"].iloc[0]
            back_geojson = gpd.read_file(geojson)["note"].iloc[0]

        # Missing, not empty. Which flavour of missing pandas hands back — None
        # or NaN — depends on what else is in the column, and asserting one of
        # them would be pinning the wrong thing. The difference that matters is
        # that the shapefile lost the distinction and the GeoJSON kept it.
        import pandas as pd

        self.assertTrue(pd.isna(back_shp), repr(back_shp))
        self.assertEqual(back_geojson, "")

    def test_the_fixture_carries_gadms_own_way_of_writing_nothing(self):
        """``NA``, the two-letter string, not an empty cell and not a null.

        Verified against ``gadm41_VNM_1.shp``: ``NL_NAME_1`` and ``CC_1`` read
        "NA" in all 63 rows and ``ISO_1`` in 59 of them. A detector that tests
        for emptiness sees a value here; one that tests for the string sees a
        gap. Either way the fixture has to carry the trap rather than a tidier
        version of it.
        """
        region = fixture("shp", "region")
        self.assertEqual(set(region["NL_NAME_1"]), {"NA"})
        self.assertEqual(set(region["ISO_1"]), {"NA"})
        self.assertEqual(list(region["VARNAME_1"]), list(region["NAME_1"]))

    def test_kml_keeps_the_whole_attribute_table(self):
        """Measured against a real KML, and it overturns what the plan assumed.

        KML carries a ``<Schema>`` of ``SimpleField`` declarations and hangs the
        values off each feature, so every column survives the round trip. The
        plan expected a name and a description; the truth is the full table. A
        map drawn from KML can therefore show population like any other.

        What KML *adds* is twelve presentation fields of its own, and those are
        the ones that look like data and are not.
        """
        region = fixture("kml", "region")
        for kept in ("GID_1", "GID_0", "COUNTRY", "NAME_1", "TYPE_1",
                     "ENGTYPE_1", "CC_1", "HASC_1"):
            self.assertIn(kept, region.columns)
        self.assertEqual(list(region["NAME_1"]), list(fixture("shp", "region")["NAME_1"]))
        for presentation in ("id", "Name", "description", "timestamp",
                             "tessellate", "extrude", "visibility", "icon"):
            self.assertIn(presentation, region.columns)

    def test_a_shapefile_without_a_codepage_file_mangles_accented_names(self):
        """The cheapest way to lose a place name, found on two real downloads.

        A shapefile keeps its attributes in a DBF, and a DBF does not record
        which encoding it used. The convention is a companion ``.cpg`` file
        holding the name of the codepage. Without it the reader guesses, and
        the guess is Latin-1, so UTF-8 bytes come back as mojibake: ``é`` reads
        as ``Ã©``.

        The damage scales with how many diacritics the language uses. On a
        Canadian download it cost one name in thirteen — Québec. On a
        Vietnamese one from the same collection it cost **53 of 63**, because
        almost every province name carries a mark. The fix is a five-byte file.

        This is not a Vietnam problem and not a foreign-country problem. It is
        a shapefile problem, and it arrives silently: the names are all still
        there, they are simply the wrong strings.
        """
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        frame = gpd.GeoDataFrame(
            {"name": ["Québec", "Đắk Nông", "Ontario"]},
            geometry=[sg.box(i, 0, i + 1, 1) for i in range(3)], crs="EPSG:4326")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "accents.shp"
            frame.to_file(path)
            self.assertTrue(path.with_suffix(".cpg").exists(),
                            "the writer is expected to record the codepage")
            self.assertEqual(list(gpd.read_file(path)["name"]), list(frame["name"]))

            path.with_suffix(".cpg").unlink()
            without = list(gpd.read_file(path)["name"])

        self.assertEqual(without[2], "Ontario")           # no marks, unharmed
        self.assertNotEqual(without[0], "Québec")
        self.assertNotEqual(without[1], "Đắk Nông")
        self.assertEqual(without[0], "QuÃ©bec")

    def test_kml_swallows_a_column_that_happens_to_be_called_name(self):
        """The trap underneath the good news.

        A field literally called ``NAME`` is promoted into KML's own ``<name>``
        element on the way out, so it comes back as ``Name`` and is gone under
        its original heading. GADM's ``NAME_1`` is not promoted and survives
        untouched; a source that spells the column ``NAME`` — and a widely used
        US state boundary file does exactly that — loses it.

        So the same reader, on two files of the same data, has to look for two
        different column names. Written and read here rather than asserted from
        the fixture, because the fixture has no column KML would promote.
        """
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        frame = gpd.GeoDataFrame(
            {"NAME": ["Alpha", "Beta"], "POP": [10, 20]},
            geometry=[sg.box(0, 0, 1, 1), sg.box(1, 0, 2, 1)], crs="EPSG:4326")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "promoted.kml"
            frame.to_file(path, driver="KML")
            back = gpd.read_file(path)

        self.assertNotIn("NAME", back.columns)
        self.assertEqual(list(back["Name"]), ["Alpha", "Beta"])
        # and the second trap in the same round trip: the writer declares every
        # SimpleField as type="string", so a count comes back as text. A KML
        # written by some other tool can declare int and float properly — a US
        # state file to hand does — so the reader cannot trust either way and
        # has to coerce. A population column read as text is never offered as
        # something to map.
        self.assertEqual(list(back["POP"]), ["10", "20"])


# --------------------------------------------------------------------------
# Reading any of the three formats, and choosing a projection to draw them in
# --------------------------------------------------------------------------

def boxes(spans, crs="EPSG:4326"):
    """A frame of rectangles given as (lon0, lat0, lon1, lat1)."""
    gpd = geopandas_or_skip()
    import shapely.geometry as sg

    return gpd.GeoDataFrame({"name": [f"u{i}" for i in range(len(spans))]},
                            geometry=[sg.box(*s) for s in spans], crs=crs)


def meridian_of(gdf) -> float:
    return float(dataio.thematic_crs(gdf).split("+lon_0=")[1].split()[0])


class OwnBoundariesOnly(unittest.TestCase):
    """A test that builds its own boundaries has to be sure they are the ones read.

    The installer sets ``EASY_MAP_SHAPEFILES`` at the user level so that a
    globally installed skill can draw from any working folder, and that setting
    outranks the project root. On a machine where the skill is installed, a test
    that hands ``load_shapes`` a temporary project therefore gets the machine's
    own Vietnamese boundaries and never notices: the call succeeds, the frame is
    full, and every count is wrong.

    Found by writing a test that expected 40 units and got 34 — the number of
    Vietnamese provinces. A test asserting something weaker would have passed.
    """

    def setUp(self):
        import os

        self._saved = os.environ.pop(dataio.SHAPEFILE_ENV, None)
        if self._saved is not None:
            self.addCleanup(os.environ.__setitem__, dataio.SHAPEFILE_ENV, self._saved)


class TestAnyOfTheThreeFormatsLoads(OwnBoundariesOnly):
    """The acceptance test for this round: a tier folder holding a GeoJSON or a
    KML draws the same map as one holding a shapefile."""

    def load(self, kind: str, tier: str):
        """The fixture's tier folder, copied under the name the loader expects."""
        geopandas_or_skip()
        source = FIXTURES / kind / "fictavia" / tier
        if not source.exists():
            self.skipTest("chưa dựng fixture")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "shapefiles" / "provinces"
            target.mkdir(parents=True)
            for path in source.iterdir():
                shutil.copy(path, target / path.name)
            return dataio.load_shapes(dataio.load(require_geo=True),
                                      Path(folder), "province")

    def test_all_three_carry_the_same_geometry_through_the_loader(self):
        reference = self.load("shp", "region")
        self.assertEqual(len(reference), 8)
        for kind in ("geojson", "kml"):
            frame = self.load(kind, "region")
            self.assertEqual(len(frame), 8, kind)
            self.assertEqual(sorted(round(float(a), 9) for a in frame.geometry.area),
                             sorted(round(float(a), 9) for a in reference.geometry.area),
                             kind)

    def test_all_three_are_given_the_same_projection(self):
        """Which is the point of inferring it from the geometry rather than
        from anything written in the file: the three files disagree about
        column names and about types, and agree about where the country is."""
        crs = {kind: dataio.thematic_crs(self.load(kind, "region"))
               for kind in ("shp", "geojson", "kml")}
        self.assertEqual(len(set(crs.values())), 1, crs)

    def test_every_format_gets_a_shape_id(self):
        for kind in ("shp", "geojson", "kml"):
            frame = self.load(kind, "district")
            self.assertEqual(list(frame["__shape_id"]), list(range(40)), kind)


class TestTheProjectionComesFromTheData(unittest.TestCase):

    def test_the_fixture_lands_where_it_was_measured_by_hand(self):
        self.assertAlmostEqual(meridian_of(fixture("shp", "region")), 25.54, places=2)

    def test_a_country_across_the_antimeridian_is_not_centred_on_africa(self):
        """The failure that made this rule necessary.

        Averaging −179 and 179 arithmetically gives 0, which is the Gulf of
        Guinea. The two are half a degree apart, not 358. On the real United
        States file the arithmetic mean comes out at 0.32, and the projection
        then turns valid state outlines into self-intersecting ones.
        """
        straddling = boxes([(177.0, 10.0, 179.0, 12.0), (-179.0, 10.0, -177.0, 12.0)])
        self.assertAlmostEqual(centre_lon(straddling), 0.0, places=6)   # the trap
        self.assertGreater(abs(meridian_of(straddling)), 179.0)

    def test_a_scatter_of_small_islands_does_not_drag_the_centre_out_to_sea(self):
        """Vietnam's version of this is Hoàng Sa and Trường Sa; the fixture's is
        two squares in the east. Weighting by area is what replaces the
        hard-coded meridian that used to separate them."""
        mainland_only = boxes([(0.0, 0.0, 10.0, 10.0)])
        with_islands = boxes([(0.0, 0.0, 10.0, 10.0),
                              (59.9, 5.0, 60.0, 5.1), (60.4, 5.0, 60.5, 5.1)])
        self.assertAlmostEqual(centre_lon(with_islands), 30.25, places=2)   # the trap
        self.assertAlmostEqual(meridian_of(with_islands),
                               meridian_of(mainland_only), places=1)

    def test_a_country_barely_taller_than_a_point_still_gets_two_parallels(self):
        """Two standard parallels on top of each other is where a conic stops
        being a conic. A city state has to come out with a usable projection
        rather than a division by nothing."""
        crs = dataio.thematic_crs(boxes([(103.6, 1.25, 104.0, 1.47)]))
        lat_1 = float(crs.split("+lat_1=")[1].split()[0])
        lat_2 = float(crs.split("+lat_2=")[1].split()[0])
        self.assertGreater(lat_2 - lat_1, 0.5)

    def test_the_poles_do_not_produce_a_parallel_past_ninety(self):
        """A sliver of territory at the pole is where the two guards meet.

        The span is under a degree, so it is padded outwards; the padding
        pushes the northern edge past 90, and a standard parallel there is not
        a parallel. The first draft of this test used a territory reaching
        89.9 and passed with the clamp removed, because the two-sixths rule
        pulled the parallels inside 89 on its own — it proved nothing.
        """
        crs = dataio.thematic_crs(boxes([(-40.0, 89.6, 20.0, 90.0)]))
        for key in ("+lat_1=", "+lat_2=", "+lat_0="):
            self.assertLessEqual(abs(float(crs.split(key)[1].split()[0])), 89.0, key)

    def test_the_render_command_resolves_the_projection_once_for_the_run(self):
        """Read out of the source, because the mistake it guards against is a
        mistake in the caller rather than in the projection.

        ``thematic_crs(shapes)`` and ``run_thematic_crs(deps, root)`` return
        almost the same string, and swapping one for the other changes nothing
        anyone would see: a commune map would simply be centred 0.0023 degrees
        away from the national locator drawn beside it. Every behavioural test
        here passes either way, which is why this one reads the call instead.
        """
        import ast

        source = (ROOT / "skills" / "easy-map" / "scripts" / "easy_map.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        body = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "command_render")
        called = {ast.unparse(node.func) for node in ast.walk(body)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}

        self.assertIn("dataio.run_thematic_crs", called)
        self.assertNotIn("dataio.thematic_crs", called)

    def test_every_projection_it_produces_can_actually_be_used(self):
        for label, frame in (("fixture", fixture("shp", "region")),
                             ("vietnam", vietnam("province"))):
            projected = frame.to_crs(dataio.thematic_crs(frame))
            self.assertTrue(projected.geometry.is_valid.all(), label)
            projected.geometry.union_all()          # this is what used to die


class TestTheFolderLayout(OwnBoundariesOnly):
    """One folder per country, one folder per tier, and the old shape moved
    across on the first command rather than left for the user to redo."""

    def root(self, folder):
        root = Path(folder) / "shapefiles"
        root.mkdir(parents=True)
        return root

    def dataset(self, tier: Path, count: int, name="units"):
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        tier.mkdir(parents=True, exist_ok=True)
        gpd.GeoDataFrame({"ten_tinh": [f"u{i}" for i in range(count)]},
                         geometry=[sg.box(i, 0, i + 1, 1) for i in range(count)],
                         crs="EPSG:4326").to_file(tier / f"{name}.shp")

    def test_the_old_two_folder_layout_moves_itself_under_viet_nam(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "provinces", 3)
            self.dataset(root / "communes", 9)

            moved = dataio.migrate_legacy_layout(root)

            self.assertEqual([m["trạng_thái"] for m in moved],
                             ["đã_chuyển", "đã_chuyển"])
            self.assertFalse((root / "provinces").exists())
            self.assertTrue((root / "viet-nam" / "province" / "units.shp").is_file())
            self.assertTrue((root / "viet-nam" / "commune" / "units.shp").is_file())
            self.assertEqual(dataio.countries(root), ["viet-nam"])

    def test_a_move_never_overwrites_what_is_already_there(self):
        """The two could be different data, and only the user knows which is
        wanted. Reported and left alone rather than resolved by guessing."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "provinces", 3, name="old")
            self.dataset(root / "viet-nam" / "province", 5, name="new")

            moved = dataio.migrate_legacy_layout(root)

            self.assertEqual(moved[0]["trạng_thái"], "bỏ_qua_vì_đích_đã_có")
            self.assertTrue((root / "provinces" / "old.shp").is_file())
            self.assertTrue((root / "viet-nam" / "province" / "new.shp").is_file())

    def test_the_tier_order_comes_from_the_counts_not_the_names(self):
        """``comuna`` sorts before ``judet`` and would be backwards; counting
        features is right for every country there is."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "romania" / "comuna", 40)
            self.dataset(root / "romania" / "judet", 6)

            order = dataio.tiers(root, "romania")

            self.assertEqual([t["thư_mục"] for t in order], ["judet", "comuna"])
            self.assertEqual([t["vai_trò"] for t in order],
                             [dataio.COARSE, dataio.FINE])

    def test_a_country_with_one_tier_can_be_drawn_at_that_tier(self):
        """The case the old layout could not express at all: both folders had
        to exist or the lookup failed, so a boundary set that stops at states
        could not be loaded even to draw the states."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "united-states" / "state", 51)

            order = dataio.tiers(root, "united-states")
            self.assertEqual([t["vai_trò"] for t in order], [dataio.COARSE])

            found = dataio.find_boundaries(Path(folder), "state")
            self.assertEqual(found.parent.name, "state")
            self.assertEqual(dataio.find_boundaries(Path(folder), dataio.COARSE),
                             found)
            with self.assertRaises(SystemExit):
                dataio.find_boundaries(Path(folder), dataio.FINE)

    def test_more_than_one_country_is_refused_rather_than_guessed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "canada" / "province", 13)
            self.dataset(root / "viet-nam" / "province", 34)

            with self.assertRaises(SystemExit) as raised:
                dataio.find_boundaries(Path(folder), dataio.COARSE)
            self.assertIn("canada", str(raised.exception))
            self.assertIn("viet-nam", str(raised.exception))

            named = dataio.find_boundaries(Path(folder), dataio.COARSE,
                                           country="canada")
            self.assertEqual(named.parent.parent.name, "canada")

    def test_a_folder_name_becomes_a_role_before_anything_else_sees_it(self):
        """Read out of the source, and here is why that is the honest way.

        Everything downstream asks ``admin_level == "commune"`` to decide how
        to behave — which name column to use, which index to match against,
        whether to draw a locator. A request for a folder called ``district``
        has to become the role ``commune`` at the seam. If the folder name
        stays in circulation instead, a fine tier goes down every coarse-tier
        branch and the map comes out wrong in a dozen small ways at once.

        Seven defects were planted in this round's code and six were caught by
        behaviour. This was the one that was not: every test still passed with
        the folder name in place, because the fixtures happen to name their
        tiers ``province`` and ``commune`` and the two coincide.
        """
        import ast

        source = ROOT / "skills" / "easy-map" / "scripts" / "easy_map.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        body = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "command_render")
        assigned = [ast.unparse(node.value) for node in ast.walk(body)
                    if isinstance(node, ast.Assign)
                    and any(ast.unparse(t) == "admin_level" for t in node.targets)]

        self.assertTrue(assigned, "command_render no longer sets admin_level")
        for expression in assigned:
            self.assertNotIn("thư_mục", expression)
        self.assertTrue(any("vai_trò" in e for e in assigned), assigned)

    def test_the_two_roles_are_the_words_the_rest_of_the_engine_uses(self):
        """The roles are not free-form: the whole engine branches on these two
        strings, so renaming them here would be a silent rewrite of every
        branch that reads them."""
        self.assertEqual((dataio.COARSE, dataio.FINE), ("province", "commune"))

    def test_an_unreadable_file_does_not_take_down_the_listing(self):
        """Counting features runs while saying what is *available*. A boundary
        file that cannot be opened is a real error, but raising it here would
        take down the one command whose job is to report what is present."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "somewhere" / "state", 4)
            broken = root / "somewhere" / "rubbish"
            broken.mkdir()
            (broken / "not-really.geojson").write_text("{", encoding="utf-8")

            order = dataio.tiers(root, "somewhere")

            self.assertEqual([t["thư_mục"] for t in order], ["state", "rubbish"])
            self.assertEqual(order[0]["số_đơn_vị"], 4)
            self.assertIsNone(order[1]["số_đơn_vị"])


class TestARepairedCodepage(OwnBoundariesOnly):

    def frame_in(self, folder, names, codepage: bool):
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        tier = folder / "shapefiles" / "provinces"
        tier.mkdir(parents=True)
        path = tier / "units.shp"
        gpd.GeoDataFrame({"ten_tinh": list(names)},
                         geometry=[sg.box(i, 0, i + 1, 1) for i in range(len(names))],
                         crs="EPSG:4326").to_file(path)
        if not codepage:
            path.with_suffix(".cpg").unlink()
        return path

    def test_the_names_come_back_right_and_the_repair_is_reported(self):
        names = ["Québec", "Đắk Nông", "Ontario"]
        with tempfile.TemporaryDirectory() as folder:
            self.frame_in(Path(folder), names, codepage=False)
            notes: list = []
            frame = dataio.load_shapes(dataio.load(require_geo=True),
                                       Path(folder), "province", notes=notes)

        self.assertEqual(list(frame["ten_tinh"]), names)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["tệp"], "province/units.shp")
        self.assertEqual(notes[0]["cách_sửa"], "province/units.cpg")
        self.assertGreaterEqual(notes[0]["số_giá_trị"], 2)

    def test_a_file_that_was_never_broken_is_left_alone_and_unreported(self):
        names = ["Québec", "Ontario"]
        with tempfile.TemporaryDirectory() as folder:
            self.frame_in(Path(folder), names, codepage=True)
            notes: list = []
            frame = dataio.load_shapes(dataio.load(require_geo=True),
                                       Path(folder), "province", notes=notes)
        self.assertEqual(list(frame["ten_tinh"]), names)
        self.assertEqual(notes, [])

    def test_a_file_that_declares_its_codepage_is_taken_at_its_word(self):
        """The guard that stops the repair from becoming the fault.

        Some real string genuinely is "QuÃ©bec" — a column of raw text, a name
        somebody typed. If it arrives in a file that names its own codepage,
        there is nothing to infer and nothing to fix, and repairing it anyway
        would corrupt data on the strength of a guess.

        Without the ``.cpg`` check this passes silently, because the round trip
        succeeds on that string whether or not anything is wrong.
        """
        names = ["QuÃ©bec", "Ontario"]
        with tempfile.TemporaryDirectory() as folder:
            self.frame_in(Path(folder), names, codepage=True)
            notes: list = []
            frame = dataio.load_shapes(dataio.load(require_geo=True),
                                       Path(folder), "province", notes=notes)
        self.assertEqual(list(frame["ten_tinh"]), names)
        self.assertEqual(notes, [])

    def test_a_genuine_latin_1_name_is_not_mistaken_for_mojibake(self):
        """The round trip is the test, not the presence of an odd character.

        The mis-read forms below are built from the definition of the fault —
        UTF-8 bytes decoded as Latin-1 — rather than pasted in, so the test
        cannot drift from what it claims to be about.

        "Åland" mis-typed as "Ãland" is not a mis-read: 0xC3 followed by an
        ASCII letter is not a valid UTF-8 sequence. A keyword list of
        suspicious characters would have corrupted it.
        """
        for good in ("Québec", "Đắk Nông", "Hà Nội"):
            broken = good.encode("utf-8").decode("latin-1")
            self.assertNotEqual(broken, good)
            self.assertEqual(dataio.demojibake(broken), good)

        self.assertIsNone(dataio.demojibake("Ãland"))
        self.assertIsNone(dataio.demojibake("Ontario"))
        self.assertIsNone(dataio.demojibake("Québec"))


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

    def test_a_country_can_now_be_asked_for_by_name(self):
        """This line used to record the opposite.

        ``find_boundaries`` took a tier and nothing else, and turned anything
        that was not ``province`` into ``communes``; the fixture could not be
        reached at all. It is now addressed by country and by tier, and the
        tier can be named either by its role or by its own folder name.
        """
        root = str(FIXTURES / "shp")
        by_folder = dataio.find_boundaries(ROOT, "region", override=root,
                                           country="fictavia")
        by_role = dataio.find_boundaries(ROOT, "province", override=root,
                                         country="fictavia")
        self.assertEqual(by_folder, by_role)
        self.assertEqual(by_folder.parent.name, "region")

        self.assertEqual(dataio.countries(Path(root)), ["fictavia"])
        with self.assertRaises(SystemExit):
            dataio.find_boundaries(ROOT, "province", override=root,
                                   country="nowhere")

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
