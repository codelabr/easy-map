"""No machine of ours may appear in what ships.

Every file the installer copies is read on somebody else's computer. A path from
the machine the skill was written on is wrong there by definition, and an
instruction file is the worst place for one: it is prose an agent reads as
guidance, so a concrete-looking path invites it to pattern-match on the example
instead of following the rule.

The rule is that a worked example must describe the SHAPE of what went wrong,
never the folder it went wrong in. Anything genuinely per-machine is computed at
run time and returned by the engine; the installer rewrites the command paths in
its own copy of SKILL.md, which is why this only ever checks the source.
"""

from __future__ import annotations

import re
import pathlib
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

SKILL = Path(context.ENGINE).parent

#: The folders install.ps1 and install.sh copy. `assets` holds fonts, which are
#: binary and carry their own licence checks elsewhere.
SHIPPED = ("*.md", "agents/*.yaml", "references/*.md", "scripts/*.py",
           "scripts/emap/*.py")

#: A URL is not a filesystem path, and the style reference cites published
#: guidance by link on purpose.
URL = re.compile(r"https?://\S+")

FORBIDDEN = (
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}[^\s`'\"]*"),
     "a drive-letter path from the machine this was written on"),
    # The bare scheme is allowed: the rule these files state is *about* file://
    # URLs, so they have to be able to name one. What is forbidden is a scheme
    # with a real path hanging off it.
    (re.compile(r"file:///[A-Za-z0-9]"),
     "a file:// URL pointing somewhere; the engine computes those and "
     "returns them in mở_tệp"),
    (re.compile(r"/(mnt|Users|home)/[^\s`'\"]+"),
     "an absolute path into somebody's home or mount point"),
)


def shipped_files() -> list[Path]:
    found: list[Path] = []
    for pattern in SHIPPED:
        found.extend(sorted(SKILL.glob(pattern)))
    return found


class TestNothingLeaksAMachine(unittest.TestCase):
    def test_there_are_files_to_check(self):
        """A glob that matches nothing would make every test below vacuous."""
        self.assertGreater(len(shipped_files()), 15)

    def test_no_shipped_file_names_a_real_folder(self):
        for path in shipped_files():
            relative = path.relative_to(SKILL).as_posix()
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = URL.sub("", line)
                for pattern, why in FORBIDDEN:
                    hit = pattern.search(stripped)
                    self.assertIsNone(
                        hit, f"{relative}:{number} carries {why}: "
                             f"{hit.group(0) if hit else ''!r}\n"
                             f"  Describe what went wrong, not where.")


class TestEveryDocumentedFlagIsARealFlag(unittest.TestCase):
    """A flag a document offers has to be one the command accepts.

    There is a check like this for the Vietnamese user guide, and it did its
    job. It covered one file, so it never saw ``--shapefile-root``, which
    ``shapefiles/README.md`` and the handoff both offered as the first place the
    engine looks for boundaries. No such flag has ever existed: the override is
    an argument of ``dataio.shapefile_root`` that only the tests pass. A reader
    following that sentence gets ``unrecognized arguments`` and no map.

    So this one reads every document that ships, not one of them.
    """

    ROOT = Path(context.ENGINE).parents[2]

    #: Documents a user or an agent reads as instruction. ``docs/`` is
    #: deliberately absent: it is not distributed, and its guide has its own
    #: check in this file.
    DOCUMENTS = ("README.md", "shapefiles/README.md",
                 "skills/easy-map/SKILL.md",
                 "skills/easy-map/references/*.md",
                 "skills/easy-map/assets/fonts/README.md")

    #: Flags belonging to other programs, named on purpose: uv, pip, fontTools,
    #: and the installers, which parse their own arguments.
    FOREIGN = {"--with", "--no-cache-dir", "--name-IDs", "--targets", "--quiet",
               "--ref", "--skip-python", "--skip-shapefiles", "--help"}

    def documents(self) -> list[Path]:
        found: list[Path] = []
        for pattern in self.DOCUMENTS:
            found.extend(sorted(self.ROOT.glob(pattern)))
        return found

    def accepted(self) -> set[str]:
        """The flags the command declares, read off its own source.

        The parser is assembled inside ``main()`` and there is no seam to call,
        so this reads the source rather than building a second parser that could
        drift from the first.
        """
        source = (Path(context.ENGINE) / "easy_map.py").read_text(encoding="utf-8")
        return set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', source))

    def test_there_are_documents_and_flags_to_check(self):
        """Either glob coming back empty would make the test below vacuous."""
        self.assertGreater(len(self.documents()), 4)
        self.assertGreater(len(self.accepted()), 20)

    def test_no_document_offers_a_flag_the_command_rejects(self):
        known = self.accepted() | self.FOREIGN
        for path in self.documents():
            relative = path.relative_to(self.ROOT).as_posix()
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                # letters after the first may be capitals: fontTools spells
                # its flag --name-IDs, and stopping at the capital reported a
                # flag called "--name-" that nobody ever wrote
                for flag in re.findall(r"`(--[a-z][A-Za-z0-9-]*)", line):
                    self.assertIn(
                        flag, known,
                        f"{relative}:{number} offers {flag}, which "
                        f"easy_map.py does not accept. Either add the flag or "
                        f"stop offering it.")


class TestTheUserGuideCountsTheWarningsCorrectly(unittest.TestCase):
    """A number written into prose has nothing recomputing it.

    The guide said seventeen checks. There were fifteen functions and
    twenty-five warnings, and the sentence had been wrong for some time — the
    same way ``slidedeck/README.md`` carried 0.41% long after the real figure
    had moved to several per cent. Either the number is pinned or it should not
    be a number.
    """

    GUIDE = (pathlib.Path(__file__).resolve().parents[1]
             / "docs" / "HUONG-DAN-SU-DUNG.md")

    @unittest.skipIf(not (pathlib.Path(__file__).resolve().parents[1]
                          / "docs" / "HUONG-DAN-SU-DUNG.md").exists(),
                     "the guide is not distributed with the skill")
    def test_the_stated_number_is_the_number_of_warnings(self):
        import re

        from emap import messages as msg

        text = self.GUIDE.read_text(encoding="utf-8")
        stated = re.search(r"\*\*(\d+) cảnh báo\*\*", text)
        self.assertIsNotNone(stated, "the guide no longer states a count")
        self.assertEqual(int(stated.group(1)), len(msg.ISSUES))

    @unittest.skipIf(not (pathlib.Path(__file__).resolve().parents[1]
                          / "docs" / "HUONG-DAN-SU-DUNG.md").exists(),
                     "the guide is not distributed with the skill")
    def test_every_flag_the_guide_offers_is_one_the_command_accepts(self):
        """A guide proposing a flag the command rejects is worse than silence:
        the reader tries it and the run stops on a usage error."""
        import re

        import easy_map

        # read the flags off the source rather than building a parser: the
        # parser is assembled inside main() and there is no seam to call
        source = pathlib.Path(easy_map.__file__).read_text(encoding="utf-8")
        known = set(re.findall(r'add_argument\("(--[a-z-]+)"', source))
        self.assertTrue(known, "no flags found in the command at all")
        offered = set(re.findall(r"`(--[a-z-]+)", self.GUIDE.read_text(encoding="utf-8")))
        self.assertTrue(offered, "the guide offers no flags at all")
        self.assertEqual(sorted(offered - known), [])


if __name__ == "__main__":
    unittest.main()
