"""What a column *means*, in Vietnamese public-health vocabulary.

Getting this right drives three downstream decisions that the previous renderer
got wrong:

* how to aggregate duplicate rows (summing a coverage rate is nonsense),
* how to label legend classes (a count has no decimals; a rate per 100.000 is
  not a percent),
* which column deserves colour and which deserves symbol size.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Iterable, NamedTuple, Sequence

from . import messages as msg

__all__ = ["infer", "denominator", "find_denominator", "format_value",
           "order_categories"]

COUNT = "count"
PERCENT = "percent"
RATE_PER = "rate-per-capita"
POINT = "percentage-point"
MONEY = "money"
RATIO = "ratio"
SCORE = "score"
CATEGORY = "category"
TIME = "time"
IDENTIFIER = "identifier"
TEXT = "text"
COORDINATE = "coordinate"
UNKNOWN = "unknown"

#: semantic -> how duplicate rows for one geography may be combined
AGGREGATION = {
    COUNT: ("sum", ["sum", "mean", "median", "max", "min"]),
    MONEY: ("sum", ["sum", "mean", "median", "max", "min"]),
    PERCENT: ("weighted-mean", ["weighted-mean", "mean", "median", "max", "min"]),
    RATE_PER: ("recompute", ["recompute", "weighted-mean", "mean", "median"]),
    POINT: ("weighted-mean", ["weighted-mean", "mean", "median"]),
    RATIO: ("weighted-mean", ["weighted-mean", "mean", "median"]),
    SCORE: ("mean", ["mean", "median", "max", "min"]),
    CATEGORY: ("mode", ["mode", "first"]),
}

#: semantics that must never be added together
NEVER_SUM = {PERCENT, RATE_PER, POINT, RATIO, SCORE}

_COUNT_WORDS = [
    "so ca", "so nguoi", "so luot", "so mau", "so lieu ca", "so tre", "so ho",
    "so co so", "so diem", "so lieu", "so don vi", "so lan", "so ngay", "so gio",
    "dan so", "so dan", "so luong", "so lieu tiem", "so mui", "so lieu xet nghiem",
    "ca mac", "ca benh", "ca tu vong", "tu vong", "mac moi", "nhiem moi",
    "so tiem", "lieu vac xin", "so vac xin", "so test", "so xet nghiem",
]
_PERCENT_WORDS = [
    "ty le", "tile", "bao phu", "do bao phu", "muc hoan thien", "phan tram",
    "ty le duong tinh", "ty le tiem", "ty le bao phu", "muc do", "dat chi tieu",
]
_RATE_WORDS = ["ty suat", "tren 100", "tren 10", "tren 1.000", "/100.000", "/100000",
               "/1.000", "/1000", "per 100", "moi 100", "tren moi"]
_POINT_WORDS = ["diem %", "diem phan tram", "diem pt", "percentage point", "chenh lech ty le"]
# "dong" alone is not a money word: "đồng nhiễm" (co-infection) deaccents to
# "dong nhiem", and reading that as currency labelled TB/HIV case counts "đồng".
# Currency has to be qualified, or written as a unit in parentheses.
_MONEY_WORDS = ["ngan sach", "chi phi", "kinh phi", "vnd", "usd", "gia tri",
                "doanh thu", "dau tu", "trieu dong", "ty dong", "nghin dong",
                "so tien", "tong tien", "muc chi", "giai ngan"]
_MONEY_UNIT_PATTERN = re.compile(r"[(\[]\s*(vnd|usd|dong|trieu|ty)\s*[)\]]")
_SCORE_WORDS = ["diem so", "chi so", "score", "index", "xep hang", "thu hang"]
#: English spellings matter as much as Vietnamese ones: a PEPFAR export labels
#: its period columns "Fiscal Year" and "Quarter", and reading a four-digit year
#: as a quantity is how a year ends up being summed. None of these collides with
#: another word once the accents are stripped, so they are safe to match on the
#: deaccented name — which matters, because exports are inconsistent about
#: diacritics.
_TIME_WORDS = ["ky bao cao", "thoi gian", "period", "date", "time", "year",
               "quarter", "fiscal", "month", "week", "fy"]

#: Vietnamese period words where the diacritic is the *only* thing separating the
#: period from an unrelated word:
#:
#:     năm  year     nam   male, south      Số ca phát hiện - Nam · Tỉnh Nam Định
#:     quý  quarter  quy   rule, scale      Quy mô dân số
#:     tháng month   thang ladder, scale    Thang điểm đánh giá
#:     ngày day      ngay  straight, at once
#:     tuần week     tuấn  a given name
#:
#: Matching these after deaccenting read six of seventeen test headings as
#: periods, including a province-name column. So they are matched on the name as
#: written, and the bare spelling only counts when the heading carries no
#: diacritics at all — if the writer accents the rest of it, an unaccented "Nam"
#: is not "năm".
_TIME_WORDS_VI = {"năm": "nam", "quý": "quy", "tháng": "thang",
                  "ngày": "ngay", "tuần": "tuan"}

#: What the numbers in such a column have to look like before the name is
#: believed. A heading is a hint; the values are the evidence.
_PERIOD_RANGE = {"nam": (1900, 2100), "quy": (1, 4), "thang": (1, 12),
                 "tuan": (1, 53), "ngay": (1, 31)}
#: ``_has`` matches whole words, so a keyword ending in a separator can never
#: fire: ``"ma "`` compiles to ``(?<!\w)ma\ (?!\w)``, which demands a non-word
#: character *after* the space. Measured: "Mã ĐV", "Mã tỉnh" and "Mã" all fell
#: through to `category` — and a category is mappable, so the skill would offer
#: to colour a map by province code.
_ID_WORDS = ["code", "id", "so hieu", "ky hieu"]

#: "mã" (code) against "má", "mà", "ma" — the same collision as the period words
#: below, handled the same way.
_ID_WORDS_VI = {"mã": "ma"}
_LON_WORDS = ["kinh do", "longitude", "long", "lon", "x_toa do", "toa do x"]
_LAT_WORDS = ["vi do", "latitude", "lat", "y_toa do", "toa do y"]

#: percent column -> words that identify its natural denominator column
_DENOMINATOR_HINTS = {
    "bao phu": ["dan so muc tieu", "muc tieu", "dan so"],
    "duong tinh": ["xet nghiem", "so mau", "tiep can"],
    "tiem": ["dan so muc tieu", "doi tuong", "dan so"],
    "hoan thien": ["so bao cao", "so don vi"],
    "sang loc": ["dan so muc tieu", "doi tuong"],
}


def deaccent(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower().strip()


def _has(haystack: str, words: Iterable[str]) -> bool:
    """Match whole words only, so 'tiến' never counts as 'tiền'."""
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", haystack) for w in words)


def _keyword(column: str, plain: Sequence[str],
             accented: dict[str, str]) -> str | None:
    """Which keyword this heading carries: ``"generic"``, a bare spelling, or none.

    ``plain`` is matched on the deaccented heading, because exports are
    inconsistent about diacritics. ``accented`` holds the words where the
    diacritic is the whole meaning, and those are matched on the heading as
    written — the bare spelling counts only when the heading carries no
    diacritics at all, since a writer who accents the rest of it did not mean
    the other word.
    """
    name = deaccent(column)
    if _has(name, plain):
        return "generic"
    written = str(column or "").lower()
    for marked, bare in accented.items():
        if _has(written, [marked]):
            return bare
    if name == written:
        for marked, bare in accented.items():
            if _has(name, [bare]):
                return bare
    return None


def _time_word(column: str) -> str | None:
    """Which period word this heading carries, or ``None``.

    Returns ``"generic"`` for the unambiguous list and the bare Vietnamese
    spelling otherwise, so the caller knows which range of values to expect.
    """
    return _keyword(column, _TIME_WORDS, _TIME_WORDS_VI)


def _id_word(column: str) -> str | None:
    return _keyword(column, _ID_WORDS, _ID_WORDS_VI)


def _period_values(word: str, nums: Sequence[float]) -> bool:
    """Whether the numbers could be periods of the kind the heading named."""
    lo, hi = _PERIOD_RANGE[word]
    return bool(nums) and all(float(n).is_integer() and lo <= n <= hi for n in nums)


def _numeric(values: Sequence[Any]) -> list[float]:
    out = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isnan(f):
            out.append(f)
    return out


def is_integer_like(values: Sequence[Any]) -> bool:
    nums = _numeric(values)
    return bool(nums) and all(abs(n - round(n)) < 1e-9 for n in nums)


def infer(column: str, values: Sequence[Any], is_numeric: bool) -> dict[str, Any]:
    """Classify one column. Name evidence outranks distribution evidence."""
    name = deaccent(column)
    nums = _numeric(values)
    unique = len({str(v) for v in values if v is not None})

    if not is_numeric:
        if _time_word(column):
            return _pack(TIME, column, msg.text("semantic.time"))
        if _id_word(column):
            return _pack(IDENTIFIER, column, msg.text("semantic.identifier"))
        if 0 < unique <= max(12, len(values) * 0.15):
            return _pack(CATEGORY, column, msg.text("semantic.category"), levels=unique)
        return _pack(TEXT, column, msg.text("semantic.text"))

    # numeric from here
    # The world, not one country. These read ``100 <= abs(v) <= 115`` and
    # ``7 <= abs(v) <= 24`` until the multi-country work: Vietnam's own extent,
    # written into the meaning of the word "longitude". Everywhere else the
    # column was quietly reclassified as a count, so a point map was never
    # offered and nothing said why.
    #
    # The column's *name* still has to say what it is — a bare column of
    # numbers between -180 and 180 is not a longitude — so widening the range
    # loosens the second half of a two-part test, not the whole of it.
    if _has(name, _LON_WORDS) and nums and all(abs(v) <= 180 for v in nums):
        return _pack(COORDINATE, column, msg.text("semantic.longitude"), axis="lon")
    if _has(name, _LAT_WORDS) and nums and all(abs(v) <= 90 for v in nums):
        return _pack(COORDINATE, column, msg.text("semantic.latitude"), axis="lat")
    if _has(name, _POINT_WORDS):
        return _pack(POINT, column, msg.text("semantic.percentage-point"), signed=True)
    if _has(name, _RATE_WORDS) or re.search(r"/\s*\d[\d.,]*\s*dan", name):
        return _pack(RATE_PER, column, _rate_unit(column))
    if _has(name, _MONEY_WORDS) or _MONEY_UNIT_PATTERN.search(name):
        return _pack(MONEY, column, _money_unit(column))
    if _has(name, _PERCENT_WORDS) or "%" in column:
        scale = "unit" if nums and max(nums) <= 1.5 else "percent"
        return _pack(PERCENT, column, msg.text("semantic.percent"), scale=scale)
    if _has(name, _SCORE_WORDS):
        return _pack(SCORE, column, msg.text("semantic.score"))
    # A numeric period column has to look like one. "Số ca mắc trong ngày" does
    # carry the word "ngày", but it is a count of cases qualified by a period,
    # not a period — and a heading that names a quantity outranks one that names
    # a timeframe.
    word = _time_word(column)
    if word and not _has(name, _COUNT_WORDS) and (
            word == "generic" or _period_values(word, nums)):
        return _pack(TIME, column, msg.text("semantic.time"))
    if _has(name, _COUNT_WORDS) or (is_integer_like(values) and nums and min(nums) >= 0):
        return _pack(COUNT, column, msg.text("semantic.count"), integer=True)
    return _pack(UNKNOWN, column, msg.text("semantic.continuous"))


def _rate_unit(column: str) -> str:
    m = re.search(r"/\s*([\d.,]+)", column)
    return (msg.text("semantic.per-capita", per=m.group(1)) if m
            else msg.text("semantic.rate"))


def _money_unit(column: str) -> str:
    name = deaccent(column)
    for token, unit in (("vnd", "VND"), ("usd", "USD"), ("dong", "đồng")):
        if token in name:
            return unit
    return "tiền"


def _pack(semantic: str, column: str, unit: str, **extra: Any) -> dict[str, Any]:
    default, allowed = AGGREGATION.get(semantic, ("mean", ["mean", "median"]))
    out: dict[str, Any] = {
        "column": column,
        "semantic": semantic,
        "unit": unit,
        "integer": extra.pop("integer", False),
        "default_aggregation": default,
        "allowed_aggregation": allowed,
        "safe_to_sum": semantic not in NEVER_SUM,
        "mappable": semantic in {COUNT, PERCENT, RATE_PER, POINT, MONEY, RATIO, SCORE,
                                 CATEGORY, UNKNOWN},
    }
    out.update(extra)
    return out


#: Vietnamese scales that look like plain categories but are actually ordered.
#: Showing these alphabetically ("Cao, Rất cao, Thường quy") misreads the data.
#: Ordered scales, written low to high, accent-stripped. English rows sit
#: beside the Vietnamese ones because the map text can be either and a column
#: of English grades is no more orderable by alphabet than a Vietnamese one:
#: "Good, High, Low, Medium" is what the fallback produces.
ORDINAL_SCALES = [
    ["thuong quy", "rat thap", "thap", "trung binh", "kha", "cao", "rat cao", "khan cap"],
    ["chua dat", "dat", "vuot"],
    ["kem", "yeu", "trung binh", "kha", "tot", "rat tot"],
    ["khong", "mot phan", "toan bo"],
    # how often, and how urgent — both common in programme reporting
    ["khong bao gio", "hiem khi", "thinh thoang", "thuong xuyen", "luon luon"],
    ["thap", "trung binh", "cao", "khan cap"],
    # agreement, the shape most survey exports arrive in
    ["rat khong dong y", "khong dong y", "trung lap", "dong y", "rat dong y"],
    ["routine", "very low", "low", "medium", "high", "very high", "urgent"],
    ["not met", "met", "exceeded"],
    ["poor", "weak", "fair", "good", "very good", "excellent"],
    ["none", "partial", "full"],
    ["never", "rarely", "sometimes", "often", "always"],
    ["strongly disagree", "disagree", "neutral", "agree", "strongly agree"],
]

#: A label that opens with its own rank: ``1. Thấp``, ``2 - Trung bình``,
#: ``A) Kém``. Whoever exported the column already stated the order; reading it
#: off is more reliable than any table of words could be.
_RANKED = re.compile(r"^\s*(\d{1,2}|[a-zA-Z])\s*[.)\-–:]\s*\S")


def _rank(label: str) -> tuple[int, str] | None:
    match = _RANKED.match(str(label))
    if not match:
        return None
    mark = match.group(1)
    return ((int(mark), "") if mark.isdigit()
            else (ord(mark.lower()) - ord("a"), ""))


def order_categories(values: Sequence[Any]) -> list[str] | None:
    """Sort category labels by meaning when they belong to a known ordered scale.

    Returns None for genuinely unordered categories, which then keep their
    alphabetical order and a qualitative palette.
    """
    labels = [str(v) for v in dict.fromkeys(values)]
    if len(labels) < 2:
        return None

    # a rank the exporter wrote into the label itself outranks any guess
    ranks = {label: _rank(label) for label in labels}
    if all(r is not None for r in ranks.values()):
        if len({r[0] for r in ranks.values()}) == len(labels):
            return sorted(labels, key=lambda label: ranks[label][0])

    keys = {label: deaccent(label).strip().lower() for label in labels}
    for scale in ORDINAL_SCALES:
        if all(keys[label] in scale for label in labels):
            return sorted(labels, key=lambda label: scale.index(keys[label]))
    return None


#: words that carry no meaning when comparing one column name to another
_STOPWORDS = {"ty", "le", "suat", "so", "nguoi", "cua", "va", "trong", "tren", "cac",
              "duoc", "dang", "muc", "do", "cong", "chuong", "trinh", "moi", "tai"}


def _tokens(name: str) -> set[str]:
    parts = re.split(r"[^\w]+", deaccent(name))
    return {p for p in parts if p and not p.isdigit() and p not in _STOPWORDS}


def _magnitude(info: dict[str, Any]) -> float:
    for key in (STAT_SUM, STAT_MAX, STAT_MEDIAN):
        value = info.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


#: Keys that ``profile.describe_columns`` attaches to a numeric column. They are
#: defined here and imported there so the producer and the consumers can never
#: drift apart — a silent mismatch once disabled the check below entirely.
STAT_MIN = "min"
STAT_MEDIAN = "median"
STAT_MAX = "max"
STAT_SUM = "total"

#: mean relative error allowed before a numerator/denominator pair is accepted.
#: Row-wise agreement is either near-exact or plainly wrong, so this stays tight;
#: a loose threshold matched unrelated columns by coincidence.
_FIT_TOLERANCE = 0.02


def rate_multiplier(info: dict[str, Any]) -> float:
    """The factor a numerator/denominator ratio is multiplied by to give this rate."""
    semantic = info.get("semantic")
    if semantic == PERCENT:
        return 1.0 if info.get("scale") == "unit" else 100.0
    if semantic == RATE_PER:
        m = re.search(r"([\d][\d.,]*)", str(info.get("unit", "")))
        if m:
            digits = re.sub(r"[.,]", "", m.group(1))
            if digits.isdigit() and int(digits) > 0:
                return float(int(digits))
        return 100_000.0
    return 100.0


def _fit_denominator(rate_info: dict[str, Any] | None, counts: list[dict[str, Any]],
                     series: dict[str, Sequence[Any]]) -> str | None:
    """Find the pair of counts that actually reproduces the rate, row by row.

    Naming is unreliable: a rate is named after its numerator, so word overlap
    picks the wrong column. Arithmetic is reliable — but only row by row.
    Comparing column totals lets unrelated columns agree by coincidence.
    """
    if not rate_info:
        return None
    observed = series.get(rate_info["column"])
    if not observed:
        return None
    scale = rate_multiplier(rate_info)

    best: tuple[float, str] | None = None
    for denominator in counts:
        d_values = series.get(denominator["column"])
        if not d_values:
            continue
        for numerator in counts:
            if numerator["column"] == denominator["column"]:
                continue
            n_values = series.get(numerator["column"])
            if not n_values:
                continue
            errors = []
            for r, n, d in zip(observed, n_values, d_values):
                r, n, d = _as_float(r), _as_float(n), _as_float(d)
                if r is None or n is None or d is None or d <= 0 or r <= 0:
                    continue
                errors.append(abs(n / d * scale - r) / r)
            if len(errors) < max(3, len(observed) * 0.5):
                continue
            score = sum(errors) / len(errors)
            if score <= _FIT_TOLERANCE and (best is None or score < best[0]):
                best = (score, denominator["column"])
    return best[1] if best else None


def _as_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


#: How a weighting column was arrived at. ``FITTED`` means the arithmetic
#: reproduced the rate row by row and the answer is as good as the data.
#: Everything else is a guess from the column's name, and a guess can pick a
#: rate's own **numerator** — measured on real HIV data, four of seven rates
#: were named-matched and two of those took their own numerator as the weight.
FITTED, BY_NAME, BY_HINT, BY_POPULATION, NONE = (
    "fitted", "name", "hint", "population", "none")

#: The bases that were proved rather than guessed. A caller deciding whether to
#: warn asks this rather than listing the guesses, so a basis added later is
#: treated as unproven until somebody says otherwise.
PROVEN = {FITTED}


class Denominator(NamedTuple):
    """The column a rate should be weighted by, and how it was arrived at."""

    column: str | None
    basis: str


def denominator(percent_column: str, candidates: Iterable[dict[str, Any]],
                series: dict[str, Sequence[Any]] | None = None) -> Denominator:
    """Pick the column a rate should be weighted by, and say on what grounds.

    Pass ``series`` — column name to its values — whenever the data is at hand;
    the arithmetic check is far more reliable than anything based on names.

    The basis travels with the answer because the two are not interchangeable:
    a fitted denominator is arithmetic, a named one is a guess about what
    somebody meant by a column heading. Returning only the column made those
    look the same to every caller, and the guess went into the weighted mean
    with nothing said.
    """
    candidates = list(candidates)
    counts = [c for c in candidates if c.get("semantic") == COUNT]
    if not counts:
        return Denominator(None, NONE)

    rate_info = next((c for c in candidates if c.get("column") == percent_column), None)
    if series:
        fitted = _fit_denominator(rate_info, counts, series)
        if fitted:
            return Denominator(fitted, FITTED)

    # naming is only a fallback, and then the largest match wins, because a
    # denominator is never smaller than its own numerator
    target = _tokens(percent_column)
    scored = [(len(target & _tokens(c["column"])), _magnitude(c), c["column"]) for c in counts]
    best_overlap = max(s[0] for s in scored)
    if best_overlap >= 1:
        tier = [s for s in scored if s[0] == best_overlap]
        return Denominator(max(tier, key=lambda s: s[1])[2], BY_NAME)

    name = deaccent(percent_column)
    for trigger, hints in _DENOMINATOR_HINTS.items():
        if trigger not in name:
            continue
        for hint in hints:
            for c in counts:
                if hint in deaccent(c["column"]):
                    return Denominator(c["column"], BY_HINT)
    for c in counts:
        if "dan so" in deaccent(c["column"]):
            return Denominator(c["column"], BY_POPULATION)
    return Denominator(None, NONE)


def find_denominator(percent_column: str, candidates: Iterable[dict[str, Any]],
                     series: dict[str, Sequence[Any]] | None = None) -> str | None:
    """The column alone, for callers that have no use for the grounds."""
    return denominator(percent_column, candidates, series).column


# --- presentation ----------------------------------------------------------
def localise_digits(text: str, lang: str | None = None) -> str:
    """Both digit separators, in the language the map is printed in.

    Python formats in the C convention: comma groups the thousands, dot marks
    the decimal. English keeps that; Vietnamese swaps **both**.

    Swapping only the thousands separator — which is what this module did until
    a Vietnamese map was looked at closely — puts two meanings of the same
    character on one page: the circle legend read "5.576" for a count while the
    colour legend read "89.9%" for a share. A reader who trusts the first
    reading of the dot gets the second number wrong by a factor of a thousand.

    Every number the map prints goes through here, so the convention is decided
    once rather than at each call site.
    """
    from . import i18n

    # Named rather than assumed, so a language that groups with a space or
    # marks the decimal with an apostrophe can say so instead of being sorted
    # into one of two camps.
    thousands = i18n.t(lang, "thousands")
    decimal = i18n.t(lang, "decimal")
    if (thousands, decimal) == (",", "."):
        return text                       # already the convention Python used
    # a placeholder, so the two replacements cannot undo each other
    return (text.replace(",", "\x00").replace(".", decimal)
                .replace("\x00", thousands))


def group_digits(value: float, lang: str | None = None) -> str:
    """A whole number with its thousands grouped for the map's language."""
    return localise_digits(f"{value:,.0f}", lang)


