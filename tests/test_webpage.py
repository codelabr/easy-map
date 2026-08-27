"""The self-contained interactive page.

Three promises are worth a test. The page must stay assemblable from the cache
alone, so a second render extends it instead of replacing what the first one
produced. It must reference nothing outside itself, because it is meant to be
emailed on its own. And every label its JavaScript asks for must exist in every
language — the keys here are read out of the page source rather than typed
again, so a renamed key fails the test instead of quietly falling back.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import semantics as sem, webpage

PERCENT = sem.infer("Bao phủ 2026 (%)", [51.3, 86.0], True)


def spec(lang: str = "vi", title: str = "Bao phủ 2026") -> dict:
    return {"language": lang, "title": title, "legend_title": "Bao phủ (%)",
            "symbol_legend_title": "Số ca"}


def make(kind: str = webpage.STILL, lang: str = "vi", family: str = "bao-phu",
         label: str = "Bao phủ — toàn quốc", periods=()) -> dict:
    shapes = [{"id": "1", "name": "Hà Nội", "d": "M0,0L1,0L1,1Z"}]
    return webpage.entry(kind=kind, spec=spec(lang), family=family, label=label,
                         images=["iVBORw0KGgo="] * max(len(periods), 1),
                         shapes=shapes, periods=periods,
                         values={"1": ["51.3%"] * max(len(periods), 1)})


class TestCell(unittest.TestCase):
    def test_missing_value_uses_the_spoken_word_not_a_dash(self):
        self.assertEqual(webpage.cell(None, PERCENT, "vi", "chưa có số liệu"),
                         "chưa có số liệu")
        self.assertEqual(webpage.cell(float("nan"), PERCENT, "en", "no data"), "no data")

    def test_present_value_is_formatted_by_its_semantic(self):
        self.assertEqual(webpage.cell(51.3, PERCENT, "vi", "–"), "51,3%")

    def test_the_tooltip_uses_the_same_separators_as_the_map(self):
        """The hover box is read beside the plate, so it cannot disagree."""
        self.assertEqual(webpage.cell(51.3, PERCENT, "en", "–"), "51.3%")

    def test_a_category_keeps_its_own_label(self):
        self.assertEqual(webpage.cell("Ưu tiên cao", {}, "vi", "–"), "Ưu tiên cao")


class TestBuild(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_capture_means_no_page(self):
        self.assertIsNone(webpage.build(self.run_dir, webpage.STILL))

    def test_a_second_render_extends_the_page_instead_of_replacing_it(self):
        """One request may render twice — two languages, two layouts."""
        webpage.stash(self.run_dir, "bao-phu_vi", make(lang="vi"))
        first = webpage.build(self.run_dir, webpage.STILL)
        webpage.stash(self.run_dir, "bao-phu_en", make(lang="en", family="coverage"))
        second = webpage.build(self.run_dir, webpage.STILL)
        self.assertEqual(first["maps_in_page"], 1)
        self.assertEqual(second["maps_in_page"], 2)
        self.assertEqual(second["language"], ["en", "vi"])
        self.assertEqual(first["files"], second["files"])

    def test_rendering_the_same_map_again_does_not_duplicate_it(self):
        webpage.stash(self.run_dir, "bao-phu_vi", make())
        webpage.stash(self.run_dir, "bao-phu_vi", make())
        self.assertEqual(webpage.build(self.run_dir, webpage.STILL)["maps_in_page"], 1)

    def test_still_maps_and_a_time_series_land_in_separate_files(self):
        webpage.stash(self.run_dir, "bao-phu_vi", make())
        webpage.stash(self.run_dir, "ca-moi_vi",
                      make(kind=webpage.SERIES, family="ca-moi", periods=("2024", "2025")))
        still = webpage.build(self.run_dir, webpage.STILL)
        series = webpage.build(self.run_dir, webpage.SERIES)
        self.assertNotEqual(still["files"], series["files"])
        self.assertEqual(still["maps_in_page"], 1)
        self.assertEqual(series["maps_in_page"], 1)

    def test_page_title_prefers_the_vietnamese_edition(self):
        webpage.stash(self.run_dir, "coverage_en",
                      webpage.entry(kind=webpage.STILL, spec=spec("en", "Coverage 2026"),
                                    family="coverage", label="Coverage",
                                    images=["x"], shapes=[]))
        webpage.stash(self.run_dir, "z-bao-phu_vi", make())
        page = Path(webpage.build(self.run_dir, webpage.STILL)["files"])
        self.assertIn("<title>Bao phủ 2026</title>", page.read_text(encoding="utf-8"))

    def test_a_damaged_capture_does_not_take_the_page_down(self):
        webpage.stash(self.run_dir, "bao-phu_vi", make())
        (self.run_dir / webpage.CACHE_DIR / webpage.STILL / "broken.json").write_text(
            "{not json", encoding="utf-8")
        self.assertEqual(webpage.build(self.run_dir, webpage.STILL)["maps_in_page"], 1)


class TestSelfContained(unittest.TestCase):
    """The whole point of the file is that it survives being emailed alone."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        webpage.stash(self.run_dir, "bao-phu_vi", make())
        self.page = Path(webpage.build(self.run_dir, webpage.STILL)["files"]
                         ).read_text(encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_nothing_is_fetched_from_the_network(self):
        for pattern in ("http://", "https://", "<link", "<script src", "@import", "url("):
            self.assertNotIn(pattern, self.page, f"page reaches outside itself: {pattern}")

    def test_no_sibling_file_is_referenced(self):
        for src in re.findall(r'src="([^"]*)"', self.page):
            self.assertTrue(src == "" or src.startswith("data:"),
                            f"page depends on an external file: {src}")

    def test_the_data_travels_inside_the_page(self):
        self.assertIn('"Hà Nội"', self.page)
        self.assertIn("51.3%", self.page)


class TestLabelContract(unittest.TestCase):
    """Keys are read out of the page source, so a rename fails here.

    Writing the expected keys by hand is how a test ends up agreeing with
    itself: it has happened in this project before, and a branch that never ran
    stayed green for 93 tests.
    """

    def test_the_hover_target_is_the_shape_not_its_outline(self):
        """SVG's default stroke-width is one *user unit*, and the overlay's
        viewBox is 100 wide against an image some 700px wide — an invisible
        7px outline that collected the mouse. Near a border the stroke of
        whichever feature was drawn later sat over its neighbour's interior and
        the tooltip named the wrong province: 45 of 131 interior points
        resolved to another feature. Both declarations are load-bearing."""
        rule = re.search(r"\.canvas path\s*\{([^}]*)\}", webpage.PAGE)
        self.assertIsNotNone(rule, "quy tắc .canvas path đã đổi tên hoặc biến mất")
        body = rule.group(1).replace(" ", "")
        self.assertIn("pointer-events:fill", body)
        self.assertIn("stroke-width:0", body)

    def wanted(self) -> set[str]:
        found = set(re.findall(r"\bw\.([a-z_]+)", webpage.PAGE))
        found |= set(re.findall(r"\bwords\(\)\.([a-z_]+)", webpage.PAGE))
        return found

    def test_the_page_asks_for_at_least_the_labels_we_know_about(self):
        self.assertTrue({"map", "search", "period", "play", "pause"} <= self.wanted(),
                        "the scan found nothing; the regex has drifted from the page")

    def test_every_label_the_page_asks_for_exists_in_every_language(self):
        for code, words in webpage.TEXT.items():
            missing = sorted(self.wanted() - set(words))
            self.assertEqual(missing, [], f"'{code}' is missing {missing}")

    def test_the_languages_carry_the_same_keys(self):
        self.assertEqual(set(webpage.TEXT["vi"]), set(webpage.TEXT["en"]))

    def test_the_detail_panel_is_wired_to_the_page(self):
        """The panel is assembled in JavaScript from ids in the markup. A renamed
        id leaves both halves valid on their own and the panel silently dead."""
        for element in ("spot", "veil", "panel", "portrait", "lift", "liftG",
                        "lifted", "cardName", "cardRows", "spotClose"):
            self.assertIn(f'id="{element}"', webpage.PAGE, element)
            self.assertIn(f"$('{element}')", webpage.PAGE, element)

    def test_the_panel_floats_over_the_window_not_over_the_map(self):
        """A national map is taller than the window, so a panel positioned
        against the map itself can open below the fold and look like nothing
        happened."""
        rule = re.search(r"\.spot\s*\{([^}]*)\}", webpage.PAGE)
        self.assertIsNotNone(rule, "quy tắc .spot đã đổi tên hoặc biến mất")
        self.assertIn("position:fixed", rule.group(1).replace(" ", ""))

    def test_the_enlarged_shape_keeps_its_stroke_at_any_magnification(self):
        """A commune enlarged thirty times would otherwise carry a thirty-times
        outline, and the shape would read as a blot."""
        rule = re.search(r"\.portrait path\s*\{([^}]*)\}", webpage.PAGE)
        self.assertIsNotNone(rule, "quy tắc .portrait path đã đổi tên hoặc biến mất")
        self.assertIn("vector-effect:non-scaling-stroke", rule.group(1).replace(" ", ""))

    def test_the_panel_starts_at_the_unit_and_flies_from_there(self):
        """Without the two nested frames the browser coalesces the start and end
        transforms and the panel simply appears — the flight is the whole point
        of opening it from the shape rather than from the middle of the screen."""
        self.assertIn("startTransform", webpage.PAGE)
        self.assertIn("requestAnimationFrame(() => requestAnimationFrame(",
                      webpage.PAGE)

    def body(self, name: str) -> str:
        """One top-level JavaScript function out of the page."""
        found = re.search(r"\nfunction " + name + r"\(.*?\n\}", webpage.PAGE, re.S)
        self.assertIsNotNone(found, f"không tìm thấy hàm {name}() trong trang")
        return found.group(0)

    def test_the_flight_measures_the_landmass_not_the_whole_outline(self):
        """A unit's outline covers every fragment it owns. Khánh Hòa's reaches
        Trường Sa, so its rectangle is 378px wide and centred at sea while the
        land the reader clicked is 38px and elsewhere — the panel flew from a
        place nobody pointed at, 193px off. ``box`` is the main landmass."""
        source = self.body("unitOnScreen")
        self.assertIn("s.box", source)
        self.assertIn("canvas.getBoundingClientRect()", source)
        start = self.body("startTransform")
        self.assertIn("unitOnScreen", start)
        self.assertNotIn("data-id", start,
                         "chuyến bay lại đo đường viền đầy đủ thay vì phần đất chính")

    def test_the_resting_rectangle_is_worked_out_not_measured(self):
        """Measuring meant clearing the transform and reading the panel back,
        which mid-flight returns wherever the animation has reached — and the
        clearing starts a transition of its own. Closing then ended hundreds of
        pixels from the unit."""
        source = self.body("panelAtRest")
        self.assertIn("offsetWidth", source)
        self.assertNotIn("style.transform", source,
                         "phép đo lại động vào transform, sẽ nhiễu với hoạt ảnh")

    def test_closing_works_the_flight_out_again_rather_than_reusing_it(self):
        """The page can be scrolled or the window resized while the panel is up,
        and either moves the unit underneath it."""
        source = self.body("closeSpot")
        self.assertIn("startTransform(flying)", source)

    def test_the_payload_carries_both_languages_whatever_was_rendered(self):
        """The reader may switch language; the chrome must not fall back silently."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            webpage.stash(run_dir, "bao-phu_vi", make())
            page = Path(webpage.build(run_dir, webpage.STILL)["files"]).read_text(encoding="utf-8")
        data = json.loads(re.search(r"const D = (\{.*?\});\n", page, re.S).group(1))
        self.assertEqual(set(data["text"]), {"vi", "en"})


class TestThereIsSomethingToZoomInTo(unittest.TestCase):
    """The page lets the reader magnify the map. Detail has to exist for that.

    Measured before this was fixed: the page caps its own width at 1180 CSS
    pixels and the plate was embedded at 150 dpi, so 1519 image pixels covered
    1180 — detail ran out at 1.29x, and on a 2x display the image was already
    being enlarged at rest. The zoom went to a fixed 8x, so most of its range
    magnified an image with nothing left to give.
    """

    def page_width(self) -> int:
        """The widest the map is ever drawn, read from the page's own CSS."""
        import re

        from emap import webpage

        found = re.search(r"\.wrap\s*{[^}]*max-width:\s*(\d+)px", webpage.PAGE)
        self.assertIsNotNone(found, "the page no longer caps its width")
        return int(found.group(1))

    def test_the_embedded_plate_is_wider_than_the_page_can_show(self):
        """The invariant, stated so it survives a change to either number: a
        plate no wider than its own frame has nothing to reveal."""
        from emap import layout, webpage

        # a report plate is about ten inches across; the exact figure comes from
        # the layout rather than being repeated here
        inches = layout.COLUMN_IN + 0.30 + layout.MARGIN_IN * 2 + 7.0
        pixels = inches * webpage.HTML_DPI
        self.assertGreater(pixels, self.page_width() * 1.5,
                           f"{webpage.HTML_DPI} dpi leaves nothing to zoom into")

    def test_the_page_is_still_small_enough_to_send(self):
        """The whole point of one self-contained file is that it can be
        attached to an email. Detail is worth paying for; a page nobody can
        send is not."""
        from emap import webpage

        self.assertLessEqual(webpage.HTML_DPI, 300)

    def test_the_zoom_ceiling_is_read_from_the_image_not_fixed(self):
        """A fixed ceiling cannot know how much detail this plate has, on this
        window, on this display."""
        from emap import webpage

        self.assertIn("naturalWidth", webpage.PAGE)
        self.assertIn("devicePixelRatio", webpage.PAGE)
        self.assertNotIn("Math.min(8, Math.max(1, z * factor))", webpage.PAGE)

    def test_the_ceiling_never_falls_below_a_useful_amount(self):
        """A very wide window on a small plate would otherwise compute a
        ceiling of 1 and leave the reader unable to zoom at all."""
        import re

        from emap import webpage

        found = re.search(r"return Math\.max\((\d+), Math\.min\((\d+),",
                          webpage.PAGE)
        self.assertIsNotNone(found, "the ceiling is no longer clamped")
        floor, cap = int(found.group(1)), int(found.group(2))
        self.assertGreaterEqual(floor, 2)
        self.assertGreater(cap, floor)


if __name__ == "__main__":
    unittest.main()


class TestUnitFacts(unittest.TestCase):
    """The three numbers the card adds come from the shapefile, not the dataset.

    They are the same on every map of the same places, which is exactly why a
    reader reaches for them when a mapped value looks surprising.
    """

    class Row(dict):
        """Enough of a GeoDataFrame row for :func:`webpage.facts`."""

    def frame(self, rows: list[dict], columns: list[str]):
        import types

        table = types.SimpleNamespace(columns=columns)
        table.iterrows = lambda: ((i, r) for i, r in enumerate(rows))
        return table

    def test_each_language_gets_its_own_separators(self):
        rows = [{"__shape_id": 1, "dtich_km2": 3359.8, "dan_so": 8807523,
                 "matdo_km2": 2621.5}]
        cols = ["__shape_id", "dtich_km2", "dan_so", "matdo_km2"]
        vi = webpage.facts(self.frame(rows, cols), "vi")["1"]
        en = webpage.facts(self.frame(rows, cols), "en")["1"]
        self.assertEqual(vi["area"], "3.359,8")
        self.assertEqual(en["area"], "3,359.8")
        self.assertEqual(vi["population"], "8.807.523")
        self.assertEqual(en["population"], "8,807,523")

    def test_a_column_the_shapefile_lacks_is_left_out_not_zeroed(self):
        """"0 people" is a claim; saying nothing is the truth. This is what a
        shapefile from another source will hit first."""
        rows = [{"__shape_id": 7, "dtich_km2": 12.5}]
        found = webpage.facts(self.frame(rows, ["__shape_id", "dtich_km2"]), "vi")
        self.assertEqual(set(found["7"]), {"area"})

    def test_a_shapefile_with_none_of_them_reports_nothing(self):
        rows = [{"__shape_id": 7}]
        self.assertEqual(webpage.facts(self.frame(rows, ["__shape_id"]), "vi"), {})

    def test_a_missing_value_in_a_present_column_is_skipped(self):
        rows = [{"__shape_id": 7, "dtich_km2": float("nan"), "dan_so": 100}]
        found = webpage.facts(self.frame(rows, ["__shape_id", "dtich_km2", "dan_so"]), "vi")
        self.assertEqual(set(found["7"]), {"population"})


class TestTellingTwoLayoutsApart(unittest.TestCase):
    """The same map in two layouts arrives under one title.

    It used to arrive under one *file name* too, so the second render silently
    replaced the first while run_manifest went on listing both.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def stash_both_layouts(self):
        for layout in ("report", "banner"):
            payload = make(family=f"bao-phu_{layout}")
            payload["layout"] = layout
            webpage.stash(self.run_dir, f"bao-phu_{layout}_vi", payload)

    def labels(self) -> list[str]:
        page = Path(webpage.build(self.run_dir, webpage.STILL)["files"]).read_text(
            encoding="utf-8")
        data = json.loads(re.search(r"const D = (\{.*?\});\n", page, re.S).group(1))
        return [e["label"] for e in data["entries"]]

    def test_both_layouts_reach_the_page(self):
        self.stash_both_layouts()
        self.assertEqual(webpage.build(self.run_dir, webpage.STILL)["maps_in_page"], 2)

    def test_the_picker_does_not_offer_the_same_line_twice(self):
        self.stash_both_layouts()
        labels = self.labels()
        self.assertEqual(len(set(labels)), 2, labels)
        self.assertTrue(any("report" in x for x in labels), labels)
        self.assertTrue(any("banner" in x for x in labels), labels)

    def test_a_single_layout_keeps_its_label_clean(self):
        payload = make()
        payload["layout"] = "report"
        webpage.stash(self.run_dir, "bao-phu_report_vi", payload)
        self.assertEqual(self.labels(), ["Bao phủ — toàn quốc"])


class TestTheDetailPanelStatesAMissingValueOnce(unittest.TestCase):
    """A gap in the data has one look, whichever row it lands in.

    The panel showed a commune with neither a coverage rate nor a case count.
    "no data" came out italic and grey on one row and bold and black on the
    other, because the colour row tested for the gap and the circle row did not
    — so the same absence read as a quiet note above and a headline below.

    The function under test is JavaScript, and asserting on its source would
    only restate it. It is lifted out of the page and run instead, which is the
    only way to see what a reader would see.
    """

    HARNESS = """
      let at = 0;
      const words = () => ({nodata: 'no data', points: 'points', area: 'area',
                            population: 'population', density: 'density',
                            unit_area: 'km2', unit_density: 'p/km2'});
      %s
      console.log(JSON.stringify(facts(%s, '1')));
    """

    @staticmethod
    def source() -> str:
        """``function facts`` as it is shipped, sliced out by brace depth."""
        start = webpage.PAGE.index("function facts(e, id) {")
        depth, i = 0, start
        while True:
            if webpage.PAGE[i] == "{":
                depth += 1
            elif webpage.PAGE[i] == "}":
                depth -= 1
                if depth == 0:
                    return webpage.PAGE[start:i + 1]
            i += 1

    def run_facts(self, entry: dict) -> str:
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:                       # the page still ships; this check does not
            self.skipTest("node is not installed")
        script = self.HARNESS % (self.source(), json.dumps(entry))
        done = subprocess.run([node, "-e", script], capture_output=True,
                              text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def entry(self, value: str, symbol: str) -> dict:
        return {"legend": {"value": "Coverage rate", "symbol": "Cases"},
                "values": {"1": [value]}, "symbols": {"1": [symbol]},
                "points": {}, "facts": {"1": {"population": "54,084"}}}

    def test_both_rows_mark_a_gap_the_same_way(self):
        html = self.run_facts(self.entry("no data", "no data"))
        self.assertEqual(html.count('<b class="none">no data'), 2, html)
        self.assertNotIn('<b class="">no data', html)

    def test_a_value_that_is_there_is_still_stated_plainly(self):
        html = self.run_facts(self.entry("92.0%", "120"))
        self.assertIn('<b class="">92.0%', html)
        self.assertIn('<b class="">120', html)
        self.assertNotIn("none", html)

    def test_one_row_missing_and_one_present_do_not_borrow_each_other(self):
        html = self.run_facts(self.entry("no data", "120"))
        self.assertIn('<b class="none">no data', html)
        self.assertIn('<b class="">120', html)

    def test_the_facts_from_the_shapefile_keep_their_units(self):
        html = self.run_facts(
            {"legend": {"value": "Coverage rate", "symbol": ""},
             "values": {"1": ["no data"]}, "symbols": {}, "points": {},
             "facts": {"1": {"area": "49.3"}}})
        self.assertIn('<b class="">49.3<u>km2</u>', html)
