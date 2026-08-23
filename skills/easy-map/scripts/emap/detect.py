"""Working out what a boundary file is, from the boundary file.

The engine used to know one answer: the name of a province lives in
``ten_tinh``. That is true of exactly one dataset in the world. This module
replaces the knowing with looking — at the columns, at what is in them, and at
how the two tiers of a country line up against each other.

**Three named schemes, then a general path.** Three sources cover most of what
anyone will drop in, and each announces itself in its column names, so those
three are read directly rather than guessed at. What matters is that the guess
is the *fallback* and not the mechanism: a country whose file matches nothing
still has to work.

**Everything comes back with its evidence.** Not because the JSON needs
decorating, but because the agent has to decide whether to ask. "All 34 of the
finer tier's parent names are known at the coarser tier" is a fact somebody can
act on; "confidence: high" is a mood. Twenty-six of thirty-four is the case
worth stopping for, and only the evidence distinguishes it.

**What is deliberately not done here:** picking the name column by counting
distinct values. It is the first idea everybody has and it is wrong on the
data this project already ships — ``ten_xa`` holds 2,849 distinct names across
3,321 communes while ``ma_xa`` holds 3,321, so the count picks the code every
time. The rules below use what a name *looks like* instead, and lean hardest on
the one piece of evidence a code column cannot fake: matching the other tier.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

#: How sure the reading is. Three words rather than a number, because the
#: number would invite arithmetic on it and there is nothing to compute.
SURE = "chắc chắn"
LIKELY = "khá chắc"
ASK = "phải hỏi"

VIETNAM, GADM, GEOBOUNDARIES, GENERIC = "viet-nam", "gadm", "geoboundaries", "generic"

#: GADM writes this where it has nothing. Verified against gadm41_VNM_1.shp:
#: ``NL_NAME_1`` and ``CC_1`` read "NA" in all 63 rows, ``ISO_1`` in 59. Read as
#: a value it is a two-letter name for sixty-three different provinces.
GADM_NULL = "NA"

#: A name column holds names. These are the shapes a name does not have: all
#: digits, or a code like ``VN-44`` or ``XFA.1_1``.
_CODE = re.compile(r"^[\W\d_]*$|^[A-Z]{1,4}[.\-_][\w.\-]*$")

#: Longer than this and it is prose, not a name. The longest Vietnamese
#: province name is 17 characters; ``quy_mo`` in the same file runs past 90.
_MAX_NAME = 60


def _text_values(gdf, column, limit: int = 400) -> list[str]:
    values = []
    for value in gdf[column].dropna().head(limit):
        if isinstance(value, str):
            values.append(value.strip())
    return values


#: A column of one repeated value is not a column of names. Measured on every
#: real name column to hand — the lowest is GADM's third level at 0.686 across
#: 11,163 units, and Vietnam's communes sit at 0.858 — against the decoys that
#: fooled the first draft of this: a US ``TYPE`` column reading "Land" for all
#: 53 states (0.019), a Canadian ``source`` column holding one URL (0.077), and
#: a ``MONTH_ADM`` column of month names (0.240).
#:
#: This is a floor, not a ranking. Ranking by distinct values is the trap the
#: module docstring warns about and it stays refused; asking a column to hold
#: more than one value before it can be a name column is a different question
#: with a different answer.
_MIN_VARIETY = 0.5

#: Shortest median length a column of names plausibly has. Every real name
#: column measured sits at 8 or above; the codes that survive the variety
#: floor sit at 2 to 4 — ``AR`` for Arkansas, ``05`` for its FIPS code,
#: ``CABC`` for British Columbia.
_NAME_LENGTH = range(5, 31)


def _looks_like_names(values: Sequence[str]) -> float:
    """How much a column reads like place names, between 0 and 1.

    None of these signals decides alone. The values have to be text, vary,
    carry letters, not be codes, and be about the length a place name is. A
    column that does all of that is a name column or a very convincing
    impression of one, and the caller is told how close the runner-up came so
    that a photo finish can become a question instead of a decision.
    """
    if not values:
        return 0.0
    if len(set(values)) / len(values) < _MIN_VARIETY:
        return 0.0
    lengths = sorted(len(v) for v in values)
    median = lengths[len(lengths) // 2]
    if median < 2 or median > _MAX_NAME:
        return 0.0

    lettered = sum(1 for v in values if any(c.isalpha() for c in v))
    coded = sum(1 for v in values if _CODE.match(v))
    spaced = sum(1 for v in values if " " in v)
    nulls = sum(1 for v in values if v == GADM_NULL)

    score = (lettered - coded - nulls) / len(values)
    # A space is weak evidence on its own — "Huế" has none — so it nudges
    # rather than decides, and so does the length.
    score += 0.15 * (spaced / len(values))
    # Length is not a nudge in one direction. Every real name column measured
    # sits between 8 and 11 characters; every code that survives the variety
    # floor sits at 2 to 4. A median under five is therefore strong evidence
    # *against*, and is weighted as such, while being in range is only mild
    # evidence for.
    if median in _NAME_LENGTH:
        score += 0.15
    elif median < _NAME_LENGTH.start:
        score -= 0.45
    else:
        score -= 0.25
    return max(0.0, min(1.0, score))


def _by_name(gdf, wanted: Sequence[str]) -> str | None:
    """The first of ``wanted`` present, matched without regard to case.

    Case-insensitively because the same column is ``NAME`` in a shapefile and
    ``Name`` after a trip through KML, and a reader that knows only one of
    those spellings works on one file and not the other.
    """
    lookup = {str(c).lower(): c for c in gdf.columns}
    return next((lookup[w.lower()] for w in wanted if w.lower() in lookup), None)


def _gadm_level(gdf) -> int | None:
    """Which GADM level this file is, or None if it is not a GADM file.

    Level 0 is the country outline — one feature, and no ``NAME_i`` at all. It
    is not a tier, and the distinction matters: dropped into a tier folder
    beside levels 1 and 2 it has the smallest feature count of the three, so a
    rule that ranks tiers by size would hand the coarsest role to the outline
    of the whole country.
    """
    if _by_name(gdf, ["GID_0"]) is None:
        return None
    levels = [i for i in range(5, 0, -1) if _by_name(gdf, [f"NAME_{i}"])]
    if levels:
        return max(levels)
    return 0 if _by_name(gdf, ["COUNTRY", "NAME_0"]) else None


def identify(gdf) -> dict[str, Any]:
    """What this frame is: which scheme wrote it, and where the names are.

    Returns the name column for the tier itself, the column naming its parent
    where the file carries one, the country if the file says so, and the level
    if the scheme numbers its levels. Never raises: a frame nothing recognises
    comes back on the general path with whatever the columns support, and the
    caller decides whether that is enough to draw.
    """
    columns = [str(c) for c in gdf.columns if c != "geometry"]

    # --- Vietnam ---------------------------------------------------------
    province = _by_name(gdf, ["ten_tinh"])
    commune = _by_name(gdf, ["ten_xa"])
    if province or commune:
        merged = _by_name(gdf, ["sap_nhap"])
        evidence = ", ".join(c for c in (province, commune, merged) if c)
        return {
            "bộ": VIETNAM,
            "độ_tin_cậy": SURE,
            "bằng_chứng": f"có cột {evidence}",
            "cột_tên": commune or province,
            "cột_cha": province if commune else None,
            "quốc_gia": "Việt Nam",
            "cấp": 2 if commune else 1,
            # The merger history is Vietnam's alone. No other source carries a
            # column like it, which is why the crosswalk belongs to this
            # detector rather than to a tier.
            "cột_sáp_nhập": merged,
        }

    # --- GADM ------------------------------------------------------------
    level = _gadm_level(gdf)
    if level is not None:
        country_column = _by_name(gdf, ["COUNTRY", "NAME_0"])
        country = None
        if country_column:
            values = _text_values(gdf, country_column, limit=1)
            country = values[0] if values else None
        if level == 0:
            return {
                "bộ": GADM, "độ_tin_cậy": SURE,
                "bằng_chứng": f"có GID_0 và {country_column or 'COUNTRY'}, "
                              f"không có NAME_1 — đây là đường viền quốc gia",
                "cột_tên": country_column, "cột_cha": None,
                "quốc_gia": country, "cấp": 0, "là_đường_viền_quốc_gia": True,
            }
        return {
            "bộ": GADM, "độ_tin_cậy": SURE,
            "bằng_chứng": f"có GID_0 và NAME_{level}",
            "cột_tên": _by_name(gdf, [f"NAME_{level}"]),
            "cột_cha": _by_name(gdf, [f"NAME_{level - 1}"]) if level > 1 else None,
            "quốc_gia": country, "cấp": level,
            # An unaccented spelling of every name, which is exactly what the
            # matcher builds for itself — worth handing over rather than
            # recomputing.
            "cột_không_dấu": _by_name(gdf, [f"VARNAME_{level}"]),
        }

    # --- geoBoundaries ---------------------------------------------------
    shape_name = _by_name(gdf, ["shapeName"])
    shape_group = _by_name(gdf, ["shapeGroup"])
    if shape_name and shape_group:
        shape_type = _by_name(gdf, ["shapeType"])
        kind = (_text_values(gdf, shape_type, limit=1) or [""])[0] if shape_type else ""
        digits = re.sub(r"\D", "", kind)
        return {
            "bộ": GEOBOUNDARIES, "độ_tin_cậy": SURE,
            "bằng_chứng": f"có shapeName và shapeGroup" + (f", shapeType={kind}" if kind else ""),
            "cột_tên": shape_name, "cột_cha": None,
            "quốc_gia": (_text_values(gdf, shape_group, limit=1) or [None])[0],
            "cấp": int(digits) if digits else None,
        }

    # --- everything else -------------------------------------------------
    scored = sorted(((_looks_like_names(_text_values(gdf, c)), c) for c in columns),
                    reverse=True)
    best = scored[0] if scored else (0.0, None)
    if best[0] <= 0.0:
        return {
            "bộ": GENERIC, "độ_tin_cậy": ASK, "bằng_chứng":
                f"không cột nào đọc như tên địa danh; các cột: {', '.join(columns)}",
            "cột_tên": None, "cột_cha": None, "quốc_gia": None, "cấp": None,
        }
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    clear = best[0] - runner_up
    return {
        "bộ": GENERIC,
        # A clear winner is worth acting on; a photo finish between two text
        # columns is worth a question, because picking wrong here labels every
        # unit on the map with the wrong string and nothing downstream notices.
        "độ_tin_cậy": LIKELY if clear >= 0.25 else ASK,
        "bằng_chứng": f"'{best[1]}' đọc như tên địa danh ({best[0]:.2f}); "
                      f"cột kế tiếp {scored[1][1] if len(scored) > 1 else '-'} "
                      f"({runner_up:.2f})",
        "cột_tên": best[1], "cột_cha": None, "quốc_gia": None, "cấp": None,
    }


def link_tiers(coarse, coarse_reading: dict[str, Any],
               fine, fine_reading: dict[str, Any]) -> dict[str, Any]:
    """Which column of the finer tier names its parent, and how well it fits.

    The one piece of evidence a code column cannot fake. A column that holds
    the coarser tier's own names, on most of its rows, is the parent link —
    whatever it is called and whatever language it is in.

    Where the scheme already said which column it is, this checks that claim
    rather than replacing it: the answer is the same, and a claim that does not
    survive its own check is worth knowing about.
    """
    known = {v.strip() for v in _text_values(coarse, coarse_reading["cột_tên"], 5000)} \
        if coarse_reading.get("cột_tên") else set()
    if not known or fine is None:
        return {"cột_cha": None, "độ_tin_cậy": ASK,
                "bằng_chứng": "không đọc được cột tên của cấp thô"}

    best, best_share = None, 0.0
    for column in (str(c) for c in fine.columns if c != "geometry"):
        values = _text_values(fine, column, 5000)
        if not values:
            continue
        share = sum(1 for v in values if v in known) / len(values)
        if share > best_share:
            best, best_share = column, share

    claimed = fine_reading.get("cột_cha")
    if best_share < 0.5:
        return {
            "cột_cha": claimed, "độ_tin_cậy": ASK,
            "bằng_chứng": f"không cột nào của cấp mịn khớp tên cấp thô quá một nửa "
                          f"(cao nhất {best or '-'} {best_share:.0%})",
        }
    matched = sum(1 for v in _text_values(fine, best, 5000) if v in known)
    total = len(_text_values(fine, best, 5000))
    return {
        "cột_cha": best,
        "độ_tin_cậy": SURE if best_share >= 0.999 else LIKELY,
        "bằng_chứng": f"{matched}/{total} giá trị của '{best}' có trong tập tên "
                      f"cấp thô" + ("" if claimed in (None, best)
                                    else f"; lược đồ khai '{claimed}'"),
    }
