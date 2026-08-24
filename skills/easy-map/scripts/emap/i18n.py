"""Language of the finished map.

Only machine-generated text is translated: the kicker, the auto insight, legend
furniture, the source and method footer, and the north arrow letter.

**Two languages are built in; any language can be printed.** Vietnamese and
English are here because they are the two the warnings are written in and the
two this project was built for. Every string below can be replaced one at a
time by the caller, so a map for a Lao ministry is a matter of passing the
sentences rather than of adding a column to this table — which nobody could
check, and which would go stale the first time a phrase was reworded.

Three things are deliberately **not** translated:

* place names — they come from the shapefile and a Vietnamese toponym stays
  Vietnamese in any language,
* the title, legend title and any user-supplied note — those come from the user
  or from the workbook's own column names,
* the warnings in ``guardrails.py`` — those are spoken to the user in chat, not
  printed on the map, so the agent relays them in whatever language it is
  conversing in.
"""

from __future__ import annotations

from typing import Any

DEFAULT = "vi"
LANGUAGES = ("vi", "en")

#: Strings handed in by the caller, replacing the table below key by key. Set
#: once per run from the command line; read through :func:`t` like any other
#: string, so nothing downstream needs to know it happened.
_OVERRIDES: dict[str, str] = {}


def use(overrides: dict[str, str] | None) -> None:
    _OVERRIDES.clear()
    _OVERRIDES.update(overrides or {})


def overrides() -> dict[str, str]:
    return dict(_OVERRIDES)


def keys() -> list[str]:
    """Every string a caller may replace, for a message that lists them."""
    return sorted(STRINGS[DEFAULT])

#: suffix appended to every output file name, e.g. ``ban-do_vi.png``
def suffix(lang: str) -> str:
    return normalise(lang)


def normalise(lang: str | None) -> str:
    lang = (lang or DEFAULT).strip().lower()
    return lang if lang in LANGUAGES else DEFAULT


STRINGS: dict[str, dict[str, str]] = {
    "vi": {
        "north": "B",
        "no_data": "Chưa có số liệu",
        "kicker_commune": "BẢN ĐỒ CẤP XÃ/PHƯỜNG",
        "kicker_province": "BẢN ĐỒ CẤP TỈNH/THÀNH PHỐ",
        # For a country whose tiers are not called provinces and communes. The
        # folder's own word goes in, because it is the word that country uses.
        "kicker_tier": "BẢN ĐỒ CẤP {tier}",
        # Both separators, named rather than assumed. Vietnamese swaps the pair
        # and a language that does neither can say so.
        "thousands": ".",
        "decimal": ",",
        "scope_national": "toàn quốc",
        "change_legend": "Thay đổi (điểm %)",
        "unit_point": "điểm %",
        "insight_values": "{with_data}/{total} đơn vị có số liệu. Cao nhất là {name} với {value}.",
        "insight_frame": "{total} đơn vị hành chính trong khung bản đồ.",
        "insight_points": "{points} vị trí được chấm theo toạ độ trên nền {total} đơn vị hành chính.",
        "insight_plain": "{with_data}/{total} đơn vị có số liệu.",
        "insight_category": "{with_data}/{total} đơn vị có số liệu. Nhóm phổ biến nhất là {name} ({count} đơn vị).",
        "source": "Nguồn: {file}; ranh giới hành chính từ shapefile của dự án.",
        "method_classes": "Màu chia {classes} nhóm theo {method}.",
        "method_symbol": "Diện tích vòng tròn tỷ lệ với số lượng.",
        "method_aggregate": "Dòng trùng địa danh được gộp bằng {method}.",
        "method_points": "Mỗi chấm là một vị trí theo toạ độ trong bảng dữ liệu.",
        "method_grey": "Đơn vị màu xám là chưa có số liệu, không phải bằng 0.",
        "class_quantile": "phân vị",
        "class_equal-interval": "khoảng đều",
        "class_natural-breaks": "ngắt tự nhiên",
        "agg_sum": "cộng tổng",
        "agg_mean": "trung bình đơn giản",
        "agg_median": "trung vị",
        "agg_max": "lấy giá trị lớn nhất",
        "agg_min": "lấy giá trị nhỏ nhất",
        "agg_mode": "lấy nhóm xuất hiện nhiều nhất",
        "agg_first": "lấy dòng đầu tiên",
        "agg_weighted-mean": "trung bình có trọng số",
        "agg_by": "{method} theo '{column}'",
    },
    "en": {
        "north": "N",
        "no_data": "No data",
        "kicker_commune": "COMMUNE-LEVEL MAP",
        "kicker_province": "PROVINCE-LEVEL MAP",
        "kicker_tier": "{tier}-LEVEL MAP",
        "thousands": ",",
        "decimal": ".",
        "scope_national": "nationwide",
        "change_legend": "Change (percentage points)",
        "unit_point": "pp",
        "insight_values": "{with_data} of {total} units have data. Highest is {name} at {value}.",
        "insight_frame": "{total} administrative units in the map frame.",
        "insight_points": "{points} locations plotted from coordinates over {total} administrative units.",
        "insight_plain": "{with_data} of {total} units have data.",
        "insight_category": "{with_data} of {total} units have data. The most common group is {name} ({count} units).",
        "source": "Source: {file}; administrative boundaries from the project shapefile.",
        "method_classes": "Colour is split into {classes} classes by {method}.",
        "method_symbol": "Circle area is proportional to the count.",
        "method_aggregate": "Rows sharing a place name are combined using {method}.",
        "method_points": "Each dot is one location from the coordinates in the table.",
        "method_grey": "Grey units have no data, which is not the same as zero.",
        "class_quantile": "quantiles",
        "class_equal-interval": "equal intervals",
        "class_natural-breaks": "natural breaks",
        "agg_sum": "a sum",
        "agg_mean": "an unweighted mean",
        "agg_median": "a median",
        "agg_max": "the maximum",
        "agg_min": "the minimum",
        "agg_mode": "the most frequent category",
        "agg_first": "the first row",
        "agg_weighted-mean": "a weighted mean",
        "agg_by": "{method} on '{column}'",
    },
}


