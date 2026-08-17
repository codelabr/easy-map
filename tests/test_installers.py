"""The two installers, checked for things that break them silently.

Neither script is importable and neither can be exercised from Python, so this
covers only what static inspection can prove. That is still worth having: an
em-dash in a comment once turned the whole PowerShell installer into a parse
error, and nothing about the file looked wrong.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

INSTALL = Path(context.ENGINE).parents[2] / "install"
POWERSHELL = INSTALL / "install.ps1"
SHELL = INSTALL / "install.sh"
SCRIPTS = (POWERSHELL, SHELL, INSTALL / "web.ps1", INSTALL / "web.sh")


class TestPlainAscii(unittest.TestCase):
    def test_the_scripts_hold_nothing_outside_ascii(self):
        """Windows PowerShell 5.1 reads a .ps1 with no BOM as the system
        codepage, not UTF-8. One accented character anywhere in the file --
        including inside a comment -- becomes mojibake and takes the parser
        down with it. The shell scripts are held to the same rule so the pair
        can be edited together without one of them being a trap.
        """
        for path in SCRIPTS:
            raw = path.read_bytes()
            offending = sorted({b for b in raw if b > 0x7F})
            self.assertEqual(
                offending, [],
                f"{path.name} holds bytes outside ASCII "
                f"({[hex(b) for b in offending]}). On PowerShell 5.1 that "
                f"corrupts the file; write it in plain ASCII.")

    def test_no_script_carries_a_byte_order_mark(self):
        for path in SCRIPTS:
            self.assertNotEqual(path.read_bytes()[:3], b"\xef\xbb\xbf", path.name)


class TestTheTwoStayInStep(unittest.TestCase):
    """The Windows and macOS installers are meant to do the same thing. Where
    they hold the same number twice, a change to one and not the other is a
    defect that only shows up on the platform nobody tested on.
    """

    def test_they_want_the_same_python(self):
        ps = re.search(r"\$WantPython\s*=\s*'([\d.]+)'", POWERSHELL.read_text(encoding="utf-8"))
        sh = re.search(r'WANT_PYTHON="([\d.]+)"', SHELL.read_text(encoding="utf-8"))
        self.assertIsNotNone(ps, "install.ps1 no longer declares $WantPython")
        self.assertIsNotNone(sh, "install.sh no longer declares WANT_PYTHON")
        self.assertEqual(ps.group(1), sh.group(1))

    def test_they_accept_the_same_minimum(self):
        ps = re.search(r"\$MinPython\s*=\s*\[Version\]'(\d+)\.(\d+)'",
                       POWERSHELL.read_text(encoding="utf-8"))
        text = SHELL.read_text(encoding="utf-8")
        major = re.search(r"MIN_PYTHON_MAJOR=(\d+)", text)
        minor = re.search(r"MIN_PYTHON_MINOR=(\d+)", text)
        for name, found in (("$MinPython", ps), ("MIN_PYTHON_MAJOR", major),
                            ("MIN_PYTHON_MINOR", minor)):
            self.assertIsNotNone(found, f"the installers no longer declare {name}")
        self.assertEqual((ps.group(1), ps.group(2)), (major.group(1), minor.group(1)))

    def test_both_offer_the_escape_hatches(self):
        ps, sh = (POWERSHELL.read_text(encoding="utf-8"),
                  SHELL.read_text(encoding="utf-8"))
        for flag, switch in (("$SkipPython", "--skip-python"),
                             ("$SkipShapefiles", "--skip-shapefiles")):
            self.assertIn(flag, ps, f"install.ps1 lost {flag}")
            self.assertIn(switch, sh, f"install.sh lost {switch}")


class TestTheBundledBoundaries(unittest.TestCase):
    """The installer unpacks two zips that have to actually be there, under the
    names it looks for. A rename would leave the install silently boundaryless:
    the skill would read data and refuse to draw, with nothing pointing here.
    """

    ARCHIVES = Path(context.ENGINE).parents[2] / "shapefiles"

    def test_both_archives_ship(self):
        for level in ("provinces", "communes"):
            archive = self.ARCHIVES / f"{level}.zip"
            self.assertTrue(archive.is_file(), f"{archive.name} is missing")

    def test_each_archive_holds_a_complete_shapefile_set(self):
        import zipfile
        for level in ("provinces", "communes"):
            with zipfile.ZipFile(self.ARCHIVES / f"{level}.zip") as z:
                names = z.namelist()
                # Flat members, so the installer can extract straight into a
                # folder it names itself rather than inheriting one.
                self.assertFalse([n for n in names if "/" in n],
                                 f"{level}.zip has folders inside it")
                suffixes = {Path(n).suffix.lower() for n in names}
                for needed in (".shp", ".shx", ".dbf", ".prj"):
                    self.assertIn(needed, suffixes, f"{level}.zip has no {needed}")

    def test_both_installers_look_for_those_exact_names(self):
        for path in (POWERSHELL, SHELL):
            text = path.read_text(encoding="utf-8")
            for level in ("provinces", "communes"):
                self.assertIn(f"{level}.zip", text,
                              f"{path.name} does not mention {level}.zip")

    def test_under_the_per_file_limit_github_enforces(self):
        for level in ("provinces", "communes"):
            mb = (self.ARCHIVES / f"{level}.zip").stat().st_size / 1048576
            self.assertLess(mb, 100, f"{level}.zip is {mb:.1f} MB; GitHub "
                                     f"rejects a push over 100 MB per file")


if __name__ == "__main__":
    unittest.main()
