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
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import (dataio, detect, furniture, guardrails, i18n, insets,
                  matching, semantics)

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


#: Vietnam's split meridian, read from the declaration table rather than from a
#: module constant. It stopped being a constant in wave 4: a number every map in
#: the world was measured against became a number one country declares.
VN_LON = insets.declared("Việt Nam")["meridian"]


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
        land = mainland(vietnam("province"), VN_LON)
        self.assertAlmostEqual(centre_lon(land), 106.3919, places=3)
        self.assertAlmostEqual(land.total_bounds[0], 102.1439, places=3)
        self.assertAlmostEqual(land.total_bounds[2], 110.6398, places=3)

    def test_the_mainland_is_portrait(self):
        """1.90 tall to wide. Half of why a locator box sized for Vietnam
        cannot be reused unchanged for a country shaped differently."""
        self.assertAlmostEqual(aspect(mainland(vietnam("province"),
                                               VN_LON)),
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
                                                VN_LON))
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

            self.assertEqual([m["status"] for m in moved],
                             ["moved", "moved"])
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

            self.assertEqual(moved[0]["status"], "skipped_target_exists")
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

            self.assertEqual([t["folder"] for t in order], ["judet", "comuna"])
            self.assertEqual([t["role"] for t in order],
                             [dataio.COARSE, dataio.FINE])

    def test_a_country_with_one_tier_can_be_drawn_at_that_tier(self):
        """The case the old layout could not express at all: both folders had
        to exist or the lookup failed, so a boundary set that stops at states
        could not be loaded even to draw the states."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.root(folder)
            self.dataset(root / "united-states" / "state", 51)

            order = dataio.tiers(root, "united-states")
            self.assertEqual([t["role"] for t in order], [dataio.COARSE])

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
            self.assertNotIn("folder", expression)
        self.assertTrue(any("role" in e for e in assigned), assigned)

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

            self.assertEqual([t["folder"] for t in order], ["state", "rubbish"])
            self.assertEqual(order[0]["unit_count"], 4)
            self.assertIsNone(order[1]["unit_count"])


class TestReadingWhatAFileIs(unittest.TestCase):
    """Three named schemes and a general path, and what separates them."""

    def frame(self, columns: dict, rows: int | None = None):
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        count = rows if rows is not None else len(next(iter(columns.values())))
        return gpd.GeoDataFrame(columns,
                                geometry=[sg.box(i, 0, i + 1, 1) for i in range(count)],
                                crs="EPSG:4326")

    def test_the_vietnamese_schema_is_read_from_its_own_columns(self):
        reading = detect.identify(vietnam("commune"))
        self.assertEqual(reading["dataset"], detect.VIETNAM)
        self.assertEqual(reading["name_column"], "ten_xa")
        self.assertEqual(reading["parent_column"], "ten_tinh")
        self.assertEqual(reading["merger_column"], "sap_nhap")
        self.assertEqual(reading["confidence"], detect.SURE)

    def test_gadm_is_read_by_its_level_number(self):
        district = detect.identify(fixture("shp", "district"))
        self.assertEqual(district["dataset"], detect.GADM)
        self.assertEqual((district["name_column"], district["parent_column"]), ("NAME_2", "NAME_1"))
        self.assertEqual(district["level"], 2)
        self.assertEqual(district["country"], "Fictavia")

    def test_a_gadm_country_outline_is_not_a_tier(self):
        """The trap a real download springs.

        A GADM archive holds levels 0 to 3, and level 0 is the outline of the
        whole country: one feature, no ``NAME_1``, and therefore the *smallest*
        tier in the set. Ranked by size it takes the coarsest role, and every
        province in the user's table is then matched against a single shape
        called "Vietnam".
        """
        outline = self.frame({"GID_0": ["XFA"], "COUNTRY": ["Fictavia"]})
        reading = detect.identify(outline)
        self.assertEqual(reading["dataset"], detect.GADM)
        self.assertEqual(reading["level"], 0)
        self.assertTrue(reading["is_country_outline"])
        with self.assertRaises(SystemExit):
            dataio.shape_fields(outline, dataio.COARSE)

    def test_geoboundaries_is_read_from_shape_name_and_group(self):
        reading = detect.identify(self.frame({
            "shapeName": ["An Giang", "Bắc Ninh"], "shapeISO": ["VN-44", "VN-56"],
            "shapeID": ["a", "b"], "shapeGroup": ["VNM", "VNM"],
            "shapeType": ["ADM1", "ADM1"]}))
        self.assertEqual(reading["dataset"], detect.GEOBOUNDARIES)
        self.assertEqual(reading["name_column"], "shapeName")
        self.assertEqual((reading["country"], reading["level"]), ("VNM", 1))

    def test_the_general_path_does_not_pick_a_column_of_one_repeated_value(self):
        """The mistake the first draft of this made, twice over.

        A US state file carries ``TYPE``, reading "Land" for all 53 rows, and a
        Canadian one carries ``source``, holding the same URL 13 times. Both
        are text, both are the right length, and the first scoring rule gave
        them the same perfect mark as the name column beside them.
        """
        reading = detect.identify(self.frame({
            "NAME": ["Arkansas", "Colorado", "Delaware", "Florida"],
            "TYPE": ["Land"] * 4,
            "source": ["https://example.invalid"] * 4}))
        self.assertEqual(reading["name_column"], "NAME")

    def test_the_general_path_does_not_pick_a_two_letter_code(self):
        """``AR`` and ``05`` vary as much as ``Arkansas`` does — every value
        distinct — so variety cannot separate them. Length can: every real
        name column measured has a median of 8 or more, every code 4 or less."""
        reading = detect.identify(self.frame({
            "STATE_ABBR": ["AR", "CO", "DE", "FL"],
            "STATE_FIPS": ["05", "08", "10", "12"],
            "NAME": ["Arkansas", "Colorado", "Delaware", "Florida"]}))
        self.assertEqual(reading["name_column"], "NAME")
        self.assertEqual(reading["confidence"], detect.LIKELY)
        self.assertIn("STATE_ABBR", reading["evidence"])

    def test_a_photo_finish_becomes_a_question_rather_than_a_decision(self):
        """Picking wrong here labels every unit on the map with the wrong
        string and nothing downstream notices, so a close call has to reach
        the user rather than be settled quietly."""
        reading = detect.identify(self.frame({
            "ten_a": ["Alpha One", "Beta Two", "Gamma Three"],
            "ten_b": ["Delta Four", "Epsilon Five", "Zeta Six"]}))
        self.assertEqual(reading["confidence"], detect.ASK)

    def test_nothing_readable_is_said_so_rather_than_guessed_at(self):
        reading = detect.identify(self.frame({"a": ["1", "2"], "b": ["3", "4"]}))
        self.assertIsNone(reading["name_column"])
        self.assertEqual(reading["confidence"], detect.ASK)

    def test_the_parent_link_is_found_by_matching_the_other_tier(self):
        """The one piece of evidence a code column cannot fake. It is checked
        against the real files rather than a schema claim, because a schema
        that does not survive its own check is worth knowing about."""
        link = detect.link_tiers(vietnam("province"),
                                 detect.identify(vietnam("province")),
                                 vietnam("commune"),
                                 detect.identify(vietnam("commune")))
        self.assertEqual(link["parent_column"], "ten_tinh")
        self.assertEqual(link["confidence"], detect.SURE)
        self.assertIn("3321/3321", link["evidence"])

    def test_tiers_that_do_not_line_up_are_reported_rather_than_joined(self):
        coarse = self.frame({"ten_tinh": ["Hà Nội", "Huế"]})
        fine = self.frame({"ten_xa": ["Ba Đình", "Cửa Nam"],
                           "ten_tinh": ["Nowhere", "Elsewhere"]})
        link = detect.link_tiers(coarse, detect.identify(coarse),
                                 fine, detect.identify(fine))
        self.assertEqual(link["confidence"], detect.ASK)


class TestTheCountryProfile(OwnBoundariesOnly):
    """One reading per country, kept beside the boundaries, with its evidence."""

    def country(self, folder, **tiers):
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        root = Path(folder) / "shapefiles"
        for tier, columns in tiers.items():
            place = root / "atlantis" / tier
            place.mkdir(parents=True)
            count = len(next(iter(columns.values())))
            gpd.GeoDataFrame(
                columns,
                geometry=[sg.box(i, 0, i + 1, 1) for i in range(count)],
                crs="EPSG:4326").to_file(place / f"{tier}.shp")
        return root

    def test_it_records_the_reading_the_projection_and_the_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.country(
                folder,
                region={"NAME_1": ["Ardenne", "Beluar"], "GID_0": ["ATL", "ATL"],
                        "COUNTRY": ["Atlantis", "Atlantis"]},
                district={"NAME_2": ["Alder", "Brann", "Calvet", "Dorne"],
                          "NAME_1": ["Ardenne", "Ardenne", "Beluar", "Beluar"],
                          "GID_0": ["ATL"] * 4})
            reading = dataio.read_country(dataio.load(require_geo=True),
                                          root, "atlantis")

        self.assertEqual(reading["detected"]["dataset"], detect.GADM)
        self.assertEqual(reading["country_name"], "Atlantis")
        self.assertIn("+proj=aea", reading["projection"]["crs"])
        self.assertEqual(reading["parent_link"]["parent_column"], "NAME_1")
        self.assertIn("4/4", reading["parent_link"]["evidence"])
        self.assertEqual([t["role"] for t in reading["tiers"]],
                         [dataio.COARSE, dataio.FINE])

    def test_it_is_written_once_and_read_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.country(folder, region={"NAME_1": ["Ardenne", "Beluar"],
                                                "GID_0": ["ATL", "ATL"]})
            deps = dataio.load(require_geo=True)
            first = dataio.read_country(deps, root, "atlantis")
            self.assertTrue((root / dataio.PROFILE).is_file())
            again = dataio.read_country(deps, root, "atlantis")
        self.assertEqual(first, again)

    def test_it_records_that_nobody_has_declared_an_inset(self):
        """"No inset here" and "nobody has said" are different states, and the
        profile has to tell them apart — otherwise a map framed the ordinary way
        looks like a map that was examined and found not to need a box."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.country(folder, region={"NAME_1": ["Ardenne", "Beluar"],
                                                "GID_0": ["ATL", "ATL"],
                                                "COUNTRY": ["Atlantis"] * 2})
            reading = dataio.read_country(dataio.load(require_geo=True),
                                          root, "atlantis")
        self.assertIsNone(reading["inset"]["meridian"])
        self.assertEqual(reading["inset"]["source"], "undeclared")
        self.assertIn(insets.HAND_KEY, reading["inset"]["how_to_declare"])
        self.assertIn(dataio.PROFILE, reading["inset"]["how_to_declare"])

    def test_a_declaration_written_by_hand_survives_a_rebuild(self):
        """Everything else in the profile is the machine's reading and is thrown
        away the moment a boundary file changes size. A declaration is not a
        reading: losing it because somebody replaced a shapefile would undo a
        decision nobody asked to undo."""
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        with tempfile.TemporaryDirectory() as folder:
            root = self.country(folder, region={"NAME_1": ["Ardenne", "Beluar"],
                                                "GID_0": ["ATL", "ATL"],
                                                "COUNTRY": ["Atlantis"] * 2})
            deps = dataio.load(require_geo=True)
            dataio.read_country(deps, root, "atlantis")

            store = root / dataio.PROFILE
            saved = json.loads(store.read_text(encoding="utf-8"))
            saved["atlantis"]["declared"] = {insets.HAND_KEY: 0.5}
            store.write_text(json.dumps(saved, ensure_ascii=False),
                             encoding="utf-8")

            declared = dataio.read_country(deps, root, "atlantis", rebuild=True)
            self.assertEqual(declared["inset"]["meridian"], 0.5)
            self.assertEqual(declared["inset"]["source"], "declared_by_user")

            # a boundary file changes size, so every reading is recomputed
            place = root / "atlantis" / "district"
            place.mkdir()
            gpd.GeoDataFrame(
                {"NAME_2": ["Alder", "Brann", "Calvet"], "GID_0": ["ATL"] * 3,
                 "NAME_1": ["Ardenne", "Ardenne", "Beluar"]},
                geometry=[sg.box(i, 0, i + 1, 1) for i in range(3)],
                crs="EPSG:4326").to_file(place / "district.shp")
            after = dataio.read_country(deps, root, "atlantis")

        self.assertEqual(len(after["tiers"]), 2)          # it did rebuild
        self.assertEqual(after["inset"]["meridian"], 0.5)

    def test_a_declaration_takes_effect_without_waiting_for_a_rebuild(self):
        """The cache is keyed on the boundary files, and editing the profile
        changes none of them. Without reading the declaration back on every
        command, somebody writes a meridian, runs the command, and gets exactly
        the map they had before — with nothing anywhere saying why."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.country(folder, region={"NAME_1": ["Ardenne", "Beluar"],
                                                "GID_0": ["ATL", "ATL"],
                                                "COUNTRY": ["Atlantis"] * 2})
            deps = dataio.load(require_geo=True)
            self.assertIsNone(
                dataio.read_country(deps, root, "atlantis")["inset"]["meridian"])

            store = root / dataio.PROFILE
            saved = json.loads(store.read_text(encoding="utf-8"))
            saved["atlantis"]["declared"] = {insets.HAND_KEY: 0.5}
            store.write_text(json.dumps(saved, ensure_ascii=False),
                             encoding="utf-8")

            # no rebuild: the boundary files are untouched and the version matches
            again = dataio.read_country(deps, root, "atlantis")
            self.assertEqual(again["inset"]["meridian"], 0.5)
            self.assertEqual(
                json.loads(store.read_text(encoding="utf-8"))
                ["atlantis"]["inset"]["meridian"], 0.5)

    def test_a_profile_from_an_older_engine_is_rebuilt(self):
        """The cache is keyed on the boundary files, which is right for "the
        data changed" and useless for "the engine changed". A profile written
        before ``inset`` existed is valid by that key and answers None to a
        question it was never asked — Vietnam would lose its inset on every
        machine that already had a profile, and nothing would say why."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.country(folder, region={"NAME_1": ["Ardenne", "Beluar"],
                                                "GID_0": ["ATL", "ATL"],
                                                "COUNTRY": ["Atlantis"] * 2})
            deps = dataio.load(require_geo=True)
            dataio.read_country(deps, root, "atlantis")

            store = root / dataio.PROFILE
            saved = json.loads(store.read_text(encoding="utf-8"))
            stale = dict(saved["atlantis"])
            stale.pop("inset")
            stale.pop("__version")           # as the older engine wrote it
            store.write_text(json.dumps({"atlantis": stale}, ensure_ascii=False),
                             encoding="utf-8")

            again = dataio.read_country(deps, root, "atlantis")

        self.assertIn("inset", again)
        self.assertEqual(again["__version"], dataio.PROFILE_VERSION)

    def test_adding_a_tier_invalidates_it(self):
        """Kept by file name and size rather than by contents: hashing 135 MB
        on every command to notice a file nobody touched would cost more than
        the reading it protects."""
        gpd = geopandas_or_skip()
        import shapely.geometry as sg

        with tempfile.TemporaryDirectory() as folder:
            root = self.country(folder, region={"NAME_1": ["Ardenne", "Beluar"],
                                                "GID_0": ["ATL", "ATL"]})
            deps = dataio.load(require_geo=True)
            before = dataio.read_country(deps, root, "atlantis")
            self.assertEqual(len(before["tiers"]), 1)

            place = root / "atlantis" / "district"
            place.mkdir()
            gpd.GeoDataFrame(
                {"NAME_2": ["Alder", "Brann", "Calvet"], "GID_0": ["ATL"] * 3,
                 "NAME_1": ["Ardenne", "Ardenne", "Beluar"]},
                geometry=[sg.box(i, 0, i + 1, 1) for i in range(3)],
                crs="EPSG:4326").to_file(place / "district.shp")

            after = dataio.read_country(deps, root, "atlantis")
        self.assertEqual(len(after["tiers"]), 2)
        self.assertNotEqual(before["__from"], after["__from"])

    def test_a_country_outline_dropped_in_beside_the_tiers_takes_no_role(self):
        """A GADM archive unpacked wholesale is the case this guards."""
        with tempfile.TemporaryDirectory() as folder:
            root = self.country(
                folder,
                whole={"GID_0": ["ATL"], "COUNTRY": ["Atlantis"]},
                region={"NAME_1": ["Ardenne", "Beluar"], "GID_0": ["ATL", "ATL"]})
            order = dataio.tiers(root, "atlantis")
            roles = {t["folder"]: t["role"] for t in order}

            self.assertIsNone(roles["whole"])
            self.assertEqual(roles["region"], dataio.COARSE)
            self.assertEqual(
                dataio.find_boundaries(Path(folder), dataio.COARSE).parent.name,
                "region")


