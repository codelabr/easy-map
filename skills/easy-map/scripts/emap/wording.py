"""The plan, in words the reader already has — and the menu to change it by.

A real Codex run stopped at the gate as it was supposed to and then showed a
public-health officer a table whose settings read ``choropleth-symbol``,
``quantile`` and ``weighted-mean``. Stopping is worth nothing if what the person
is asked to agree to is written in the command line's own vocabulary; they can
only say yes, because saying anything else would mean knowing the vocabulary.

So every enumerated value the render command accepts carries a name and one
sentence on what choosing it does, and this module turns a setting into either a
plain row or a ready-made question: the wording, the alternatives, the
recommendation. The agent hands that straight to whatever picker its host offers
instead of inventing the options itself — an agent writing its own menu writes
the same jargon back, one layer up.

The sentences live in :mod:`messages`, not here, so the two languages stay side
by side under one parity test. What lives here is the structure: which values
exist, in what order a menu should offer them, and which settings get a menu at
all.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from . import messages, semantics as sem

#: Every enumerated value ``render`` accepts, in the order a menu should offer
#: them — most reachable alternative first, so a menu capped at three still
#: offers the two worth weighing. ``tests/test_wording.py`` compares these
#: against argparse's own ``choices``: a value added to the parser and not to
#: this table would reach the plan as a raw flag token, which is the whole
#: defect this module exists to remove.
VALUES: dict[str, tuple[str, ...]] = {
    "map_type": ("choropleth-symbol", "choropleth", "graduated-symbol",
                 "categorized", "change", "point", "boundary"),
    "classification": ("quantile", "natural-breaks", "equal-interval"),
    "labels": ("both", "names", "values", "off"),
    "layout": ("report", "banner"),
    "language": ("vi", "en"),
    "formats": ("png", "svg", "both"),
    "map_scope": ("auto", "national", "single-province", "province-series",
                  "matched-only"),
    "aggregate": ("auto", "weighted-mean", "sum", "mean", "median", "max",
                  "min", "mode", "first"),
}

#: Settings whose alternatives are valid whatever the data holds, so a menu can
#: be offered without looking at the columns first.
#:
#: ``aggregate`` and ``map_type`` are deliberately absent. Which of them is
#: right depends on what the column *means*, and a menu offering "cộng dồn"
#: beside a percentage would invite precisely the error ``cong-gop-ty-le``
#: exists to warn about. They are still shown in plain words, and the caller may
#: pass ``among=`` when it has established which alternatives actually apply.
ALWAYS_SAFE = ("language", "layout", "classification", "labels", "formats")

#: Two or three, per the host picker's own guidance: a menu long enough to
#: choose from and short enough to read.
MENU = 3


def label(setting: str, value: str, lang: str | None = None) -> str:
    """The short name of one value, as a person would say it."""
    return messages.text(f"choice.{setting}.{value}.label", lang)


def describe(setting: str, value: str, lang: str | None = None) -> str:
    """One sentence on what choosing this value does to the finished map."""
    return messages.text(f"choice.{setting}.{value}.description", lang)


def field(name: str, lang: str | None = None) -> str:
    """The name of a row in the plan table."""
    return messages.text(f"field.{name}", lang)


def count(key: str, field: str, number: int, lang: str | None = None) -> str:
    """A counted phrase: grouped digits, and the singular where one exists.

    English inflects and Vietnamese does not, so "1 rows" is a defect that can
    only appear on one side of the table — and it has appeared before. The
    thousands separator follows the conversation, like every other number the
    agent relays: a plan reading ``70080 rows`` beside a warning reading
    ``70,080`` is one document with two conventions in it.
    """
    lang = messages.normalise(lang)
    return messages.text(key, lang, singular=(number == 1),
                         **{field: sem.group_digits(number, lang)})


def options(setting: str, current: str | None, lang: str | None = None, *,
            among: Iterable[str] | None = None,
            limit: int = MENU) -> list[dict[str, Any]]:
    """The menu for one setting: what is chosen now, then the alternatives.

    The current value leads and is marked as the recommendation, because it is
    one — the skill picked it from the data. ``among`` narrows the pool to the
    values that apply to this particular table.
    """
    allowed = None if among is None else set(among)
    pool = [v for v in VALUES[setting] if allowed is None or v in allowed]
    ordered = ([current] if current in pool else []) + [v for v in pool if v != current]
    return [{"value": value,
             "label": label(setting, value, lang),
             "description": describe(setting, value, lang),
             "recommended": value == current,
             "flag": f"--{setting.replace('_', '-')} {value}"}
            for value in ordered[:limit]]


def ask(setting: str, current: str | None, lang: str | None = None, *,
        among: Iterable[str] | None = None) -> dict[str, Any]:
    """One question, complete enough to hand to a picker without rewriting it."""
    return {"item": setting,
            "question": messages.text(f"choice.{setting}.question", lang),
            "choices": options(setting, current, lang, among=among)}


def ask_in_words(setting: str, ingredients: dict[str, Any],
                 lang: str | None = None) -> dict[str, Any]:
    """A question with no menu, because its answer is a sentence.

    Every other question here offers two or three values to pick between. A
    title cannot be picked from a list — the engine must not invent one, since
    naming somebody else's figures is the one thing it has no standing to do.
    So it asks, and hands over what it does know: the columns being drawn, the
    place, and the periods. ``choices`` is absent rather than empty, so a caller
    that hands questions to a picker can tell the two kinds apart.
    """
    return {"item": setting,
            "question": messages.text(f"choice.{setting}.question", lang),
            "answered_in_words": True,
            "ingredients": ingredients}


def menu(setting: str, current: str | None, lang: str | None = None, *,
         among: Sequence[str] | None = None) -> dict[str, Any] | None:
    """``ask`` when there is a real choice to make, ``None`` when there is not.

    A question with one answer is not a question; offering it costs the reader
    a decision that has already been taken for them.
    """
    question = ask(setting, current, lang, among=among)
    return question if len(question["choices"]) > 1 else None
