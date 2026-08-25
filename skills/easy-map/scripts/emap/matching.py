"""Matching dataset place names to shapefile features.

The user is never asked for administrative codes. Province names are matched
first, then commune names *inside that province*, which is what stops a commune
called "Tân Hòa" in one province from being joined to the identical name in
another.

Unlike the previous build, every row records *how* it was matched — exact,
normalised, or fuzzy — so a reviewer can look only at the guesses.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any, Iterable, NamedTuple, Sequence

EXACT = "exact"
NORMALISED = "normalised"
#: the normalised name fits more than one real feature — e.g. Hải Phòng has both
#: "Cẩm Giang" and "Cẩm Giàng", which are identical once accents are dropped.
#: Picking either one silently would be a wrong join reported as a certain one.
AMBIGUOUS = "ambiguous"
FUZZY = "fuzzy"
OVERRIDE = "override"
#: the name is a former province folded into a current one by the 2025 merger.
#: This is an administrative fact, not a guess, so it stays high-confidence.
MERGED = "merged"
NONE = "unmatched"

HIGH = "high-confidence"
REVIEW = "needs-review"
UNMATCHED = "unmatched"

#: Longest first. Punctuation is stripped before this runs, so the abbreviated
#: forms are listed bare as well — otherwise "P. Phú Hồ" never loses its "P."
#: and only ever reaches its commune through a fuzzy guess.
_VN_PREFIXES = (
    "thanh pho", "thi tran", "thi xa", "huyen", "phuong", "quan", "tinh", "xa",
    "tp", "tt", "tx", "p", "x", "q", "h",
)

#: English-language datasets write the administrative word at the end instead of
#: the start. PEPFAR's MER export says "Ho Chi Minh City" where the shapefile
#: says "TP. Hồ Chí Minh"; without this the two never meet, and that one name
#: carried half the rows in the file.
_VN_SUFFIXES = ("city", "province", "municipality")

#: A word that joins a type to a name — "Region **of** Ardenne". Stripping the
#: type word alone leaves "of ardenne", which matches nothing.
#:
#: Short and closed on purpose, and **known to be incomplete**: it holds the
#: connectors of the languages this project has data for. A language whose
#: connector is missing loses nothing it had before — the name simply keeps the
#: word, exactly as every name did until now.
_CONNECTORS = ("of", "de", "del", "della", "du", "da", "the")


class Affixes(NamedTuple):
    """The administrative words to strip off a place name before matching.

    Two lists that disagree are the one way this can fail — an index built
    stripping "district" and a lookup that does not will miss every row — so
    the pair travels with the index built from it rather than sitting in a
    module-level default.
    """

    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()


#: Vietnam's own words, named for the country rather than left as the default.
#: A default is how every other country came to be matched against Vietnamese
#: grammar without anything saying so.
VIETNAM = Affixes(prefixes=_VN_PREFIXES, suffixes=_VN_SUFFIXES)

#: Strip nothing. For a country that declares no type words this is the honest
#: reading: the name is the name.
NOTHING = Affixes()

#: Spellings of the one country whose affix list is written here rather than
#: read from its data. Kept beside the list so the two can never disagree, and
#: kept to one country for the same reason the inset table is.
_VIETNAM_NAMES = ("viet nam", "vietnam", "việt nam", "vnm", "vn")


def is_vietnam(name: Any) -> bool:
    """Whether ``VIETNAM`` is the list this country's names should be read with."""
    if not name:
        return False
    text = str(name).strip().lower().replace("-", " ").replace("_", " ")
    return text in _VIETNAM_NAMES


def affixes_from_type_words(words) -> Affixes:
    """The words a boundary file declares for its own administrative types.

    GADM writes them out — ``TYPE_2`` is ``Districtul``, ``ENGTYPE_2`` is
    ``District`` — so the list is read rather than guessed from the names,
    which is the thing the plan ruled out of scope. Each word goes in both
    lists: the file says what the type is called, not which end of a name a
    person writes it on. One table says "Alder District" and the next says
    "District of Alder".
    """
    seen: list[str] = []
    for raw in words:
        word = normalize_plain(raw)
        if word and word not in seen:
            seen.append(word)
    ordered = tuple(sorted(seen, key=len, reverse=True))
    return Affixes(prefixes=ordered, suffixes=ordered)


class Index(dict):
    """A name index that remembers the affixes it was built with.

    Subclassing ``dict`` leaves every reader unchanged; the attribute is what
    makes the invariant structural, so a lookup cannot strip a different set of
    words than the index it is looking into.
    """

    def __init__(self, mapping=(), affixes: Affixes = NOTHING):
        super().__init__(mapping)
        self.affixes = affixes


