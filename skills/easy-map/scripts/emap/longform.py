"""Understanding a table where one row is one observation, not one place.

The fixtures this project grew up on are *wide*: a row is a commune and every
measure has its own column, so "what should the map show?" is answered by naming
a column. A real programme export is *long*: one numeric column holds every
value, and what it means is written in the neighbouring category columns. A
PEPFAR MER extract puts 70.000 rows and 23 indicators through a single ``Value``
column.

Read that file with the wide-format assumption and the profile offers to colour
the map by ``Indicator Code`` — which is not a quantity at all. Worse, summing
``Value`` per province across the whole sheet adds a count to itself once per
disaggregation, and the total looks perfectly reasonable.

So the question changes shape. It is no longer "which column" but "which
indicator, in which period, from which disaggregation" — and, before any of
that, "which columns must be pinned down so nothing is counted twice".

Everything here works on plain sequences rather than dataframes: these are the
rules that decide whether a number is honest, and they are worth testing without
a pandas install in the way.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence

from . import messages as msg

#: column names that announce themselves as the single measure
_MEASURE_NAMES = ("value", "giá trị", "gia tri", "amount", "số liệu", "so lieu",
                  "result", "kết quả", "ket qua", "measure")

#: column names that announce themselves as naming *what* was measured
_AXIS_NAMES = ("indicator", "chỉ số", "chi so", "metric", "measure name",
               "tên chỉ tiêu", "ten chi tieu", "chỉ tiêu", "chi tieu")

#: a code-shaped value: TX_CURR, HTS_TST, PREP_NEW
_CODE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+")

#: semantics that can hold the number being measured. Time is excluded on
#: purpose — a fiscal year is numeric and is not a quantity.
MEASURE_SEMANTICS = {"count", "percent", "rate-per-capita", "percentage-point",
                     "money", "ratio", "score"}

#: semantics that can name *what* a row is about. "identifier" belongs here:
#: a column called "Indicator Code" is read as an identifier, and excluding it
#: made the axis search pick a neighbouring column and answer with confidence.
DIMENSION_SEMANTICS = {"category", "identifier", "text"}

#: how a numerator and a denominator are usually written down. Bare "n" and "d"
#: are deliberately absent: pairing two indicators wrongly produces a ratio that
#: is confidently mapped and completely false.
_NUMERATOR = ("num", "numerator", "tử số", "tu so", "tuso")
_DENOMINATOR = ("den", "denominator", "mẫu số", "mau so", "mauso")


#: pandas hands back NaN and the string "nan" for a blank cell, and str(None)
#: is the word "None" — all three have been seen offered as a real choice
_BLANK = {"", "nan", "none", "nat", "null", "<na>"}


def label_of(value: Any) -> str:
    """The value as a choice a person could pick, or '' if there is nothing there."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:      # NaN
        return ""
    text = str(value).strip()
    return "" if text.lower() in _BLANK else text


def _clean(values: Iterable[Any]) -> list[str]:
    return [t for t in (label_of(v) for v in values) if t]


# --- is this long at all? -------------------------------------------------

def looks_long(column_infos: Sequence[dict[str, Any]], row_count: int,
               distinct_places: int) -> dict[str, Any] | None:
    """Evidence that the sheet is long-format, or None.

    The giveaway is arithmetic rather than semantic: a wide table has about one
    row per place, a long one has many, and all of them share a single measure.
    """
    numeric = [c for c in column_infos if c.get("semantic") in MEASURE_SEMANTICS]
    categories = [c for c in column_infos if c.get("semantic") in DIMENSION_SEMANTICS]
    if len(numeric) != 1 or len(categories) < 2 or distinct_places <= 0:
        return None
    per_place = row_count / distinct_places
    if per_place < 3:
        return None
    return {
        "value_column": numeric[0]["column"],
        "row_count": row_count,
        "geographic_units": distinct_places,
        "rows_per_unit": round(per_place, 1),
        "why": msg.text("longform.is-a-long-table", singular=len(categories) == 1,
                           column=numeric[0]["column"],
                           per_place=f"{per_place:.0f}", categories=len(categories)),
    }


def measure_column(column_infos: Sequence[dict[str, Any]]) -> str | None:
    """The one column holding the numbers."""
    named = [c["column"] for c in column_infos
             if str(c["column"]).strip().lower() in _MEASURE_NAMES]
    if named:
        return named[0]
    numeric = [c["column"] for c in column_infos
               if c.get("semantic") in {"count", "percent", "rate-per-capita", "money"}]
    return numeric[0] if len(numeric) == 1 else None


def indicator_axis(column_infos: Sequence[dict[str, Any]],
                   samples: dict[str, Sequence[Any]]) -> str | None:
    """Which category column says *what* each row measures.

    Ranked on three signals rather than one, because a real export may use any
    of them: the column is named for it, its values are written as codes, or it
    simply has the cardinality of an indicator list.
    """
    best, best_score = None, 0
    for info in column_infos:
        if info.get("semantic") not in DIMENSION_SEMANTICS:
            continue
        name = str(info["column"])
        values = _clean(samples.get(name, []))
        if not values:
            continue
        levels = len(set(values))
        score = 0
        if any(hint in name.strip().lower() for hint in _AXIS_NAMES):
            score += 6
        coded = sum(1 for v in set(values) if _CODE.match(v))
        if coded:
            score += 4 if coded >= len(set(values)) * 0.5 else 2
        if 3 <= levels <= 200:
            score += 2
        if score > best_score:
            best, best_score = name, score
    return best if best_score >= 4 else None


