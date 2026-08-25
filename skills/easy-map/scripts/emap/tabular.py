"""Getting a usable table out of a real spreadsheet.

Everything else in this engine assumes a tidy frame: header on the first row,
numbers stored as numbers, every column meaning something. Real workbooks are
not like that. The file that prompted this module has four sheets — one clean
export, one pivot table whose header sits seven rows down, and two that are
empty or nearly so.

Read those with the tidy assumption and nothing fails loudly. The pivot sheet
comes back as twenty columns called ``Unnamed: 2`` … ``Unnamed: 19`` and the
profile cheerfully offers a map option for it. That is the failure mode this
project keeps meeting: a confident answer about something meaningless.

So three questions get answered here, all of them before any analysis starts:
which row is the header, which text columns are really numbers, and whether the
sheet is worth going on with at all.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from . import messages as msg

#: how far down to look for a header. Title blocks and pivot filters are short;
#: past this it is more likely the sheet has no header at all.
MAX_HEADER_SCAN = 15

#: a column pandas had to invent a name for
UNNAMED = re.compile(r"^unnamed:?\s*\d*$", re.I)

#: joins the tiers of a stacked header: "Số ca phát hiện" over "Nam" becomes
#: "Số ca phát hiện - Nam". A plain hyphen, because the result is typed into
#: ``--value-column`` by hand often enough to matter.
HEADER_JOIN = " - "

#: strings that mean "no value", not "zero"
BLANK_TEXT = {"", "-", "--", "—", "n/a", "na", "n.a.", "null", "none", "nan",
              "không có", "khong co", "chưa có", "chua co", "..", "..."}

#: 1.234.567 — dot as a thousands separator, the Vietnamese convention
_VN_THOUSANDS = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")
#: 1,234,567.89 — the English convention
_EN_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
#: 12,5 — decimal comma with no grouping
_DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:      # NaN
        return True
    return str(value).strip().lower() in BLANK_TEXT


def is_unnamed(name: Any) -> bool:
    return bool(UNNAMED.match(str(name).strip()))


# --- merged cells --------------------------------------------------------

def fill_merged(rows: list[list[Any]],
                ranges: Sequence[tuple[int, int, int, int]]) -> list[list[Any]]:
    """Write a merged block's value into every cell the block covers.

    A spreadsheet stores a merged block as one value in the top-left cell and
    nothing anywhere else, so a province written once and merged down over its
    four quarterly rows arrives as one name and three blanks. Blank there means
    "same as above", not "missing" — and the difference is three rows that
    silently fail to match a place name.

    ``ranges`` are ``(row0, col0, row1, col1)``, zero-based and inclusive.
    """
    out = [list(row) for row in rows]
    for r0, c0, r1, c1 in ranges:
        if r0 >= len(out) or c0 >= len(out[r0]):
            continue
        value = out[r0][c0]
        if is_blank(value):
            continue
        for r in range(r0, min(r1, len(out) - 1) + 1):
            for c in range(c0, c1 + 1):
                if c < len(out[r]):
                    out[r][c] = value
    return out


def header_top(start: int, ranges: Sequence[tuple[int, int, int, int]]) -> int:
    """The first row of the header block, given a row somewhere inside it.

    Filling the merges makes the upper tier repeat itself — "Số ca phát hiện"
    lands in two adjacent cells — and the header scorer marks repeats down,
    because on a data row repeats mean a total line. So it picks the *lower*
    tier, and the group name is lost. A row sitting inside a downward merge is
    never the top of a header; walk up until it is.
    """
    while True:
        above = [r0 for r0, _, r1, _ in ranges if r0 < start <= r1]
        if not above:
            return start
        start = min(above)


def header_depth(start: int, ranges: Sequence[tuple[int, int, int, int]]) -> int:
    """How many rows the header occupies, read from the merges themselves.

    A two-tier header is built by merging the single-tier columns down across
    both rows while the grouped column spans sideways across the top one. That
    downward merge is the reliable signal: guessing from cell contents means
    deciding whether "Nam" is a column name or a value, which is exactly the
    judgement that goes wrong.
    """
    depth = 1
    for r0, _, r1, _ in ranges:
        if r0 == start and r1 > r0:
            depth = max(depth, r1 - r0 + 1)
    return depth


def join_header(rows: Sequence[Sequence[Any]], start: int, depth: int) -> list[str]:
    """Column names read down through every tier of the header.

    Repeats collapse, so a column merged down both tiers keeps its single name
    while a grouped one gains its parent: "Số ca phát hiện - Nam".
    """
    width = max((len(rows[r]) for r in range(start, min(start + depth, len(rows)))),
                default=0)
    names: list[str] = []
    for c in range(width):
        parts: list[str] = []
        for r in range(start, min(start + depth, len(rows))):
            row = rows[r]
            value = row[c] if c < len(row) else None
            if is_blank(value):
                continue
            text = str(value).strip()
            if not parts or parts[-1] != text:
                parts.append(text)
        names.append(HEADER_JOIN.join(parts) if parts else f"Unnamed: {c}")
    return names


#: Above this share of self-named columns the sheet is broken, not grouped: a
#: pivot export arrives as twenty columns of ``Unnamed``, and no header on earth
#: groups nine columns in ten under a heading.
UNNAMED_LIMIT = 0.5


def looks_merged(names: Sequence[Any], first_column: Sequence[Any]) -> bool:
    """Whether a sheet is worth re-reading for merged cells.

    Reading merges means loading the workbook without openpyxl's read-only
    mode, which on a 6 MB export costs 67 seconds against 0.02. That price is
    only worth paying when something suggests merges are there:

    * a column pandas had to name itself, sitting **next to** a named one —
      the right-hand half of a header that spans two columns arrives empty;
    * gaps in the first column that sit directly under a filled cell, which is
      what a merged-down block looks like once the merge is gone.

    The "next to a named one" part is what keeps this off pivot sheets. Without
    it the detector fired on three side sheets of one export and spent 220
    seconds finding no merges at all.
    """
    labels = [str(n).strip() for n in names]
    unnamed = [is_unnamed(n) for n in labels]
    if labels and sum(unnamed) and sum(unnamed) / len(labels) < UNNAMED_LIMIT:
        if any(unnamed[i] and not unnamed[i - 1] for i in range(1, len(labels))):
            return True
    values = list(first_column)
    if len(values) < 4:
        return False
    gaps = sum(1 for i, v in enumerate(values)
               if is_blank(v) and i and not is_blank(values[i - 1]))
    trailing = sum(1 for v in values if is_blank(v))
    return gaps >= 2 and trailing / len(values) >= 0.2


# --- more than one table on a sheet ---------------------------------------

#: Blank rows in a row needed before a gap counts as a divider. One blank row
#: is spacing; several is somebody starting a new table underneath.
TABLE_GAP = 2


def table_blocks(rows: Sequence[Sequence[Any]],
                 min_gap: int = TABLE_GAP) -> list[tuple[int, int]]:
    """Row ranges of the separate tables in one sheet, inclusive.

    Somebody appending a second table below the first — a summary, then a
    budget — is common enough to matter, and reading it plainly gives one table
    whose lower half has the wrong columns entirely. This only *finds* them:
    which table the user wants is not a decision to make on their behalf.

    A run of rows counts as a table when it is at least two rows deep and at
    least two columns wide, so a title block above the data is not mistaken for
    a table of its own.
    """
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0
    for i, row in enumerate(rows):
        if all(is_blank(c) for c in row):
            gap += 1
            if start is not None and gap >= min_gap:
                blocks.append((start, i - gap))
                start = None
        else:
            if start is None:
                start = i
            gap = 0
    if start is not None:
        blocks.append((start, len(rows) - 1))
    return [b for b in blocks if _is_table(rows[b[0]:b[1] + 1])]


def _is_table(block: Sequence[Sequence[Any]]) -> bool:
    filled = [r for r in block if any(not is_blank(c) for c in r)]
    if len(filled) < 2:
        return False
    return max(sum(1 for c in r if not is_blank(c)) for r in filled) >= 2


# --- which row is the header? --------------------------------------------

def _looks_like_header(row: Sequence[Any]) -> float:
    """How much this row behaves like a set of column names.

    A header is wide, textual and free of repeats. A data row is just as wide
    but carries numbers; a pivot filter row is two cells and nothing else.
    """
    filled = [c for c in row if not is_blank(c)]
    if len(filled) < 2:
        return 0.0
    texts = [str(c).strip() for c in filled if not isinstance(c, (int, float))]
    unique = len({str(c).strip().lower() for c in filled})

    width = len(filled)
    textiness = len(texts) / len(filled)
    uniqueness = unique / len(filled)
    # a name is a phrase, not a paragraph
    sane_length = sum(1 for t in texts if 1 <= len(t) <= 60) / max(len(texts), 1)
    return width * textiness * uniqueness * sane_length


def header_row(rows: Sequence[Sequence[Any]], max_scan: int = MAX_HEADER_SCAN) -> int:
    """Index of the row holding the column names.

    Returns 0 when nothing scores better, so a tidy sheet is unaffected and an
    empty one does not get a spurious header picked out of blank cells.
    """
    best, best_score = 0, 0.0
    limit = min(len(rows), max_scan)
    for i in range(limit):
        score = _looks_like_header(rows[i])
        # a header needs data under it, not just more header
        if i + 1 >= len(rows) or score <= 0:
            continue
        below = [r for r in rows[i + 1:i + 6] if any(not is_blank(c) for c in r)]
        if not below:
            continue
        if score > best_score * 1.15:        # ties go to the earlier row
            best, best_score = i, score
    return best


# --- numbers wearing a text coat -----------------------------------------

def parse_number(value: Any) -> float | None:
    """A number written by a person, or None.

    Vietnamese groups thousands with a dot and English with a comma, so the same
    string can mean two things; the shape of the whole string decides, never a
    single separator seen on its own.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return None if (isinstance(value, float) and value != value) else float(value)
    if is_blank(value):
        return None
    text = str(value).strip().replace(" ", " ").replace(" ", "")
    text = text.rstrip("%")
    if not text or text in {"-", "+"}:
        return None

    if _VN_THOUSANDS.match(text):
        text = text.replace(".", "").replace(",", ".")
    elif _EN_THOUSANDS.match(text):
        text = text.replace(",", "")
    elif _DECIMAL_COMMA.match(text):
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def numeric_share(values: Sequence[Any]) -> tuple[float, int]:
    """Share of the non-blank cells that are really numbers, and how many."""
    present = [v for v in values if not is_blank(v)]
    if not present:
        return 0.0, 0
    parsed = [v for v in present if parse_number(v) is not None]
    return len(parsed) / len(present), len(parsed)