class TestNoticingLandFarFromTheRest(unittest.TestCase):
    """The warning that was owed since the United States map came out framed
    from the Aleutians to Maine with nothing said about it."""

    def test_a_compact_country_keeps_the_whole_frame(self):
        land = insets.land_masses(boxes([(0, 0, 10, 10), (10, 0, 20, 10)])
                                  .to_crs("EPSG:3857"))
        self.assertEqual(land["mass_count"], 1)
        self.assertAlmostEqual(land["main_mass_width_share"], 1.0, places=3)

    def test_one_far_piece_costs_the_main_body_most_of_the_width(self):
        frame = boxes([(0, 0, 10, 10), (90, 0, 92, 2)]).to_crs("EPSG:3857")
        land = insets.land_masses(frame)
        self.assertEqual(land["mass_count"], 2)
        self.assertLess(land["main_mass_width_share"], 0.2)

    def test_pieces_close_enough_to_touch_are_one_land_mass(self):
        """Provinces in the shipped Vietnamese data do not share exactly
        coincident borders, so a union alone leaves 2,666 pieces where there
        are 218 land masses. Two kilometres of tolerance is what closes the
        slivers without closing a strait."""
        self.assertEqual(len(vietnam("province")), 34)
        projected = vietnam("province").to_crs(
            dataio.thematic_crs(vietnam("province")))
        self.assertEqual(insets.land_masses(projected)["mass_count"], 218)

    def test_the_warning_names_what_the_reader_loses(self):
        land = {"main_mass_width_share": 0.43, "mass_count": 451}
        issues = guardrails.check_detached_territory(land, inset_drawn=False,
                                                     lang="en")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], guardrails.CRITICAL)
        self.assertIn("43%", issues[0]["problem"])
        self.assertIn("57%", issues[0]["why"])

    def test_an_inset_answers_the_question_so_nothing_is_said(self):
        """Vietnam's frame gives its mainland 47% of the width and its map is
        right, because the archipelagos are in a box. The warning is about the
        two together — land far away, and nothing done about it."""
        land = {"main_mass_width_share": 0.47, "mass_count": 218}
        self.assertEqual(
            guardrails.check_detached_territory(land, inset_drawn=True), [])

    def test_a_frame_the_main_body_nearly_fills_is_not_worth_a_warning(self):
        for width in (0.80, 0.93, 1.0):
            self.assertEqual(guardrails.check_detached_territory(
                {"main_mass_width_share": width}, inset_drawn=False), [],
                width)

    def test_a_country_measured_end_to_end(self):
        """Canada keeps 93% and says nothing; the United States keeps 43% and
        says so. Both read from the country profile the render already builds."""
        deps = dataio.load(require_geo=True)
        root = ROOT / "shapefiles"
        for country, quiet in (("canada", True), ("united-states", False)):
            if not (root / country).is_dir():
                self.skipTest(f"chưa có ranh giới {country}")
            land = dataio.read_country(deps, root, country).get("detached_land")
            issues = guardrails.check_detached_territory(land, inset_drawn=False)
            self.assertEqual(not issues, quiet, country)


