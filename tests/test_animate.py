"""The parts of the video builder that decide what each frame shows.

Everything here is arithmetic on the schedule and the colours — no encoder, no
figure. That is deliberate: the frame plan and the blend are where a video can
be quietly wrong (a period skipped, a colour that never arrives at its class),
while a broken encoder fails loudly and is reported.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import animate


class TestFramePlan(unittest.TestCase):
    def plan(self, periods):
        return animate._frame_plan(periods)

    def test_a_single_period_is_held_and_never_faded(self):
        plan = self.plan(["Q1"])
        self.assertTrue(all(a == b == 0 and t == 0.0 for a, b, t in plan))

    def test_every_period_gets_held_before_the_next(self):
        plan = self.plan(["Q1", "Q2", "Q3"])
        held = {a for a, b, t in plan if a == b}
        self.assertEqual(held, {0, 1, 2})

    def test_the_series_starts_on_the_first_period_and_ends_on_the_last(self):
        plan = self.plan(["Q1", "Q2", "Q3"])
        self.assertEqual(plan[0][:2], (0, 0))
        self.assertEqual(plan[-1][:2], (2, 2))

    def test_a_fade_only_ever_moves_to_the_next_period(self):
        """Never a jump: a viewer watching a dissolve is being told these two
        periods are adjacent."""
        for a, b, _ in self.plan(["Q1", "Q2", "Q3", "Q4"]):
            self.assertIn(b - a, (0, 1))

    def test_the_blend_runs_between_the_two_frames_it_joins(self):
        fades = [t for a, b, t in self.plan(["Q1", "Q2"]) if a != b]
        self.assertTrue(fades)
        self.assertTrue(all(0.0 < t < 1.0 for t in fades))
        self.assertEqual(fades, sorted(fades))

    def test_the_hold_is_long_enough_to_read_a_map(self):
        hold = sum(1 for a, b, _ in self.plan(["Q1", "Q2"]) if a == b == 0)
        self.assertGreaterEqual(hold / animate.FPS, 1.5)

    def test_longer_series_take_proportionally_longer(self):
        two, four = len(self.plan(["a", "b"])), len(self.plan(["a", "b", "c", "d"]))
        self.assertGreater(four, two * 1.8)


class TestBlending(unittest.TestCase):
    def test_a_colour_reads_back_as_itself(self):
        self.assertEqual(animate._hex_to_rgb("#ffffff"), (1.0, 1.0, 1.0))
        self.assertEqual(animate._hex_to_rgb("#000000"), (0.0, 0.0, 0.0))

    def test_a_leading_hash_is_optional(self):
        self.assertEqual(animate._hex_to_rgb("005eaa"), animate._hex_to_rgb("#005eaa"))

    def test_the_start_and_end_of_a_blend_are_the_two_colours(self):
        a, b = "#000000", "#ffffff"
        self.assertEqual(animate._blend(a, b, 0.0), (0.0, 0.0, 0.0))
        self.assertEqual(animate._blend(a, b, 1.0), (1.0, 1.0, 1.0))

    def test_the_middle_is_the_middle(self):
        """A dissolve is a transition, not a claim about a measurement between
        two reporting periods — but it still has to land on the real colour at
        each end, or a class boundary appears to move while the data stands
        still."""
        for channel in animate._blend("#000000", "#ffffff", 0.5):
            self.assertAlmostEqual(channel, 0.5, places=6)


class TestWriterChoice(unittest.TestCase):
    """Which container the video lands in depends on the machine, so the test
    checks the pairing rather than the answer: a GIF named .mp4 is a file
    nothing will play."""

    def test_the_container_always_matches_the_writer(self):
        writer, container = animate.available_writer(None)
        self.assertIn(writer, ("ffmpeg", "pillow"))
        self.assertEqual(container, "mp4" if writer == "ffmpeg" else "gif")


if __name__ == "__main__":
    unittest.main()
