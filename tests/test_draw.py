"""One whole plate, drawn, and the report it hands back about itself.

``render.draw`` is where every other module meets: the framing, the classes,
the colours, the furniture, the labels, the inset, the overflow check. Nothing
tested it directly. The pieces were pinned one at a time, and a map can still
come out wrong when the pieces are assembled — the colour list cycled across
2,703 paths was every piece behaving correctly and the map unreadable.

What is pinned here is the **report**, because the report is the only account
anyone gets without opening the PNG. If it says a unit was painted and the unit
was not, or says nothing overflowed when a heading lies across the map, then
every check built on it is checking a fiction.

Fictavia is used rather than Vietnam: it is the fixture that exists to be drawn,
it is small, and a test that only passes for one country is not testing the
engine.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "countries"

try:
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:                                   # pragma: no cover
    gpd = None


def fictavia():
    frame = gpd.read_file(FIXTURES / "shp" / "fictavia" / "region"
                          / "Fictavia_region.shp")
    frame = frame.to_crs("EPSG:3857")
    frame = frame.reset_index(drop=True)
    frame["__shape_id"] = range(len(frame))
    frame["ten"] = frame["NAME_1"].astype(str)
    return frame


@unittest.skipIf(gpd is None, "geopandas/matplotlib not installed")
class DrawCase(unittest.TestCase):
    FONTS = {"display": "DejaVu Serif", "text": "DejaVu Sans"}

    def setUp(self):
        self.frame = fictavia()

    def spec(self, **over):
        base = {
            "language": "en", "layout": "report", "map_type": "choropleth",
            "value_column": "__value", "value_info": {"semantic": "count",
                                                      "integer": True},
            "bins": None, "name_field": "ten", "labels": "off",
            "title": "Fictavia", "kicker": "REGION-LEVEL MAP",
            "insight": "", "source": "", "method": "", "dpi": 80,
            "side_panel": True, "legend_title": "Cases",
            "inset_meridian": None, "locator": False,
        }
        base.update(over)
        return base

    def numbers(self, values=None):
        frame = self.frame.copy()
        frame["__value"] = values if values is not None else list(
            range(10, 10 + len(frame)))
        return frame

    def draw(self, frame, spec):
        from emap import classify, render

        if (spec.get("bins") is None and spec.get("value_column")
                and spec.get("map_type") not in ("categorized", "boundary")):
            wanted = [v for v in frame["__value"] if v is not None and v == v]
            spec = dict(spec, bins=classify.compute_bins(wanted, "quantile", 4))
        out = render.draw(None, frame=frame, spec=spec, fonts=self.FONTS)
        self.addCleanup(plt.close, out["plate"].fig)
        return out


class TestWhatTheReportSaysWasDrawn(DrawCase):
    def test_a_plain_map_reports_no_overflow(self):
        """The baseline every other overflow finding is read against. If this
        is noisy, nobody will believe the report when it is right."""
        out = self.draw(self.numbers(), self.spec())
        self.assertEqual(out["overflow"], [])

    def test_the_legend_reports_the_number_of_classes_it_drew(self):
        from emap import classify

        frame = self.numbers()
        bins = classify.compute_bins(list(frame["__value"]), "quantile", 4)
        out = self.draw(frame, self.spec(bins=bins))
        self.assertEqual(out["legend_classes"], bins["classes"])

    def test_every_unit_is_accounted_for_by_a_colour(self):
        """The fills are what the interactive page enlarges a unit with. A unit
        missing from here is a unit the page cannot show."""
        out = self.draw(self.numbers(), self.spec())
        self.assertEqual(set(out["fills"]),
                         {str(i) for i in self.frame["__shape_id"]})

    def test_a_unit_with_no_number_keeps_the_no_data_colour(self):
        """Grey is a statement — "not measured" — and it has to be the same
        grey the legend shows."""
        from emap import render

        values = [10] * len(self.frame)
        values[0] = float("nan")
        out = self.draw(self.numbers(values), self.spec())
        self.assertEqual(out["fills"]["0"], render.NO_DATA_FILL)
        self.assertNotEqual(out["fills"]["1"], render.NO_DATA_FILL)

    def test_a_map_with_no_numbers_at_all_still_draws(self):
        """Boundary maps, and any request whose join matched nothing. Drawing
        the outlines and saying so beats refusing."""
        out = self.draw(self.frame.assign(__value=None),
                        self.spec(map_type="boundary", value_column=None,
                                  bins=None))
        self.assertIsNotNone(out["plate"])
        self.assertEqual(out["legend_classes"], 0)

    def test_the_locator_reports_whether_it_was_actually_drawn(self):
        """It is dropped when there is no room, and the report is the only
        place that difference shows."""
        out = self.draw(self.numbers(), self.spec())
        self.assertFalse(out["locator"])


class TestTheReportCatchesWhatOnlyAPngWouldShow(DrawCase):
    def test_a_heading_too_long_for_its_column_is_reported(self):
        """The fault that ran a sentence across the map. It stays on the paper,
        so nothing raises and the file looks finished."""
        out = self.draw(self.numbers(), self.spec(
            legend_title="Confirmed cases per one hundred thousand residents, "
                         "by region, financial year 2026"))
        self.assertTrue(out["overflow"], "a heading this long must be reported")
        self.assertEqual(out["overflow"][0]["outside_of"], "legend column")

    def test_the_report_names_the_side_and_the_distance(self):
        """"Something overflowed" sends the reader to look at twelve plates."""
        out = self.draw(self.numbers(), self.spec(
            legend_title="Confirmed cases per one hundred thousand residents, "
                         "by region, financial year 2026"))
        entry = out["overflow"][0]
        self.assertIn(entry["side"], {"left", "right", "top", "bottom"})
        self.assertGreater(entry["over_pt"], 0)


class TestWritingThePlateOut(DrawCase):
    def test_a_png_is_written_and_the_figure_is_closed(self):
        """``save`` closes the figure. A run that draws twelve plates and
        closes none holds twelve full-size canvases in memory at once."""
        import tempfile

        from emap import render

        out = self.draw(self.numbers(), self.spec())
        number = out["plate"].fig.number
        self.assertIn(number, plt.get_fignums())
        with tempfile.TemporaryDirectory() as folder:
            written = render.save(out["plate"], Path(folder), "map", dpi=60)
            self.assertEqual([p.suffix for p in written], [".png"])
            self.assertTrue(written[0].exists())
            self.assertGreater(written[0].stat().st_size, 1000)
        # asked by number, not by object: ``plt.figure(n)`` would *create* the
        # figure it was looking for and the check would always pass
        self.assertNotIn(number, plt.get_fignums())

    def test_both_formats_land_beside_each_other(self):
        import tempfile

        from emap import render

        out = self.draw(self.numbers(), self.spec())
        with tempfile.TemporaryDirectory() as folder:
            written = render.save(out["plate"], Path(folder), "map",
                                  formats="both", dpi=60)
            self.assertEqual(sorted(p.suffix for p in written), [".png", ".svg"])
            for path in written:
                self.assertTrue(path.exists(), path)

    def test_the_folder_is_made_rather_than_demanded(self):
        """The run folder exists, but a per-request subfolder may not."""
        import tempfile

        from emap import render

        out = self.draw(self.numbers(), self.spec())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "not" / "yet"
            written = render.save(out["plate"], target, "map", dpi=60)
            self.assertTrue(written[0].exists())


class TestThePayloadTheInteractivePageIsBuiltFrom(DrawCase):
    """``webpage.capture_still`` reads the live axes, so it can only be
    exercised on a plate that was really drawn."""

    def payload(self, **over):
        from emap import webpage

        spec = self.spec(**over)
        frame = self.numbers()
        out = self.draw(frame, spec)
        return webpage.capture_still(out["plate"], frame, dict(spec, bins=None),
                                     family="fictavia_report",
                                     label="Fictavia", fills=out["fills"])

    def test_one_shape_per_unit_with_its_name(self):
        payload = self.payload()
        self.assertEqual(len(payload["shapes"]), len(self.frame))
        self.assertEqual({s["name"] for s in payload["shapes"]},
                         set(self.frame["ten"]))

    def test_the_picture_travels_inside_the_payload(self):
        """The page is one file with nothing beside it, so the image cannot be
        a path."""
        payload = self.payload()
        self.assertEqual(len(payload["images"]), 1)
        self.assertGreater(len(payload["images"][0]), 1000)
        self.assertNotIn("/", payload["images"][0][:40])

    def test_every_shape_has_a_reading_for_the_tooltip(self):
        payload = self.payload()
        self.assertEqual(set(payload["values"]),
                         {s["id"] for s in payload["shapes"]})

    def test_the_readings_are_formatted_the_way_the_map_formats_them(self):
        """A tooltip disagreeing with the plate under it is worse than no
        tooltip: the reader cannot tell which one to believe."""
        payload = self.payload(language="en")
        self.assertTrue(all(v[0] and "." not in v[0]
                            for v in payload["values"].values()),
                        payload["values"])

    def test_the_payload_carries_the_language_it_was_drawn_in(self):
        for lang in ("vi", "en"):
            with self.subTest(lang=lang):
                self.assertEqual(self.payload(language=lang)["lang"], lang)


if __name__ == "__main__":
    unittest.main()