class TestPrintingAMapInAnyLanguage(unittest.TestCase):
    """Two languages are built in; any *Latin-script* language can be printed.

    The limit is the packaged typeface, not this table: it holds no Greek,
    Cyrillic, Thai or Han, and ``fonts.undrawable`` stops the run rather than
    lettering a plate in empty boxes. The examples below are Romanian for that
    reason.
    """

    def tearDown(self):
        i18n.use(None)

    def test_a_supplied_string_replaces_the_built_in_one(self):
        self.assertEqual(i18n.t("en", "no_data"), "No data")
        i18n.use({"no_data": "Fără date"})
        self.assertEqual(i18n.t("en", "no_data"), "Fără date")
        self.assertEqual(i18n.t("vi", "no_data"), "Fără date")

    def test_a_supplied_string_keeps_its_placeholders(self):
        i18n.use({"insight_plain": "{with_data} din {total} unități au date."})
        self.assertEqual(i18n.t("en", "insight_plain", with_data=40, total=40),
                         "40 din 40 unități au date.")

    def test_strings_not_supplied_stay_in_the_language_asked_for(self):
        i18n.use({"no_data": "Fără date"})
        self.assertEqual(i18n.t("en", "north"), "N")
        self.assertEqual(i18n.t("vi", "north"), "B")

    def test_the_separators_are_named_rather_than_assumed(self):
        """Vietnamese swaps both; English swaps neither; a language that groups
        with a space can say so instead of being sorted into one of two camps."""
        self.assertEqual(semantics.localise_digits("1,234.5", "en"), "1,234.5")
        self.assertEqual(semantics.localise_digits("1,234.5", "vi"), "1.234,5")
        i18n.use({"thousands": " ", "decimal": ","})
        self.assertEqual(semantics.localise_digits("1,234.5", "en"), "1 234,5")

    def test_the_kicker_uses_the_word_the_country_uses(self):
        """``PROVINCE-LEVEL MAP`` above a map of United States counties tells
        the reader the wrong thing about what they are looking at."""
        self.assertEqual(i18n.kicker("en", "province", tier="province"),
                         "PROVINCE-LEVEL MAP")
        self.assertEqual(i18n.kicker("en", "commune", tier="district"),
                         "DISTRICT-LEVEL MAP")
        self.assertEqual(i18n.kicker("en", "province", tier="state"),
                         "STATE-LEVEL MAP")

    def test_vietnams_kicker_is_unchanged(self):
        for level, tier, expected in (("province", "province", "BẢN ĐỒ CẤP TỈNH/THÀNH PHỐ"),
                                      ("commune", "commune", "BẢN ĐỒ CẤP XÃ/PHƯỜNG")):
            self.assertEqual(i18n.kicker("vi", level, tier=tier), expected)
            self.assertEqual(i18n.kicker("vi", level), expected)

    def test_every_key_can_be_replaced_and_only_real_keys(self):
        keys = i18n.keys()
        for expected in ("no_data", "north", "source", "thousands", "decimal",
                         "kicker_tier"):
            self.assertIn(expected, keys)
        self.assertNotIn("no_such_key", keys)