# --- what must be pinned down --------------------------------------------

def varying_axes(place_keys: Sequence[Any],
                 axes: dict[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Columns that make one place appear on more than one row.

    Each of these is a way to count the same people twice. Naming them is the
    whole job: an unpinned axis does not raise an error, it quietly inflates a
    total that still looks plausible on the map.
    """
    groups: dict[Any, list[int]] = defaultdict(list)
    for i, key in enumerate(place_keys):
        groups[key].append(i)

    duplicated = {k: idx for k, idx in groups.items() if len(idx) > 1}
    if not duplicated:
        return []

    out = []
    for name, values in axes.items():
        places, extra = 0, 0
        for idx in duplicated.values():
            distinct = {str(values[i]) for i in idx if i < len(values)}
            if len(distinct) > 1:
                places += 1
                extra += len(distinct) - 1
        if places:
            out.append({"column": name, "split_units": places,
                        "extra_values": extra})
    out.sort(key=lambda d: -d["extra_values"])
    return out


#: values that mean "everything above, added up already"
_TOTAL_LIKE = ("total", "(total)", "all", "tổng", "tong", "tất cả", "tat ca",
               "chung", "overall")


def is_total_like(value: Any) -> bool:
    text = str(value or "").strip().strip("()").lower()
    return text in {t.strip("()") for t in _TOTAL_LIKE}


def double_counting_axes(place_keys: Sequence[Any],
                         axes: dict[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """The axes where summing is not merely wide but *wrong*.

    Splitting a province across its sites, or across age bands, is a partition:
    the parts add up to the whole and summing them is the right thing to do.
    An axis that offers a pre-computed total **beside** its detail rows is a
    different animal — add those together and every person is counted twice,
    and the result still looks like a believable number.
    """
    out = []
    for axis in varying_axes(place_keys, axes):
        values = {str(v) for v in axes.get(axis["column"], []) if v is not None}
        totals = sorted(v for v in values if is_total_like(v))
        if totals and len(values) > len(totals):
            out.append({**axis, "total_value": totals,
                        "why": msg.text("longform.totals-and-detail-together",
                                           totals=", ".join(totals))})
    return out


def pin_warning(axes: Sequence[dict[str, Any]], place_count: int) -> str | None:
    """Spoken to the user, so it says what to do rather than what was noticed."""
    if not axes:
        return None
    parts = []
    for axis in axes[:4]:
        reason = axis.get("why")
        parts.append(f"'{axis['column']}'" + (f" ({reason})" if reason else ""))
    return msg.text("longform.needs-pinning", singular=len(axes) == 1,
                    count=len(axes), columns=", ".join(parts),
                    split=axes[0]["split_units"], places=place_count)


# --- which indicators are worth offering ---------------------------------

def indicator_slices(indicators: Sequence[Any], places: Sequence[Any],
                     values: Sequence[Any],
                     periods: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    """One entry per indicator, ranked by how much of the map it can fill."""
    rows: dict[str, dict[str, Any]] = {}
    for i, raw in enumerate(indicators):
        name = label_of(raw)
        if not name:
            continue
        slot = rows.setdefault(name, {"indicator": name, "row_count": 0,
                                      "unit": set(), "period": set(), "total": 0.0})
        slot["row_count"] += 1
        if i < len(places) and places[i] is not None:
            slot["unit"].add(str(places[i]))
        if periods is not None and i < len(periods) and periods[i] is not None:
            slot["period"].add(str(periods[i]))
        if i < len(values):
            try:
                slot["total"] += float(values[i])
            except (TypeError, ValueError):
                pass

    out = []
    for slot in rows.values():
        out.append({
            "indicator": slot["indicator"],
            "row_count": slot["row_count"],
            "units_present": len(slot["unit"]),
            "available_periods": sorted(slot["period"]),
            "raw_total": round(slot["total"], 1),
        })
    out.sort(key=lambda d: (-d["units_present"], -d["row_count"]))
    return out


# --- choosing the slice ---------------------------------------------------

#: two totals within this of each other are treated as the same quantity
SAME_TOTAL = 0.005


def pin_options(values: Sequence[Any], places: Sequence[Any],
                amounts: Sequence[Any]) -> list[dict[str, Any]]:
    """Every value a pin column could take, measured rather than guessed.

    Coverage is what makes a map worth drawing, so that leads; the total comes
    with it because two values that produce the same total are the tell-tale of
    double counting.
    """
    rows: dict[str, dict[str, Any]] = {}
    for i, raw in enumerate(values):
        name = label_of(raw)
        if not name:
            continue
        slot = rows.setdefault(name, {"value": name, "row_count": 0,
                                      "unit": set(), "total": 0.0})
        slot["row_count"] += 1
        if i < len(places) and places[i] is not None:
            slot["unit"].add(str(places[i]))
        if i < len(amounts):
            try:
                slot["total"] += float(amounts[i])
            except (TypeError, ValueError):
                pass

    out = [{"value": s["value"], "row_count": s["row_count"],
            "unit_count": len(s["unit"]), "total": round(s["total"], 1),
            "is_total_row": is_total_like(s["value"])}
           for s in rows.values()]
    out.sort(key=lambda d: (-d["unit_count"], -d["total"]))
    return out


def duplicated_totals(options: Sequence[dict[str, Any]]) -> list[list[str]]:
    """Groups of values that add up to the same thing.

    If '(total)' and 'By Age - Sex' both come to 49.706, they are not two
    populations — they are one population written down twice. Summing across
    them doubles it, and the doubled figure still looks like a caseload.
    """
    groups: list[list[dict[str, Any]]] = []
    for option in sorted(options, key=lambda d: -d["total"]):
        for group in groups:
            head = group[0]["total"]
            if head > 0 and abs(option["total"] - head) / head <= SAME_TOTAL:
                group.append(option)
                break
        else:
            groups.append([option])
    return [[o["value"] for o in g] for g in groups if len(g) > 1]


def recommend_pin(options: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The value to pin, and why — in words the agent can repeat to the user.

    A pre-computed total wins a tie on coverage: it is the publisher's own
    aggregate, so choosing it avoids inheriting whatever the detail rows leave
    out. Otherwise the widest coverage wins, because a pin that empties the map
    is not a safer choice, it is a different failure.
    """
    usable = [o for o in options if o["unit_count"] > 0]
    if not usable:
        return None
    best_cover = max(o["unit_count"] for o in usable)
    tied = [o for o in usable if o["unit_count"] == best_cover]
    totals = [o for o in tied if o["is_total_row"]]
    pick = totals[0] if totals else max(tied, key=lambda o: o["total"])

    if len(usable) == 1:
        why = msg.text("longform.only-one-value")
    elif pick["is_total_row"]:
        why = msg.text("longform.is-a-total-row", units=pick["unit_count"])
    else:
        why = msg.text("longform.covers-the-most-units", units=pick["unit_count"])
    return {**pick, "why": why,
            "alternatives": [o["value"] for o in usable if o["value"] != pick["value"]][:6]}


# --- numerator / denominator pairs ---------------------------------------

def _split_role(name: str) -> tuple[str, str] | None:
    """Trailing "Num"/"Den" and their spellings, including two-word Vietnamese.

    ``"Sàng lọc tử số"`` needs the last *two* tokens, so the tail is grown rather
    than taken from a single separator.
    """
    text = str(name).strip()
    tokens = re.split(r"([ _-])", text)          # keep separators to rebuild the stem
    words = [t for t in tokens if t not in (" ", "_", "-", "")]
    for take in (2, 1):
        if len(words) <= take:
            continue
        role = " ".join(words[-take:]).lower().rstrip(".")
        stem = text
        for _ in range(take):
            stem = re.sub(r"[ _-][^ _-]+$", "", stem)
        if role in _NUMERATOR:
            return stem.strip(), "num"
        if role in _DENOMINATOR:
            return stem.strip(), "den"
    return None


def ratio_pairs(names: Iterable[Any]) -> list[dict[str, str]]:
    """Indicators that only mean something as a fraction of each other.

    TX_PVLS Num over TX_PVLS Den is viral suppression. Mapping either side on
    its own maps programme size, which is very nearly a population map.
    """
    found: dict[str, dict[str, str]] = defaultdict(dict)
    for raw in names:
        split = _split_role(raw)
        if split:
            stem, role = split
            found[stem][role] = str(raw).strip()
    return [{"name": stem, "numerator": roles["num"], "denominator": roles["den"]}
            for stem, roles in sorted(found.items())
            if "num" in roles and "den" in roles]


# --- filters --------------------------------------------------------------

def parse_where(expressions: Sequence[str]) -> list[tuple[str, str]]:
    """``"Quarter=Q2"`` -> ``("Quarter", "Q2")``, keeping spaces inside values."""
    out = []
    for raw in expressions or []:
        text = str(raw)
        if "=" not in text:
            raise ValueError(msg.text("error.where-bad-format", given=repr(raw)))
        column, _, value = text.partition("=")
        column, value = column.strip(), value.strip()
        if not column:
            raise ValueError(msg.text("error.where-missing-column", given=repr(raw)))
        out.append((column, value))
    return out


def describe_filters(pairs: Sequence[tuple[str, str]]) -> str:
    return "; ".join(f"{c} = {v}" for c, v in pairs)


def unknown_values(column: str, wanted: str,
                   present: Sequence[Any]) -> list[str] | None:
    """Nearest real values when a filter matches nothing — a typo costs a whole run."""
    seen = [str(v).strip() for v in present if v is not None]
    if wanted in seen:
        return None
    counts = Counter(seen)
    target = wanted.strip().lower()
    close = [v for v in counts if target and target in v.lower()]
    return (close or [v for v, _ in counts.most_common(8)])[:8]