def deaccent(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower()


def normalize_plain(value: Any) -> str:
    """Accents, case and punctuation only — no administrative words removed."""
    text = deaccent(value)
    # the hyphen goes too: one source writes "Ba Ria-Vung Tau" and the other
    # "Bà Rịa - Vũng Tàu", and keeping it turned an exact match into a guess
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize(value: Any, affixes: Affixes) -> str:
    """The key a name is matched under.

    ``affixes`` has no default. Until now it did — Vietnam's — which is how
    "Alder District" reached the map as a different place from "Alder", and how
    a table of Fictavian districts joined to nothing at all. Every caller now
    says whose administrative words it means.
    """
    text = normalize_plain(value)
    for prefix in affixes.prefixes:
        if text.startswith(prefix + " "):
            text = text[len(prefix) + 1:]
            # "Region of Ardenne": the type word is gone, and the joining word
            # would otherwise stay behind in its place
            for joiner in _CONNECTORS:
                if text.startswith(joiner + " "):
                    text = text[len(joiner) + 1:]
                    break
            break
    for suffix in affixes.suffixes:
        if text.endswith(" " + suffix):
            text = text[: -(len(suffix) + 1)]
            break
    return re.sub(r"\s+", " ", text).strip()


def _ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz

        return float(max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b)))
    except ImportError:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


def build_index(features: Iterable[dict[str, Any]], affixes: Affixes) -> Index:
    """features: dicts with at least ``name`` and ``shape_id``.

    A feature may also carry ``aliases`` — other spellings the boundary file
    gives for the same unit, such as GADM's ``VARNAME_1`` — and each is indexed
    beside the name. That turns "Ba Ria - Vung Tau" from a fuzzy guess into an
    exact hit, and the map still shows the name, never the alias.
    """
    index = Index(affixes=affixes)
    for f in features:
        for spelling in [f["name"], *(f.get("aliases") or [])]:
            key = normalize(spelling, affixes)
            if not key:
                continue
            bucket = index.setdefault(key, [])
            if f not in bucket:
                bucket.append(f)
    return index


def match_one(raw: Any, index: dict[str, list[dict[str, Any]]],
              *, raw_exact: dict[str, dict[str, Any]] | None = None,
              fuzzy_floor: float = 82.0) -> tuple[dict[str, Any] | None, float, str]:
    text = str(raw or "").strip()
    if not text:
        return None, 0.0, NONE
    if raw_exact and text in raw_exact:
        return raw_exact[text], 100.0, EXACT

    key = normalize(text, index.affixes)
    if key in index:
        features = index[key]
        # tell a literal hit apart from one that needed prefix/accent handling,
        # so a reviewer can see which joins involved any interpretation at all
        literal = next((f for f in features if str(f["name"]).strip() == text), None)
        chosen = literal if literal is not None else features[0]
        if chosen.get("merged_from"):
            return chosen, 100.0, MERGED
        if literal is not None:
            return literal, 100.0, EXACT
        if len({str(f["name"]).strip() for f in features}) > 1:
            return features[0], 100.0, AMBIGUOUS
        return features[0], 100.0, NORMALISED

    best, best_score = None, 0.0
    for candidate_key, features in index.items():
        score = _ratio(key, candidate_key)
        if score > best_score:
            best, best_score = features[0], score
    if best is not None and best_score >= fuzzy_floor:
        return best, best_score, FUZZY
    return None, best_score, NONE


def _display_name(feature: dict[str, Any] | None) -> str:
    """The name to show on the map: always the current one, never a former one."""
    if not feature:
        return ""
    return str(feature.get("canonical") or feature["name"]).strip()