class TestTheMapTextFlag(unittest.TestCase):
    """``--map-text KEY=VALUE``, and what it refuses."""

    @classmethod
    def setUpClass(cls):
        cls.cli = context.cli()

    def test_pairs_become_overrides(self):
        self.assertEqual(
            self.cli._map_text(["no_data=Fără date", "north=N"]),
            {"no_data": "Fără date", "north": "N"})

    def test_an_empty_value_is_a_value(self):
        """Somebody printing a map with no north letter at all is asking for
        an empty string, not making a mistake."""
        self.assertEqual(self.cli._map_text(["north="]), {"north": ""})

    def test_a_value_containing_an_equals_sign_survives(self):
        self.assertEqual(self.cli._map_text(["source=a=b"]), {"source": "a=b"})

    def test_a_key_that_does_not_exist_is_refused_by_name(self):
        """Accepted silently, a misspelled key would leave the map in the
        built-in language while the run reported that the text had been set —
        which is the worst of both, because nobody would look again."""
        with self.assertRaises(SystemExit) as raised:
            self.cli._map_text(["no_dataa=Fără date"])
        self.assertIn("no_dataa", str(raised.exception))

    def test_something_that_is_not_a_pair_is_refused(self):
        for bad in ("no_data", "=Fără date", ""):
            with self.assertRaises(SystemExit):
                self.cli._map_text([bad])

    def test_nothing_supplied_is_not_an_error(self):
        self.assertEqual(self.cli._map_text(None), {})
        self.assertEqual(self.cli._map_text([]), {})


