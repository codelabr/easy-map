"""Drawing one finished map plate."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from . import (classify, furniture as furn, i18n, insets, labels as lab,
               layout as lay, semantics as sem)

NO_DATA_FILL = classify.NO_DATA
NO_DATA_EDGE = "#ffffff"
OUTLINE = "#5a6b75"
INTERNAL_EDGE = "#ffffff"

LABEL_COLORS = {"name": furn.INK, "value": furn.PRIMARY, "leader": "#8a969e"}


def view_bounds(frame, lon: float | None
                ) -> tuple[tuple[float, float, float, float], dict | None]:
    """The rectangle the map looks at, and the inset plan that goes with it.

    Single source of truth for framing: the page's aspect ratio and the axes
    limits both come from here, because computing them apart is how a map ends
    up with the right shape and the wrong crop.

    ``lon`` is the meridian the country declared, read from its profile and not
    worked out again here. None means the country declared none, and the frame
    is then simply the geometry's own bounds.
    """
    plan = insets.view(frame, lon)
    if plan is None:
        return tuple(float(v) for v in frame.total_bounds), None
    return plan["view_bounds"], plan


def geometry_aspect(frame, lon: float | None) -> float:
    """Width over height of the framed rectangle, or 1.0 when there is none.

    ``if height`` was meant to be that fallback and was not: a frame holding no
    usable geometry has bounds of NaN, NaN is truthy, and the division returned
    NaN — which then sized a figure and went into the metadata, where a NaN is
    not valid JSON. Defensive: no run has been seen to reach it, and the fix is
    to make the guard that already exists do what it says.
    """
    minx, miny, maxx, maxy = view_bounds(frame, lon)[0]
    height = maxy - miny
    if not math.isfinite(height) or height == 0:
        return 1.0
    width = maxx - minx
    return width / height if math.isfinite(width) else 1.0


def median_feature_width(frame) -> float:
    bounds = frame.geometry.bounds
    widths = (bounds["maxx"] - bounds["minx"]).tolist()
    widths = sorted(w for w in widths if w and w > 0)
    return widths[len(widths) // 2] if widths else 0.0


def symbol_radii(values: Sequence[float], scale: dict[str, float],
                 span_y: float, *, max_frac: float = 0.021,
                 min_frac: float = 0.0022) -> list[float]:
    """Area-proportional: radius follows the square root of the value.

    It used to interpolate between a minimum and a maximum radius instead, which
    is a different curve entirely: a province with twelve times the caseload drew
    a circle barely twice as wide. The legend, meanwhile, sized its key circles
    by true area — so the key did not describe the map it sat beside.

    ``min_frac`` is now only a visibility floor for very small values, not part
    of the scale. ``scale`` is shared across a province series so a circle of a
    given size means the same number on every sheet.
    """
    vmax = float(scale.get("max_value") or 1.0)
    rmax, floor = span_y * max_frac, span_y * min_frac
    out = []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)) or v <= 0:
            out.append(0.0)
        else:
            out.append(max(floor, rmax * math.sqrt(min(float(v) / vmax, 1.0))))
    return out


def draw(deps, *, frame, spec: dict[str, Any], fonts: dict[str, str],
         provinces=None, locator_name: str | None = None) -> dict[str, Any]:
    """Render one map and return the plate plus a drawing report."""
    # Which meridian, if any, splits this country's offshore territory off. It
    # arrives already decided, the same way the projection does.
    inset_lon = spec.get("inset_meridian")
    aspect = geometry_aspect(frame, inset_lon)
    plate = lay.build(
        spec.get("layout", "report"), aspect,
        kicker=spec.get("kicker", ""), title=spec.get("title", ""),
        insight=spec.get("insight", ""), source=spec.get("source", ""),
        method=spec.get("method", ""), fonts=fonts, dpi=spec.get("dpi", 220),
        side_panel=spec.get("side_panel", True),
        timeline_in=spec.get("timeline_in", 0.0),
    )
    ax = plate.map_ax
    lang = i18n.normalise(spec.get("language"))
    map_type = spec.get("map_type", "choropleth")
    value_col = spec.get("value_column")
    info = spec.get("value_info", {})

    has_data = frame[frame[value_col].notna()] if value_col else frame.iloc[0:0]
    no_data = frame[frame[value_col].isna()] if value_col else frame

    # Framing has to be decided before the first polygon is drawn: when the
    # archipelagos go to an inset, the main map draws the mainland only.
    inset_plan = insets.view(frame, inset_lon)

    # every polygon layer, remembered with its **full** geometry, so the inset
    # repaints the same rows in the same colours instead of deciding again
    painted: list[tuple[Any, dict[str, Any]]] = []

    def paint(rows, **kwargs):
        insets.clip_for_drawing(rows, inset_plan).plot(ax=ax, **kwargs)
        painted.append((rows, kwargs))
        return ax.collections[-1]

    if len(no_data):
        paint(no_data, facecolor=NO_DATA_FILL, edgecolor=NO_DATA_EDGE,
              linewidth=0.35, zorder=1)

    legend_pairs: list[tuple[str, str]] = []
    data_layer = None          # the artist an animation repaints frame by frame
    # what each feature was actually painted, so the interactive page can enlarge
    # a unit in its own colour instead of guessing the rule a second time
    shape_fills: dict[str, str] = {str(int(s)): NO_DATA_FILL for s in frame["__shape_id"]}

    def remember(rows, colours_used) -> None:
        shape_fills.update({str(int(s)): c
                            for s, c in zip(rows["__shape_id"], colours_used)})

    if map_type in {"choropleth", "choropleth-symbol", "change"} and len(has_data):
        edges = spec["bins"]["edges"]
        colours = classify.palette(len(edges) - 1, diverging=(map_type == "change"))
        fills = [colours[classify.class_index(v, edges)] for v in has_data[value_col]]
        data_layer = paint(has_data, color=fills, edgecolor=INTERNAL_EDGE,
                           linewidth=0.55, zorder=2)
        legend_pairs = list(zip(colours, classify.bin_labels(edges, info, lang)))
        remember(has_data, fills)
    elif map_type == "categorized" and len(has_data):
        cats, mapping = classify.category_colours(has_data[value_col],
                                                  spec.get("category_order"))
        fills = [mapping[str(v)] for v in has_data[value_col]]
        data_layer = paint(has_data, color=fills, edgecolor=INTERNAL_EDGE,
                           linewidth=0.55, zorder=2)
        legend_pairs = [(mapping[c], c) for c in cats]
        remember(has_data, fills)
    elif map_type in {"graduated-symbol", "boundary", "point"}:
        paint(frame, facecolor="#f4f6f7", edgecolor=NO_DATA_EDGE, linewidth=0.35, zorder=1)
        remember(frame, ["#f4f6f7"] * len(frame))

    insets.clip_for_drawing(frame, inset_plan).dissolve().boundary.plot(
        ax=ax, edgecolor=OUTLINE, linewidth=1.15, zorder=3)

    (minx, miny, maxx, maxy), _ = view_bounds(frame, inset_lon)
    padx, pady = (maxx - minx) * 0.045, (maxy - miny) * 0.045
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.set_aspect("equal")
    ax.set_axis_off()
    span_y = (maxy - miny) + 2 * pady

    # drawn before the labels so its rectangle can be reserved: a place name
    # parked over the inset would be unreadable and would say nothing useful
    inset_box = None
    if inset_plan is not None:
        furn.archipelago_inset(ax, inset_plan, painted,
                               label=spec.get("inset_label"))
        ix, iy, iw, ih = inset_plan["inset_box"]
        inset_box = (ix, iy, ix + iw, iy + ih)

    # --- symbols ----------------------------------------------------------
    symbol_col = spec.get("symbol_column")
    symbol_info = spec.get("symbol_info", {})
    radii: list[float] = []
    symbol_rows = has_data
    if symbol_col and map_type in {"choropleth-symbol", "graduated-symbol"}:
        symbol_rows = frame[frame[symbol_col].notna()]
        radii = symbol_radii(symbol_rows[symbol_col].tolist(), spec.get("symbol_scale", {}),
                             span_y)
        pts = symbol_rows.geometry.representative_point()
        from matplotlib.patches import Circle

        for px, py, r in zip(pts.x, pts.y, radii):
            if r <= 0:
                continue
            ax.add_patch(Circle((px, py), r, facecolor="none", edgecolor=furn.SLATE,
                                lw=1.2, alpha=0.92, zorder=6))

    point_report = None
    if map_type == "point" and spec.get("points") is not None:
        pts = spec["points"]
        # colour says which kind of place, size says how big — the same two
        # channels the area map uses, and chosen by the same rule: a category
        # goes to colour, a magnitude to size
        if pts.get("colours"):
            legend_pairs = list(pts["legend_pairs"])
        ax.scatter(pts["x"], pts["y"],
                   s=pts.get("sizes") or spec.get("point_size", 34),
                   c=pts.get("colours") or furn.PRIMARY,
                   edgecolors="white", linewidths=0.7, alpha=0.9, zorder=6)
        point_report = {"point_count": len(pts["x"])}

    # --- labels -----------------------------------------------------------
    label_mode = spec.get("labels", "names")
    label_report: dict[str, Any] = {"drawn": 0}

    # a proportional-symbol map has no colour column, so its labels come from
    # the symbol column instead
    label_rows, label_col, label_info = has_data, value_col, info
    if map_type == "graduated-symbol" and (value_col is None or not len(has_data)):
        label_rows, label_col, label_info = symbol_rows, symbol_col, symbol_info
    elif map_type in {"boundary", "point"} or value_col is None or not len(has_data):
        # a reference map labels the geography itself; there is no value to show
        label_rows, label_col, label_info = frame, None, {}

    if label_mode != "off" and len(label_rows):
        name_field = spec["name_field"]
        pts = label_rows.geometry.representative_point()
        radius_by_id = {}
        if radii:
            for sid, r in zip(symbol_rows["__shape_id"], radii):
                radius_by_id[sid] = r
        items = []
        areas = label_rows.geometry.area if label_col is None else None
        for i, ((_, row), px, py) in enumerate(zip(label_rows.iterrows(), pts.x, pts.y)):
            value_text = None
            if label_col is not None and label_mode in ("values", "both"):
                # signed change needs a decimal so small movements are not shown as 0
                # the legend already worked out how many decimals this data
                # needs; printing fewer on the map turned 99.74% into "100%",
                # which for viral suppression is a different claim entirely
                decimals = classify.label_decimals(spec.get("bins"))
                if decimals is None:
                    decimals = 1 if label_info.get("semantic") == sem.POINT else 0
                value_text = sem.format_value(row[label_col], label_info,
                                              decimals=decimals, lang=lang)
            if label_col is None:
                # no value to rank by: give the roomiest units their name first
                rank = float(areas.iloc[i])
            else:
                try:
                    rank = abs(float(row[label_col]))
                except (TypeError, ValueError):   # categories have no magnitude
                    rank = 0.0
            items.append({
                "x": px, "y": py, "name": str(row[name_field]),
                "value_text": value_text,
                # No symbol drawn means nothing to keep clear. The default
                # used to be a fraction of the frame, which reserved a circle
                # of blank space around every unit on a plain choropleth --
                # space no ink ever occupied, and enough of it to push names
                # off their own units.
                "keepout": radius_by_id.get(row["__shape_id"], 0.0),
                "rank": rank,
            })
        label_report = lab.place(ax, items, colors=LABEL_COLORS,
                                 fontsize=spec.get("label_fontsize", 8.0),
                                 max_labels=spec.get("max_labels", 45),
                                 keepout_boxes=[inset_box] if inset_box else ())

    if spec.get("scale_bar", True):
        furn.scale_bar(ax, lang=lang)
    if spec.get("north_arrow", True):
        furn.north_arrow(ax, letter=i18n.t(lang, "north"))

    # --- side panel -------------------------------------------------------
    panel = plate.panel_ax
    y = lay.panel_start(plate)
    if legend_pairs:
        y = furn.colour_legend(
            panel, 0.0, y, [c for c, _ in legend_pairs], [l for _, l in legend_pairs],
            spec.get("legend_title", value_col or ""),
            no_data_label=spec.get("no_data_label") or i18n.t(lang, "no_data"),
        )
    if symbol_col and radii:
        vmax = float(spec.get("symbol_scale", {}).get("max_value") or 0) or 1.0
        picks = classify.symbol_legend_values(vmax, integer=bool(symbol_info.get("integer", True)))
        y = furn.symbol_legend(
            panel, 0.0, y - 0.01, picks, spec.get("symbol_legend_title", symbol_col),
            format_value=lambda v: sem.format_value(v, symbol_info, decimals=0, lang=lang),
        )
    elif map_type == "point" and (spec.get("points") or {}).get("size_scale"):
        # the dots are sized by the same s = s_max·(v/vmax) the key draws with,
        # so the key is true for its own map
        scale = spec["points"]["size_scale"]
        size_info = spec["points"].get("size_info", {})
        picks = classify.symbol_legend_values(
            float(scale.get("max_value") or 1.0),
            integer=bool(size_info.get("integer", True)))
        y = furn.symbol_legend(
            panel, 0.0, y - 0.01, picks, scale.get("title", ""),
            format_value=lambda v: sem.format_value(v, size_info, decimals=0, lang=lang),
        )

    locator_drawn = False
    if provinces is not None and locator_name and spec.get("locator", True):
        rect = furn.locator_rect(
            plate.fig, plate.panel_left,
            plate.map_bottom + plate.map_height * max(0.02, y - 0.03),
            plate.panel_width * 0.62, floor=plate.map_bottom,
            # from the country being drawn, not from a constant measured once
            aspect=furn.locator_aspect(provinces),
        )
        if rect is not None:
            furn.locator(plate.fig, rect, provinces, locator_name,
                         name_field=spec.get("province_name_field", "ten_tinh"))
            locator_drawn = True

    # measured last, once every piece of furniture is on the page: a title that
    # runs off the paper is written to the PNG without complaint, and only
    # somebody looking at the image would ever know
    return {"plate": plate, "labels": label_report, "points": point_report,
            "overflow": lay.overflow(plate.fig, panels=[plate.panel_ax]),
            "legend_classes": len(legend_pairs), "locator": locator_drawn,
            # what the framing decided: whether an inset was drawn, and how much
            # of the width the mainland ended up with
            "inset": insets.summary(inset_plan),
            # the rows **as drawn**: an animation recolours ``data_layer`` path
            # by path, so it has to count parts on the same geometry that
            # produced those paths. Handing back the unclipped rows would make
            # the repeat counts disagree with the artist and shift every colour.
            "data_layer": data_layer,
            "fills": shape_fills,
            "data_rows": insets.clip_for_drawing(has_data, inset_plan)}


def part_counts(gdf) -> list[int]:
    """How many drawn paths each feature produces.

    A province is a MultiPolygon — mainland plus islands — so 34 features become
    thousands of paths. A per-feature colour list has to be expanded to match, or
    matplotlib cycles it across the paths and the map turns to noise.
    """
    counts = []
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            counts.append(0)
        elif geom.geom_type.startswith("Multi") or geom.geom_type == "GeometryCollection":
            counts.append(len(geom.geoms))
        else:
            counts.append(1)
    return counts


def save(plate: lay.Plate, folder: Path, name: str, formats: str = "png",
         dpi: int = 220, outline_svg_text: bool = True) -> list[Path]:
    import matplotlib.pyplot as plt

    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    wanted = ["png"] if formats == "png" else (["svg"] if formats == "svg" else ["png", "svg"])
    for fmt in wanted:
        if fmt == "svg":
            # ``outline_svg_text`` used to name a branch that did not do it: the
            # two paths differed only by a dpi that means nothing to SVG and a
            # metadata line. Whether the letters came out as outlines was
            # decided entirely by matplotlib's own ``svg.fonttype``, which this
            # never set — so it happened to work because the default is 'path',
            # and anyone with 'none' in their matplotlibrc got an SVG that
            # names "EasyMap Serif" and falls back wherever that is not
            # installed. Same fault as the page that carried no font of its own.
            with plt.rc_context({"svg.fonttype": "path" if outline_svg_text
                                 else "none"}):
                plate.fig.savefig(folder / f"{name}.svg", format="svg",
                                  facecolor="white",
                                  metadata={"Creator": "easy-map"})
        else:
            plate.fig.savefig(folder / f"{name}.{fmt}", dpi=dpi, facecolor="white")
        written.append(folder / f"{name}.{fmt}")
    plt.close(plate.fig)
    return written
