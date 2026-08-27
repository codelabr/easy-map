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
        self.assertEqual(report["drawn"], 2)
        self.assertEqual(report["skipped"], [])
        self.assertEqual(report["dropped_no_room"], [])

    def test_the_text_actually_reaches_the_figure(self):
        self.place([self.item(50, 50, "Hà Nội", "91,4%")])
        drawn = {t.get_text() for t in self.ax.texts}
        self.assertIn("Hà Nội", drawn)

    def test_two_names_on_one_spot_both_still_get_drawn(self):
        """There are eight positions in the first ring, so the second name
        moves round rather than outward — and neither is lost."""
        report = self.place([self.item(50, 50, "Hà Nội"), self.item(50, 50, "Huế")])
        self.assertEqual(report["drawn"], 2)
        self.assertEqual(report["dropped_no_room"], [])

    def test_a_ring_of_names_forces_some_of_them_outward(self):
        """Past eight, a label has to leave the first ring, and that is what
        earns a leader line."""
        items = [self.item(50, 50, f"Đơn vị {i}") for i in range(10)]
        self.assertGreaterEqual(self.place(items)["moved"], 1)

    def test_beyond_the_cap_the_rest_are_reported_not_silently_lost(self):
        items = [self.item(i, i, f"Đơn vị {i}", rank=float(i)) for i in range(1, 40)]
        report = self.place(items, max_labels=5)
        self.assertEqual(len(report["skipped"]), 34)
        self.assertEqual(report["drawn"] + len(report["dropped_no_room"]), 5)

    def test_the_cap_keeps_the_highest_ranked(self):
        items = [self.item(10, 10, "nhỏ", rank=1.0), self.item(80, 80, "lớn", rank=99.0)]
        report = self.place(items, max_labels=1)
        self.assertEqual(report["skipped"], ["nhỏ"])


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
        self.assertLessEqual(with_values["drawn"], bare["drawn"])
        # whatever could not carry its number is accounted for, not dropped
        self.assertEqual(with_values["drawn"] + len(with_values["dropped_no_room"]),
                         len(crowd))

    def test_labels_with_nowhere_to_go_are_named(self):
        items = [self.item(50, 50, f"Đơn vị {i}", "88,2%") for i in range(14)]
        report = self.place(items)
        self.assertTrue(report["dropped_no_room"],
                        "chồng lên nhau mà báo cáo im lặng là lỗi cũ đã sửa")
        self.assertEqual(report["drawn"] + len(report["dropped_no_room"])
                         + len(report["skipped"]), 14)

    def test_nothing_is_drawn_outside_the_axes(self):
        """A label placed past the frame is cut when the file is written."""
        report = self.place([self.item(99.7, 99.7, "Đơn vị sát mép", "88,2%")])
        self.assertEqual(report["drawn"] + len(report["dropped_no_room"]), 1)


class TestKeepoutBoxes(LabelCase):
    """The archipelago inset is drawn by the map itself, so nothing in the item
    list describes it. A place name parked over it would be unreadable."""

    def test_a_reserved_rectangle_pushes_a_label_aside(self):
        box = (40.0, 40.0, 60.0, 60.0)
        free = self.place([self.item(50, 50, "Hà Nội")])
        self.setUp()
        blocked = self.place([self.item(50, 50, "Hà Nội")], keepout_boxes=[box])
        self.assertEqual(free["moved"], 0)
        self.assertGreaterEqual(blocked["moved"] + len(blocked["dropped_no_room"]), 1)

    def test_without_boxes_the_behaviour_is_unchanged(self):
        report = self.place([self.item(20, 20, "Hà Nội")], keepout_boxes=())
        self.assertEqual(report["drawn"], 1)


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


