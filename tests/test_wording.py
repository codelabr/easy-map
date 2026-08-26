"""The plan has to be readable by the person being asked to agree to it.

The gate already stops the agent. What it stopped it with, on a real Codex run,
was a table whose settings read ``choropleth-symbol``, ``quantile`` and
``weighted-mean`` — presented to a public-health officer who could only say yes,
because saying anything else would have meant knowing the vocabulary. Stopping
to ask a question nobody can answer is not asking.

So these tests hold two lines. Every value the command line accepts must have a
name and a sentence in both languages — checked against argparse's own
``choices`` rather than a list copied beside it, because a copied list is how
this project has twice shipped two halves of one decision. And no flag token may
survive into anything a reader sees.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import messages as msg, wording


#: Words that belong to the command line and to nobody else. A label or a
#: description containing one of these has failed at the only job it has.
#: ``png`` and ``svg`` are absent on purpose — those are file formats a reader
#: already meets in a save dialog, not GIS vocabulary. So is ``boundary``, which
#: is an ordinary English word before it is a flag value; the test below covers
#: that case by refusing a label that is merely its own value.
JARGON = ("choropleth", "quantile", "categorized", "weighted-mean", "natural-breaks",
          "equal-interval", "graduated-symbol", "banner", "matched-only",
          "province-series", "single-province", "map-type", "map_type", "--")


def parser_choices() -> dict[str, tuple[str, ...]]:
    """What ``render`` actually accepts, read off the parser itself."""
    cli = context.cli()
    render = cli.build_parser()._subparsers._group_actions[0].choices["render"]
    by_flag = {}
    for action in render._actions:
        if not action.choices:
            continue
        for flag in action.option_strings:
            by_flag[flag.lstrip("-").replace("-", "_")] = tuple(action.choices)
    return by_flag


class TestEveryValueTheCommandAcceptsHasWords(unittest.TestCase):
    """The list in :mod:`wording` and the list in argparse are one decision.

    Kept apart, a value added to the parser reaches the plan as a raw token and
    nothing fails until a reader is looking at it.
    """

    def setUp(self):
        self.accepted = parser_choices()

    def test_the_two_lists_are_the_same_list(self):
        for setting, values in wording.VALUES.items():
            with self.subTest(setting=setting):
                self.assertIn(setting, self.accepted,
                              f"{setting} is not a --{setting} the parser knows")
                self.assertEqual(set(values), set(self.accepted[setting]))

    def test_every_value_has_a_name_and_a_sentence_in_both_languages(self):
        for setting, values in wording.VALUES.items():
            for value in values:
                for lang in msg.LANGUAGES:
                    with self.subTest(setting=setting, value=value, lang=lang):
                        self.assertTrue(wording.label(setting, value, lang).strip())
                        self.assertTrue(wording.describe(setting, value, lang).strip())

    def test_every_setting_has_a_question(self):
        for setting in wording.VALUES:
            for lang in msg.LANGUAGES:
                with self.subTest(setting=setting, lang=lang):
                    text = msg.text(f"choice.{setting}.question", lang)
                    self.assertTrue(text.strip().endswith("?"), text)

    def test_every_row_of_the_plan_has_a_heading_in_both_languages(self):
        for name in ("data", "data-slice", "map-kind", "coloured-by",
                     "circles-by", "title", "legend", "symbol-legend",
                     "scope", "layout", "language",
                     "classes", "labels", "repeated-rows", "output"):
            for lang in msg.LANGUAGES:
                with self.subTest(name=name, lang=lang):
                    self.assertTrue(wording.field(name, lang).strip())


class TestWhenAPlaceColumnIsRequired(unittest.TestCase):
    """The guard that turns ``KeyError: None`` into a sentence.

    Its first version was one condition written inline, and it blocked the one
    run that legitimately has no place column — a point map placed from
    coordinates. Every test in this project stayed green while it did, which is
    why the rule now has a name and this class.
    """

    def args(self, **over):
        import argparse

        base = dict(map_type="choropleth", admin_level="province",
                    province_column=None, commune_column=None)
        base.update(over)
        return argparse.Namespace(**base)

    def setUp(self):
        self.cli = context.cli()

    def test_a_map_with_no_place_column_is_stopped(self):
        for level in ("province", "commune"):
            self.assertTrue(self.cli._needs_place_column(
                self.args(admin_level=level)), level)

    def test_naming_the_column_satisfies_it(self):
        self.assertFalse(self.cli._needs_place_column(
            self.args(province_column="Tỉnh")))
        self.assertFalse(self.cli._needs_place_column(
            self.args(admin_level="commune", commune_column="Xã")))

    def test_a_commune_column_alone_is_not_enough_at_province_level(self):
        """The parent name is what a province map joins on."""
        self.assertTrue(self.cli._needs_place_column(
            self.args(admin_level="province", commune_column="Xã")))

    def test_a_point_map_from_coordinates_needs_no_place_column(self):
        """The case the first guard broke. ``command_render`` calls it
        ``coordinates_only`` and does no name matching for it at all."""
        self.assertFalse(self.cli._needs_place_column(self.args(map_type="point")))

    def test_a_point_map_that_does_name_places_is_still_checked(self):
        """Naming one column and not the other is the mistake, not the mode."""
        self.assertTrue(self.cli._needs_place_column(
            self.args(map_type="point", admin_level="province",
                      commune_column="Xã")))


class TestNoFlagTokenReachesTheReader(unittest.TestCase):
    def test_no_label_or_sentence_carries_command_line_vocabulary(self):
        for setting, values in wording.VALUES.items():
            for value in values:
                for lang in msg.LANGUAGES:
                    written = (wording.label(setting, value, lang) + " "
                               + wording.describe(setting, value, lang)).lower()
                    for token in JARGON:
                        with self.subTest(setting=setting, value=value,
                                          lang=lang, token=token):
                            self.assertNotIn(token, written)

    def test_the_value_itself_stays_out_of_its_own_label(self):
        """The laziest possible translation is the one to guard against."""
        for setting, values in wording.VALUES.items():
            for value in values:
                for lang in msg.LANGUAGES:
                    with self.subTest(setting=setting, value=value, lang=lang):
                        self.assertNotEqual(wording.label(setting, value, lang).lower(),
                                            value.lower())


class TestTheMenu(unittest.TestCase):
    def test_the_current_value_leads_and_is_the_recommendation(self):
        offered = wording.options("classification", "natural-breaks", "vi")
        self.assertEqual(offered[0]["value"], "natural-breaks")
        self.assertTrue(offered[0]["recommended"])
        self.assertFalse(any(o["recommended"] for o in offered[1:]))

    def test_it_stays_short_enough_to_read(self):
        for setting in wording.VALUES:
            with self.subTest(setting=setting):
                offered = wording.options(setting, None, "vi")
                self.assertLessEqual(len(offered), wording.MENU)

    def test_a_long_list_still_offers_the_current_value_first(self):
        """``aggregate`` has nine values and a menu holds three; the one in use
        must not be the one that falls off the end."""
        offered = wording.options("aggregate", "first", "vi")
        self.assertEqual(offered[0]["value"], "first")

    def test_among_narrows_the_pool_to_what_applies(self):
        offered = wording.options("map_scope", "national", "vi",
                                  among=("national", "province-series"))
        self.assertEqual({o["value"] for o in offered},
                         {"national", "province-series"})

    def test_every_option_carries_the_flag_that_would_set_it(self):
        for option in wording.options("layout", "report", "vi"):
            self.assertEqual(option["flag"],
                             f"--layout {option['value']}")

    def test_a_question_with_one_answer_is_not_asked(self):
        self.assertIsNone(wording.menu("map_scope", "national", "vi",
                                       among=("national",)))
        self.assertIsNotNone(wording.menu("layout", "report", "vi"))

    def test_the_menu_follows_the_conversation_language(self):
        previous = msg.use("en")
        try:
            self.assertEqual(wording.options("language", "vi")[0]["label"], "Vietnamese")
            msg.use("vi")
            self.assertEqual(wording.options("language", "vi")[0]["label"], "Tiếng Việt")
        finally:
            msg.use(previous)


class TestThePlanTable(unittest.TestCase):
    """The table itself, built from fakes so it can be read without a shapefile."""

    def setUp(self):
        self.cli = context.cli()
        self.previous = msg.use("vi")

    def tearDown(self):
        msg.use(self.previous)

    def args(self, **over):
        import argparse
        base = dict(sheet="Sheet1", where=None, map_type="choropleth",
                    symbol_column=None, layout="report", language="vi",
                    classification="quantile", labels="both", formats="png",
                    dpi=220, no_html=False, chosen_explicitly=set(),
                    # the wording on the plate is part of the plan now, and
                    # argparse always sets these four
                    title=None, legend_title=None, symbol_legend_title=None,
                    period_column=None)
        base.update(over)
        return argparse.Namespace(**base)

    #: distinguishes "the caller said nothing" from "the caller said no classes"
    DEFAULT_BINS = {"classes": 5}

    def plan(self, *, scope="national", prepared=None, method="sum",
             bins=DEFAULT_BINS, value_column="Tỷ lệ", **over):
        return self.cli._plan(self.args(**over), "a.xlsx", [1] * 34, value_column,
                              scope, prepared or [{"name": "national"}], method, bins)

    def rows(self, numbered):
        return {r["item"]: r for r in numbered}

    def test_no_row_shows_a_flag_value(self):
        _, numbered, _ = self.plan(map_type="choropleth-symbol", symbol_column="Số ca",
                                   method="weighted-mean")
        for row in numbered:
            for token in JARGON:
                with self.subTest(row=row["item"], token=token):
                    self.assertNotIn(token, row["value"].lower())

    def test_a_csv_does_not_claim_to_have_a_sheet(self):
        _, numbered, _ = self.plan(sheet=None)
        self.assertNotIn("sheet", self.rows(numbered)["Dữ liệu"]["value"])

    def test_a_single_national_map_is_not_described_twice(self):
        _, numbered, _ = self.plan(scope="national")
        self.assertEqual(self.rows(numbered)["Phạm vi bản đồ"]["value"],
                         "Một tấm toàn quốc")

    def test_a_series_names_the_maps_it_will_draw(self):
        _, numbered, _ = self.plan(scope="province-series",
                                   prepared=[{"name": "Hà Nội"}, {"name": "Huế"}])
        value = self.rows(numbered)["Phạm vi bản đồ"]["value"]
        self.assertIn("2 tấm", value)
        self.assertIn("Hà Nội, Huế", value)

    def test_settings_the_skill_chose_are_marked_as_such(self):
        _, numbered, _ = self.plan(chosen_explicitly={"layout"})
        rows = self.rows(numbered)
        self.assertNotIn("note", rows["Bố cục"])
        self.assertIn("note", rows["Nhãn trên bản đồ"])

    def test_the_headings_follow_the_conversation_language(self):
        msg.use("en")
        _, numbered, _ = self.plan()
        self.assertIn("Map language", self.rows(numbered))

    def test_the_unasked_settings_come_back_as_finished_questions(self):
        _, _, must_ask = self.plan()
        self.assertEqual([q["item"] for q in must_ask],
                         ["language", "layout", "title"])
        for question in must_ask:
            self.assertTrue(question["question"].endswith("?"))
            if question.get("answered_in_words"):
                continue
            self.assertGreaterEqual(len(question["choices"]), 2)
            self.assertTrue(question["choices"][0]["recommended"])

    def test_the_title_is_asked_for_in_words_with_the_facts_to_build_it(self):
        """It cannot be a menu. The engine has no standing to name somebody
        else's figures, so it asks — and hands over what it does know."""
        _, _, must_ask = self.plan(map_type="choropleth-symbol",
                                   symbol_column="Số ca")
        question = next(q for q in must_ask if q["item"] == "title")
        self.assertTrue(question["answered_in_words"])
        self.assertNotIn("choices", question)
        self.assertEqual(question["ingredients"]["columns"],
                         ["Tỷ lệ", "Số ca"])

    def test_a_setting_given_on_the_command_line_is_not_asked_about(self):
        _, _, must_ask = self.plan(
            chosen_explicitly={"language", "layout", "title"}, title="A title")
        self.assertEqual(must_ask, [])

    def test_the_map_type_menu_appears_only_when_both_channels_are_filled(self):
        _, with_both, _ = self.plan(map_type="choropleth-symbol", symbol_column="Số ca")
        self.assertIn("choices", self.rows(with_both)["Loại bản đồ"])
        _, fill_only, _ = self.plan(symbol_column=None)
        self.assertNotIn("choices", self.rows(fill_only)["Loại bản đồ"])

    def test_no_menu_ever_offers_to_hide_the_units_without_data(self):
        """``matched-only`` turns "we surveyed 12 of 34 provinces" into a
        picture of a country with 12 provinces. It stays reachable by name and
        unreachable by menu."""
        for scope in ("national", "province-series", "single-province"):
            _, numbered, _ = self.plan(scope=scope,
                                       prepared=[{"name": "Hà Nội"}, {"name": "Huế"}])
            for row in numbered:
                with self.subTest(scope=scope, row=row["item"]):
                    self.assertNotIn("matched-only",
                                     [o["value"] for o in row.get("choices", [])])

    def test_the_menu_marks_the_resolved_value_rather_than_the_flag(self):
        """``--map-scope auto`` became a real framing; offering "auto" back as
        the current choice would offer the reader what they already have."""
        _, numbered, _ = self.plan(scope="province-series",
                                   prepared=[{"name": "Hà Nội"}, {"name": "Huế"}])
        offered = self.rows(numbered)["Phạm vi bản đồ"]["choices"]
        self.assertEqual(offered[0]["value"], "province-series")
        self.assertTrue(offered[0]["recommended"])

    def test_a_plan_with_no_classes_says_so_instead_of_breaking(self):
        _, numbered, _ = self.plan(bins={}, method="n/a")
        rows = self.rows(numbered)
        self.assertEqual(rows["Chia nhóm màu"]["value"], "không áp dụng")
        self.assertEqual(rows["Gộp dòng trùng"]["value"], "không áp dụng")

    def test_the_hash_stands_for_what_the_reader_read(self):
        """Two plans that look identical to a reader must not unlock separately,
        and two that read differently must not share a code."""
        from emap import confirm
        first, _, _ = self.plan()
        again, _, _ = self.plan()
        changed, _, _ = self.plan(labels="off")
        self.assertEqual(confirm.token(first), confirm.token(again))
        self.assertNotEqual(confirm.token(first), confirm.token(changed))


