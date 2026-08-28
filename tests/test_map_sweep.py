"""The sweep's case list, checked without drawing anything.

``tools/sweep_maps.py`` draws 503 maps. That is 3 to 4 hours of CPU, so it is
run deliberately rather than by ``python -m unittest`` — but the *list* it draws
from can rot silently, and a rotted list is worse than no sweep at all: a case
naming a column the generator no longer writes is refused in a fraction of a
second, the sweep reports "refused" among 500 lines, and the eye reads it as
covered.

Five of the first six cases written here were wrong in exactly that way. Two
sized a proportional-symbol map with ``--value-column``, which that map type
refuses; three passed ``--province``, which ``render`` does not define at all
and argparse rejected as an ambiguous prefix of ``--province-column``. None of
it was a defect in the skill. All of it would have been reported as one.

So this file checks the parts that cost nothing: every flag parses, every
workbook and column named exists, and no two cases share a name — two cases with
one name write to one folder, and the second silently overwrites the first.
"""

from __future__ import annotations

import importlib.util
import unittest
from collections import Counter
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

ROOT = Path(context.ENGINE).parents[2]
SWEEP = ROOT / "tools" / "sweep_maps.py"
GENERATOR = ROOT / "tools" / "generate_programme_data.py"


def load(path: Path):
    """Load a tool by path.

    ``runpy.run_path`` hands back a *copy* of the globals, so anything rebound
    afterwards leaves the real module untouched — a mistake already made once in
    this suite, in ``test_installers``.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheCaseListIsWellFormed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sweep = load(SWEEP)
        cls.cases = cls.sweep.cases()
        cls.parser = context.cli().build_parser()

    def test_there_are_enough_cases_to_be_a_sweep(self):
        """The number is the point of the exercise, so it is stated once and
        checked, rather than believed."""
        self.assertGreaterEqual(len(self.cases), 500)

    def test_every_case_has_a_name_of_its_own(self):
        """Two cases with one name share a run folder, and the second
        overwrites the first: the sweep would report 503 successes having drawn
        502 maps."""
        repeated = [name for name, count
                    in Counter(name for _, name, _ in self.cases).items()
                    if count > 1]
        self.assertEqual(repeated, [])

    def test_every_case_parses(self):
        """A flag the command does not define, or a value outside its choices,
        is an argparse error the sweep reports as a refusal — indistinguishable,
        at a glance, from the skill refusing a bad request."""
        for group, name, tail in self.cases:
            argv = self.sweep.full_argv(name, tail)
            with self.subTest(case=f"{group}/{name}"):
                try:
                    self.parser.parse_args(argv)
                except SystemExit as exc:      # argparse exits rather than raises
                    self.fail(f"argparse rejected the case ({exc}): "
                              f"{' '.join(argv[4:])}")

    def test_every_case_answers_the_three_questions_the_gate_asks(self):
        """Language, layout and title. A case that leaves one open stops at the
        confirmation gate and draws nothing, which is the gate working — but it
        would be counted here as a failure of the map."""
        for group, name, tail in self.cases:
            argv = self.sweep.full_argv(name, tail)
            with self.subTest(case=f"{group}/{name}"):
                for flag in ("--language", "--layout", "--title"):
                    self.assertIn(flag, argv)

    def test_a_proportional_symbol_map_is_never_sized_by_value_column(self):
        """The mistake that produced three of the first five false failures.
        ``graduated-symbol`` has no fill to colour, so it refuses
        ``--value-column`` rather than ignoring it."""
        for group, name, tail in self.cases:
            if "graduated-symbol" not in tail:
                continue
            with self.subTest(case=f"{group}/{name}"):
                self.assertIn("--symbol-column", tail)

    def test_every_workbook_a_case_names_is_one_the_generator_writes(self):
        """Read off the generator's own source rather than listing the files:
        the files are not tracked, so on a clean checkout there are none, and a
        test that globbed the folder would pass by being vacuous."""
        source = GENERATOR.read_text(encoding="utf-8")
        wanted = sorted({tail[tail.index("--excel") + 1]
                         for _, _, tail in self.cases if "--excel" in tail})
        self.assertTrue(wanted)
        for path in wanted:
            stem = Path(path).stem
            with self.subTest(workbook=stem):
                # the generator builds names from a programme slug and a suffix,
                # so the check is that both halves appear in it
                head, _, tail_part = stem.partition("-")
                self.assertIn(head, source, f"{stem}: no such programme")
                self.assertIn(tail_part.split("-")[0], source, stem)

    def test_every_column_a_case_names_is_one_the_generator_writes(self):
        """The failure this is really about: a column renamed in the generator
        and not in the sweep. Every case would be refused with 'column not
        found', and 503 refusals still look like a sweep that ran."""
        source = GENERATOR.read_text(encoding="utf-8")
        flags = ("--value-column", "--symbol-column", "--weight-column",
                 "--point-color-column", "--point-size-column",
                 "--province-column", "--commune-column", "--period-column",
                 "--lon-column", "--lat-column", "--indicator-column")
        named = set()
        for _, _, tail in self.cases:
            for flag in flags:
                if flag in tail:
                    named.add(tail[tail.index(flag) + 1])
        self.assertGreater(len(named), 20)
        for column in sorted(named):
            with self.subTest(column=column):
                self.assertIn(column, source)

    def test_the_column_table_matches_the_generator_programme_for_programme(self):
        """The sweep keeps its own copy of the column names, so that building a
        case list does not mean opening 34 workbooks. A copy is a thing that can
        disagree, so it is compared against the original here."""
        generator = load(GENERATOR)
        for slug, spec in generator.PROGRAMMES.items():
            with self.subTest(programme=slug):
                self.assertIn(slug, self.sweep.COLUMNS)
                mirrored = self.sweep.COLUMNS[slug]
                for key in ("mau_so", "quan_the", "dem", "dem_2", "ty_le", "suat"):
                    self.assertEqual(mirrored[key], spec[key][0], key)
                self.assertEqual(mirrored["nhom"], spec["nhom"][0])

    def test_the_groups_cover_what_the_sweep_claims_to_cover(self):
        """A group quietly emptied by an edit would take its whole axis with it,
        and the total would still look healthy because another axis grew."""
        counts = Counter(group for group, _, _ in self.cases)
        for group in ("core", "classes", "commune", "period", "missing", "point",
                      "options", "labels", "aggregate", "messages", "longform",
                      "matching", "commune-series", "scope"):
            with self.subTest(group=group):
                self.assertGreaterEqual(counts[group], 3)

    def test_both_administrative_levels_and_every_map_type_appear(self):
        levels = {tail[tail.index("--admin-level") + 1]
                  for _, _, tail in self.cases if "--admin-level" in tail}
        self.assertEqual(levels, {"province", "commune"})
        kinds = {tail[tail.index("--map-type") + 1]
                 for _, _, tail in self.cases if "--map-type" in tail}
        self.assertEqual(kinds, {"choropleth", "choropleth-symbol",
                                 "graduated-symbol", "categorized", "boundary",
                                 "change", "point"})


if __name__ == "__main__":
    unittest.main()