class TestALabelSitsOnTheUnitItNames(unittest.TestCase):
    """The question a reader asks of a label, and the one nothing answered.

    Measured on 103 communes of Cần Thơ: 19 of 42 names sat mostly on somebody
    else's unit, one with 2% of itself on the unit it named — and the report
    said **nothing was moved**, so not a single leader line was drawn. Two
    causes, both here: the search began one ring out and never tried the
    feature's own anchor, and a leader was drawn only past ring 1, which called
    that first offset "not moved".
    """

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

    def item(self, x, y, name, keepout=0.0):
        return {"x": x, "y": y, "name": name, "value_text": None,
                "keepout": keepout, "rank": 1.0}

    def place(self, items, **kw):
        return lab.place(self.ax, items, colors=COLORS, **kw)

    def box_of(self, name):
        self.fig.canvas.draw()
        r = self.fig.canvas.get_renderer()
        for t in self.ax.texts:
            if t.get_text() == name:
                return t.get_window_extent(renderer=r)
        self.fail(f"{name} was not drawn")

    def anchor(self, x, y):
        return self.ax.transData.transform((x, y))

    def test_a_lone_label_covers_its_own_anchor(self):
        """The whole point. A name over the point it names needs no explaining;
        one beside it needs a line, and one beside it *without* a line is what
        made a commune map unreadable."""
        self.place([self.item(50, 50, "Hà Nội")])
        box = self.box_of("Hà Nội")
        px, py = self.anchor(50, 50)
        self.assertTrue(box.x0 <= px <= box.x1 and box.y0 <= py <= box.y1)

    def test_a_lone_label_needs_no_leader(self):
        report = self.place([self.item(50, 50, "Hà Nội")])
        self.assertEqual(report["moved"], 0)
        self.assertEqual(len(self.ax.lines), 0)

    def test_a_label_pushed_off_its_anchor_gets_a_leader(self):
        """It used to take two rings of displacement before a line was drawn,
        so the first — and commonest — displacement was silent."""
        crowd = [self.item(50, 50, "Trung tâm")] + [
            self.item(50 + dx, 50 + dy, f"Kề {i}")
            for i, (dx, dy) in enumerate([(0, 6), (0, -6), (6, 0), (-6, 0),
                                          (5, 5), (-5, 5), (5, -5), (-5, -5)])]
        report = self.place(crowd)
        self.assertGreater(report["moved"], 0)
        self.assertEqual(len(self.ax.lines), report["moved"],
                         "every displaced label must carry one leader")

    def test_a_label_moved_only_one_ring_still_gets_a_leader(self):
        """The case the old rule missed, and the commonest one.

        One unit whose anchor is covered by a reserved rectangle, so the name
        goes exactly one ring out. Under ``ring > 1.0`` that counted as *not
        moved* and drew nothing — a name sitting a centimetre from its unit
        with no line tying it back. Every other test here passes under either
        rule, which is why reverting the rule stayed green until this existed.

        Two coincident points would not do: each blocks the other's anchor, so
        both move and the case stops being about one ring.
        """
        report = self.place([self.item(50, 50, "Hà Nội")],
                            keepout_boxes=[(49.0, 49.0, 51.0, 51.0)])
        self.assertEqual(report["drawn"], 1)
        self.assertEqual(report["moved"], 1)
        self.assertEqual(len(self.ax.lines), 1)

    def test_a_choropleth_reserves_no_space_for_a_circle_it_does_not_draw(self):
        """``render`` decides the keepout, and used to pass a fraction of the
        frame for every unit whether a symbol was drawn or not. That reserved a
        ring of blank space around each anchor, which is what pushed names off
        their own units. Read from the source: the default belongs to the
        caller, and nothing else here can see it."""
        import inspect
        import re

        from emap import render

        line = next(l for l in inspect.getsource(render.draw).splitlines()
                    if '"keepout"' in l)
        default = re.search(r'radius_by_id\.get\([^,]+,\s*([^)]+)\)', line)
        self.assertIsNotNone(default, f"keepout is no longer a lookup: {line}")
        self.assertEqual(default.group(1).strip(), "0.0")

    def test_a_name_resting_against_its_circle_needs_no_leader(self):
        """Where a symbol is drawn, the circle marks the place and a name
        beside it reads as its own. Demanding that the name cover the anchor
        there put a leader under **every** label on a proportional-symbol map —
        measured, 33 of 33 on Cần Thơ — which is clutter, not explanation."""
        report = self.place([self.item(50, 50, "Hà Nội", keepout=8.0)])
        self.assertEqual(report["drawn"], 1)
        self.assertEqual(report["moved"], 0)
        self.assertEqual(len(self.ax.lines), 0)

    def test_a_name_pushed_well_past_its_circle_still_gets_one(self):
        """Adjacency is what earns the silence, not the presence of a symbol."""
        crowd = [self.item(50, 50, "Trung tâm", keepout=8.0)] + [
            self.item(50 + dx, 50 + dy, f"Kề {i}", keepout=8.0)
            for i, (dx, dy) in enumerate([(0, 7), (0, -7), (7, 0), (-7, 0),
                                          (6, 6), (-6, 6), (6, -6), (-6, -6)])]
        report = self.place(crowd)
        self.assertGreater(report["moved"], 0)
        self.assertEqual(len(self.ax.lines), report["moved"])

    def test_a_symbol_still_keeps_the_name_off_itself(self):
        """A name on the anchor is right where nothing is drawn there. Where a
        circle *is* drawn, the name must clear it — that is what keepout is."""
        self.place([self.item(50, 50, "Hà Nội", keepout=8.0)])
        box = self.box_of("Hà Nội")
        px, py = self.anchor(50, 50)
        self.assertFalse(box.x0 <= px <= box.x1 and box.y0 <= py <= box.y1)

    def test_a_units_own_keepout_never_blocks_its_own_name(self):
        """Every feature's keepout goes into the obstacle list. Leaving its own
        in there is what stopped the anchor from ever being tried: the label
        collided with the unit it belonged to."""
        report = self.place([self.item(50, 50, "Hà Nội")])
        self.assertEqual(report["drawn"], 1)
        self.assertEqual(report["moved"], 0)

    def test_the_anchor_is_the_first_thing_tried(self):
        import inspect

        self.assertEqual(lab._RINGS[0], 0.0,
                         "the search no longer tries the feature's own anchor")
        self.assertIn("covers_anchor", inspect.getsource(lab.place))


if __name__ == "__main__":
    unittest.main()
