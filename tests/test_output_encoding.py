"""The engine must print Vietnamese whatever the console is set to.

Every reply carries Vietnamese - the JSON keys themselves do - and on Windows
Python encodes stdout with the machine's legacy codepage rather than UTF-8, for
a pipe as much as for a console. Before this was fixed, every command on such a
machine died with UnicodeEncodeError inside ``json.dumps``, which reads as a
bug in the engine rather than as an encoding setting.

These run the CLI as a real subprocess: the defect lives in how the interpreter
is started, so asserting anything in-process would test the wrong thing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

CLI = Path(context.ENGINE) / "easy_map.py"

#: Codepages that cannot represent Vietnamese. cp1252 is the Western European
#: default on a great many Windows installations; cp1258 is Vietnamese Windows
#: and still fails on the combining forms the engine emits.
LEGACY = ("cp1252", "cp1258", "ascii")


def run_list(encoding: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = encoding
    # Clear the two escape hatches, so the test measures the code and not a
    # setting that happens to be present on the developer's machine.
    env.pop("PYTHONUTF8", None)
    with tempfile.TemporaryDirectory() as project:
        return subprocess.run(
            [sys.executable, str(CLI), "list", "--project-root", project],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)


class TestLegacyConsoles(unittest.TestCase):
    def test_the_command_survives_a_codepage_without_vietnamese(self):
        for encoding in LEGACY:
            with self.subTest(encoding=encoding):
                done = run_list(encoding)
                self.assertEqual(
                    done.returncode, 0,
                    f"PYTHONIOENCODING={encoding} broke the command:\n{done.stderr[-600:]}")
                self.assertNotIn("UnicodeEncodeError", done.stderr)

    def test_the_vietnamese_survives_too(self):
        """Exiting zero is not enough: the accents must reach the reader rather
        than being replaced or dropped."""
        for encoding in LEGACY:
            with self.subTest(encoding=encoding):
                done = run_list(encoding)
                self.assertIn("project_root", done.stdout,
                              f"PYTHONIOENCODING={encoding} mangled the reply")


if __name__ == "__main__":
    unittest.main()
