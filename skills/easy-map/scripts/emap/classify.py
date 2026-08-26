"""Turning numbers into classes, colours and honest labels.

Three defects from the previous renderer are fixed here:

* a count legend could read ``46.5`` because the median of integers is not an
  integer — count breaks are now snapped to whole numbers,
* quantile breaks on small samples produced meaningless slivers such as
  ``66–67%`` — near-empty or near-zero-width classes are merged,
* every map in a province series computed its own breaks, so the same blue meant
  different things on different sheets — breaks can now be computed once for the
  whole series and reused.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from . import messages as msg, semantics as sem

# Monotone-lightness sequential ramps anchored on the primary blue #005eaa.
# The previous palette ran blue -> teal -> blue, which is not a sequential ramp.
BLUES = {
    3: ["#cfe6f7", "#5d9fd0", "#005eaa"],
    4: ["#dceefb", "#a2cbe9", "#4a8cc4", "#005eaa"],
    5: ["#dceefb", "#a9d2ec", "#6ba9d5", "#2f7cb8", "#005eaa"],
    6: ["#e7f4fc", "#c0e0f3", "#8fc0e2", "#5b9bcc", "#2c76b4", "#00559a"],
    7: ["#e7f4fc", "#c8e4f4", "#9fcae6", "#74acd6", "#4a8cc4", "#256fb0", "#004e8e"],
}

# Diverging ramp for signed change: pink <-> blue, never red/green.
DIVERGING = {
    3: ["#e57373", "#f2f2f2", "#5d9fd0"],
    4: ["#af4448", "#e9a6a8", "#a2cbe9", "#005eaa"],
    5: ["#af4448", "#e9a6a8", "#f2f2f2", "#a2cbe9", "#005eaa"],
    6: ["#8f2f33", "#c96d70", "#f0cccd", "#c4dff2", "#5d9fd0", "#004e8e"],
    7: ["#8f2f33", "#c96d70", "#f0cccd", "#f2f2f2", "#c4dff2", "#5d9fd0", "#004e8e"],
}

QUALITATIVE = ["#005eaa", "#497d0c", "#00695c", "#fbab18", "#af4448", "#712177",
               "#29434e", "#bb4d00"]

NO_DATA = "#eceef0"

METHODS = ("quantile", "equal-interval", "natural-breaks")


def palette(classes: int, diverging: bool = False) -> list[str]:
    table = DIVERGING if diverging else BLUES
    classes = max(3, min(7, classes))
    return list(table[classes])


def category_colours(values) -> tuple[list[str], dict[str, str]]:
    """Colours for a set of category labels, in the order they should be read.

    A scale with an order — "thấp, trung bình, cao" — gets the sequential ramp
    running low to high, so darker means more. Genuinely unordered groups get
    the qualitative palette instead, because a ramp on them would invent a
    ranking the data does not have.

    Shared by the area map and the point map: two places deciding this
    separately is how the same three groups end up in different colours on two
    plates of one request.
    """
    from . import semantics as sem

    labels = [str(v) for v in values]
    ordered = sem.order_categories(labels)
    if ordered:
        ramp = palette(len(ordered))
        return list(ordered), {c: ramp[i] for i, c in enumerate(ordered)}
    cats = sorted(set(labels))
    return cats, {c: QUALITATIVE[i % len(QUALITATIVE)] for i, c in enumerate(cats)}


def _raw_edges(values: Sequence[float], method: str, classes: int, deps=None) -> list[float]:
    data = sorted(float(v) for v in values)
    lo, hi = data[0], data[-1]
    if method == "equal-interval":
        step = (hi - lo) / classes if hi > lo else 1.0
        return [lo + step * i for i in range(classes + 1)]
    if method == "natural-breaks":
        try:
            import mapclassify

            jenks = mapclassify.NaturalBreaks(data, k=classes)
            return [lo] + [float(b) for b in jenks.bins]
        except Exception:
            method = "quantile"
    # quantile
    edges = [lo]
    for i in range(1, classes):
        pos = (len(data) - 1) * i / classes
        low = math.floor(pos)
        high = min(low + 1, len(data) - 1)
        edges.append(data[low] + (data[high] - data[low]) * (pos - low))
    edges.append(hi)
    return edges


def _snap_integers(edges: list[float]) -> list[float]:
    out = [float(math.floor(edges[0]))]
    for e in edges[1:]:
        out.append(float(round(e)))
    out[-1] = float(math.ceil(edges[-1]))
    return out


def _collapse(edges: list[float], values: Sequence[float], integer: bool) -> list[float]:
    """Drop breaks that create empty or visually meaningless classes."""
    span = edges[-1] - edges[0]
    if span <= 0:
        return [edges[0], edges[0] + (1 if integer else 1e-6)]
    min_width = max(span * 0.04, 1.0 if integer else 0.0)

    kept = [edges[0]]
    for e in edges[1:-1]:
        if e - kept[-1] < min_width:
            continue
        kept.append(e)
    kept.append(edges[-1])
    if kept[-1] - kept[-2] < min_width and len(kept) > 2:
        kept.pop(-2)

    # remove classes that would contain no observation at all
    pruned = [kept[0]]
    for i in range(1, len(kept)):
        lo, hi = pruned[-1], kept[i]
        occupied = any(lo <= v <= hi for v in values) if i < len(kept) - 1 else True
        if occupied or i == len(kept) - 1:
            pruned.append(hi)
    return pruned


def _diverging_edges(data: Sequence[float], classes: int) -> tuple[list[float], list[str]]:
    """Breaks anchored on zero, so the neutral colour really means 'no change'.

    Each side keeps its own quantiles, so a skewed distribution does not waste
    half the ramp, but zero is always a class boundary.
    """
    negatives = sorted(v for v in data if v < 0)
    positives = sorted(v for v in data if v > 0)
    if not negatives or not positives:
        return [], []
    k = classes if classes % 2 == 0 else classes - 1
    k = max(2, k)
    half = k // 2

    def side(values: list[float], count: int, ascending: bool) -> list[float]:
        out = []
        for i in range(1, count):
            pos = (len(values) - 1) * i / count
            low = math.floor(pos)
            high = min(low + 1, len(values) - 1)
            out.append(values[low] + (values[high] - values[low]) * (pos - low))
        return out if ascending else out

    edges = [negatives[0]] + side(negatives, half, True) + [0.0]
    edges += side(positives, half, True) + [positives[-1]]
    return sorted(set(edges)), [msg.text("bins.diverging-around-zero")]


def compute_bins(values: Sequence[float], method: str, classes: int,
                 info: dict[str, Any] | None = None,
                 center_zero: bool = False) -> dict[str, Any]:
    """Return break edges plus a note describing any automatic adjustment."""
    data = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not data:
        raise ValueError(msg.text("error.no-numeric-value"))
    info = info or {}
    integer = bool(info.get("integer")) or info.get("semantic") == sem.COUNT
    distinct = len(set(data))

    notes: list[str] = []
    asked = classes
    classes = max(2, min(classes, distinct))
    if classes != asked:
        notes.append(msg.text("bins.fewer-classes", asked=asked, classes=classes,
                              distinct=distinct))

    edges: list[float] = []
    if center_zero:
        edges, extra = _diverging_edges(data, classes)
        notes.extend(extra)
        if not edges:
            notes.append(msg.text("bins.sequential"))
    if not edges:
        edges = _raw_edges(data, method if method in METHODS else "quantile", classes)
        if integer:
            edges = _snap_integers(edges)
    edges = sorted(set(edges))
    if not center_zero:
        edges = _collapse(edges, data, integer)

    if len(edges) - 1 < classes:
        notes.append(msg.text("bins.classes-merged", classes=len(edges) - 1))
    return {"edges": edges, "classes": len(edges) - 1, "integer": integer,
            "method": method, "notes": notes}


def shared_bins(groups: dict[str, Sequence[float]], method: str, classes: int,
                info: dict[str, Any] | None = None,
                center_zero: bool = False) -> dict[str, Any]:
    """One set of breaks for every map in a series, so colours compare."""
    pooled: list[float] = []
    for values in groups.values():
        pooled.extend(v for v in values if v is not None)
    result = compute_bins(pooled, method, classes, info, center_zero)
    result["shared_across"] = sorted(groups)
    result["notes"].append(msg.text("bins.shared-scale"))
    return result


def class_index(value: float, edges: Sequence[float]) -> int:
    for i in range(len(edges) - 1):
        if value <= edges[i + 1] + 1e-9:
            return i
    return len(edges) - 2


def label_decimals(bins: dict[str, Any] | None) -> int | None:
    """How many decimals the map labels need to agree with the legend.

    A legend reading 99.20%–99.25% beside a label reading "99%" is two different
    statements about one number, and rounding 99.74% up to "100%" is the worse
    half of that pair.
    """
    edges = (bins or {}).get("edges")
    if not edges or (bins or {}).get("integer"):
        return None
    return _decimals(edges)


def bin_labels(edges: Sequence[float], info: dict[str, Any],
               lang: str | None = None) -> list[str]:
    """Class ranges. The unit lives in the legend heading, not on both endpoints,
    except for percent where the sign is unambiguous and readers expect it."""
    integer = bool(info.get("integer")) or info.get("semantic") == sem.COUNT
    labels = []
    d = _decimals(edges)
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        if integer:
            low = int(lo) + (1 if i > 0 else 0)
            labels.append(f"{sem.group_digits(low, lang)}–{sem.group_digits(int(hi), lang)}")
        elif info.get("semantic") == sem.POINT:
            labels.append(f"{_signed(lo, d)} … {_signed(hi, d)}")
        else:
            labels.append(f"{sem.format_value(lo, info, decimals=d, lang=lang)}–"
                          f"{sem.format_value(hi, info, decimals=d, lang=lang)}")
    return labels


def _signed(value: float, decimals: int) -> str:
    text = f"{value:+.{decimals}f}"
    # a value of -0.0 (or -0.4 shown with no decimals) must not read as "-0"
    if float(text) == 0:
        return f"{0:.{decimals}f}"
    return text


#: Most decimals a class label may carry. Past this the number stops being a
#: quantity a reader holds in mind and becomes a serial number.
MAX_DECIMALS = 6


def _decimals(edges: Sequence[float]) -> int:
    """Enough decimals that no two class edges print the same.

    The span alone is not enough to decide this. A column of cases over
    population runs 0.005 to 0.020: the span says two decimals, and two
    decimals print four of the five classes as ``0.01%–0.01%``. A legend that
    cannot tell its own classes apart is worse than a coarser map, because it
    still looks precise.

    So the span picks a floor and the edges themselves settle it — widened
    until every printed edge differs from its neighbour, or until the ceiling
    says the difference is too fine to be worth showing.
    """
    span = edges[-1] - edges[0]
    if span >= 20:
        places = 0
    elif span >= 2:
        places = 1
    else:
        places = 2
    while places < MAX_DECIMALS:
        shown = [f"{e:.{places}f}" for e in edges]
        if len(set(shown)) == len(shown):
            break
        places += 1
    return places


def symbol_scale(values: Sequence[float]) -> dict[str, float]:
    """Shared symbol reference so circle area compares across maps in a series."""
    data = [float(v) for v in values if v is not None and v > 0]
    if not data:
        return {"max_value": 1.0, "min_value": 0.0}
    return {"max_value": max(data), "min_value": min(data)}


def symbol_legend_values(max_value: float, integer: bool = True) -> list[float]:
    picks = [max_value * 0.12, max_value * 0.45, max_value]
    if integer:
        picks = [max(1, round(p)) for p in picks]
        out: list[float] = []
        for p in picks:
            if p not in out:
                out.append(p)
        return out
    return picks
