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
        info["thiếu"] = round(1 - len(values) / total, 4) if total else 1.0
        info["số_giá_trị_khác_nhau"] = len({str(v) for v in values})
        info["ví_dụ"] = [str(v) for v in values[:4]]
        if is_numeric and values:
            nums = sorted(float(v) for v in values)
            info[sem.STAT_MIN] = nums[0]
            info[sem.STAT_MEDIAN] = nums[len(nums) // 2]
            info[sem.STAT_MAX] = nums[-1]
            info[sem.STAT_SUM] = sum(nums)
        if dictionary and column in dictionary:
            info["mô_tả_từ_bảng"] = dictionary[column]
            info["nguồn_ý_nghĩa"] = msg.text("nguon-y-nghia.tu-dien")
        else:
            info["nguồn_ý_nghĩa"] = msg.text("nguon-y-nghia.suy-luan")
        out.append(info)
    return out


def location_candidates(df, columns: Sequence[dict[str, Any]], province_names: Sequence[str],
                        commune_names: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """Score text columns by how many of their values exist in the shapefile."""
    provinces = {matching.normalize(n) for n in province_names}
    communes = {matching.normalize(n) for n in commune_names}
    result: dict[str, list[dict[str, Any]]] = {"tỉnh": [], "xã": []}

    for info in columns:
        if info["semantic"] in {sem.COUNT, sem.PERCENT, sem.RATE_PER, sem.MONEY,
                                sem.POINT, sem.COORDINATE}:
            continue
        values = [str(v) for v in df[info["column"]].tolist() if v is not None and not _isnan(v)]
        if not values:
            continue
        keys = [matching.normalize(v) for v in values]
        p_hit = sum(1 for k in keys if k in provinces) / len(keys)
        c_hit = sum(1 for k in keys if k in communes) / len(keys)
        if p_hit >= 0.35:
            result["tỉnh"].append({"cột": info["column"], "khớp": round(p_hit, 3)})
        if c_hit >= 0.35:
            result["xã"].append({"cột": info["column"], "khớp": round(c_hit, 3)})
    result["tỉnh"].sort(key=lambda d: -d["khớp"])
    result["xã"].sort(key=lambda d: -d["khớp"])
    return result


def coordinate_candidates(columns: Sequence[dict[str, Any]]) -> dict[str, str | None]:
    lon = next((c["column"] for c in columns
                if c["semantic"] == sem.COORDINATE and c.get("axis") == "lon"), None)
    lat = next((c["column"] for c in columns
                if c["semantic"] == sem.COORDINATE and c.get("axis") == "lat"), None)
    return {"kinh_độ": lon, "vĩ_độ": lat}


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
    level = msg.text("cap.xa" if admin_level == "commune" else "cap.tinh")
    options: list[dict[str, Any]] = []

    def option(kind: str, score: int, columns: dict[str, Any] | None = None,
               **fmt: Any) -> dict[str, Any]:
        """One ranked option; its two sentences come from the message table."""
        return {"loại": kind,
                "tên_dễ_hiểu": msg.text(f"phuong-an.{kind}.tên"),
                **(columns or {}),
                "vì_sao": msg.text(f"phuong-an.{kind}.vì_sao", **fmt),
                "điểm": score}

    if rates and counts:
        options.append(option(
            "choropleth-symbol", 100,
            {"màu_theo": rates[0]["column"], "vòng_tròn_theo": counts[0]["column"]},
            fill=rates[0]["column"], level=level, symbol=counts[0]["column"]))
    if rates:
        options.append(option("choropleth", 88, {"màu_theo": rates[0]["column"]},
                              fill=rates[0]["column"], level=level))
    if counts:
        options.append(option("graduated-symbol", 84 if not rates else 70,
                              {"vòng_tròn_theo": counts[0]["column"]},
                              symbol=counts[0]["column"]))
    if points:
        options.append(option("change", 80, {"màu_theo": points[0]["column"]},
                              fill=points[0]["column"]))
    if categories:
        options.append(option("categorized", 74, {"màu_theo": categories[0]["column"]},
                              fill=categories[0]["column"],
                              levels=categories[0].get("levels")))
    if coords.get("kinh_độ") and coords.get("vĩ_độ"):
        options.append(option("point", 72))
    if not options:
        options.append(option("boundary", 40))
    options.sort(key=lambda o: -o["điểm"])
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
        pairs.append({"chỉ_số": stem, "gốc": entries[0][1], "so_sánh": entries[-1][1],
                      "vì_sao": msg.text("cap-cot-theo-nam", first=entries[0][0],
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
        if info["thiếu"] >= 0.4 and info.get("mappable"):
            issues.append(guardrails._issue(
                "thieu-nhieu", guardrails.WARNING,
                fmt={"column": info["column"], "share": f"{info['thiếu']:.0%}"}))
    return issues


def build(deps, df, *, sheet: str | None, admin_level: str,
          province_names: Sequence[str], commune_names: Sequence[str],
          dictionary: dict[str, str] | None = None) -> dict[str, Any]:
    columns = describe_columns(deps, df, dictionary)
    coords = coordinate_candidates(columns)
    locations = location_candidates(df, columns, province_names, commune_names)
    options = map_options(columns, admin_level, coords)

    # attach a weighting column to every rate, so aggregation stays honest
    series = {c["column"]: df[c["column"]].tolist() for c in columns
              if c["semantic"] in {sem.COUNT, sem.PERCENT, sem.RATE_PER, sem.POINT}}
    for info in columns:
        if info["semantic"] in {sem.PERCENT, sem.RATE_PER, sem.POINT}:
            info["cột_trọng_số"] = sem.find_denominator(info["column"], columns, series)

    return {
        "sheet": sheet,
        "số_dòng": int(len(df)),
        "số_cột": int(df.shape[1]),
        "cấp_hành_chính_giả_định": admin_level,
        "cột": columns,
        "cột_địa_danh": locations,
        "cột_toạ_độ": coords,
        "cột_thời_gian": [c["column"] for c in columns if c["semantic"] == sem.TIME],
        "cặp_so_sánh_theo_năm": find_pairs(columns),
        "phương_án_bản_đồ": options,
        "cảnh_báo_chất_lượng": quality_flags(deps, df, columns),
        "có_từ_điển_dữ_liệu": bool(dictionary),
    }
