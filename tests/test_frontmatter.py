"""The YAML both assistants read before anything else.

A skill whose frontmatter will not parse is not a skill with a bad description;
it is a skill that does not load. This went unnoticed until it was already in a
public repository, because nothing here had ever read those few lines.

The rule these tests enforce is narrow and mechanical: a plain (unquoted) YAML
scalar may not contain a colon followed by a space, because the parser reads
that as the start of a nested mapping and stops. Prose about a "two-tier local
government model: province and commune" trips it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)

SKILL = Path(context.ENGINE).parent
FRONTMATTER = SKILL / "SKILL.md"
AGENT_CARD = SKILL / "agents" / "openai.yaml"


def frontmatter(path: Path) -> str:
    """The block between the opening and closing `---` of a Markdown file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise AssertionError(f"{path.name} does not open with ---")
    end = text.find("\n---", 3)
    if end == -1:
        raise AssertionError(f"{path.name} never closes its frontmatter")
    return text[3:end]


def plain_scalars(block: str) -> list[tuple[str, str]]:
    """Every top-level ``key: value`` written as a plain scalar.

    Block scalars (``|``, ``>``) and their indented bodies are skipped on
    purpose: a colon inside one of those is ordinary text, which is the whole
    reason for writing it that way.
    """
    found: list[tuple[str, str]] = []
    lines = block.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value[:1] in ("|", ">"):
            # Swallow the indented body that belongs to this block scalar.
            while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
                i += 1
            continue
        found.append((key.strip(), value))
    return found


class TestItParses(unittest.TestCase):
    def test_no_byte_order_mark_in_front_of_the_opening_marker(self):
        """A BOM before `---` hides the frontmatter, and hides it selectively.

        The installer used to introduce one, because `Set-Content -Encoding
        UTF8` writes a mark on Windows PowerShell 5.1. Codex then did not
        register the skill at all while Claude Code stripped the mark and gave
        no sign anything was wrong, so the failure looked like a Codex problem
        rather than an encoding one. An editor saving as "UTF-8 with BOM" would
        do the same to the source.
        """
        for path in (FRONTMATTER, AGENT_CARD):
            head = path.read_bytes()[:3]
            self.assertNotEqual(
                head, b"\xef\xbb\xbf",
                f"{path.name} starts with a UTF-8 byte-order mark; the "
                f"assistant will not see its frontmatter.")

    def test_no_plain_scalar_hides_a_mapping(self):
        """The defect itself: an unquoted value carrying ': '."""
        for name, block in (
            ("SKILL.md", frontmatter(FRONTMATTER)),
            ("agents/openai.yaml", AGENT_CARD.read_text(encoding="utf-8")),
        ):
            for key, value in plain_scalars(block):
                if not value or value[0] in "\"'":
                    continue
                self.assertNotIn(
                    ": ", value,
                    f"{name}: the value of '{key}' is a plain scalar containing "
                    f"': ', which YAML reads as a nested mapping. Quote it, or "
                    f"write it as a > block.")

    def test_a_real_parser_accepts_both(self):
        """Belt and braces, when the library happens to be installed."""
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        for name, block in (
            ("SKILL.md", frontmatter(FRONTMATTER)),
            ("agents/openai.yaml", AGENT_CARD.read_text(encoding="utf-8")),
        ):
            try:
                loaded = yaml.safe_load(block)
            except yaml.YAMLError as exc:  # pragma: no cover - the failure path
                self.fail(f"{name} does not parse: {exc}")
            self.assertIsInstance(loaded, dict, name)


class TestWhatTheAssistantsNeed(unittest.TestCase):
    def test_both_cards_carry_a_name_and_a_description(self):
        for name, block in (
            ("SKILL.md", frontmatter(FRONTMATTER)),
            ("agents/openai.yaml", AGENT_CARD.read_text(encoding="utf-8")),
        ):
            keys = [key for key, _ in plain_scalars(block)]
            block_keys = [
                line.partition(":")[0].strip()
                for line in block.split("\n")
                if line[:1] and not line[:1].isspace() and ":" in line
            ]
            for wanted in ("name", "description"):
                self.assertIn(wanted, keys + block_keys, f"{name} has no '{wanted}'")

    def test_the_name_is_the_folder_it_lives_in(self):
        """Both assistants resolve a skill by its folder, so the two must agree."""
        for name, block in (
            ("SKILL.md", frontmatter(FRONTMATTER)),
            ("agents/openai.yaml", AGENT_CARD.read_text(encoding="utf-8")),
        ):
            declared = dict(plain_scalars(block)).get("name")
            self.assertEqual(declared, SKILL.name, name)


if __name__ == "__main__":
    unittest.main()