class TestSuggestingALanguage(unittest.TestCase):
    """A suggestion, never a decision."""

    def test_the_two_sources_are_reported_separately(self):
        hint = i18n.suggest("vi")
        self.assertEqual(hint["country"], "vi")
        self.assertIn("vi", hint["suggestion"])
        self.assertIn("machine", hint)

    def test_agreement_is_judged_on_the_language_not_the_spelling(self):
        """Windows answers ``English_United States`` where Linux answers
        ``en_GB``, so the machine's own word is reported as it comes and
        compared on its first two letters."""
        self.assertTrue(i18n._same_language("english", "en"))
        self.assertTrue(i18n._same_language("vietnamese", "vi"))
        self.assertFalse(i18n._same_language("english", "vi"))
        self.assertFalse(i18n._same_language(None, "vi"))

    def test_only_a_country_whose_language_is_not_in_doubt_is_claimed(self):
        """"Canada speaks English" would be a guess, and a wrong one in
        Québec — the province this project has already had trouble spelling."""
        self.assertEqual(detect.country_language("Vietnam"), "vi")
        self.assertEqual(detect.country_language("VNM"), "vi")
        self.assertEqual(detect.country_language("Việt Nam"), "vi")
        self.assertIsNone(detect.country_language("Canada"))
        self.assertIsNone(detect.country_language("Fictavia"))
        self.assertIsNone(detect.country_language(None))

    def test_nothing_here_narrows_the_map_to_two_languages(self):
        """The suggestion is about what to offer. What can actually be printed
        is settled by the override table, which takes any string at all."""
        hint = i18n.suggest("vi")
        self.assertNotIn("chỉ_được_chọn", hint)
        self.assertLessEqual(len(hint["suggestion"]), 2)


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
        self.assertEqual(notes[0]["files"], "province/units.shp")
        self.assertEqual(notes[0]["how_to_fix"], "province/units.cpg")
        self.assertGreaterEqual(notes[0]["value_count"], 2)

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

    def test_the_gadm_schema_is_now_read_rather_than_refused(self):
        """This line used to record the opposite.

        ``shape_fields`` looked ``ten_tinh`` up in a list of five spellings and
        raised on anything else, so a GADM frame could not be drawn at all. It
        now asks ``detect`` what the file is, and the two fixed lists are gone
        from the module.
        """
        self.assertEqual(dataio.shape_fields(fixture("shp", "region"), "province"),
                         {"province": "NAME_1", "commune": None})
        self.assertEqual(dataio.shape_fields(fixture("shp", "district"), "commune"),
                         {"province": "NAME_1", "commune": "NAME_2"})
        self.assertFalse(hasattr(dataio, "PROVINCE_NAME_FIELDS"))
        self.assertFalse(hasattr(dataio, "COMMUNE_NAME_FIELDS"))

    def test_the_same_answer_comes_back_from_all_three_formats(self):
        """This line used to record an accident.

        ``name`` was in both fixed lists and KML gives every feature a
        ``Name``, so the KML fixture matched — on a column that was right
        there purely by luck, while the shapefile of the same data raised.
        Loud failure on one format and quiet luck on another was the shape of
        the risk. The reading is now taken from the schema, so all three
        formats answer the same.
        """
        for tier, role, expected in (
                ("region", "province", {"province": "NAME_1", "commune": None}),
                ("district", "commune", {"province": "NAME_1", "commune": "NAME_2"})):
            for kind in ("shp", "geojson", "kml"):
                self.assertEqual(dataio.shape_fields(fixture(kind, tier), role),
                                 expected, f"{kind}/{tier}")

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

    def test_the_locator_box_now_takes_the_shape_of_the_country_in_it(self):
        """This line used to record the opposite, and it understated the fault.

        ``LOCATOR_ASPECT = 2.2`` was described as Vietnam's bounding box. It was
        not Vietnam's either: in the projection the map is drawn in, and
        including the archipelagos the locator shows, Vietnam's frame is 1.10
        tall to wide. The box was twice as tall as its contents for the one
        country it was measured for, and four to seven times too tall for the
        others.
        """
        self.assertFalse(hasattr(furniture, "LOCATOR_ASPECT"))

        for label, frame, expected in (
                ("vietnam", vietnam("province"), 1.10),
                ("fictavia", fixture("shp", "region"), 0.33)):
            projected = frame.to_crs(dataio.thematic_crs(frame))
            self.assertAlmostEqual(furniture.locator_aspect(projected), expected,
                                   places=2, msg=label)

    def test_a_locator_box_is_never_thinner_than_a_line(self):
        """A country twenty to one would otherwise get a box whose caption is
        wider than the map above it."""
        low, high = furniture.LOCATOR_LIMITS
        self.assertEqual(furniture.locator_aspect(boxes([(0, 0, 200, 1)])), low)
        self.assertEqual(furniture.locator_aspect(boxes([(0, 0, 1, 200)])), high)

    def test_the_archipelago_meridian_is_no_longer_everyones(self):
        """This line used to record the opposite.

        It read: 111.0°E sits east of everything Fictavia has, so its two island
        groups are read as mainland and the frame stretches to hold them. That
        was true of every country in the world except one, because 111.0 was a
        module constant every frame was measured against.

        It is now a declaration, so the sentence has two halves. Vietnam's
        number is unchanged and still misses Fictavia — a country that declares
        nothing gets no inset rather than Vietnam's. And Fictavia can declare
        42.0 and have its own islands set aside, which is the half that did not
        exist before.
        """
        self.assertEqual(VN_LON, 111.0)
        whole = fixture("shp", "region")
        parts = len(whole.explode(index_parts=False, ignore_index=True))
        self.assertEqual(len(mainland(whole, VN_LON)), parts)
        self.assertIsNone(insets.declared("Fictavia"))

        own = insets.declaration("Fictavia", {insets.HAND_KEY: 42.0})["meridian"]
        self.assertEqual(own, 42.0)
        self.assertLess(len(mainland(whole, own)), parts)

    def test_the_coordinate_rule_now_covers_the_whole_world(self):
        """This line used to record the opposite.

        The rule read ``lon 100..115`` and ``lat 7..24`` — Vietnam's own
        extent. A Fictavian coordinate column was classified as a count, so a
        point map was never offered and nothing warned; the column simply
        stopped being a coordinate.
        """
        for column, values in (("longitude", [105.8, 106.7, 108.2]),
                               ("longitude", [12.5, 25.5, 38.9]),
                               ("longitude", [-96.8, -75.2, -122.4]),
                               ("latitude", [10.8, 16.5, 21.0]),
                               ("latitude", [44.5, 47.5, 50.5]),
                               ("latitude", [-33.9, -1.2, 71.4])):
            self.assertEqual(semantics.infer(column, values, True)["semantic"],
                             semantics.COORDINATE, (column, values))

    def test_the_administrative_words_now_come_from_the_boundary_file(self):
        """This line used to record the opposite.

        It read: ``matching._PREFIXES`` is Vietnamese and the plan keeps it that
        way, so "Alder District" and "Alder" do not normalise to the same
        string. The list is no longer Vietnamese and no longer a module
        constant — it is read off the columns the boundary file uses to name its
        own administrative types, which is not the same as guessing it from the
        place names. The plan ruled the guess out; it did not rule out reading
        what the file already says.

        Vietnam's own list stays hand-written, because Vietnam's shapefile
        carries no type column at all.
        """
        vietnam = matching.VIETNAM
        self.assertEqual(matching.normalize("Xã Alder", vietnam), "alder")

        # what Fictavia's own file declares: TYPE_2 in its language, ENGTYPE_2
        # in English
        districts = matching.affixes_from_type_words(["Districtul", "District"])
        regions = matching.affixes_from_type_words(["Regiune", "Region"])
        self.assertEqual(matching.normalize("Alder District", districts), "alder")
        self.assertEqual(matching.normalize("Districtul Alder", districts), "alder")
        self.assertEqual(matching.normalize("Region of Ardenne", regions), "ardenne")

        # and a country that declares nothing keeps its names whole, rather
        # than having Vietnamese grammar applied to them
        self.assertEqual(matching.normalize("Alder District", matching.NOTHING),
                         "alder district")

    def test_the_users_table_now_joins(self):
        """This line used to record the opposite.

        It read: forty rows, forty misses, best fuzzy score 60.9 — under the
        floor of 82, so nothing was quietly accepted and every row came back
        ``unmatched``. Failing loudly was the one thing that was already right.

        The same forty rows now match exactly, on the words the boundary file
        declares for itself.
        """
        rows = (FIXTURES / "fictavia_testing.csv").read_text(
            encoding="utf-8").splitlines()[1:]
        names = [line.split(",")[1] for line in rows]
        shapes = fixture("shp", "district")
        affixes = matching.affixes_from_type_words(shapes["TYPE_2"].tolist()
                                                   + shapes["ENGTYPE_2"].tolist())
        index = matching.build_index(
            [{"name": n, "shape_id": i} for i, n in enumerate(shapes["NAME_2"])],
            affixes)

        outcomes = []
        for name in names:
            feature, score, method = matching.match_one(name, index)
            outcomes.append((feature, matching.status_for(method, score)))

        self.assertEqual(len(names), 40)
        self.assertEqual({status for _, status in outcomes}, {"high-confidence"})
        self.assertEqual([f for f, _ in outcomes if f is None], [])


