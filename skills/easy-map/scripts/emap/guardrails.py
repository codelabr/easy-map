"""Scientific safety checks, written for a reader who is not a statistician.

Each check returns a plain explanation plus a concrete alternative. Nothing here
blocks the user: the agreed behaviour is warn, propose, then do what the user
decides.

The wording lives in :mod:`messages`, in both languages, keyed by the same id the
warning carries. This module decides *whether* a warning fires and supplies the
numbers; it does not hold any sentence.
"""

from __future__ import annotations

from typing import Any, Sequence

from . import messages as msg, semantics as sem

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"


def _issue(key: str, severity: str, *, fmt: dict[str, Any] | None = None,
           extra: dict[str, Any] | None = None, counts: Any = None,
           lang: str | None = None) -> dict[str, Any]:
    """One warning: its id, how serious it is, and its three sentences.

    ``fmt`` fills the placeholders in the message template; ``extra`` adds
    machine-readable fields to the JSON. They are separate arguments because a
    value is often needed for one and not the other — the share behind
    "only 12 of 34" is printed as a percentage and carried as a number.

    ``counts`` is the quantity the sentence is about, when there is one. English
    inflects around it and Vietnamese does not, so the number is handed to the
    message table rather than to a string built here.
    """
    out: dict[str, Any] = {"id": key, "severity": severity}
    out.update(msg.issue(key, lang, singular=(counts == 1), **(fmt or {})))
    out.update(extra or {})
    return out


def check_coverage(with_data: int, in_frame: int,
                   lang: str | None = None) -> list[dict[str, Any]]:
    if in_frame <= 0:
        return []
    share = with_data / in_frame
    if share >= 0.35:
        return []
    severity = CRITICAL if share < 0.15 else WARNING
    return [_issue(
        "coverage-thap", severity, lang=lang, counts=with_data,
        fmt={"with_data": with_data, "in_frame": in_frame, "share": f"{share:.0%}"},
        extra={"share": round(share, 4)},
    )]


def check_aggregation(column_info: dict[str, Any], method: str,
                      duplicated_rows: int,
                      lang: str | None = None) -> list[dict[str, Any]]:
    if duplicated_rows <= 0:
        return []
    semantic = column_info.get("semantic")
    name = column_info.get("column")
    if method == "sum" and semantic in sem.NEVER_SUM:
        return [_issue("cong-gop-ty-le", CRITICAL, lang=lang,
                       fmt={"column": name},
                       extra={"column": name, "semantic": semantic})]
    if semantic in sem.NEVER_SUM and method == "mean" and not column_info.get("weight_column"):
        return [_issue("trung-binh-khong-trong-so", WARNING, lang=lang,
                       fmt={"column": name}, extra={"column": name})]
    return []


def check_colour_choice(column_info: dict[str, Any], map_type: str,
                        lang: str | None = None) -> list[dict[str, Any]]:
    if map_type not in {"choropleth", "choropleth-symbol"}:
        return []
    if column_info.get("semantic") not in {sem.COUNT, sem.MONEY}:
        return []
    name = column_info.get("column")
    return [_issue("to-mau-so-dem", WARNING, lang=lang,
                   fmt={"column": name}, extra={"column": name})]


def check_percent_range(values: Sequence[float], column_info: dict[str, Any],
                        lang: str | None = None) -> list[dict[str, Any]]:
    if column_info.get("semantic") != sem.PERCENT:
        return []
    nums = [v for v in values if v is not None]
    if not nums:
        return []
    scale = column_info.get("scale", "percent")
    hi = max(nums) * (100 if scale == "unit" else 1)
    lo = min(nums) * (100 if scale == "unit" else 1)
    name = column_info.get("column")
    out = []
    if hi > 100.5:
        out.append(_issue(
            "phan-tram-vuot-100", WARNING, lang=lang,
            # the warning is a sentence in the conversation, so its digits follow
            # the conversation's convention, not the map's
            fmt={"column": name, "value": sem.localise_digits(f"{hi:.1f}", msg.normalise(lang))},
        ))
    if lo < 0:
        out.append(_issue(
            "phan-tram-am", WARNING, lang=lang,
            fmt={"column": name, "value": sem.localise_digits(f"{lo:.1f}", msg.normalise(lang))},
        ))
    return out


