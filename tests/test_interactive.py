"""Capturing a time series as an interactive page.

One frame per period, not the video's hundreds — so the page usually ends up
smaller than the MP4. This runs the real capture on a two-square map, because
the parts worth checking are the ones that only appear once a figure has been
drawn: that every period produced a frame, that the hover table has a value for
each of them, and that the file gathers renders instead of replacing them.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import dataio, fonts, interactive, semantics as sem


def two_squares():
    import geopandas as gpd
    import shapely.geometry as sg

    return gpd.GeoDataFrame(
        {"__shape_id": [1, 2], "ten_tinh": ["Hà Nội", "Huế"]},
        geometry=[sg.box(0, 0, 1, 1), sg.box(2, 0, 3, 1)], crs="EPSG:4326")


class TestCapture(unittest.TestCase):
    PERIODS = ["Quý I", "Quý II"]

    def setUp(self):
        import matplotlib
        matplotlib.use("Agg")

        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        self.deps = dataio.load(require_geo=True, require_plot=True)
        self.fonts = fonts.install(self.deps.matplotlib)
        self.frame = two_squares()
        self.info = sem.infer("Tỷ lệ bao phủ (%)", [51.3, 86.0], True)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, name="ban-do_vi", symbols=None, language="vi"):
        spec = {"layout": "report", "map_type": "choropleth", "language": language,
                "value_column": "__value", "symbol_column": "__symbol" if symbols else None,
                "value_info": self.info, "symbol_info": {}, "name_field": "ten_tinh",
                "title": "Bao phủ theo quý", "kicker": "", "insight": "",
                "source": "", "method": "", "dpi": 90,
                "bins": {"edges": [50.0, 60.0, 70.0, 90.0]}}
        return interactive.build(
            self.deps, frame=self.frame, periods=self.PERIODS,
            values_by_period={"Quý I": {1: 55.0, 2: 65.0},
                              "Quý II": {1: 75.0, 2: 85.0}},
            symbols_by_period=symbols, spec=spec, fonts=self.fonts,
            out_dir=self.out, name=name)

    def payload(self):
        page = self.out / "ban_do_theo_thoi_gian.html"
        text = page.read_text(encoding="utf-8")
        start = text.index("PAYLOAD") if "PAYLOAD" in text else 0
        return text, start

    def test_every_period_becomes_one_frame(self):
        report = self.build()
        self.assertEqual(report["số_kỳ"], 2)

    def test_every_unit_can_be_hovered(self):
        self.assertEqual(self.build()["số_đơn_vị_rê_chuột_được"], 2)

    def test_the_page_is_written_where_the_request_lives(self):
        self.build()
        self.assertTrue((self.out / "ban_do_theo_thoi_gian.html").exists())

    def test_it_writes_the_series_page_not_the_still_one(self):
        self.build()
        self.assertFalse((self.out / "ban_do_tuong_tac.html").exists())

    def test_a_second_language_is_gathered_into_the_same_page(self):
        """The suffix is stripped so both editions share one family, and the
        page offers a language switch instead of the second render replacing
        the first."""
        self.build(name="ban-do_vi", language="vi")
        self.build(name="ban-do_en", language="en")
        text, _ = self.payload()
        self.assertIn('"vi"', text)
        self.assertIn('"en"', text)

    def test_re_rendering_the_same_map_does_not_double_it(self):
        first = self.build(name="ban-do_vi")
        again = self.build(name="ban-do_vi")
        self.assertEqual(first, again)


if __name__ == "__main__":
    unittest.main()
