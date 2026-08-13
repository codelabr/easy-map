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

FILL = "màu vùng"
SYMBOL = "vòng tròn"

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

    ``requests``: ``[{"tên": ..., "semantic": ...}, ...]`` in the order the user
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
            rejected.append({**item, "vì_sao": _why_not(item)})

    maps: list[dict[str, Any]] = []
    while fills or symbols:
        fill = fills.pop(0) if fills else None
        symbol = symbols.pop(0) if symbols else None
        maps.append({
            "màu_vùng": fill,
            "vòng_tròn": symbol,
            "loại": map_type(fill, symbol),
            "lý_do": _explain(fill, symbol),
        })

    out: dict[str, Any] = {"bản_đồ": maps, "không_xếp_được": rejected}
    if len(maps) > 1:
        out["vì_sao_tách"] = msg.text("kenh.tach-tam", maps=len(maps))
    return out


def _explain(fill: dict[str, Any] | None, symbol: dict[str, Any] | None) -> list[str]:
    out = []
    if fill:
        out.append(msg.text("kenh.mau-vung", name=fill["tên"], semantic=fill["semantic"]))
    if symbol:
        out.append(msg.text("kenh.vong-tron", name=symbol["tên"]))
    if not fill and symbol:
        out.append(msg.text("kenh.khong-co-mau"))
    return out


def _why_not(item: dict[str, Any]) -> str:
    semantic = item.get("semantic", "")
    if semantic in {sem.TIME, sem.IDENTIFIER, sem.TEXT}:
        return msg.text("kenh.khong-phai-dai-luong", name=item["tên"], semantic=semantic)
    if semantic == sem.COORDINATE:
        return msg.text("kenh.la-toa-do", name=item["tên"])
    return msg.text("kenh.khong-ro-ngu-nghia", name=item["tên"],
                    semantic=semantic or msg.text("kenh.khong-ro"))


def conflicts(requests: Sequence[dict[str, Any]]) -> list[str]:
    """Warnings worth saying out loud before the allocation is accepted."""
    out = []
    fills = [r for r in requests if _channel(r.get("semantic", "")) == FILL]
    symbols = [r for r in requests if _channel(r.get("semantic", "")) == SYMBOL]
    if len(fills) > 1:
        out.append(msg.text("kenh.tranh-mau", count=len(fills),
                            names=", ".join(f"'{r['tên']}'" for r in fills)))
    if len(symbols) > 1:
        out.append(msg.text("kenh.tranh-vong-tron", count=len(symbols),
                            names=", ".join(f"'{r['tên']}'" for r in symbols)))
    categories = [r for r in fills if r["semantic"] == sem.CATEGORY]
    if categories and len(fills) > len(categories):
        out.append(msg.text("kenh.tron-phan-loai"))
    return out


def summary_lines(plan: dict[str, Any]) -> list[str]:
    """One line per map, for the numbered confirmation table."""
    out = []
    for i, item in enumerate(plan["bản_đồ"], 1):
        parts = []
        if item["màu_vùng"]:
            parts.append(msg.text("kenh.dong-mau", name=item["màu_vùng"]["tên"]))
        if item["vòng_tròn"]:
            parts.append(msg.text("kenh.dong-vong-tron", name=item["vòng_tròn"]["tên"]))
        prefix = (msg.text("kenh.dong-tien-to", n=i)
                  if len(plan["bản_đồ"]) > 1 else "")
        out.append(f"{prefix}{item['loại']} — " + ", ".join(parts))
    return out
