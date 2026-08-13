"""The gate that makes the agent stop and show its plan before it draws.

Everything the plan is made of was already decided — the slice, the map type,
the scope, the classification, the language. What was missing is any reason for
the agent to *pause*. SKILL.md has told it to, in plain words, since the first
version; a real Codex run read those words and drew three maps without asking a
single question. Instructions lose to momentum.

So the rule moves into the command. ``render`` without ``--confirmed`` does all
the work except the drawing and hands back a numbered plan plus a short code
derived from that plan. Only that code unlocks the drawing, and it cannot be
guessed or reasoned out — the agent has to run the planning step, put the table
in front of the person, and come back. The same trick already fixed
``--run-folder``: a contract nobody can forget is one the code will not let them.

The code is a hash of the settings, not a nonce, which buys the other half of
the promise. Change the classification after the user agreed and the old code
stops matching, so a changed plan has to be shown again — which is exactly the
rule "đổi xong in lại cả bảng rồi hỏi lần nữa", now enforced rather than
requested.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from . import messages

#: Long enough that a wrong code is never accepted by accident, short enough to
#: read aloud and retype.
LENGTH = 8

STATUS = "chờ_xác_nhận"


def token(settings: dict[str, Any]) -> str:
    """A short code standing for exactly this set of settings.

    Sorted keys and a plain separator, so the same plan always produces the same
    code and a session that re-plans an unchanged request does not churn.
    """
    material = json.dumps(settings, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:LENGTH]


def matches(supplied: str | None, settings: dict[str, Any]) -> bool:
    return bool(supplied) and supplied.strip().lower() == token(settings)


def gate(settings: dict[str, Any], numbered: list[dict[str, Any]],
         warnings: list[dict[str, Any]], must_ask: list[dict[str, Any]],
         command: str, *, language_stated: bool = True) -> dict[str, Any]:
    """What to print instead of drawing, when the plan has not been agreed yet.

    ``numbered`` is the table the agent shows, each row already in plain words
    and carrying its own alternatives where it has any; ``must_ask`` holds the
    questions for the settings that were supposed to come from the person and
    did not, so the agent asks about those rather than about everything.

    Both arrive as finished questions — wording, options, recommendation — for
    one reason. Left to compose its own, an agent writes the flag names back
    into the menu, and the reader is once again asked to choose between
    ``quantile`` and ``natural-breaks``.
    """
    code = token(settings)
    # A code cannot stand for a plan with a question still open in it, so while
    # ``must_ask`` has anything in it no code is issued at all. Saying that here
    # keeps an agent from spending a turn trying the one it was given.
    guidance = messages.text("cổng.trình-bày")
    if must_ask:
        guidance += messages.text("cổng.chưa-hỏi")
    else:
        guidance += messages.text("cổng.khi-đồng-ý", code=code)
    guidance += messages.text("cổng.đổi-thiết-lập")
    if not language_stated:
        # both languages, deliberately: this is the one note whose whole subject
        # is that the engine's idea of the conversation language is a guess
        guidance += "".join(messages.text("cổng.chưa-nêu-ngôn-ngữ", lang)
                            for lang in messages.LANGUAGES)
    return {
        "trạng_thái": STATUS,
        "mã_xác_nhận": None if must_ask else code,
        "phương_án": numbered,
        "phải_hỏi": must_ask,
        "cảnh_báo": warnings,
        "hướng_dẫn": guidance,
        "lệnh_khi_đã_đồng_ý": None if must_ask else f"{command} --confirmed {code}",
    }