class TestTheFilePicker(unittest.TestCase):
    def setUp(self):
        self.cli = context.cli()
        self.previous = msg.use("vi")

    def tearDown(self):
        msg.use(self.previous)

    def files(self):
        return [{"files": "a.xlsx", "sheet": [
                    {"sheet": "Tỉnh", "usable": True, "estimated_rows": 34,
                     "suggested_level": "province"},
                    {"sheet": "Ghi chú", "usable": False}]},
                {"files": "b.xlsx", "sheet": [
                    {"sheet": "Xã", "usable": True, "estimated_rows": 1,
                     "suggested_level": "commune"}]}]

    def test_only_the_sheets_that_can_become_a_map_are_offered(self):
        picked = self.cli._quick_pick(self.files())
        self.assertEqual([o["sheet"] for o in picked["choices"]][:2], ["Tỉnh", "Xã"])

    def test_there_is_always_a_way_off_the_list(self):
        """input/ holds fixtures and other people's work. A menu with no exit
        invites someone to map a table that is not theirs."""
        picked = self.cli._quick_pick(self.files())
        self.assertIsNone(picked["choices"][-1]["files"])
        self.assertEqual(picked["choices"][-1]["number"], len(picked["choices"]))

    def test_each_option_says_what_is_in_it(self):
        picked = self.cli._quick_pick(self.files())
        self.assertIn("34 dòng", picked["choices"][0]["description"])
        self.assertIn("xã/phường", picked["choices"][1]["description"])

    def test_an_empty_folder_still_offers_the_way_off(self):
        picked = self.cli._quick_pick([])
        self.assertEqual(len(picked["choices"]), 1)
        self.assertIsNone(picked["choices"][0]["files"])


