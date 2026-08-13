"""Converting pre-2025 province names onto the 34 current ones.

Without this, every year before the merger loses most of the country: names like
"Sóc Trăng" or "Hậu Giang" simply are not on a 34-province map, and the rows
carrying them vanish from the join without anything looking wrong.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import crosswalk, matching


class FakeFrame:
    """Just enough of a GeoDataFrame for the crosswalk: columns and iterrows."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    @property
    def columns(self):
        return list(self._rows[0]) if self._rows else []

    def iterrows(self):
        return enumerate(self._rows)


PROVINCES = FakeFrame([
    {"ten_tinh": "Cần Thơ", "sap_nhap": "Cần Thơ, Sóc Trăng, Hậu Giang", "__shape_id": 1},
    {"ten_tinh": "An Giang", "sap_nhap": "An Giang, Kiên Giang", "__shape_id": 2},
    {"ten_tinh": "Cao Bằng", "sap_nhap": "không sáp nhập", "__shape_id": 3},
    {"ten_tinh": "Huế", "sap_nhap": "Thừa Thiên Huế", "__shape_id": 4},
])


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.table = crosswalk.build(PROVINCES)

    def test_former_provinces_point_at_the_current_one(self):
        self.assertEqual(self.table["Sóc Trăng"], "Cần Thơ")
        self.assertEqual(self.table["Hậu Giang"], "Cần Thơ")
        self.assertEqual(self.table["Kiên Giang"], "An Giang")

    def test_a_surviving_name_maps_to_itself(self):
        self.assertEqual(self.table["Cần Thơ"], "Cần Thơ")
        self.assertEqual(self.table["Cao Bằng"], "Cao Bằng")

    def test_a_renamed_province_is_covered(self):
        self.assertEqual(self.table["Thừa Thiên Huế"], "Huế")

    def test_missing_column_yields_an_empty_table(self):
        bare = FakeFrame([{"ten_tinh": "Cần Thơ", "__shape_id": 1}])
        self.assertEqual(crosswalk.build(bare), {})


class TestMatchingThroughAliases(unittest.TestCase):
    def setUp(self):
        self.index = matching.build_index(crosswalk.alias_features(PROVINCES))

    def test_a_former_name_resolves_to_the_current_shape(self):
        feature, score, method = matching.match_one("Sóc Trăng", self.index)
        self.assertEqual(method, matching.MERGED)
        self.assertEqual(feature["shape_id"], 1)
        self.assertEqual(score, 100.0)

    def test_conversion_is_a_fact_not_a_guess(self):
        self.assertEqual(matching.status_for(matching.MERGED, 100.0), matching.HIGH)

    def test_a_current_name_is_still_an_exact_match(self):
        _, _, method = matching.match_one("Cao Bằng", self.index)
        self.assertEqual(method, matching.EXACT)

    def test_the_review_shows_the_current_province_not_the_former_one(self):
        review = matching.review_province(
            [{"province": "Hậu Giang"}, {"province": "Cần Thơ"}], self.index)
        by_input = {r["dataset_province"]: r for r in review}
        self.assertEqual(by_input["Hậu Giang"]["matched_province"], "Cần Thơ")
        self.assertEqual(by_input["Hậu Giang"]["match_method"], matching.MERGED)
        self.assertEqual(by_input["Cần Thơ"]["match_method"], matching.EXACT)

    def test_two_former_provinces_land_on_one_shape(self):
        review = matching.review_province(
            [{"province": "Sóc Trăng"}, {"province": "Hậu Giang"}], self.index)
        self.assertEqual({r["shape_id"] for r in review}, {1})

    def test_summary_counts_conversions(self):
        review = matching.review_province(
            [{"province": "Sóc Trăng"}, {"province": "Cao Bằng"}], self.index)
        self.assertEqual(matching.summarize(review)["merged"], 1)

    def test_report_lists_what_was_converted(self):
        review = matching.review_province([{"province": "Kiên Giang"}], self.index)
        report = crosswalk.summarize(review)
        self.assertEqual(report["số_tên_cũ_đã_quy_đổi"], 1)
        self.assertEqual(report["ví_dụ"], ["Kiên Giang → An Giang"])
class TestAgainstTheRealShapefile(unittest.TestCase):
    """The fake frame above is convenient and it is not evidence.

    Its Huế row says ``sap_nhap: "Thừa Thiên Huế"``. The shapefile says
    ``"không sáp nhập"`` — the province was renamed, not merged, so its former
    name is recorded nowhere and the join for it silently failed. The test was
    green the whole time, because it was asserting against data it had invented.

    So this class reads the file the renderer reads. It is skipped where
    geopandas or the shapefile is missing; the rule still holds, the check just
    cannot run.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import geopandas
        except ImportError:                      # pragma: no cover - env-dependent
            raise unittest.SkipTest("geopandas is needed to read the shapefile")
        folder = Path(__file__).resolve().parents[1] / "shapefiles" / "provinces"
        shp = sorted(folder.glob("*.shp"))
        if not shp:                              # pragma: no cover - env-dependent
            raise unittest.SkipTest("the province shapefile is not present")
        cls.gdf = geopandas.read_file(shp[0])
        cls.gdf["__shape_id"] = range(len(cls.gdf))
        cls.table = crosswalk.build(cls.gdf)
        cls.current = {str(n).strip() for n in cls.gdf["ten_tinh"]}

    def test_the_renamed_province_resolves(self):
        """The one this class was written for."""
        self.assertEqual(self.table.get("Thừa Thiên Huế"), "Huế")

    def test_every_pre_2025_province_is_reachable(self):
        """63 provinces before the reorganisation, 34 after. A table that cannot
        name all 63 loses rows out of any series that starts before 2025."""
        self.assertEqual(len(self.table), 64)     # 63 former names + Huế itself
        self.assertEqual(len(self.current), 34)

    def test_every_former_name_lands_on_a_province_that_exists(self):
        for former, current in self.table.items():
            with self.subTest(former=former):
                self.assertIn(current, self.current)

    def test_each_rename_is_still_needed_and_still_lands_somewhere(self):
        """A later shapefile may start recording a rename in `sap_nhap`, or may
        drop the province the rename points at. Either way this entry becomes
        wrong rather than merely redundant, and it should be noticed here."""
        for former, current in crosswalk.RENAMED.items():
            with self.subTest(former=former):
                self.assertIn(current, self.current)
                self.assertNotIn(former, self.current,
                                 f"{former} is a current name; the rename is stale")

    def test_the_former_name_reaches_the_same_shape_as_the_new_one(self):
        aliases = crosswalk.alias_features(self.gdf)
        by_name = {a["name"]: a["shape_id"] for a in aliases}
        for former, current in crosswalk.RENAMED.items():
            with self.subTest(former=former):
                self.assertIn(former, by_name)
                self.assertEqual(by_name[former], by_name[current])

    def test_no_alias_is_listed_twice(self):
        """A rename that a future shapefile also records as a merger would
        otherwise put the same name in the index twice."""
        names = [a["name"] for a in crosswalk.alias_features(self.gdf)]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
