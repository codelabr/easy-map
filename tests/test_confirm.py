"""The gate that makes the agent stop before it draws.

Written after a real Codex run drew three maps without asking a single question.
SKILL.md had told it to stop, in plain words, since the first version — so the
tests here are not about the wording. They are about the property that survives
an agent in a hurry: without the code there is no picture, and the code cannot
be arrived at except by running the planning step first.
"""

from __future__ import annotations

import re
import unittest

import context  # noqa: F401  (path bootstrap)
from emap import confirm, messages as msg


def plan(**over) -> dict:
    base = {"Dữ liệu": "a.xlsx › sheet S (34 dòng)", "Loại bản đồ": "choropleth",
            "Đo lường": "Tỷ lệ", "Phạm vi": "national — 1 tấm: toàn quốc",
            "Bố cục": "report", "Ngôn ngữ bản đồ": "vi",
            "Phân lớp": "quantile, 5 nhóm", "Nhãn": "both",
            "Tổng hợp": "weighted-mean", "Đầu ra": "PNG 220 dpi"}
    base.update(over)
    return base


class TestTheCodeStandsForOnePlan(unittest.TestCase):
    def test_the_same_plan_always_gives_the_same_code(self):
        """A session that re-plans an unchanged request must not churn."""
        self.assertEqual(confirm.token(plan()), confirm.token(plan()))

    def test_key_order_does_not_change_the_code(self):
        shuffled = dict(reversed(list(plan().items())))
        self.assertEqual(confirm.token(shuffled), confirm.token(plan()))

    def test_changing_any_setting_changes_the_code(self):
        """Agreeing to five classes is not agreeing to three. Every line of the
        table the person read has to be part of what the code stands for."""
        original = confirm.token(plan())
        for field, value in (("Phân lớp", "quantile, 3 nhóm"),
                             ("Ngôn ngữ bản đồ", "en"),
                             ("Bố cục", "banner"),
                             ("Phạm vi", "matched-only — 1 tấm"),
                             ("Nhãn", "off"),
                             ("Đo lường", "Số ca"),
                             ("Đầu ra", "PNG 300 dpi")):
            with self.subTest(field=field):
                self.assertNotEqual(confirm.token(plan(**{field: value})), original)

    def test_the_code_is_short_enough_to_read_aloud(self):
        code = confirm.token(plan())
        self.assertEqual(len(code), confirm.LENGTH)
        self.assertTrue(code.isalnum())


class TestNothingButTheRightCodeOpensTheGate(unittest.TestCase):
    def test_no_code_at_all(self):
        self.assertFalse(confirm.matches(None, plan()))
        self.assertFalse(confirm.matches("", plan()))

    def test_a_plausible_looking_invention(self):
        """The failure mode is an agent that wants to finish, not an attacker."""
        for guess in ("confirmed", "yes", "true", "00000000", "deadbeef", "ok"):
            with self.subTest(guess=guess):
                self.assertFalse(confirm.matches(guess, plan()))

    def test_the_code_from_a_different_plan(self):
        stale = confirm.token(plan(**{"Phân lớp": "quantile, 3 nhóm"}))
        self.assertFalse(confirm.matches(stale, plan()))

    def test_the_right_code_opens_it(self):
        self.assertTrue(confirm.matches(confirm.token(plan()), plan()))

    def test_case_and_stray_spaces_are_forgiven(self):
        """The code travels through a chat and back; a capital letter is not a
        reason to make someone start over."""
        code = confirm.token(plan())
        self.assertTrue(confirm.matches(f"  {code.upper()} ", plan()))


class TestWhatTheAgentIsHandedInstead(unittest.TestCase):
    def setUp(self):
        self.out = confirm.gate(
            plan(), [{"number": 1, "item": "Dữ liệu", "value": "a.xlsx"}],
            [{"id": "low-coverage", "severity": "warning"}], [],
            "python easy_map.py render --excel a.xlsx")

    def test_it_says_plainly_that_nothing_was_drawn(self):
        """An agent skimming the reply must not read it as a finished job."""
        self.assertEqual(self.out["status"], confirm.STATUS)
        self.assertIn("CHƯA VẼ GÌ CẢ", self.out["guidance"])

    def test_it_carries_the_plan_and_the_warnings(self):
        self.assertEqual(len(self.out["settings"]), 1)
        self.assertEqual(len(self.out["warnings"]), 1)
        self.assertEqual(self.out["must_ask"], [])

    def test_the_ready_made_command_carries_the_matching_code(self):
        """Handing back the exact command removes the last excuse for guessing."""
        code = self.out["confirm_code"]
        self.assertTrue(self.out["command_when_agreed"].endswith(f"--confirmed {code}"))
        self.assertTrue(confirm.matches(code, plan()))

    def test_it_tells_the_agent_to_wait_rather_than_to_continue(self):
        self.assertIn("DỪNG LẠI CHỜ TRẢ LỜI", self.out["guidance"])


