"""A change map names two columns. Naming one that is not there.

``--baseline-column`` and ``--comparison-column`` take **column names**: the map
is one column minus the other. A table with a period column invites writing a
year instead, because a year is what the two figures differ by — and that is
exactly what the map sweep's first draft did, seven times.

The engine's answer was ``KeyError: '2026'``, straight out of pandas. Two
guards immediately above it in the same function exist precisely to stop that
kind of answer reaching a person: a missing workbook and a missing place column
both used to arrive as tracebacks and were given sentences. This was the third,
and it had been missed because nothing exercised it.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

from emap import dataio

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "countries"


class TestNamingAColumnThatIsNotThere(unittest.TestCase):
    def setUp(self):
        self.cli = context.cli()
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        shutil.copytree(FIXTURES / "shp" / "fictavia",
                        self.project / "shapefiles" / "fictavia")
        (self.project / "input").mkdir()
        (self.project / "input" / "two-years.csv").write_text(
            "Region,Rate 2022,Rate 2026\n"
            "Region of Ardenne,41.0,52.5\n"
            "Region of Brelan,38.2,44.1\n"
            "Region of Cormont,55.4,49.8\n",
            encoding="utf-8")
        # the installer's variable beats the project's own folder, by design
        self.previous = os.environ.get(dataio.SHAPEFILE_ENV)
        os.environ[dataio.SHAPEFILE_ENV] = str(self.project / "shapefiles")
        self.addCleanup(self.restore)

    def restore(self):
        if self.previous is None:
            os.environ.pop(dataio.SHAPEFILE_ENV, None)
        else:
            os.environ[dataio.SHAPEFILE_ENV] = self.previous

    def render(self, baseline: str, comparison: str):
        argv = ["render", "--project-root", str(self.project),
                "--run-folder", "run", "--excel", "input/two-years.csv",
                "--admin-level", "region", "--province-column", "Region",
                "--map-type", "change", "--map-scope", "national",
                "--baseline-column", baseline,
                "--comparison-column", comparison,
                "--language", "en", "--layout", "report",
                "--title", "A title", "--no-html", "--messages", "en"]
        args = self.cli.build_parser().parse_args(argv)
        args.chosen_explicitly = self.cli._explicit(argv)
        if getattr(args, "project_root_sub", None):
            args.project_root = args.project_root_sub
        if getattr(args, "messages_sub", None):
            args.messages = args.messages_sub
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.command_render(args)
        return out.getvalue()

    def test_a_year_where_a_column_belongs_is_refused_not_raised(self):
        """The exact mistake, and the exact old failure: a bare ``KeyError``."""
        with self.assertRaises(SystemExit) as caught:
            self.render("2022", "2026")
        self.assertIn("2022", str(caught.exception))
        self.assertNotIsInstance(caught.exception, KeyError)

    def test_the_refusal_says_which_flag_and_what_is_there(self):
        """A stop that names neither the flag nor the columns present leaves the
        reader guessing which of the two they got wrong."""
        with self.assertRaises(SystemExit) as caught:
            self.render("2022", "Rate 2026")
        message = str(caught.exception)
        self.assertIn("--baseline-column", message)
        self.assertIn("Rate 2022", message, "the columns present are not named")

    def test_the_second_flag_is_checked_too(self):
        """Checking only the first would let the same traceback through from the
        other flag, which is the more likely one to be mistyped: it is the one
        the reader writes last."""
        with self.assertRaises(SystemExit) as caught:
            self.render("Rate 2022", "2026")
        self.assertIn("--comparison-column", str(caught.exception))

    def test_two_real_columns_are_accepted(self):
        """The guard must not refuse the case it protects.

        The claim is checked against what comes back, not against the absence of
        an exception: a guard that refused everything would also "not crash",
        and the first version of this test asserted exactly that much.
        """
        import json

        payload = json.loads(self.render("Rate 2022", "Rate 2026"))
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertIsNotNone(payload["confirm_code"])
        # the change map's own column, built by subtraction, reached the plan
        drawn = " ".join(str(row) for row in payload.get("settings", []))
        self.assertIn("2026", drawn)


if __name__ == "__main__":
    unittest.main()
