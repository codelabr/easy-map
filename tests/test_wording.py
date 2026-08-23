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
                    text = msg.text(f"chọn.{setting}.câu_hỏi", lang)
                    self.assertTrue(text.strip().endswith("?"), text)

    def test_every_row_of_the_plan_has_a_heading_in_both_languages(self):
        for name in ("dữ-liệu", "lát-dữ-liệu", "loại-bản-đồ", "tô-màu-theo",
                     "vòng-tròn-theo", "phạm-vi", "bố-cục", "ngôn-ngữ",
                     "chia-nhóm", "nhãn", "gộp-dòng", "đầu-ra"):
            for lang in msg.LANGUAGES:
                with self.subTest(name=name, lang=lang):
                    self.assertTrue(wording.field(name, lang).strip())


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
        self.assertEqual(offered[0]["giá_trị"], "natural-breaks")
        self.assertTrue(offered[0]["khuyến_nghị"])
        self.assertFalse(any(o["khuyến_nghị"] for o in offered[1:]))

    def test_it_stays_short_enough_to_read(self):
        for setting in wording.VALUES:
            with self.subTest(setting=setting):
                offered = wording.options(setting, None, "vi")
                self.assertLessEqual(len(offered), wording.MENU)

    def test_a_long_list_still_offers_the_current_value_first(self):
        """``aggregate`` has nine values and a menu holds three; the one in use
        must not be the one that falls off the end."""
        offered = wording.options("aggregate", "first", "vi")
        self.assertEqual(offered[0]["giá_trị"], "first")

    def test_among_narrows_the_pool_to_what_applies(self):
        offered = wording.options("map_scope", "national", "vi",
                                  among=("national", "province-series"))
        self.assertEqual({o["giá_trị"] for o in offered},
                         {"national", "province-series"})

    def test_every_option_carries_the_flag_that_would_set_it(self):
        for option in wording.options("layout", "report", "vi"):
            self.assertEqual(option["cờ"],
                             f"--layout {option['giá_trị']}")

    def test_a_question_with_one_answer_is_not_asked(self):
        self.assertIsNone(wording.menu("map_scope", "national", "vi",
                                       among=("national",)))
        self.assertIsNotNone(wording.menu("layout", "report", "vi"))

    def test_the_menu_follows_the_conversation_language(self):
        previous = msg.use("en")
        try:
            self.assertEqual(wording.options("language", "vi")[0]["nhãn"], "Vietnamese")
            msg.use("vi")
            self.assertEqual(wording.options("language", "vi")[0]["nhãn"], "Tiếng Việt")
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
                    dpi=220, no_html=False, chosen_explicitly=set())
        base.update(over)
        return argparse.Namespace(**base)

    #: distinguishes "the caller said nothing" from "the caller said no classes"
    DEFAULT_BINS = {"classes": 5}

    def plan(self, *, scope="national", prepared=None, method="sum",
             bins=DEFAULT_BINS, value_column="Tỷ lệ", **over):
        return self.cli._plan(self.args(**over), "a.xlsx", [1] * 34, value_column,
                              scope, prepared or [{"tên": "toàn quốc"}], method, bins)

    def rows(self, numbered):
        return {r["mục"]: r for r in numbered}

    def test_no_row_shows_a_flag_value(self):
        _, numbered, _ = self.plan(map_type="choropleth-symbol", symbol_column="Số ca",
                                   method="weighted-mean")
        for row in numbered:
            for token in JARGON:
                with self.subTest(row=row["mục"], token=token):
                    self.assertNotIn(token, row["giá_trị"].lower())

    def test_a_csv_does_not_claim_to_have_a_sheet(self):
        _, numbered, _ = self.plan(sheet=None)
        self.assertNotIn("sheet", self.rows(numbered)["Dữ liệu"]["giá_trị"])

    def test_a_single_national_map_is_not_described_twice(self):
        _, numbered, _ = self.plan(scope="national")
        self.assertEqual(self.rows(numbered)["Phạm vi bản đồ"]["giá_trị"],
                         "Một tấm toàn quốc")

    def test_a_series_names_the_maps_it_will_draw(self):
        _, numbered, _ = self.plan(scope="province-series",
                                   prepared=[{"tên": "Hà Nội"}, {"tên": "Huế"}])
        value = self.rows(numbered)["Phạm vi bản đồ"]["giá_trị"]
        self.assertIn("2 tấm", value)
        self.assertIn("Hà Nội, Huế", value)

    def test_settings_the_skill_chose_are_marked_as_such(self):
        _, numbered, _ = self.plan(chosen_explicitly={"layout"})
        rows = self.rows(numbered)
        self.assertNotIn("ghi_chú", rows["Bố cục"])
        self.assertIn("ghi_chú", rows["Nhãn trên bản đồ"])

    def test_the_headings_follow_the_conversation_language(self):
        msg.use("en")
        _, numbered, _ = self.plan()
        self.assertIn("Map language", self.rows(numbered))

    def test_the_unasked_settings_come_back_as_finished_questions(self):
        _, _, must_ask = self.plan()
        self.assertEqual([q["mục"] for q in must_ask], ["language", "layout"])
        for question in must_ask:
            self.assertTrue(question["câu_hỏi"].endswith("?"))
            self.assertGreaterEqual(len(question["lựa_chọn"]), 2)
            self.assertTrue(question["lựa_chọn"][0]["khuyến_nghị"])

    def test_a_setting_given_on_the_command_line_is_not_asked_about(self):
        _, _, must_ask = self.plan(chosen_explicitly={"language", "layout"})
        self.assertEqual(must_ask, [])

    def test_the_map_type_menu_appears_only_when_both_channels_are_filled(self):
        _, with_both, _ = self.plan(map_type="choropleth-symbol", symbol_column="Số ca")
        self.assertIn("lựa_chọn", self.rows(with_both)["Loại bản đồ"])
        _, fill_only, _ = self.plan(symbol_column=None)
        self.assertNotIn("lựa_chọn", self.rows(fill_only)["Loại bản đồ"])

    def test_no_menu_ever_offers_to_hide_the_units_without_data(self):
        """``matched-only`` turns "we surveyed 12 of 34 provinces" into a
        picture of a country with 12 provinces. It stays reachable by name and
        unreachable by menu."""
        for scope in ("national", "province-series", "single-province"):
            _, numbered, _ = self.plan(scope=scope,
                                       prepared=[{"tên": "Hà Nội"}, {"tên": "Huế"}])
            for row in numbered:
                with self.subTest(scope=scope, row=row["mục"]):
                    self.assertNotIn("matched-only",
                                     [o["giá_trị"] for o in row.get("lựa_chọn", [])])

    def test_the_menu_marks_the_resolved_value_rather_than_the_flag(self):
        """``--map-scope auto`` became a real framing; offering "auto" back as
        the current choice would offer the reader what they already have."""
        _, numbered, _ = self.plan(scope="province-series",
                                   prepared=[{"tên": "Hà Nội"}, {"tên": "Huế"}])
        offered = self.rows(numbered)["Phạm vi bản đồ"]["lựa_chọn"]
        self.assertEqual(offered[0]["giá_trị"], "province-series")
        self.assertTrue(offered[0]["khuyến_nghị"])

    def test_a_plan_with_no_classes_says_so_instead_of_breaking(self):
        _, numbered, _ = self.plan(bins={}, method="n/a")
        rows = self.rows(numbered)
        self.assertEqual(rows["Chia nhóm màu"]["giá_trị"], "không áp dụng")
        self.assertEqual(rows["Gộp dòng trùng"]["giá_trị"], "không áp dụng")

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
        return [{"tệp": "a.xlsx", "sheet": [
                    {"sheet": "Tỉnh", "dùng_được": True, "số_dòng_ước_tính": 34,
                     "cấp_gợi_ý": "province"},
                    {"sheet": "Ghi chú", "dùng_được": False}]},
                {"tệp": "b.xlsx", "sheet": [
                    {"sheet": "Xã", "dùng_được": True, "số_dòng_ước_tính": 1,
                     "cấp_gợi_ý": "commune"}]}]

    def test_only_the_sheets_that_can_become_a_map_are_offered(self):
        picked = self.cli._quick_pick(self.files())
        self.assertEqual([o["sheet"] for o in picked["lựa_chọn"]][:2], ["Tỉnh", "Xã"])

    def test_there_is_always_a_way_off_the_list(self):
        """input/ holds fixtures and other people's work. A menu with no exit
        invites someone to map a table that is not theirs."""
        picked = self.cli._quick_pick(self.files())
        self.assertIsNone(picked["lựa_chọn"][-1]["tệp"])
        self.assertEqual(picked["lựa_chọn"][-1]["số"], len(picked["lựa_chọn"]))

    def test_each_option_says_what_is_in_it(self):
        picked = self.cli._quick_pick(self.files())
        self.assertIn("34 dòng", picked["lựa_chọn"][0]["mô_tả"])
        self.assertIn("xã/phường", picked["lựa_chọn"][1]["mô_tả"])

    def test_an_empty_folder_still_offers_the_way_off(self):
        picked = self.cli._quick_pick([])
        self.assertEqual(len(picked["lựa_chọn"]), 1)
        self.assertIsNone(picked["lựa_chọn"][0]["tệp"])