#: below this, the column is text that happens to contain a few figures
NUMERIC_ENOUGH = 0.9


def coerce_column(values: Sequence[Any]) -> tuple[list[Any], dict[str, Any]] | None:
    """Convert a text column of numbers, or None if it is genuinely text.

    Reports what it did: a column silently turning into numbers is its own kind
    of wrong answer, and the count of cells it could not read is the part worth
    seeing.
    """
    share, count = numeric_share(values)
    if share < NUMERIC_ENOUGH or count == 0:
        return None
    out: list[Any] = []
    unreadable = []
    for v in values:
        if is_blank(v):
            out.append(None)
            continue
        parsed = parse_number(v)
        if parsed is None:
            out.append(None)
            unreadable.append(str(v).strip())
        else:
            out.append(parsed)
    return out, {"cells_changed": count,
                 "unreadable_cells": len(unreadable),
                 "unreadable_examples": sorted(set(unreadable))[:5]}


# --- which column holds place names? --------------------------------------

#: A sample is enough to recognise a place column, and a workbook may hold
#: sheets far too large to read in full just to find out whether it is worth
#: reading at all.
SURVEY_ROWS = 300

#: Share of a column's distinct values that must be real place names. A province
#: column can sit below this and still be right — a programme file holds a dozen
#: provinces plus entries like "_Military Vietnam" that are not places at all.
PROVINCE_SHARE = 0.6