class TestCountedPhrases(unittest.TestCase):
    def test_english_says_one_row_not_one_rows(self):
        self.assertEqual(wording.count("table.row-count", "rows", 1, "en"), "1 row")
        self.assertEqual(wording.count("table.row-count", "rows", 8, "en"), "8 rows")

    def test_vietnamese_does_not_inflect(self):
        self.assertEqual(wording.count("table.plate-count", "maps", 1, "vi"), "1 tấm")
        self.assertEqual(wording.count("table.plate-count", "maps", 9, "vi"), "9 tấm")

    def test_the_thousands_separator_follows_the_conversation(self):
        """A plan reading "70080 rows" beside a warning reading "70,080" is one
        document with two conventions in it."""
        self.assertEqual(wording.count("table.row-count", "rows", 70080, "en"), "70,080 rows")
        self.assertEqual(wording.count("table.row-count", "rows", 70080, "vi"), "70.080 dòng")


if __name__ == "__main__":
    unittest.main()


class TestTheGateRefusesAPlanWithAQuestionStillOpen(unittest.TestCase):
    """Runs ``render`` for real, up to the point where it would draw.

    This is the one line that does the enforcing, and every other test in this
    file works on the pieces around it. The gap it closes was invisible to all
    of them: the code hashes the *settings*, and a defaulted map language reads
    in the plan exactly like a chosen one, so two runs — one with `--language`,
    one without — came back with the identical code. Only comparing the two runs
    against each other showed it.

    Nothing is drawn on either path, so this costs a read and a match, not a
    figure.
    """

    REPO = Path(__file__).resolve().parents[1]

    def setUp(self):
        try:
            import geopandas  # noqa: F401
            import matplotlib  # noqa: F401
        except ImportError:                      # the rule holds; this check cannot run
            self.skipTest("geopandas and matplotlib are needed to reach the gate")
        self.cli = context.cli()
        self.previous = msg.use("vi")

    def tearDown(self):
        msg.use(self.previous)
        # A run that reached the gate writes nothing, which is the point. But
        # this test is also what a broken gate is measured with, and a broken
        # gate does write — so clear up after it rather than leave a folder that
        # would make the next run fail for the wrong reason.
        import shutil
        shutil.rmtree(self.REPO / "output" / self.FOLDER, ignore_errors=True)

    #: never created while the gate holds
    FOLDER = "khong-bao-gio-duoc-tao"

    def render(self, *extra: str) -> dict:
        import contextlib
        import io as _io

        # named because the repository now holds boundaries for more than one
        # country, and a command that does not say which is refused rather than
        # answered by guessing
        argv = ["render", "--project-root", str(self.REPO),
                "--country", "viet-nam",
                "--run-folder", self.FOLDER,
                "--excel", "input/chuong_trinh_hiv_tinh.xlsx",
                "--sheet", "Dữ liệu tỉnh 2026",
                "--admin-level", "province",
                "--province-column", "Tỉnh/thành phố",
                "--map-scope", "national", "--map-type", "choropleth",
                "--value-column", "Tỷ lệ điều trị ARV (%)", *extra]
        args = self.cli.build_parser().parse_args(argv)
        args.chosen_explicitly = self.cli._explicit(argv)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.command_render(args)
        return json.loads(out.getvalue())

    def test_nothing_is_written_while_a_question_is_open(self):
        self.render()
        self.assertFalse((self.REPO / "output" / self.FOLDER).exists())

    def test_no_code_comes_back_at_all(self):
        payload = self.render()
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertIsNone(payload["confirm_code"])
        self.assertEqual([q["item"] for q in payload["must_ask"]],
                         ["language", "layout", "title"])

    def test_the_two_runs_would_otherwise_have_shared_a_code(self):
        """The heart of it, and why the hash alone cannot force a question.

        Answering ``--language`` changes nothing a reader can see: the table
        already read "Tiếng Việt", because that is what the default resolved to.
        Two runs, one asked and one not, therefore hash the same. Only
        ``must_ask`` tells them apart.

        The title is the other kind. Answering it *does* change a row, so the
        rows are compared with that one set aside — the claim here is about the
        settings whose answer is invisible, which is the whole difficulty.
        """
        answered = self.render("--language", "vi", "--layout", "report",
                               "--title", "Một tiêu đề")
        self.assertEqual(answered["must_ask"], [])
        self.assertIsNotNone(answered["confirm_code"])

        def apart(payload):
            return [r["value"] for r in payload["settings"]
                    if "iêu đề" not in r["item"]]

        self.assertEqual(apart(answered), apart(self.render()))

    def test_answering_the_title_does_change_the_table(self):
        """Unlike the language, and deliberately: the person is agreeing to a
        specific set of words on the plate, so the code has to stand for them."""
        titled = self.render("--language", "vi", "--layout", "report",
                             "--title", "Một tiêu đề")
        row = next(r for r in titled["settings"] if "iêu đề bản đồ" in r["item"])
        self.assertEqual(row["value"], "Một tiêu đề")
        self.assertNotIn("note", row)

    def test_the_code_from_the_answered_run_does_not_unlock_the_unanswered_one(self):
        code = self.render("--language", "vi", "--layout", "report",
                           "--title", "Một tiêu đề")["confirm_code"]
        payload = self.render("--confirmed", code)
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertFalse((self.REPO / "output" / self.FOLDER).exists())
