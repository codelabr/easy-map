"""The two installers, checked for things that break them silently.

Neither script is importable and neither can be exercised from Python, so this
covers only what static inspection can prove. That is still worth having: an
em-dash in a comment once turned the whole PowerShell installer into a parse
error, and nothing about the file looked wrong.
"""

from __future__ import annotations

import re
import shutil
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


class TestTheBoundaryArchives(unittest.TestCase):
    """The archives are release assets now, not repository content.

    They used to be committed: 88 MB across two files, the commune one 74.7 MB
    against GitHub's 50 MB warning, and every country added would have landed in
    the history of every clone for ever. So they are attached to a release and
    fetched at install time, and nothing here can assert that a file is present
    — it is deliberately not.

    What is worth pinning is the contract between the two halves: the names
    ``tools/pack_boundaries.py`` writes are the names the installers ask for,
    and the layout inside an archive is the layout the engine expects.
    """

    PACKER = Path(context.ENGINE).parents[2] / "tools" / "pack_boundaries.py"

    def pack(self, country="fictavia", tier="region"):
        """Run the real packer over a synthetic country.

        Loaded as a module rather than through ``runpy``: ``run_path`` hands
        back a *copy* of the globals, so rebinding ``OUT`` in it leaves the
        function still writing to the repository's own dist folder — which is
        what the first version of this did.
        """
        import importlib.util
        import tempfile

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        source = folder / "shapefiles" / country / tier
        source.mkdir(parents=True)
        for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            (source / f"Bờ cõi{suffix}").write_bytes(b"x" * 64)

        spec = importlib.util.spec_from_file_location("packer", self.PACKER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.SOURCE = folder / "shapefiles"
        module.OUT = folder / "dist"
        module.pack(module.SOURCE / country)
        return folder / "dist"

    def test_one_archive_per_country_and_tier(self):
        out = self.pack()
        self.assertEqual([p.name for p in sorted(out.glob("*.zip"))],
                         ["fictavia-region.zip"])

    def test_the_layout_lives_inside_the_archive(self):
        """So unpacking is extraction into the root and the installer needs to
        know no folder names at all — which is what lets a country be added
        without touching either installer."""
        import zipfile

        out = self.pack()
        with zipfile.ZipFile(out / "fictavia-region.zip") as archive:
            names = archive.namelist()
        self.assertTrue(names)
        for name in names:
            self.assertTrue(name.startswith("fictavia/region/"), name)

    def test_a_complete_shapefile_set_including_the_code_page(self):
        """``.cpg`` is not optional here: without it a reader guesses the code
        page and Vietnamese names come back as mojibake."""
        import zipfile

        out = self.pack()
        with zipfile.ZipFile(out / "fictavia-region.zip") as archive:
            suffixes = {Path(n).suffix.lower() for n in archive.namelist()}
        for needed in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            self.assertIn(needed, suffixes)

    def test_a_set_with_no_codepage_file_is_reported(self):
        """Found on the Canada set: no ``.cpg``, so a plain reader decodes its
        UTF-8 names as Latin-1 and Québec arrives as ``QuÃ©bec`` — a province
        that can never match a spreadsheet. The engine detects and repairs that
        when it reads; anything else opening the archive gets the mojibake, so
        packing it away silently spreads the problem rather than the fix."""
        import importlib.util
        import tempfile

        spec = importlib.util.spec_from_file_location("packer", self.PACKER)
        packer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packer)

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        naked = [folder / f"a{s}" for s in (".shp", ".shx", ".dbf", ".prj")]
        for f in naked:
            f.write_bytes(b"x")
        warning = packer.codepage_warning(naked)
        self.assertIsNotNone(warning)
        self.assertIn("a.shp", warning)
        self.assertIn(".cpg", warning)

        dressed = naked + [folder / "a.cpg"]
        dressed[-1].write_text("UTF-8", encoding="ascii")
        self.assertIsNone(packer.codepage_warning(dressed))

    def test_the_warning_does_not_stop_the_packing(self):
        """A set that is usable today should still be packable. Reporting is
        the right response to something the engine already works around."""
        out = self.pack()
        self.assertTrue(list(out.glob("*.zip")))

    def test_both_installers_ask_for_the_same_assets(self):
        """Two installers drifting apart is how one platform silently installs
        without boundaries."""
        names = {}
        for path in (POWERSHELL, SHELL):
            text = path.read_text(encoding="utf-8")
            names[path.name] = set(re.findall(r"'?(viet-nam-[a-z]+)'?", text))
        first, second = names.values()
        self.assertTrue(first, "no assets named in the installer")
        self.assertEqual(first, second)

    def test_the_asset_names_follow_the_packer_s_own_rule(self):
        """``<country>-<tier>`` — stated once, in the packer, and read back
        here rather than written out a second time."""
        packer = self.PACKER.read_text(encoding="utf-8")
        self.assertIn('f"{country.name}-{tier_name}.zip"', packer)
        for name in re.findall(r"'(viet-nam-[a-z]+)'", POWERSHELL.read_text(encoding="utf-8")):
            # split at the *last* hyphen: a country name may hold one of its
            # own, and "viet-nam" is exactly such a name
            country, _, tier = name.rpartition("-")
            self.assertEqual(country, "viet-nam")
            self.assertIn(tier, {"province", "commune"})

    def test_a_local_archive_is_preferred_over_downloading(self):
        """The way to install on a closed network is to carry the zips in by
        hand, so a copy beside the installer has to win."""
        for path in (POWERSHELL, SHELL):
            text = path.read_text(encoding="utf-8")
            with self.subTest(installer=path.name):
                self.assertIn("[local]", text)

    def test_a_downloaded_archive_is_cleaned_up(self):
        """It was fetched for this run. A copy the user placed in shapefiles/
        is theirs and must survive."""
        for path in (POWERSHELL, SHELL):
            text = path.read_text(encoding="utf-8")
            with self.subTest(installer=path.name):
                self.assertRegex(text, r"(rm -f|Remove-Item) [^\r\n]*tmp")


if __name__ == "__main__":
    unittest.main()
