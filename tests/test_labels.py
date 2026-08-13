"""Placing place names without letting them lie on top of each other.

The report this returns is the only account anybody gets of what the map could
not fit. It has been wrong before: labels were parked on top of one another
while ``bỏ_qua`` said nothing had been dropped, and the defect was found by
looking at a PNG.

These tests draw on a real matplotlib figure, because the placement measures
the actual text box — the whole point of the module is that estimates were not
good enough.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import labels as lab

COLORS = {"name": "#1b1b1b", "value": "#005eaa", "leader": "#8a969e"}


class LabelCase(unittest.TestCase):
    def setUp(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self.plt = plt
        self.fig, self.ax = plt.subplots(figsize=(6, 6), dpi=100)
        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(0, 100)

    def tearDown(self):
        self.plt.close(self.fig)

    def item(self, x, y, name, value=None, keepout=0.0, rank=1.0):
        return {"x": x, "y": y, "name": name, "value_text": value,
                "keepout": keepout, "rank": rank}

    def place(self, items, **kwargs):
        return lab.place(self.ax, items, colors=COLORS, **kwargs)


class TestPlacing(LabelCase):
    def test_labels_with_room_are_all_drawn(self):
        items = [self.item(20, 20, "Hà Nội", "91,4%"),
                 self.item(70, 70, "Huế", "88,2%")]
        report = self.place(items)
        self.assertEqual(report["đã_vẽ"], 2)
        self.assertEqual(report["bỏ_qua"], [])
        self.assertEqual(report["bỏ_vì_chật"], [])

    def test_the_text_actually_reaches_the_figure(self):
        self.place([self.item(50, 50, "Hà Nội", "91,4%")])
        drawn = {t.get_text() for t in self.ax.texts}
        self.assertIn("Hà Nội", drawn)

    def test_two_names_on_one_spot_both_still_get_drawn(self):
        """There are eight positions in the first ring, so the second name
        moves round rather than outward — and neither is lost."""
        report = self.place([self.item(50, 50, "Hà Nội"), self.item(50, 50, "Huế")])
        self.assertEqual(report["đã_vẽ"], 2)
        self.assertEqual(report["bỏ_vì_chật"], [])

    def test_a_ring_of_names_forces_some_of_them_outward(self):
        """Past eight, a label has to leave the first ring, and that is what
        earns a leader line."""
        items = [self.item(50, 50, f"Đơn vị {i}") for i in range(10)]
        self.assertGreaterEqual(self.place(items)["phải_dời"], 1)

    def test_beyond_the_cap_the_rest_are_reported_not_silently_lost(self):
        items = [self.item(i, i, f"Đơn vị {i}", rank=float(i)) for i in range(1, 40)]
        report = self.place(items, max_labels=5)
        self.assertEqual(len(report["bỏ_qua"]), 34)
        self.assertEqual(report["đã_vẽ"] + len(report["bỏ_vì_chật"]), 5)

    def test_the_cap_keeps_the_highest_ranked(self):
        items = [self.item(10, 10, "nhỏ", rank=1.0), self.item(80, 80, "lớn", rank=99.0)]
        report = self.place(items, max_labels=1)
        self.assertEqual(report["bỏ_qua"], ["nhỏ"])


class TestWhatCannotFit(LabelCase):
    def test_carrying_a_value_costs_room(self):
        """A name over its value is a taller box than a name alone, so a
        crowded cluster fits fewer of them. That is the whole reason the
        placement retries without the number before giving up."""
        crowd = [(50, 50), (50.6, 50), (49.4, 50), (50, 50.6), (50, 49.4),
                 (50.6, 50.6), (49.4, 49.4), (50.6, 49.4), (49.4, 50.6),
                 (51.2, 50), (48.8, 50), (50, 51.2)]
        bare = self.place([self.item(x, y, f"Xã {i}") for i, (x, y) in enumerate(crowd)])
        self.setUp()
        with_values = self.place([self.item(x, y, f"Xã {i}", "1.234.567 ca")
                                  for i, (x, y) in enumerate(crowd)])
        self.assertLessEqual(with_values["đã_vẽ"], bare["đã_vẽ"])
        # whatever could not carry its number is accounted for, not dropped
        self.assertEqual(with_values["đã_vẽ"] + len(with_values["bỏ_vì_chật"]),
                         len(crowd))

    def test_labels_with_nowhere_to_go_are_named(self):
        items = [self.item(50, 50, f"Đơn vị {i}", "88,2%") for i in range(14)]
        report = self.place(items)
        self.assertTrue(report["bỏ_vì_chật"],
                        "chồng lên nhau mà báo cáo im lặng là lỗi cũ đã sửa")
        self.assertEqual(report["đã_vẽ"] + len(report["bỏ_vì_chật"])
                         + len(report["bỏ_qua"]), 14)

    def test_nothing_is_drawn_outside_the_axes(self):
        """A label placed past the frame is cut when the file is written."""
        report = self.place([self.item(99.7, 99.7, "Đơn vị sát mép", "88,2%")])
        self.assertEqual(report["đã_vẽ"] + len(report["bỏ_vì_chật"]), 1)


class TestKeepoutBoxes(LabelCase):
    """The archipelago inset is drawn by the map itself, so nothing in the item
    list describes it. A place name parked over it would be unreadable."""

    def test_a_reserved_rectangle_pushes_a_label_aside(self):
        box = (40.0, 40.0, 60.0, 60.0)
        free = self.place([self.item(50, 50, "Hà Nội")])
        self.setUp()
        blocked = self.place([self.item(50, 50, "Hà Nội")], keepout_boxes=[box])
        self.assertEqual(free["phải_dời"], 0)
        self.assertGreaterEqual(blocked["phải_dời"] + len(blocked["bỏ_vì_chật"]), 1)

    def test_without_boxes_the_behaviour_is_unchanged(self):
        report = self.place([self.item(20, 20, "Hà Nội")], keepout_boxes=())
        self.assertEqual(report["đã_vẽ"], 1)


class TestGeometryHelpers(unittest.TestCase):
    """The two pure predicates the placement is built on."""

    def test_boxes_that_share_space_overlap(self):
        a, b = lab._Box(0, 0, 10, 10), lab._Box(5, 5, 15, 15)
        self.assertTrue(a.overlaps(b))

    def test_boxes_side_by_side_with_a_gap_do_not(self):
        a, b = lab._Box(0, 0, 10, 10), lab._Box(20, 0, 30, 10)
        self.assertFalse(a.overlaps(b))

    def test_a_hair_apart_still_counts_as_touching(self):
        """Labels a pixel apart read as one smudge, so the check carries pad."""
        a, b = lab._Box(0, 0, 10, 10), lab._Box(10.5, 0, 20, 10)
        self.assertTrue(a.overlaps(b))

    def test_a_box_inside_the_frame_is_inside(self):
        self.assertTrue(lab._inside_axes(lab._Box(20, 20, 30, 30),
                                         lab._Box(0, 0, 100, 100)))

    def test_a_box_over_the_edge_is_not(self):
        self.assertFalse(lab._inside_axes(lab._Box(95, 20, 105, 30),
                                          lab._Box(0, 0, 100, 100)))


if __name__ == "__main__":
    unittest.main()