def candidates_for(text: Any, index: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Every real name the normalised form of ``text`` could refer to."""
    return sorted({str(f["name"]).strip()
                   for f in index.get(normalize(text, index.affixes), [])})


def status_for(method: str, score: float, secondary: float | None = None) -> str:
    if method == NONE:
        return UNMATCHED
    if method == AMBIGUOUS:
        return REVIEW          # only the user can say which one was meant
    if method in (EXACT, NORMALISED, OVERRIDE, MERGED):
        return HIGH if (secondary is None or secondary >= 90) else REVIEW
    return REVIEW if score < 93 or (secondary is not None and secondary < 90) else HIGH


def review_province(rows: Sequence[dict[str, Any]], province_index) -> list[dict[str, Any]]:
    """rows: [{'province': raw}] -> one record per distinct province name."""
    out, seen = [], {}
    for row in rows:
        raw = row.get("province")
        key = str(raw or "").strip()
        if key in seen:
            seen[key]["row_count"] += 1
            continue
        feature, score, method = match_one(raw, province_index)
        record = {
            "dataset_province": key,
            # an alias entry carries the current province under 'canonical'
            "matched_province": _display_name(feature),
            "province_score": round(score, 1),
            "match_method": method,
            "status": status_for(method, score),
            "shape_id": feature["shape_id"] if feature else "",
            "candidates": ("; ".join(candidates_for(raw, province_index))
                           if method == AMBIGUOUS else ""),
            "row_count": 1,
        }
        seen[key] = record
        out.append(record)
    return out


def review_commune(rows: Sequence[dict[str, Any]], province_index,
                   commune_index_by_province: dict[str, dict[str, list[dict[str, Any]]]],
                   overrides: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """rows: [{'province': raw, 'commune': raw}] -> one record per pair."""
    from . import prefs

    out, seen = [], {}
    overrides = overrides or {}
    for row in rows:
        p_raw = str(row.get("province") or "").strip()
        c_raw = str(row.get("commune") or "").strip()
        key = f"{p_raw}|{c_raw}"
        if key in seen:
            seen[key]["row_count"] += 1
            continue

        p_feature, p_score, p_method = match_one(p_raw, province_index)
        province_name = _display_name(p_feature)

        manual = prefs.override_for(overrides, province_name or p_raw, c_raw)
        if manual:
            record = _commune_record(p_raw, c_raw, province_name, manual["matched_name"],
                                     p_score, 100.0, OVERRIDE, manual["shape_id"])
        elif p_feature is None:
            record = _commune_record(p_raw, c_raw, "", "", p_score, 0.0, NONE, "")
        else:
            index = commune_index_by_province.get(province_name, {})
            c_feature, c_score, c_method = match_one(c_raw, index)
            record = _commune_record(
                p_raw, c_raw, province_name,
                c_feature["name"] if c_feature else "",
                p_score, c_score, c_method,
                c_feature["shape_id"] if c_feature else "",
                candidates_for(c_raw, index) if c_method == AMBIGUOUS else None,
            )
        seen[key] = record
        out.append(record)
    return out


def shape_lookup(review: Sequence[dict[str, Any]], admin_level: str, *,
                 drop_ambiguous: bool = True) -> dict[str, int]:
    """Place name -> shape id, for joining the dataset to the map.

    An ambiguous row does carry a shape id, but it is the first of several
    equally good candidates — the review table needs it to show what would have
    been picked. Joining on it draws a coin flip that the finished map gives no
    sign of, so by default such rows are left out and the unit stays grey.
    """
    lookup: dict[str, int] = {}
    for r in review:
        if str(r.get("shape_id", "")) == "":
            continue
        if drop_ambiguous and r.get("match_method") == AMBIGUOUS:
            continue
        province = str(r["dataset_province"]).strip()
        key = province if admin_level == "province" else \
            f"{province}|{str(r['dataset_commune']).strip()}"
        lookup[key] = int(r["shape_id"])
    return lookup


def _commune_record(p_raw, c_raw, p_name, c_name, p_score, c_score, method, shape_id,
                    candidates: list[str] | None = None):
    return {
        "dataset_province": p_raw,
        "dataset_commune": c_raw,
        "matched_province": p_name,
        "matched_commune": c_name,
        "province_score": round(p_score, 1),
        "commune_score": round(c_score, 1),
        "match_score": round((p_score + c_score) / 2, 1),
        "match_method": method,
        "status": status_for(method, c_score, p_score),
        "shape_id": shape_id,
        "candidates": "; ".join(candidates) if candidates else "",
        "row_count": 1,
    }


def summarize(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(records),
        "high-confidence": sum(1 for r in records if r["status"] == HIGH),
        "needs-review": sum(1 for r in records if r["status"] == REVIEW),
        "unmatched": sum(1 for r in records if r["status"] == UNMATCHED),
        "fuzzy": sum(1 for r in records if r.get("match_method") == FUZZY),
        "ambiguous": sum(1 for r in records if r.get("match_method") == AMBIGUOUS),
        "merged": sum(1 for r in records if r.get("match_method") == MERGED),
    }


def rows_needing_attention(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r["status"] in (REVIEW, UNMATCHED)]
