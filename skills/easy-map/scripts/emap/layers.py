"""Assigning variables to the channels a map actually has.

A thematic map carries two quantitative channels and no more: the fill colour of
each area, and the size of a circle drawn on it. That is a cartographic fact
rather than a limit of this engine, and it is what makes "let the user add and
remove columns" a solvable problem instead of an open one — there is no search
space, only an assignment.

The two channels are not interchangeable. Filling areas by a raw count draws
population and land area, because a big province has more of everything; sizing
circles by a percentage says a large circle means a high rate, which it does
not. So each variable's semantic decides its channel, and the engine already
knows every column's semantic.

When more variables are asked for than two channels can hold, the surplus goes
to a second map in the same request rather than being refused: the run folder
and the interactive page already gather several maps behind one picker, so the
reader loses nothing but a glance.
"""

from __future__ import annotations

from typing import Any, Sequence

from . import messages as msg, semantics as sem

FILL = "fill"
SYMBOL = "symbol"

#: Semantics the fill channel can carry honestly. Everything here is already
#: normalised against something — a share, a rate, a class — so two areas of
#: different size stay comparable.
FILL_OK = {sem.PERCENT, sem.RATE_PER, sem.POINT, sem.RATIO, sem.SCORE, sem.CATEGORY}

#: Semantics the circle channel can carry. Counts and money are magnitudes: they
#: belong to a mark whose area grows with them, not to the area of a province.
SYMBOL_OK = {sem.COUNT, sem.MONEY}


def _channel(semantic: str) -> str | None:
    if semantic in FILL_OK:
        return FILL
    if semantic in SYMBOL_OK:
        return SYMBOL
    return None


def map_type(fill: dict[str, Any] | None, symbol: dict[str, Any] | None) -> str:
    if fill and symbol:
        return "choropleth-symbol"
    if fill:
        return "categorized" if fill["semantic"] == sem.CATEGORY else "choropleth"
    if symbol:
        return "graduated-symbol"
    return "boundary"


def allocate(requests: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Lay the requested variables out over as many maps as they need.

    ``requests``: ``[{"name": ..., "semantic": ...}, ...]`` in the order the user
    named them, because when two variables compete for one channel the one asked
    for first wins and the other is the one that moves.
    """
    fills, symbols, rejected = [], [], []
    for item in requests:
        channel = _channel(item.get("semantic", ""))
        if channel == FILL:
            fills.append(item)
        elif channel == SYMBOL:
            symbols.append(item)
        else:
            rejected.append({**item, "why": _why_not(item)})

    maps: list[dict[str, Any]] = []
    while fills or symbols:
        fill = fills.pop(0) if fills else None
        symbol = symbols.pop(0) if symbols else None
        maps.append({
            "fill": fill,
            "symbol": symbol,
            "kind": map_type(fill, symbol),
            "reason": _explain(fill, symbol),
        })

    out: dict[str, Any] = {"maps": maps, "unplaced": rejected}
    if len(maps) > 1:
        out["why_split"] = msg.text("channel.split-plates", maps=len(maps))
    return out


def _explain(fill: dict[str, Any] | None, symbol: dict[str, Any] | None) -> list[str]:
    out = []
    if fill:
        out.append(msg.text("channel.fill", name=fill["name"], semantic=fill["semantic"]))
    if symbol:
        out.append(msg.text("channel.circles", name=symbol["name"]))
    if not fill and symbol:
        out.append(msg.text("channel.no-fill"))
    return out


def _why_not(item: dict[str, Any]) -> str:
    semantic = item.get("semantic", "")
    if semantic in {sem.TIME, sem.IDENTIFIER, sem.TEXT}:
        return msg.text("channel.not-a-quantity", name=item["name"], semantic=semantic)
    if semantic == sem.COORDINATE:
        return msg.text("channel.is-a-coordinate", name=item["name"])
    return msg.text("channel.meaning-unclear", name=item["name"],
                    semantic=semantic or msg.text("channel.unclear"))


def conflicts(requests: Sequence[dict[str, Any]]) -> list[str]:
    """Warnings worth saying out loud before the allocation is accepted."""
    out = []
    fills = [r for r in requests if _channel(r.get("semantic", "")) == FILL]
    symbols = [r for r in requests if _channel(r.get("semantic", "")) == SYMBOL]
    if len(fills) > 1:
        out.append(msg.text("channel.fill-taken", count=len(fills),
                            names=", ".join(f"'{r['name']}'" for r in fills)))
    if len(symbols) > 1:
        out.append(msg.text("channel.circles-taken", count=len(symbols),
                            names=", ".join(f"'{r['name']}'" for r in symbols)))
    categories = [r for r in fills if r["semantic"] == sem.CATEGORY]
    if categories and len(fills) > len(categories):
        out.append(msg.text("channel.category-mixed-with-continuous"))
    return out


def summary_lines(plan: dict[str, Any]) -> list[str]:
    """One line per map, for the numbered confirmation table."""
    out = []
    for i, item in enumerate(plan["maps"], 1):
        parts = []
        if item["fill"]:
            parts.append(msg.text("channel.fill-line", name=item["fill"]["name"]))
        if item["symbol"]:
            parts.append(msg.text("channel.circles-line", name=item["symbol"]["name"]))
        prefix = (msg.text("channel.line-prefix", n=i)
                  if len(plan["maps"]) > 1 else "")
        out.append(f"{prefix}{item['kind']} — " + ", ".join(parts))
    return out