if __name__ == "__main__":
    unittest.main()


class TestAFontThatCannotDrawTheTextStopsTheRun(unittest.TestCase):
    """The rule said the run stops rather than substituting a typeface. It
    covered a missing file and a wrong family name, and not the case that
    actually reached a person: the fonts loaded, the run finished with exit
    code 0 and no warning, and every Chinese character on the plate — title,
    subtitle, legend headings, source note — came out as an empty box.
    """

    def test_the_two_built_in_languages_are_drawable(self):
        from emap import fonts, i18n

        for lang in i18n.LANGUAGES:
            with self.subTest(lang=lang):
                self.assertEqual(
                    fonts.undrawable(i18n.STRINGS[lang].values()), [])

    def test_latin_script_beyond_the_two_is_drawable(self):
        """The reason --map-text survives: these all letter correctly today."""
        from emap import fonts

        self.assertEqual(fonts.undrawable([
            "Français à ç é ê î ô û", "Español ñ á í ó ú ¿", "Straße ä ö ü",
            "Wielkopolskie ł ą ę ś ż", "Județul Bucureşti ă ș ț",
            "İstanbul ğ ş ı", "Provinsi Jawa Barat"]), [])

    def test_a_script_the_fonts_do_not_hold_is_named_character_by_character(self):
        """Naming the count alone would leave the reader guessing which words
        were at fault."""
        from emap import fonts

        self.assertEqual(fonts.undrawable(["阳性率"]), ["阳", "性", "率"])
        self.assertEqual(fonts.undrawable(["Москва"])[:2], ["М", "о"])
        self.assertTrue(fonts.undrawable(["ບໍ່ມີຂໍ້ມູນ"]))

    def test_a_character_is_named_once_however_often_it_appears(self):
        from emap import fonts

        self.assertEqual(fonts.undrawable(["率率率", "率"]), ["率"])

    def test_spaces_and_control_codes_are_not_counted_as_missing(self):
        from emap import fonts

        blank = "a" + chr(9) + "b" + chr(10) + "c" + chr(160) + "d"
        self.assertEqual(fonts.undrawable([blank]), [])

    def test_the_stop_says_which_scripts_are_covered(self):
        """A reader who has just been refused needs to know what would work."""
        from emap import messages as msg

        for lang in msg.LANGUAGES:
            text = msg.text("error.font-cannot-draw", lang, count=3,
                            characters="阳 性 率")
            with self.subTest(lang=lang):
                self.assertIn("阳", text)
                self.assertIn("3", text)