class TestAPlanWithAQuestionStillOpenGetsNoCode(unittest.TestCase):
    """The hash covers the settings, and a defaulted language reads in the table
    exactly like a chosen one — so the code alone cannot tell whether anybody
    was asked. Without this, an agent takes the code from its own planning run,
    skips the question and draws the default it invented. That is the failure
    the whole gate exists to stop, one level up.
    """

    def setUp(self):
        self.open_question = confirm.gate(
            plan(), [{"number": 1, "item": "Dữ liệu", "value": "a.xlsx"}], [],
            [{"item": "language", "question": "Chữ trên bản đồ in bằng tiếng gì?",
              "choices": [{"value": "vi"}, {"value": "en"}]}],
            "python easy_map.py render --excel a.xlsx")

    def test_no_code_is_issued_at_all(self):
        self.assertIsNone(self.open_question["confirm_code"])
        self.assertIsNone(self.open_question["command_when_agreed"])

    def test_the_reply_says_why_and_what_to_do(self):
        guidance = self.open_question["guidance"]
        self.assertIn("KHÔNG có mã nào dùng được", guidance)
        self.assertIn("must_ask", guidance)
        self.assertNotIn("--confirmed " + confirm.token(plan()), guidance)

    def test_the_same_plan_with_nothing_open_does_get_one(self):
        answered = confirm.gate(plan(), [], [], [], "python easy_map.py render")
        self.assertEqual(answered["confirm_code"], confirm.token(plan()))


class TestTheGuidanceFollowsTheConversation(unittest.TestCase):
    """The instructions the agent reads are the longest text in the reply.

    They used to be Vietnamese whatever language the conversation was, on the
    reasoning that the agent reads them and the person does not. Measured on a
    real ``--messages en`` run: 957 characters of Vietnamese prose, landing in
    front of the agent one step before it wrote to an English speaker. It
    answered in Vietnamese. What survives translation is the JSON key names,
    which stay Vietnamese because the agent has to look them up in the payload.
    """

    #: the keys of the output contract, which appear inside the guidance because
    #: the agent is told which fields to read
    KEYS = ("settings", "note", "must_ask", "choices", "question",
            "label", "description", "recommended")

    ACCENTS = re.compile(
        "[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
        re.I)

    def setUp(self):
        self.previous = msg.current()

    def tearDown(self):
        msg.use(self.previous)

    def guidance(self, lang: str, **over) -> str:
        msg.use(lang)
        return confirm.gate(plan(), [], [], over.pop("must_ask", []),
                            "python easy_map.py render", **over)["guidance"]

    def test_an_english_conversation_gets_english_instructions(self):
        text = self.guidance("en")
        self.assertIn("NOTHING HAS BEEN DRAWN", text)
        self.assertIn("STOP AND WAIT FOR AN ANSWER", text)
        self.assertNotIn("CHƯA VẼ GÌ CẢ", text)

    def test_a_vietnamese_conversation_still_gets_vietnamese(self):
        text = self.guidance("vi")
        self.assertIn("CHƯA VẼ GÌ CẢ", text)
        self.assertIn("DỪNG LẠI CHỜ TRẢ LỜI", text)

    def test_the_only_vietnamese_left_in_english_is_the_field_names(self):
        """The measurement that found the defect, kept as the test.

        Strip the contract's own key names and nothing accented may remain — a
        sentence quietly left untranslated shows up here as a number above zero.
        """
        text = self.guidance("en")
        for key in self.KEYS:
            text = text.replace(key, "")
        self.assertEqual(self.ACCENTS.findall(text), [])

    def test_the_pending_and_agreed_branches_are_translated_too(self):
        """Both halves of the fork, or half the reply reverts."""
        open_q = self.guidance("en", must_ask=[{"item": "language"}])
        self.assertIn("NO code exists", open_q)
        self.assertIn("--confirmed", self.guidance("en"))

    def test_an_unstated_message_language_is_flagged_in_both_languages(self):
        """This one note is about the engine's guess at the conversation being
        untrustworthy, so it cannot be written in the guessed language alone."""
        text = self.guidance("vi", language_stated=False)
        self.assertIn("chạy lại kèm --messages en", text)
        self.assertIn("run again with --messages en", text)

    def test_a_stated_language_gets_no_such_note(self):
        self.assertNotIn("--messages", self.guidance("vi"))


if __name__ == "__main__":
    unittest.main()


class TestTheGuidanceOnlyNamesKeysThatExist(unittest.TestCase):
    """The rule from wave 6, enforced rather than remembered.

    The gate tells the agent which fields to read. A name in that sentence that
    is not a name in that reply sends the agent looking for a key it will never
    find — and inventing is the next thing it does.
    """

    def setUp(self):
        # msg.use sets a module-level language; leaving it set leaks into every
        # test that runs after this one
        self.previous = msg.use(None)

    def tearDown(self):
        msg.use(self.previous)

    def keys_in(self, blob, found=None):
        found = set() if found is None else found
        if isinstance(blob, dict):
            for k, v in blob.items():
                found.add(k)
                self.keys_in(v, found)
        elif isinstance(blob, list):
            for v in blob:
                self.keys_in(v, found)
        return found

    def test_every_quoted_name_is_a_field_of_the_reply(self):
        import re

        from emap import wording

        for lang in msg.LANGUAGES:
            msg.use(lang)
            # a table with a row that can still change, and one open question:
            # the keys the guidance names only exist once those are there
            row = {"number": 1, "item": wording.field("labels", lang),
                   "value": "both", "note": "[chosen by the skill]",
                   **wording.menu("labels", "both", lang)}
            # both kinds of question: one picked from a menu, one written in
            # words. The guidance describes both, so both have to be present or
            # this test flags the half it cannot see.
            in_words = wording.ask_in_words(
                "title", {"columns": ["A", "B"], "place": "Việt Nam",
                          "periods": ["2026"]}, lang)
            reply = confirm.gate(plan(), [row], [],
                                 [wording.menu("layout", "report", lang), in_words],
                                 "python easy_map.py render")
            fields = self.keys_in(reply)
            quoted = set(re.findall(r"'([a-z_]{3,})'", reply["guidance"]))
            missing = sorted(q for q in quoted if q not in fields)
            with self.subTest(lang=lang):
                self.assertEqual(missing, [], f"guidance names {missing}")
