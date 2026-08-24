"""Combining duplicate rows for one geography, correctly per measure type."""

from __future__ import annotations

from typing import Any

from . import semantics as sem

METHODS = ("auto", "sum", "mean", "weighted-mean", "median", "max", "min", "mode", "first")


def resolve(method: str, info: dict[str, Any]) -> str:
    if method and method != "auto":
        return method
    default = info.get("default_aggregation", "mean")
    if default == "recompute":
        return "weighted-mean" if info.get("weight_column") else "mean"
    return default


def combine(deps, df, key: str, column: str, info: dict[str, Any], method: str,
            weight_column: str | None = None):
    """Return a Series indexed by ``key`` holding the combined value."""
    method = resolve(method, info)
    grouped = df.groupby(key)

    if method == "sum":
        return grouped[column].sum(min_count=1)
    if method == "median":
        return grouped[column].median()
    if method == "max":
        return grouped[column].max()
    if method == "min":
        return grouped[column].min()
    if method == "mode":
        return grouped[column].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
    if method == "first":
        return grouped[column].first()
    if method == "weighted-mean":
        weight_column = weight_column or info.get("weight_column")
        if weight_column and weight_column in df.columns:
            def _weighted(sub):
                w = sub[weight_column]
                v = sub[column]
                mask = v.notna() & w.notna() & (w > 0)
                if not mask.any():
                    return v.mean()
                return float((v[mask] * w[mask]).sum() / w[mask].sum())

            return grouped.apply(_weighted, include_groups=False)
        return grouped[column].mean()
    return grouped[column].mean()


def describe(method: str, info: dict[str, Any], weight_column: str | None,
             lang: str | None = None) -> str:
    from . import i18n

    resolved = resolve(method, info)
    label = i18n.t(lang, f"agg_{resolved}")
    if label == f"agg_{resolved}":       # unknown method: show it verbatim
        label = resolved
    if resolved == "weighted-mean" and weight_column:
        return i18n.t(lang, "agg_by", method=label, column=weight_column)
    return label


def duplicate_count(df, key: str) -> int:
    counts = df.groupby(key).size()
    return int((counts > 1).sum())
