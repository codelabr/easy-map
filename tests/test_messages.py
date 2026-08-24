"""The two languages of the conversation must not drift apart.

The failure this guards against is not a missing translation — that is loud. It
is a *half* translation: an entry that exists in both languages but says
something different in each, or takes a placeholder in one and not the other, so
the English reader gets a sentence with a hole in it or a warning whose advice
has quietly changed. This project has shipped that failure twice before, both
times because one decision was written down in two places.

So these tests walk the whole table rather than checking sample entries, and
they walk it from the *code* side too: every id the engine asks for must exist.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import context  # noqa: F401  (puts the engine on sys.path)

from emap import guardrails, messages as msg

ENGINE = Path(__file__).resolve().parents[1] / "skills" / "easy-map" / "scripts"


def _forms(entry) -> list[str]:
    """Every wording of one entry: a plain string, or the singular and plural."""
    return list(entry.values()) if isinstance(entry, dict) else [entry]


class TestEveryEntryHasBothLanguages(unittest.TestCase):
    def test_no_warning_is_missing_a_language(self):
        for key, entry in msg.ISSUES.items():
            with self.subTest(key=key):
                self.assertEqual(set(entry), set(msg.LANGUAGES))
                for lang, fields in entry.items():
                    self.assertEqual(set(fields) - {msg.ONE},
                                     {msg.WHAT, msg.WHY, msg.FIX},
                                     f"{key}/{lang} is missing a field")
                    for field, sentence in fields.items():
                        if field == msg.ONE:
                            continue
                        self.assertTrue(sentence.strip(), f"{key}/{lang}/{field} is empty")

    def test_no_sentence_or_fragment_is_missing_a_language(self):
        for table_name, table in (("TEXT", msg.TEXT), ("FRAGMENTS", msg.FRAGMENTS)):
            for key, entry in table.items():
                with self.subTest(table=table_name, key=key):
                    self.assertEqual(set(entry), set(msg.LANGUAGES))
                    for lang in msg.LANGUAGES:
                        for form in _forms(entry[lang]):
                            self.assertTrue(form.strip(), f"{key}/{lang} is empty")

    def test_the_two_languages_take_the_same_placeholders(self):
        """A hole in one language and a fixed word in the other is a silent bug.

        ``"{count} units"`` against ``"đơn vị"`` raises nothing at format time —
        it just prints a sentence that has lost its number.
        """
        for key, entry in msg.ISSUES.items():
            for field in (msg.WHAT, msg.WHY, msg.FIX):
                slots = {lang: msg.placeholders(entry[lang][field])
                         for lang in msg.LANGUAGES}
                with self.subTest(key=key, field=field):
                    self.assertEqual(slots["vi"], slots["en"])
                # a singular override must fill exactly the same holes as the
                # plural it replaces, or one branch of the count loses a number
                for lang in msg.LANGUAGES:
                    one = entry[lang].get(msg.ONE, {})
                    if field in one:
                        with self.subTest(key=key, field=field, form="one", lang=lang):
                            self.assertEqual(msg.placeholders(one[field]), slots[lang])
        for table in (msg.TEXT, msg.FRAGMENTS):
            for key, entry in table.items():
                slots = {lang: {frozenset(msg.placeholders(f)) for f in _forms(entry[lang])}
                         for lang in msg.LANGUAGES}
                with self.subTest(key=key):
                    self.assertEqual(len(slots["vi"]), 1,
                                     f"{key}/vi: the two forms take different fields")
                    self.assertEqual(len(slots["en"]), 1,
                                     f"{key}/en: the two forms take different fields")
                    self.assertEqual(slots["vi"], slots["en"])

    def test_the_two_languages_actually_differ(self):
        """Guards against an entry copied and never translated.

        A handful of strings are genuinely the same in both — none today, but the
        exemption list is here so a future one is declared rather than silently
        passing this test.
        """
        same_by_design: set[str] = set()
        for key, entry in msg.TEXT.items():
            if key in same_by_design:
                continue
            with self.subTest(key=key):
                self.assertNotEqual(_forms(entry["vi"]), _forms(entry["en"]),
                                    f"{key} looks untranslated")


class TestEveryKeyTheCodeAsksForExists(unittest.TestCase):
    """Walk the engine's source and collect the ids it looks up.

    A test that only reads the table would pass while the code asked for a key
    that is not in it — the mismatch only shows at run time, on the one input
    that reaches that branch.
    """

    @staticmethod
    def _requested_keys() -> dict[str, set[str]]:
        wanted: dict[str, set[str]] = {"issue": set(), "text": set(), "fragment": set()}
        for path in sorted((ENGINE / "emap").glob("*.py")) + [ENGINE / "easy_map.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else None
                if name == "_issue":
                    name = "issue"
                if name not in wanted or not node.args:
                    continue
                first = node.args[0]
                # only literal keys can be checked statically; f-strings are
                # covered by the round-trip test below
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    wanted[name].add(first.value)
        return wanted

    def test_the_source_never_asks_for_a_key_that_is_not_there(self):
        wanted = self._requested_keys()
        self.assertTrue(wanted["issue"], "found no warnings at all — the scan is broken")
        self.assertTrue(wanted["text"], "found no sentences at all — the scan is broken")
        for key in sorted(wanted["issue"]):
            self.assertIn(key, msg.ISSUES)
        for key in sorted(wanted["text"]):
            self.assertIn(key, msg.TEXT)
        for key in sorted(wanted["fragment"]):
            self.assertIn(key, msg.FRAGMENTS)

    def test_the_map_option_keys_built_by_formatting_all_exist(self):
        """``profile`` builds its keys as f-strings, so check them by hand."""
        for kind in ("choropleth-symbol", "choropleth", "graduated-symbol",
                     "change", "categorized", "point", "boundary"):
            for field in ("tên", "vì_sao"):
                self.assertIn(f"phuong-an.{kind}.{field}", msg.TEXT)


class TestTheLanguageActuallyChangesTheOutput(unittest.TestCase):
    def setUp(self):
        self.previous = msg.use(msg.DEFAULT)

    def tearDown(self):
        msg.use(self.previous)

    def test_a_warning_comes_back_in_the_chosen_language(self):
        summary = {"total": 99, "unmatched": 30, "fuzzy": 3}
        vi = guardrails.check_admin_level(summary, "commune", "SNU2", lang="vi")
        en = guardrails.check_admin_level(summary, "commune", "SNU2", lang="en")
        self.assertIn("cấp huyện", vi[0]["why"])
        self.assertIn("districts", en[0]["why"])
        # the id and the severity are machine-facing, so they do not translate
        self.assertEqual(vi[0]["id"], en[0]["id"])
        self.assertEqual(vi[0]["severity"], en[0]["severity"])

    def test_the_column_name_survives_into_both_languages(self):
        """The fragment carrying the user's own column name is glued in, so it
        is exactly the piece that a careless translation drops."""
        for lang in msg.LANGUAGES:
            found = guardrails.check_admin_level(
                {"total": 99, "unmatched": 30}, "commune", "SNU2", lang=lang)
            self.assertIn("SNU2", found[0]["why"], lang)

    def test_the_run_language_applies_when_no_language_is_passed(self):
        msg.use("en")
        found = guardrails.check_matching({"unmatched": 4})
        self.assertIn("were not found", found[0][msg.WHAT])
        self.assertIn("drop off the map", found[0][msg.WHY])
        msg.use("vi")
        found = guardrails.check_matching({"unmatched": 4})
        self.assertIn("không tìm thấy", found[0][msg.WHAT])
        self.assertIn("biến mất khỏi bản đồ", found[0][msg.WHY])

    def test_an_unknown_language_falls_back_rather_than_raising(self):
        self.assertEqual(msg.normalise("fr"), msg.DEFAULT)
        self.assertEqual(msg.normalise(None), msg.current())

    def test_use_returns_the_previous_language_so_it_can_be_restored(self):
        first = msg.use("en")
        self.assertEqual(msg.current(), "en")
        second = msg.use(first)
        self.assertEqual(second, "en")
        self.assertEqual(msg.current(), first)

    def test_english_counts_one_thing_in_the_singular(self):
        """"1 place names were matched" is a defect Vietnamese cannot have.

        The plural form is only correct above one, and the branch that reports a
        single name is the common one — most tables have a handful of oddities,
        not dozens.
        """
        one = guardrails.check_matching({"fuzzy": 1}, lang="en")[0]
        many = guardrails.check_matching({"fuzzy": 4}, lang="en")[0]
        self.assertIn("1 place name was matched", one[msg.WHAT])
        self.assertIn("4 place names were matched", many[msg.WHAT])

    def test_vietnamese_does_not_inflect_and_says_the_same_thing_either_way(self):
        one = guardrails.check_matching({"fuzzy": 1}, lang="vi")[0]
        many = guardrails.check_matching({"fuzzy": 9}, lang="vi")[0]
        self.assertEqual(one[msg.WHAT].replace("1 ", "", 1),
                         many[msg.WHAT].replace("9 ", "", 1))

    def test_every_singular_override_belongs_to_a_countable_sentence(self):
        """An override on a sentence with no number would never fire."""
        for key, entry in msg.ISSUES.items():
            for lang in msg.LANGUAGES:
                one = entry[lang].get(msg.ONE)
                if not one:
                    continue
                with self.subTest(key=key, lang=lang):
                    slots = set().union(*(msg.placeholders(s) for s in one.values()))
                    self.assertTrue(slots, f"{key}/{lang} has a singular form but no count")

    def test_numbers_inside_a_warning_follow_the_message_language(self):
        """A Vietnamese warning must not print an English decimal point.

        This is the same defect that reached a printed map: one character, two
        meanings, on one page.
        """
        info = {"column": "Tỷ lệ", "semantic": "percent", "scale": "percent"}
        vi = guardrails.check_percent_range([120.5], info, lang="vi")
        en = guardrails.check_percent_range([120.5], info, lang="en")
        self.assertIn("120,5%", vi[0]["problem"])
        self.assertIn("120.5%", en[0]["problem"])


class TestTheFlagReachesTheTable(unittest.TestCase):
    """The catalogue can be perfect and still never be selected.

    Everything above tests the table and the functions. None of it would notice
    that ``--messages en`` was accepted by argparse and then dropped on the floor
    — which is the whole path a real run takes.
    """

    def setUp(self):
        self.cli = context.cli()
        self.previous = msg.current()

    def tearDown(self):
        msg.use(self.previous)

    def _parse(self, argv):
        return self.cli.build_parser().parse_args(argv)

    def test_the_flag_is_accepted_before_and_after_the_subcommand(self):
        for argv in (["--messages", "en", "list"], ["list", "--messages", "en"]):
            with self.subTest(argv=argv):
                args = self._parse(argv)
                chosen = getattr(args, "messages_sub", None) or args.messages
                self.assertEqual(chosen, "en")

    def test_the_default_is_vietnamese(self):
        self.assertEqual(self._parse(["list"]).messages, msg.DEFAULT)
        self.assertEqual(msg.DEFAULT, "vi")

    def test_an_unsupported_code_is_refused_rather_than_ignored(self):
        """Silently falling back would ship Vietnamese to a reader who asked
        for something else and had no way to tell."""
        with self.assertRaises(SystemExit):
            self._parse(["list", "--messages", "fr"])

    def test_every_command_takes_the_flag(self):
        for command in ("start-run", "list", "survey", "profile", "render",
                        "fix-match", "import"):
            with self.subTest(command=command):
                parser = self.cli.build_parser()
                child = parser._subparsers._group_actions[0].choices[command]
                flags = {s for a in child._actions for s in a.option_strings}
                self.assertIn("--messages", flags)

    def test_the_map_language_and_the_message_language_are_independent(self):
        """The case this whole split exists for: an English-speaking officer
        producing a Vietnamese map."""
        args = self._parse(["render", "--messages", "en", "--language", "vi",
                            "--excel", "x.xlsx", "--admin-level", "province"])
        self.assertEqual(getattr(args, "messages_sub", None) or args.messages, "en")
        self.assertEqual(args.language, "vi")


if __name__ == "__main__":
    unittest.main()