def most_classes(observations: int) -> int:
    """The largest number of classes this many units can carry.

    Roughly three units per class, never fewer than two classes. The advice in
    the warning has to name *this* number rather than a fixed one, or a map
    already at the ceiling is told to reduce to the value it is using — which is
    what a reader of eight communes was told to do with three classes.
    """
    return max(2, observations // 3)


def check_classes(bins: dict[str, Any], observations: int,
                  lang: str | None = None) -> list[dict[str, Any]]:
    out = []
    for note in bins.get("notes", []):
        out.append(_issue("phan-lop-dieu-chinh", INFO, lang=lang, fmt={"note": note}))
    if observations and bins.get("classes", 0) > most_classes(observations):
        out.append(_issue(
            "qua-nhieu-nhom", WARNING, lang=lang, counts=observations,
            fmt={"classes": bins.get("classes"), "observations": observations,
                 "suggest": most_classes(observations)},
        ))
    out.extend(check_spread(bins, lang=lang))
    return out


#: below this, the difference between the highest and lowest unit is small
#: enough that a full colour ramp is reading noise as signal
FLAT_SPREAD = 0.02


def check_spread(bins: dict[str, Any], lang: str | None = None) -> list[dict[str, Any]]:
    """A colour ramp stretched across a difference that is not there.

    Viral suppression came back as 99.20% to 99.74% across five provinces. The
    quantile ramp gave each of them its own shade, and the map then says the
    provinces differ — which is exactly what half a percentage point does not
    support.
    """
    edges = bins.get("edges") or []
    if len(edges) < 2:
        return []
    low, high = float(edges[0]), float(edges[-1])
    span = high - low
    scale = max(abs(low), abs(high))
    if span <= 0 or scale <= 0 or span / scale > FLAT_SPREAD:
        return []
    code = msg.normalise(lang)
    return [_issue(
        "chenh-lech-qua-nho", WARNING, lang=lang,
        fmt={"span": sem.localise_digits(f"{span:.3g}", code),
             "scale": sem.localise_digits(f"{scale:.3g}", code)},
        extra={"span": round(span, 4)},
    )]


def check_admin_level(summary: dict[str, int], admin_level: str,
                      column: str | None = None,
                      lang: str | None = None) -> list[dict[str, Any]]:
    """A commune column that mostly does not match is probably not communes.

    Vietnam removed the district tier in 2025 and many districts share a name
    with a commune, so a district column matches enough of the commune list to
    look plausible — and the names that do match are then reported as certain,
    on the wrong unit.
    """
    total = summary.get("total") or 0
    if admin_level != "commune" or total < 10:
        return []
    unmatched = summary.get("unmatched", 0) + summary.get("fuzzy", 0)
    if unmatched / total < 0.15:
        return []
    where = (msg.fragment("cot-ten", lang, column=column) if column
             else msg.fragment("cot-dia-danh-xa", lang))
    return [_issue("co-the-khong-phai-cap-xa", CRITICAL, lang=lang, counts=unmatched,
                   fmt={"unmatched": unmatched, "total": total, "where": where})]


def check_matching(summary: dict[str, int],
                   lang: str | None = None) -> list[dict[str, Any]]:
    out = []
    if summary.get("unmatched"):
        out.append(_issue("khong-ghep-duoc", CRITICAL, lang=lang,
                          counts=summary["unmatched"],
                          fmt={"count": summary["unmatched"]}))
    if summary.get("merged"):
        out.append(_issue("quy-doi-sap-nhap", INFO, lang=lang,
                          counts=summary["merged"],
                          fmt={"count": summary["merged"]}))
    if summary.get("ambiguous"):
        # what actually happened to those rows, not what could be done about them:
        # the warning used to describe a choice the engine had already made
        dropped = summary.get("ambiguous_dropped", True)
        tail = msg.fragment("nhap-nhang-da-bo" if dropped else "nhap-nhang-da-giu", lang)
        out.append(_issue("ghep-nhap-nhang", CRITICAL, lang=lang,
                          counts=summary["ambiguous"],
                          fmt={"count": summary["ambiguous"], "tail": tail}))
    if summary.get("fuzzy"):
        out.append(_issue("ghep-can-duyet", WARNING, lang=lang,
                          counts=summary["fuzzy"],
                          fmt={"count": summary["fuzzy"]}))
    return out


def check_periods(period_values: Sequence[Any],
                  lang: str | None = None) -> list[dict[str, Any]]:
    distinct = {str(v) for v in period_values if v is not None}
    if len(distinct) <= 1:
        return []
    return [_issue("nhieu-ky-bao-cao", CRITICAL, lang=lang,
                   fmt={"count": len(distinct)},
                   extra={"periods": sorted(distinct)[:24]})]


def check_symbol_occlusion(max_radius_m: float, median_unit_width_m: float,
                           lang: str | None = None) -> list[dict[str, Any]]:
    if median_unit_width_m <= 0 or max_radius_m <= 0:
        return []
    if max_radius_m * 2 <= median_unit_width_m * 1.6:
        return []
    return [_issue("vong-tron-che-vung", WARNING, lang=lang)]


def check_diverging(values: Sequence[float], column_info: dict[str, Any],
                    lang: str | None = None) -> list[dict[str, Any]]:
    if column_info.get("semantic") != sem.POINT:
        return []
    nums = [v for v in values if v is not None]
    if not nums or min(nums) >= 0 or max(nums) <= 0:
        return []
    return [_issue("can-thang-hai-chieu", INFO, lang=lang)]


def summarize(issues: Sequence[dict[str, Any]]) -> dict[str, Any]:
    order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    ranked = sorted(issues, key=lambda i: order.get(i["severity"], 3))
    return {
        "tổng": len(ranked),
        "nghiêm_trọng": sum(1 for i in ranked if i["severity"] == CRITICAL),
        "cảnh_báo": sum(1 for i in ranked if i["severity"] == WARNING),
        "danh_sách": ranked,
    }
