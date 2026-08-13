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


if __name__ == "__main__":
    unittest.main()