def format_value(value: float | None, info: dict[str, Any], decimals: int | None = None,
                 lang: str | None = None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    if isinstance(value, str):        # categories carry their own label
        return value
    semantic = info.get("semantic", UNKNOWN)
    if semantic == COUNT:
        return group_digits(value, lang)
    if semantic == MONEY:
        return f"{group_digits(value, lang)} {info.get('unit', '')}".strip()
    if semantic == PERCENT:
        v = value * 100 if info.get("scale") == "unit" else value
        d = 1 if decimals is None else decimals
        return localise_digits(f"{v:.{d}f}%".replace(".0%", "%"), lang)
    if semantic == POINT:
        from . import i18n

        d = 1 if decimals is None else decimals
        text = f"{value:+.{d}f}"
        if float(text) == 0:          # never print "-0"
            text = f"{0:.{d}f}"
        # localise last: float() above needs the C convention it was written in
        return localise_digits(f"{text} {i18n.t(lang, 'unit_point')}", lang)
    if semantic == RATE_PER:
        d = 1 if decimals is None else decimals
        return localise_digits(f"{value:,.{d}f}", lang)
    d = 1 if decimals is None else decimals
    text = f"{value:,.{d}f}"
    if "." in text:      # trailing zeros exist only after a point; 1200 keeps its own
        text = text.rstrip("0").rstrip(".")
    return localise_digits(text, lang)


def axis_suffix(info: dict[str, Any]) -> str:
    """Short unit shown once in the legend heading rather than on every class.

    Written, and then wired to nothing for a long time. Measured on real
    labels: a percentage legend reads ``1%–6%``, ``6%–10%`` — the sign eight
    times over four classes, which is only clutter. A rate legend reads
    ``3–12``, ``12–25`` with **no unit at all**, so the reader cannot tell
    whether those are cases per hundred thousand or anything else, and the
    engine held the answer the whole time.
    """
    semantic = info.get("semantic")
    if semantic == PERCENT:
        return "%"
    if semantic == RATE_PER:
        return info.get("unit", "")
    if semantic == MONEY:
        return info.get("unit", "")
    return ""


def adds_something(unit: str, heading: str) -> bool:
    """Whether printing ``unit`` after ``heading`` tells the reader anything new.

    Compared word by word, not as strings. The first version tested whether the
    unit appeared verbatim in the heading and produced, on real data,
    ``Tỷ suất ca mới/100.000 dân (trên 100.000 dân)`` — the same fact twice,
    because one says "/100.000 dân" and the other "trên 100.000 dân". The words
    are what carry the meaning; the punctuation between them does not.

    Digits are compared separately: ``_tokens`` drops them, and a rate per
    hundred thousand differs from a rate per thousand by nothing else.
    """
    words = _tokens(unit) - _tokens(heading)
    numbers = set(re.findall(r"\d+", deaccent(unit)))
    numbers -= set(re.findall(r"\d+", deaccent(heading)))
    return bool(words or numbers)


def heading_unit(info: dict[str, Any]) -> str:
    """The unit a legend heading should carry because its labels do not.

    Only the units that go missing from the labels. ``%`` is left out on
    purpose: it sits against its number without a space and reads as part of
    it, so repeating it costs a reader nothing and moving it would change every
    percentage map already in circulation. A rate has no such mark — its labels
    are bare numbers — and that is the gap worth closing.
    """
    if info.get("semantic") != RATE_PER:
        return ""
    return axis_suffix(info).strip()
