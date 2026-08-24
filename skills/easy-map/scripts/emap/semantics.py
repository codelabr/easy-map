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
from typing import Any, Iterable, Sequence

from . import messages as msg

__all__ = ["infer", "find_denominator", "format_value", "order_categories"]

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
            return _pack(TIME, column, msg.text("y-nghia.thời-gian"))
        if _id_word(column):
            return _pack(IDENTIFIER, column, msg.text("y-nghia.mã-định-danh"))
        if 0 < unique <= max(12, len(values) * 0.15):
            return _pack(CATEGORY, column, msg.text("y-nghia.phân-loại"), levels=unique)
        return _pack(TEXT, column, msg.text("y-nghia.văn-bản"))

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
        return _pack(COORDINATE, column, msg.text("y-nghia.kinh-độ"), axis="lon")
    if _has(name, _LAT_WORDS) and nums and all(abs(v) <= 90 for v in nums):
        return _pack(COORDINATE, column, msg.text("y-nghia.vĩ-độ"), axis="lat")
    if _has(name, _POINT_WORDS):
        return _pack(POINT, column, msg.text("y-nghia.điểm-phần-trăm"), signed=True)
    if _has(name, _RATE_WORDS) or re.search(r"/\s*\d[\d.,]*\s*dan", name):
        return _pack(RATE_PER, column, _rate_unit(column))
    if _has(name, _MONEY_WORDS) or _MONEY_UNIT_PATTERN.search(name):
        return _pack(MONEY, column, _money_unit(column))
    if _has(name, _PERCENT_WORDS) or "%" in column:
        scale = "unit" if nums and max(nums) <= 1.5 else "percent"
        return _pack(PERCENT, column, msg.text("y-nghia.phần-trăm"), scale=scale)
    if _has(name, _SCORE_WORDS):
        return _pack(SCORE, column, msg.text("y-nghia.chỉ-số"))
    # A numeric period column has to look like one. "Số ca mắc trong ngày" does
    # carry the word "ngày", but it is a count of cases qualified by a period,
    # not a period — and a heading that names a quantity outranks one that names
    # a timeframe.
    word = _time_word(column)
    if word and not _has(name, _COUNT_WORDS) and (
            word == "generic" or _period_values(word, nums)):
        return _pack(TIME, column, msg.text("y-nghia.thời-gian"))
    if _has(name, _COUNT_WORDS) or (is_integer_like(values) and nums and min(nums) >= 0):
        return _pack(COUNT, column, msg.text("y-nghia.số-đếm"), integer=True)
    return _pack(UNKNOWN, column, msg.text("y-nghia.liên-tục"))


def _rate_unit(column: str) -> str:
    m = re.search(r"/\s*([\d.,]+)", column)
    return (msg.text("y-nghia.trên-dân", per=m.group(1)) if m
            else msg.text("y-nghia.tỷ-suất"))


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
ORDINAL_SCALES = [
    ["thuong quy", "rat thap", "thap", "trung binh", "kha", "cao", "rat cao", "khan cap"],
    ["chua dat", "dat", "vuot"],
    ["kem", "yeu", "trung binh", "kha", "tot", "rat tot"],
    ["khong", "mot phan", "toan bo"],
]


def order_categories(values: Sequence[Any]) -> list[str] | None:
    """Sort category labels by meaning when they belong to a known ordered scale.

    Returns None for genuinely unordered categories, which then keep their
    alphabetical order and a qualitative palette.
    """
    labels = [str(v) for v in dict.fromkeys(values)]
    if len(labels) < 2:
        return None
    keys = {label: deaccent(label).strip() for label in labels}
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
STAT_MIN = "nhỏ_nhất"
STAT_MEDIAN = "trung_vị"
STAT_MAX = "lớn_nhất"
STAT_SUM = "tổng"

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


def find_denominator(percent_column: str, candidates: Iterable[dict[str, Any]],
                     series: dict[str, Sequence[Any]] | None = None) -> str | None:
    """Pick the column a rate should be weighted by, so means stay honest.

    Pass ``series`` — column name to its values — whenever the data is at hand;
    the arithmetic check is far more reliable than anything based on names.
    """
    candidates = list(candidates)
    counts = [c for c in candidates if c.get("semantic") == COUNT]
    if not counts:
        return None

    rate_info = next((c for c in candidates if c.get("column") == percent_column), None)
    if series:
        fitted = _fit_denominator(rate_info, counts, series)
        if fitted:
            return fitted

    # naming is only a fallback, and then the largest match wins, because a
    # denominator is never smaller than its own numerator
    target = _tokens(percent_column)
    scored = [(len(target & _tokens(c["column"])), _magnitude(c), c["column"]) for c in counts]
    best_overlap = max(s[0] for s in scored)
    if best_overlap >= 1:
        tier = [s for s in scored if s[0] == best_overlap]
        return max(tier, key=lambda s: s[1])[2]

    name = deaccent(percent_column)
    for trigger, hints in _DENOMINATOR_HINTS.items():
        if trigger not in name:
            continue
        for hint in hints:
            for c in counts:
                if hint in deaccent(c["column"]):
                    return c["column"]
    for c in counts:
        if "dan so" in deaccent(c["column"]):
            return c["column"]
    return None


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
    """Short unit shown once in the legend heading rather than on every class."""
    semantic = info.get("semantic")
    if semantic == PERCENT:
        return "%"
    if semantic == RATE_PER:
        return info.get("unit", "")
    if semantic == MONEY:
        return info.get("unit", "")
    return ""
