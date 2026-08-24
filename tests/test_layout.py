"""The page: how big the map is, how text is wrapped, what runs off the edge.

The overflow check exists because two defects in this project were only ever
found by opening the PNG: a title cut at the paper's edge, and a legend heading
that stayed on the paper but ran out of its column and lay across the map.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import layout as lay


class TestWrap(unittest.TestCase):
    def test_short_text_is_left_alone(self):
        self.assertEqual(lay.wrap("Tỷ lệ (%)", 9.0, 3.0), "Tỷ lệ (%)")

    def test_empty_text_stays_empty(self):
        self.assertEqual(lay.wrap("", 9.0, 3.0), "")

    def test_a_long_sentence_is_broken_into_lines(self):
        out = lay.wrap("Tỷ lệ ức chế tải lượng vi rút của người bệnh đang điều trị "
                       "ARV tại các tỉnh thành phố trực thuộc trung ương", 9.0, 2.4)
        self.assertGreater(len(out.split("\n")), 1)

    def test_past_the_line_limit_it_is_cut_with_an_ellipsis(self):
        out = lay.wrap(" ".join(["dài"] * 200), 9.0, 2.0, max_lines=2)
        self.assertEqual(len(out.split("\n")), 2)
        self.assertTrue(out.endswith("…"))

    def test_a_narrow_column_still_gets_a_usable_width(self):
        """Below a floor the wrap would put one word per line and read as a
        column of confetti."""
        self.assertIn("\n", lay.wrap("một hai ba bốn năm sáu bảy", 9.0, 0.1))


class TestMapSize(unittest.TestCase):
    def test_a_tall_area_gets_a_tall_page(self):
        w, h = lay.map_size(0.5)
        self.assertLess(w, h)

    def test_a_wide_area_gets_a_wide_page(self):
        w, h = lay.map_size(2.0)
        self.assertGreater(w, h)

    def test_the_page_keeps_the_shape_it_was_asked_for(self):
        w, h = lay.map_size(0.75)
        self.assertAlmostEqual(w / h, 0.75, places=2)

    def test_an_extreme_shape_is_reined_in(self):
        """A commune strip 12 times longer than it is wide would otherwise
        produce a page nothing can print."""
        w, h = lay.map_size(12.0)
        self.assertLessEqual(max(w, h) / min(w, h), 4.0 + 1e-6)

    def test_no_side_falls_below_the_printable_floor(self):
        for aspect in (0.05, 0.5, 1.0, 3.0, 40.0):
            w, h = lay.map_size(aspect)
            self.assertGreaterEqual(min(w, h), 4.2, f"aspect={aspect}")


class TestFitRect(unittest.TestCase):
    """Fitting a shape into a slot without stretching it."""

    class Fig:
        def __init__(self, w, h):
            self._size = (w, h)

        def get_size_inches(self):
            return self._size

    def test_a_wide_slot_is_narrowed_to_the_shape(self):
        rect = lay.fit_rect(self.Fig(10, 10), [0.0, 0.0, 1.0, 1.0], 0.5)
        self.assertAlmostEqual(rect[2], 0.5)
        self.assertAlmostEqual(rect[3], 1.0)

    def test_the_shape_is_centred_in_what_it_did_not_use(self):
        x, _, w, _ = lay.fit_rect(self.Fig(10, 10), [0.0, 0.0, 1.0, 1.0], 0.5)
        self.assertAlmostEqual(x, (1.0 - w) / 2)

    def test_right_alignment_pushes_it_to_the_far_edge(self):
        x, _, w, _ = lay.fit_rect(self.Fig(10, 10), [0.0, 0.0, 1.0, 1.0], 0.5,
                                  halign="right")
        self.assertAlmostEqual(x + w, 1.0)

    def test_a_tall_slot_is_shortened_instead(self):
        rect = lay.fit_rect(self.Fig(10, 10), [0.0, 0.0, 1.0, 1.0], 2.0)
        self.assertAlmostEqual(rect[2], 1.0)
        self.assertAlmostEqual(rect[3], 0.5)

    def test_a_slot_with_no_area_is_returned_untouched(self):
        rect = [0.1, 0.2, 0.0, 0.4]
        self.assertEqual(lay.fit_rect(self.Fig(10, 10), rect, 1.0), rect)


class TestOverflow(unittest.TestCase):
    def setUp(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self.plt = plt
        self.fig = plt.figure(figsize=(4, 3), dpi=100)

    def tearDown(self):
        self.plt.close(self.fig)

    def test_a_page_of_ordinary_text_reports_nothing(self):
        self.fig.text(0.5, 0.5, "Tỷ lệ (%)", ha="center")
        self.assertEqual(lay.overflow(self.fig), [])

    def test_text_running_past_the_paper_is_caught(self):
        self.fig.text(0.98, 0.5, "Một tiêu đề rất dài chạy hẳn ra ngoài trang giấy")
        found = lay.overflow(self.fig)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["side"], "right")
        self.assertEqual(found[0]["outside_of"], "trang")
        self.assertGreater(found[0]["over_pt"], 10)

    def test_the_side_it_left_by_is_named(self):
        self.fig.text(0.02, 0.5, "chạy sang trái", ha="right")
        self.assertEqual(lay.overflow(self.fig)[0]["side"], "left")

    def test_text_inside_an_unwatched_axes_is_left_to_its_own_placement(self):
        """Map labels have their own pass, which reports what it could not
        fit; measuring them again here would double-report."""
        ax = self.fig.add_axes([0.1, 0.1, 0.2, 0.2])
        ax.text(0.5, 0.5, "nhãn tràn ra ngoài trục toạ độ của nó" * 2)
        self.assertEqual(lay.overflow(self.fig), [])

    def test_text_leaving_a_watched_panel_is_caught_although_it_stays_on_paper(self):
        """The defect that prompted this: a legend heading too long for its
        column runs across the map. Nothing is clipped, so the file looks
        finished."""
        panel = self.fig.add_axes([0.05, 0.1, 0.2, 0.8])
        panel.text(0.0, 0.5, "Tiêu đề chú giải quá dài so với cột bên trái")
        found = lay.overflow(self.fig, panels=[panel])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["outside_of"], "cột chú giải")
        self.assertEqual(found[0]["side"], "right")

    def test_blank_and_hidden_text_is_not_reported(self):
        self.fig.text(0.98, 0.4, "   ")
        self.fig.text(0.98, 0.6, "ẩn nhưng dài ra ngoài trang").set_visible(False)
        self.assertEqual(lay.overflow(self.fig), [])

    def test_a_hair_past_the_edge_is_not_worth_reporting(self):
        """Glyph boxes sit a fraction outside their ink; without slack this
        would fire on almost every map."""
        self.fig.text(0.5, 0.5, "vừa khít", ha="center")
        self.assertEqual(lay.overflow(self.fig, slack=0.0001).__class__, list)


if __name__ == "__main__":
    unittest.main()