class TestWhatALanguageChangesInAFileName(unittest.TestCase):
    """Which words in a file name follow ``--language`` and which never do.

    The handbook once said the scope label belongs to ``--language`` because it
    goes into the file name. The English wave then made it English in every
    language, which is the opposite — and neither state had a test, so the
    folder listing was the only place either could be seen.

    Settled the second way, deliberately: ``national`` sits beside ``_report``,
    ``_data`` and ``run_manifest.json``, and a script looking for ``*_data.csv``
    has to find both editions of a map.
    """

    def _args(self, **over):
        import argparse

        fields = {"title": "Dân số theo tỉnh, 2026", "layout": "report",
                  "language": "vi"}
        fields.update(over)
        return argparse.Namespace(**fields)

    def test_only_the_suffix_differs_between_the_two_editions(self):
        import easy_map

        ctx = {"name": "national"}
        vi = easy_map.map_basename(self._args(language="vi"), "Dân số", ctx)
        en = easy_map.map_basename(self._args(language="en"), "Dân số", ctx)
        self.assertEqual(vi[0], en[0])                  # same family
        self.assertEqual(vi[1], vi[0] + "_vi")
        self.assertEqual(en[1], en[0] + "_en")

    def test_the_engines_own_words_stay_english_in_a_vietnamese_map(self):
        import easy_map

        family, base = easy_map.map_basename(
            self._args(), "Dân số", {"name": "national"})
        self.assertEqual(base, "dan-so-theo-tinh-2026-national_report_vi")

    def test_a_place_name_is_carried_over_as_the_boundary_file_wrote_it(self):
        """The one word here that is *not* the engine's: it comes from data."""
        import easy_map

        _, base = easy_map.map_basename(
            self._args(), "Dân số", {"name": "Hà Nội"})
        self.assertTrue(base.startswith("dan-so-theo-tinh-2026-ha-noi_"), base)

    def test_the_layout_is_in_the_name_so_one_render_cannot_bury_another(self):
        import easy_map

        report = easy_map.map_basename(self._args(layout="report"), "x",
                                       {"name": "national"})[1]
        banner = easy_map.map_basename(self._args(layout="banner"), "x",
                                       {"name": "national"})[1]
        self.assertNotEqual(report, banner)

    def test_an_untitled_map_falls_back_to_an_english_word(self):
        """The fallback used to be ``ban do``, which put Vietnamese into the
        name of a map whose every other word was English."""
        import easy_map

        _, base = easy_map.map_basename(
            self._args(title=None, language="en"), None, {"name": "national"})
        self.assertEqual(base, "map-national_report_en")


