"""One country installed, and no ``--country`` on the command.

This is what a fresh install looks like, and what the documentation promises:
"With more than one country present, a command has to say which to draw. With
one, it does not."

It did not work. ``command_render`` read the flag into a local, let
``resolve_tier`` and ``load_shapes`` resolve it for themselves, and then handed
the *unresolved* ``None`` to ``dataio.read_country`` — whose signature, alone
among the three, required a name. The command died on ``root / None`` with

    TypeError: unsupported operand type(s) for /: 'WindowsPath' and 'NoneType'

which names nothing a user could act on.

962 tests did not see it, and the reason is worth keeping: the repository grew
a second and third country, so every render test was given ``--country
viet-nam`` to keep it deterministic. Naming the country is exactly what hides
this. So this file uses the invented single-country fixture and names nothing.
"""

from __future__ import annotations

import contextlib
import io
import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

from emap import dataio

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "countries"


class TestTheDocumentedDefaultPath(unittest.TestCase):
    """A project holding exactly one country, driven with no ``--country``."""

    def setUp(self):
        self.cli = context.cli()
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        shutil.copytree(FIXTURES / "shp" / "fictavia",
                        self.project / "shapefiles" / "fictavia")
        (self.project / "input").mkdir()
        shutil.copy(FIXTURES / "fictavia_testing.csv",
                    self.project / "input" / "figures.csv")
        # EASY_MAP_SHAPEFILES beats the project's own shapefiles folder, by
        # design: the installer sets it so a globally installed skill can draw
        # from any working directory. On a machine where the skill is installed
        # this test would therefore read Vietnam and report "no tier called
        # region" -- which is what it did. Point it at this project instead.
        self.previous_root = os.environ.get(dataio.SHAPEFILE_ENV)
        os.environ[dataio.SHAPEFILE_ENV] = str(self.project / "shapefiles")
        self.addCleanup(self.restore_environment)

    def restore_environment(self):
        if self.previous_root is None:
            os.environ.pop(dataio.SHAPEFILE_ENV, None)
        else:
            os.environ[dataio.SHAPEFILE_ENV] = self.previous_root

    def test_the_fixture_really_does_hold_one_country(self):
        """Otherwise the test proves nothing: with two, the command is refused
        before it can reach the code this is about."""
        self.assertEqual(dataio.countries(self.project / "shapefiles"),
                         ["fictavia"])

    def test_read_country_resolves_the_name_like_its_siblings(self):
        """The asymmetry itself, pinned. ``load_shapes`` and ``resolve_tier``
        both accept ``None`` and resolve it; this one did not, and every call
        site assumed it did."""
        profile = dataio.read_country(dataio.load(require_geo=True),
                                      self.project / "shapefiles")
        self.assertEqual(profile["country_name"], "Fictavia")
        self.assertEqual([t["folder"] for t in profile["tiers"]],
                         ["region", "district"])

    def render(self, *extra: str) -> dict:
        argv = ["render", "--project-root", str(self.project),
                "--run-folder", "run",
                "--excel", "input/figures.csv",
                "--admin-level", "region",
                "--province-column", "Region",
                "--map-scope", "national", "--map-type", "choropleth",
                "--value-column", "Tested",
                "--language", "en", "--layout", "report",
                "--title", "A title", "--no-html", *extra]
        args = self.parse(argv)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.command_render(args)
        return json.loads(out.getvalue())

    def parse(self, argv: list[str]):
        """Parse the way ``main`` does, not the way a test finds convenient.

        ``--project-root`` after a subcommand lands in ``project_root_sub`` so
        the subparser's default cannot clobber the top-level value, and ``main``
        folds it back. A test that skips the fold-back silently runs against the
        working directory instead: the first draft of this file did, and read
        that as a defect in the command. It was a defect in the test.
        """
        args = self.cli.build_parser().parse_args(argv)
        args.chosen_explicitly = self.cli._explicit(argv)
        if getattr(args, "project_root_sub", None):
            args.project_root = args.project_root_sub
        return args

    def test_the_plan_comes_back_without_naming_a_country(self):
        payload = self.render()
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertIsNotNone(payload["confirm_code"])

    def test_a_map_is_actually_drawn(self):
        """Through the gate and onto disk: the plan alone would not have caught
        the defect, which was two calls further down."""
        code = self.render()["confirm_code"]
        payload = self.render("--confirmed", code)
        self.assertNotEqual(payload.get("status"), "awaiting_confirmation", payload)
        drawn = sorted((self.project / "output" / "run").glob("*.png"))
        self.assertTrue(drawn, f"no image was written; payload={payload}")

    def test_profile_also_works_without_naming_a_country(self):
        """``command_profile`` had the same shape and the same defect."""
        args = self.parse(["profile", "--project-root", str(self.project),
                           "--excel", "input/figures.csv"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.command_profile(args)
        self.assertIn("column", json.loads(out.getvalue()))


if __name__ == "__main__":
    unittest.main()