#: The commune bar is far higher, and deliberately so. Vietnam abolished its
#: districts in 2025 and many of them share a name with a commune, so a district
#: column clears a loose bar and every match is then reported as certain — on
#: units that are not the ones the data describes. This is the single threshold
#: for that judgement; the admin-level detector reads it from here rather than
#: keeping its own, because two constants for one decision is how they drift.
COMMUNE_SHARE = 0.85


def place_columns(columns: Sequence[Any], rows: Sequence[Sequence[Any]],
                  province_keys: set[str], commune_keys: set[str],
                  affixes) -> dict[str, Any]:
    """Best province column and best commune column in a sample of rows.

    Judged on distinct values rather than cells: one province repeated ten
    thousand times is one piece of evidence, not ten thousand.
    """
    from . import matching

    best: dict[str, Any] = {"province": None, "commune": None,
                            "province_match": 0.0, "commune_match": 0.0}
    for index, name in enumerate(columns):
        values = {matching.normalize(r[index], affixes) for r in rows
                  if index < len(r) and not is_blank(r[index])}
        values.discard("")
        if not values:
            continue
        province = sum(1 for v in values if v in province_keys) / len(values)
        commune = sum(1 for v in values
                      if v in commune_keys and v not in province_keys) / len(values)
        if province >= PROVINCE_SHARE and province > best["province_match"]:
            best["province"], best["province_match"] = str(name), round(province, 3)
        if commune >= COMMUNE_SHARE and commune > best["commune_match"]:
            best["commune"], best["commune_match"] = str(name), round(commune, 3)
    return best


# --- is this sheet worth going on with? ----------------------------------

def usability(columns: Sequence[Any], row_count: int,
              place_column: str | None) -> dict[str, Any] | None:
    """Why this sheet cannot become a map, or None if it can.

    Answering this is the whole point of the module. A pivot sheet read with the
    wrong header row produces columns named ``Unnamed: 2``…``Unnamed: 19``, and
    without this the profile went on to offer a map option for it.
    """
    names = [str(c) for c in columns]
    unnamed = [n for n in names if is_unnamed(n)]

    if row_count == 0 or not names:
        return {"reason": msg.text("sheet-no-data-rows.reason"),
                "fix": msg.text("sheet-no-data-rows.fix")}
    if names and len(unnamed) / len(names) > 0.5:
        return {
            "reason": msg.text("unnamed-columns.reason", unnamed=len(unnamed),
                              total=len(names), examples=", ".join(unnamed[:4])),
            "fix": msg.text("unnamed-columns.fix"),
            "unnamed_columns": unnamed[:12],
        }
    if not place_column:
        return {
            "reason": msg.text("no-place-column.reason"),
            "fix": msg.text("no-place-column.fix"),
        }
    return None
