"""Evidence about a dataset, written for an agent that must reason like an analyst.

This module deliberately does *not* decide for the user. It reports what each
column appears to be, how complete it is, which columns look like places, and
which map options the evidence supports — each with a one-sentence reason in
plain Vietnamese that a non-technical reader can follow.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from . import guardrails, matching, messages as msg, semantics as sem


def _series_values(series) -> list[Any]:
    return [v for v in series.tolist() if v is not None and not _isnan(v)]


def _isnan(v: Any) -> bool:
    return isinstance(v, float) and math.isnan(v)


def describe_columns(deps, df, dictionary: dict[str, str] | None = None) -> list[dict[str, Any]]:
    out = []
    total = len(df)
    for column in df.columns:
        series = df[column]
        values = _series_values(series)
        is_numeric = bool(deps.pd.api.types.is_numeric_dtype(series))
        info = sem.infer(column, values, is_numeric)
        info["missing"] = round(1 - len(values) / total, 4) if total else 1.0
        info["distinct_values"] = len({str(v) for v in values})
        info["examples"] = [str(v) for v in values[:4]]
        if is_numeric and values:
            nums = sorted(float(v) for v in values)
            info[sem.STAT_MIN] = nums[0]
            info[sem.STAT_MEDIAN] = nums[len(nums) // 2]
            info[sem.STAT_MAX] = nums[-1]
            info[sem.STAT_SUM] = sum(nums)
        if dictionary and column in dictionary:
            info["dictionary_description"] = dictionary[column]
            info["semantic_source"] = msg.text("semantic-source.data-dictionary")
        else:
            info["semantic_source"] = msg.text("semantic-source.inferred")
        out.append(info)
    return out


def location_candidates(df, columns: Sequence[dict[str, Any]], province_names: Sequence[str],
                        commune_names: Sequence[str],
                        affixes=None) -> dict[str, list[dict[str, Any]]]:
    """Score text columns by how many of their values exist in the shapefile."""
    affixes = affixes if affixes is not None else matching.NOTHING
    provinces = {matching.normalize(n, affixes) for n in province_names}
    communes = {matching.normalize(n, affixes) for n in commune_names}
    result: dict[str, list[dict[str, Any]]] = {"province": [], "commune": []}

    for info in columns:
        if info["semantic"] in {sem.COUNT, sem.PERCENT, sem.RATE_PER, sem.MONEY,
                                sem.POINT, sem.COORDINATE}:
            continue
        values = [str(v) for v in df[info["column"]].tolist() if v is not None and not _isnan(v)]
        if not values:
            continue
        keys = [matching.normalize(v, affixes) for v in values]
        p_hit = sum(1 for k in keys if k in provinces) / len(keys)
        c_hit = sum(1 for k in keys if k in communes) / len(keys)
        if p_hit >= 0.35:
            result["province"].append({"column": info["column"], "match_rate": round(p_hit, 3)})
        if c_hit >= 0.35:
            result["commune"].append({"column": info["column"], "match_rate": round(c_hit, 3)})
    result["province"].sort(key=lambda d: -d["match_rate"])
    result["commune"].sort(key=lambda d: -d["match_rate"])
    return result


def coordinate_candidates(columns: Sequence[dict[str, Any]]) -> dict[str, str | None]:
    lon = next((c["column"] for c in columns
                if c["semantic"] == sem.COORDINATE and c.get("axis") == "lon"), None)
    lat = next((c["column"] for c in columns
                if c["semantic"] == sem.COORDINATE and c.get("axis") == "lat"), None)
    return {"lon": lon, "lat": lat}


def _by_semantic(columns: Sequence[dict[str, Any]], *wanted: str) -> list[dict[str, Any]]:
    return [c for c in columns if c["semantic"] in wanted and c.get("mappable")]


#: names that mark a column as a denominator or a background total rather than
#: something a programme achieved; sizing circles by population says nothing
_DENOMINATOR_LIKE = ("dan so", "quan the", "uoc tinh", "chi tieu", "muc tieu",
                     "du dieu kien", "dang quan ly", "tong so ho")
#: names that mark an outcome worth showing as burden
_OUTCOME_LIKE = ("ca ", "ca_", "mac", "tu vong", "phat hien", "nhiem", "dieu tri")


def _symbol_rank(info: dict[str, Any]) -> int:
    """Lower is better. Keeps a programme count ahead of a denominator."""
    name = sem.deaccent(info["column"]) + " "
    score = 0
    if any(marker in name for marker in _DENOMINATOR_LIKE):
        score += 5
    if info["semantic"] == sem.MONEY:
        score += 3
    if any(marker in name for marker in _OUTCOME_LIKE):
        score -= 2
    return score


def _countable(columns: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(_by_semantic(columns, sem.COUNT, sem.MONEY), key=_symbol_rank)


def map_options(columns: Sequence[dict[str, Any]], admin_level: str,
                coords: dict[str, str | None]) -> list[dict[str, Any]]:
    """Rank map types with a reason a non-specialist can evaluate."""
    rates = _by_semantic(columns, sem.PERCENT, sem.RATE_PER)
    counts = _countable(columns)
    categories = [c for c in columns if c["semantic"] == sem.CATEGORY
                  and 2 <= c.get("levels", 0) <= 8]
    points = _by_semantic(columns, sem.POINT)
    level = msg.text("tier.commune" if admin_level == "commune" else "tier.province")
    options: list[dict[str, Any]] = []

    def option(kind: str, score: int, columns: dict[str, Any] | None = None,
               **fmt: Any) -> dict[str, Any]:
        """One ranked option; its two sentences come from the message table."""
        return {"kind": kind,
                "friendly_name": msg.text(f"option.{kind}.name"),
                **(columns or {}),
                "why": msg.text(f"option.{kind}.why", **fmt),
                "points": score}

    if rates and counts:
        options.append(option(
            "choropleth-symbol", 100,
            {"fill_by": rates[0]["column"], "symbol_by": counts[0]["column"]},
            fill=rates[0]["column"], level=level, symbol=counts[0]["column"]))
    if rates:
        options.append(option("choropleth", 88, {"fill_by": rates[0]["column"]},
                              fill=rates[0]["column"], level=level))
    if counts:
        options.append(option("graduated-symbol", 84 if not rates else 70,
                              {"symbol_by": counts[0]["column"]},
                              symbol=counts[0]["column"]))
    if points:
        options.append(option("change", 80, {"fill_by": points[0]["column"]},
                              fill=points[0]["column"]))
    if categories:
        options.append(option("categorized", 74, {"fill_by": categories[0]["column"]},
                              fill=categories[0]["column"],
                              levels=categories[0].get("levels")))
    if coords.get("lon") and coords.get("lat"):
        options.append(option("point", 72))
    if not options:
        options.append(option("boundary", 40))
    options.sort(key=lambda o: -o["points"])
    return options


def find_pairs(columns: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Columns that look like the same measure at two points in time."""
    import re

    buckets: dict[str, list[tuple[int, str]]] = {}
    for c in columns:
        if not c.get("mappable") or c["semantic"] == sem.CATEGORY:
            continue
        m = re.search(r"(19|20)\d{2}", c["column"])
        if not m:
            continue
        stem = (c["column"][:m.start()] + c["column"][m.end():]).strip(" -–_()")
        buckets.setdefault(stem.lower(), []).append((int(m.group()), c["column"]))
    pairs = []
    for stem, entries in buckets.items():
        if len(entries) < 2:
            continue
        entries.sort()
        pairs.append({"indicator": stem, "baseline": entries[0][1], "comparison": entries[-1][1],
                      "why": msg.text("year-column-pairs", first=entries[0][0],
                                         last=entries[-1][0])})
    return pairs


