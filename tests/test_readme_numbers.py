"""The two figures the README states about the engine, counted from the source.

A number written into prose has nothing that recomputes it. This project has
been bitten three times: a share of area quoted at 0.41% after the measurement
changed, a blur factor of "3x" that measurement put at 1.29x, and -- found by
this file -- "17 cartographic checks" when the module holds fifteen.

So either a number in the README is pinned by a test, or it should not be
written down. These are pinned.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

ENGINE = Path(context.ENGINE)
ROOT = ENGINE.parents[2]
README = ROOT / "README.md"
GUARDRAILS = ENGINE / "emap" / "guardrails.py"
TESTS = ROOT / "tests"


def declared_checks() -> list[str]:
    """The cartographic checks, by name, as ``guardrails.py`` defines them."""
    return re.findall(r"^def (check_\w+)", GUARDRAILS.read_text(encoding="utf-8"),
                      re.MULTILINE)


class TestTheNumberOfChecks(unittest.TestCase):
    def test_the_readme_states_the_number_guardrails_actually_holds(self):
        stated = re.search(r"Runs (\d+) cartographic checks", README.read_text(encoding="utf-8"))
        self.assertIsNotNone(
            stated, "the README no longer states a number of cartographic checks; "
                    "if the sentence moved, move this test with it")
        self.assertEqual(
            int(stated.group(1)), len(declared_checks()),
            "the README's count of cartographic checks and the number of "
            "check_* functions in guardrails.py have drifted apart: "
            f"{sorted(declared_checks())}")

    def test_every_check_counted_is_one_that_runs(self):
        """Counting definitions would let a check that nothing calls inflate the
        figure. The claim is that this many checks run before drawing, so each
        one has to be reached from somewhere other than its own definition.

        ``check_periods`` is why this test exists: it was read as dead code
        once, on a search too narrow to see the call in ``profile.py``.
        """
        sources = {p: p.read_text(encoding="utf-8")
                   for p in ENGINE.rglob("*.py") if p != GUARDRAILS}
        sources[GUARDRAILS] = "\n".join(
            line for line in GUARDRAILS.read_text(encoding="utf-8").splitlines()
            if not line.startswith("def "))
        orphans = [name for name in declared_checks()
                   if not any(re.search(rf"\b{name}\s*\(", text)
                              for text in sources.values())]
        self.assertEqual(orphans, [], "declared but never called")


class TestTheNumberOfTests(unittest.TestCase):
    """The README says "more than 900 automated tests"."""

    def stated_and_actual(self) -> tuple[int, int]:
        stated = re.search(r"more than ([\d,]+)\s*\n?\s*automated tests",
                           README.read_text(encoding="utf-8"))
        self.assertIsNotNone(stated, "the README no longer states a test count")
        written = int(stated.group(1).replace(",", ""))
        actual = sum(len(re.findall(r"^\s*def test_", p.read_text(encoding="utf-8"),
                                    re.MULTILINE))
                     for p in sorted(TESTS.glob("test_*.py")))
        return written, actual

    def test_the_claim_is_true(self):
        written, actual = self.stated_and_actual()
        self.assertGreater(actual, written)

    def test_the_claim_has_not_gone_stale(self):
        """A lower bound stays true for ever while drifting further from the
        truth every week, which is its own kind of wrong. Held to the current
        round hundred, so growth past the next one has to be written down.
        """
        written, actual = self.stated_and_actual()
        self.assertLess(
            actual, written + 100,
            f"the suite has grown to {actual}; the README still says more than "
            f"{written}. Raise it to {actual // 100 * 100}.")


if __name__ == "__main__":
    unittest.main()