def t(lang: str | None, key: str, **fields: Any) -> str:
    """Look up a string: the caller's, then the language's, then Vietnamese."""
    code = normalise(lang)
    text = (_OVERRIDES.get(key) or STRINGS[code].get(key)
            or STRINGS[DEFAULT].get(key) or key)
    return text.format(**fields) if fields else text


#: What the operating system says the user reads, mapped to the two languages
#: the warnings are written in. Anything else is not forced into one of them —
#: it is reported as itself, so the agent can offer the user's own language for
#: the map even when the conversation is in English.
def system_language() -> str | None:
    """The two-letter language the machine is set to, or None."""
    import locale

    try:
        code = (locale.getlocale()[0] or "").strip()
    except Exception:                       # pragma: no cover - platform noise
        code = ""
    if not code:
        import os

        code = (os.environ.get("LANG") or os.environ.get("LC_ALL") or "").strip()
    if not code:
        return None
    # Reported as the machine words it, not squeezed into a two-letter code.
    # Windows answers ``English_United States`` where Linux answers ``en_GB``,
    # and the first two letters of an English language *name* are the ISO code
    # by luck for "English" and "Vietnamese" and by nothing at all for
    # "German", which would come out ``ge``. A readable value the agent can put
    # in a question is worth more here than a code that is sometimes invented.
    code = code.replace("-", "_").split(".")[0]
    return code.split("_")[0].lower() or None


def _same_language(a: str | None, b: str | None) -> bool:
    """Whether two language labels mean the same thing, as far as can be told.

    Compared on the first two letters, which is right for the codes and for the
    two language names this project can act on, and is not claimed to be right
    in general — see :func:`system_language`.
    """
    return bool(a and b and a[:2].lower() == b[:2].lower())


def suggest(country_language: str | None = None) -> dict[str, Any]:
    """Which language to offer for the text on the map, and why.

    Two sources, and they disagree often enough to be worth reporting
    separately: the machine's own setting, and the country whose boundaries are
    being drawn. Somebody writing to me in English very often wants a
    Vietnamese map for a Vietnamese health department, and somebody with a
    Vietnamese laptop may be preparing a map for a regional meeting.

    So this suggests and never decides. Where the two agree there is one
    obvious answer; where they differ, both are named and the user picks. The
    user can also type a language neither of them mentioned — nothing here
    restricts the map's text to the two the warnings use.
    """
    machine = system_language()
    agreed = _same_language(machine, country_language)
    offer = [c for c in (country_language, machine) if c]
    seen, ordered = set(), []
    for code in offer:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return {
        "máy": machine,
        "quốc_gia": country_language,
        "gợi_ý": ordered or [DEFAULT],
        "trùng_nhau": agreed,
        "ghi_chú": ("hệ điều hành và quốc gia của dữ liệu cùng cho một kết quả"
                    if agreed else
                    "hệ điều hành và quốc gia của dữ liệu cho hai kết quả khác nhau"
                    if machine and country_language else
                    "chỉ suy được từ một nguồn"),
    }


def kicker(lang: str | None, admin_level: str, tier: str | None = None) -> str:
    """The line above the title, naming what kind of unit is drawn.

    ``PROVINCE-LEVEL MAP`` above a map of United States counties is not a small
    infelicity: it tells the reader the wrong thing about what they are looking
    at. Where the boundary folder says what the tier is called — ``state``,
    ``judet``, ``district`` — that word is used instead of the role's.
    """
    if tier and tier not in ("province", "commune"):
        return t(lang, "kicker_tier", tier=str(tier).upper())
    return t(lang, "kicker_commune" if admin_level == "commune" else "kicker_province")