class TestTheCheckTheFontReadmePointsAt(unittest.TestCase):
    """``verify_vietnamese``: the one a maintainer is told to run.

    It has to answer the same question the engine asks before it draws, and it
    did not. It checked ``OpenSans-Regular`` alone against eight sample
    letters, while the render guard checks the **intersection** of every
    packaged face — a headline is set in the display font, so a glyph only the
    body font has is still a box. Two functions, one question, and the weaker
    one is the one the documentation points at.
    """

    def test_the_packaged_bundle_draws_every_vietnamese_letter(self):
        from emap import fonts

        self.assertEqual(fonts.verify_vietnamese(), [])

    def test_it_checks_the_whole_repertoire_not_a_handful_of_samples(self):
        from emap import fonts

        letters = fonts._vietnamese_repertoire()
        self.assertGreater(len(letters), 150)
        for probe in "ệỹẫợừửỗẳĐƯƠăâêôơư":
            with self.subTest(letter=probe):
                self.assertIn(probe, letters)

    def test_it_does_not_ask_for_letters_vietnamese_never_uses(self):
        """Sweeping in the whole of Latin Extended-A reports a retired Dutch
        letter as a gap in the bundle. A check that cries wolf teaches whoever
        runs it to expect a failure and ignore it."""
        from emap import fonts

        letters = fonts._vietnamese_repertoire()
        for stranger in "ŉøßþðæœłżšçñ":
            with self.subTest(letter=stranger):
                self.assertNotIn(stranger, letters)

    def test_it_gives_the_same_answer_as_the_guard_that_stops_a_render(self):
        """One implementation. Two that can drift is how the documentation
        ends up promising something the engine does not check.

        ``ŉ`` and ``‗`` are in the sample list on purpose: the body font has
        them and the display font does not, so they are exactly the characters
        that tell "check one font" apart from "check what every font shares".
        Without one of those, reverting to the old single-font version passed
        this test — measured, four ordinary samples all missed the five code
        points where the two answers differ.
        """
        from emap import fonts

        for sample in ("Cần Thơ", "阳性率", "Москва", "Français", "ŉ", "a‗b"):
            with self.subTest(sample=sample):
                self.assertEqual(fonts.verify_vietnamese(sample),
                                 fonts.undrawable([sample]))