def quality_flags(deps, df, columns: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for info in columns:
        if info["semantic"] == sem.TIME:
            issues.extend(guardrails.check_periods(df[info["column"]].tolist()))
        if info["semantic"] == sem.PERCENT:
            issues.extend(guardrails.check_percent_range(
                _series_values(df[info["column"]]), info))
        if info["missing"] >= 0.4 and info.get("mappable"):
            issues.append(guardrails._issue(
                "mostly-missing", guardrails.WARNING,
                fmt={"column": info["column"], "share": f"{info['missing']:.0%}"}))
    return issues


def build(deps, df, *, sheet: str | None, admin_level: str,
          province_names: Sequence[str], commune_names: Sequence[str],
          dictionary: dict[str, str] | None = None,
          affixes=None) -> dict[str, Any]:
    columns = describe_columns(deps, df, dictionary)
    coords = coordinate_candidates(columns)
    locations = location_candidates(df, columns, province_names, commune_names,
                                    affixes)
    options = map_options(columns, admin_level, coords)

    # attach a weighting column to every rate, so aggregation stays honest
    series = {c["column"]: df[c["column"]].tolist() for c in columns
              if c["semantic"] in {sem.COUNT, sem.PERCENT, sem.RATE_PER, sem.POINT}}
    for info in columns:
        if info["semantic"] in {sem.PERCENT, sem.RATE_PER, sem.POINT}:
            info["weight_column"] = sem.find_denominator(info["column"], columns, series)

    return {
        "sheet": sheet,
        "row_count": int(len(df)),
        "column_count": int(df.shape[1]),
        "assumed_admin_level": admin_level,
        "column": columns,
        "place_column": locations,
        "coordinate_columns": coords,
        "period_column": [c["column"] for c in columns if c["semantic"] == sem.TIME],
        "year_pairs": find_pairs(columns),
        "map_options": options,
        "quality_warnings": quality_flags(deps, df, columns),
        "has_data_dictionary": bool(dictionary),
    }
