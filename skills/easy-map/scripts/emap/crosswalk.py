"""Mapping Vietnam's pre-2025 provinces onto the 34 that exist now.

A time series that starts before 2025 is reported on 63 provinces; the shapefile
has 34. Without a conversion the older years simply cannot be drawn — half the
names do not exist on the map.

The conversion is not guesswork: the shapefile's ``sap_nhap`` field records, for
every current province, exactly which former provinces were merged into it.

Aggregation still matters after conversion. Two former provinces landing on one
current province become two rows for the same feature, and the existing rules
apply: counts are summed, rates are recomputed as a weighted mean and never
averaged naively.
"""

from __future__ import annotations

from typing import Any

from . import matching

NOT_MERGED = "không sáp nhập"

#: Provinces that changed name in 2025 without being merged into anything.
#:
#: ``sap_nhap`` records mergers, and a province that was only renamed is written
#: "không sáp nhập" — so its former name appears nowhere in the shapefile and a
#: table using it simply fails to join. Measured against the real file: of the 63
#: pre-2025 provinces, exactly one is unreachable this way. Thừa Thiên Huế became
#: the centrally-run city of Huế; the other ten unmerged provinces kept their
#: names.
#:
#: This is the one place in the conversion that is asserted rather than read out
#: of the data, so it is kept to what can be checked: ``tests/test_crosswalk.py``
#: loads the actual shapefile and fails if any pre-2025 name stops resolving, or
#: if an entry here becomes redundant because a later shapefile records it.
RENAMED = {"Thừa Thiên Huế": "Huế"}


def build(gdf, name_field: str = "ten_tinh", merger_field: str = "sap_nhap") -> dict[str, str]:
    """Former province name -> current province name. Includes self-mappings."""
    out: dict[str, str] = {}
    if merger_field not in gdf.columns:
        return out
    for _, row in gdf.iterrows():
        current = str(row[name_field]).strip()
        raw = str(row.get(merger_field) or "").strip()
        if not raw or raw.lower().startswith(NOT_MERGED):
            formers = [current]
        else:
            formers = [part.strip() for part in raw.split(",") if part.strip()]
        for former in formers:
            out[former] = current

    present = {str(row[name_field]).strip() for _, row in gdf.iterrows()}
    for former, current in RENAMED.items():
        if current in present and former not in out:
            out[former] = current
    return out


def alias_features(gdf, name_field: str = "ten_tinh", merger_field: str = "sap_nhap",
                   id_field: str = "__shape_id",
                   alias_field: str | None = None) -> list[dict[str, Any]]:
    """Match-index entries covering both current and former province names.

    Former names carry ``merged_from`` so the review can say a row was converted
    rather than merely matched.
    """
    features: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, row in gdf.iterrows():
        current = str(row[name_field]).strip()
        shape_id = int(row[id_field])
        entry: dict[str, Any] = {"name": current, "shape_id": shape_id}
        # a second spelling the boundary file itself gives, such as GADM's
        # VARNAME_1; NA is how GADM writes an absent cell
        alias = str(row.get(alias_field) or "").strip() if alias_field else ""
        if alias and alias != "NA" and alias != current:
            entry["aliases"] = [alias]
        features.append(entry)

        formers = []
        raw = str(row.get(merger_field) or "").strip()
        if raw and not raw.lower().startswith(NOT_MERGED):
            formers = [part.strip() for part in raw.split(",") if part.strip()]
        # a rename leaves no trace in the merger field, so it is added here
        formers += [f for f, c in RENAMED.items() if c == current]

        for former in formers:
            key = matching.normalize(former, matching.VIETNAM)
            if key == matching.normalize(current, matching.VIETNAM) or key in seen:
                continue
            seen.add(key)
            features.append({"name": former, "shape_id": shape_id,
                             "merged_from": former, "canonical": current})
    return features


def summarize(review: list[dict[str, Any]]) -> dict[str, Any]:
    """What the conversion actually did, for the footnote and the warning."""
    converted = [r for r in review if r.get("match_method") == matching.MERGED]
    targets = {r.get("matched_province") for r in converted if r.get("matched_province")}
    return {
        "renamed_count": len(converted),
        "current_province_count": len(targets),
        "examples": [f"{r['dataset_province']} → {r['matched_province']}"
                  for r in converted[:6]],
    }