class TestCountedPhrases(unittest.TestCase):
    def test_english_says_one_row_not_one_rows(self):
        self.assertEqual(wording.count("bảng.số-dòng", "rows", 1, "en"), "1 row")
        self.assertEqual(wording.count("bảng.số-dòng", "rows", 8, "en"), "8 rows")

    def test_vietnamese_does_not_inflect(self):
        self.assertEqual(wording.count("bảng.số-tấm", "maps", 1, "vi"), "1 tấm")
        self.assertEqual(wording.count("bảng.số-tấm", "maps", 9, "vi"), "9 tấm")

    def test_the_thousands_separator_follows_the_conversation(self):
        """A plan reading "70080 rows" beside a warning reading "70,080" is one
        document with two conventions in it."""
        self.assertEqual(wording.count("bảng.số-dòng", "rows", 70080, "en"), "70,080 rows")
        self.assertEqual(wording.count("bảng.số-dòng", "rows", 70080, "vi"), "70.080 dòng")


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
        self.assertEqual(payload["trạng_thái"], "chờ_xác_nhận")
        self.assertIsNone(payload["mã_xác_nhận"])
        self.assertEqual([q["mục"] for q in payload["phải_hỏi"]], ["language", "layout"])

    def test_the_two_runs_would_otherwise_have_shared_a_code(self):
        """The heart of it. Answering the questions changes nothing a reader can
        see in the table, so the hash is identical — which is exactly why the
        hash alone could not be the thing that forces the question."""
        answered = self.render("--language", "vi", "--layout", "report")
        self.assertEqual(answered["phải_hỏi"], [])
        self.assertIsNotNone(answered["mã_xác_nhận"])
        self.assertEqual([r["giá_trị"] for r in answered["phương_án"]],
                         [r["giá_trị"] for r in self.render()["phương_án"]])

    def test_the_code_from_the_answered_run_does_not_unlock_the_unanswered_one(self):
        code = self.render("--language", "vi", "--layout", "report")["mã_xác_nhận"]
        payload = self.render("--confirmed", code)
        self.assertEqual(payload["trạng_thái"], "chờ_xác_nhận")
        self.assertFalse((self.REPO / "output" / self.FOLDER).exists())
