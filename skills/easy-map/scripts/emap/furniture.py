"""Map furniture: legends, scale bar, north arrow, locator inset.

Everything returns the vertical cursor it finished at, so callers stack blocks
without hand-tuned magic offsets — that is what made the legend, the symbol key
and the locator collide in the earlier build.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

INK = "#1b1b1b"
MUTED = "#6b7780"
PRIMARY = "#005eaa"
HIGHLIGHT = "#fbab18"
SLATE = "#29434e"
HAIRLINE = "#c9d1d6"


def _pt_to_frac(ax, points: float) -> tuple[float, float]:
    """Convert a length in points to (x, y) fractions of the axes."""
    bb = ax.get_window_extent()
    px = points * ax.figure.dpi / 72.0
    return px / bb.width, px / bb.height


def colour_legend(ax, x: float, y: float, colours: Sequence[str], labels: Sequence[str],
                  title: str, *, no_data_label: str | None = "Chưa có số liệu",
                  no_data_colour: str = "#eceef0", fs_title: float = 9.5,
                  fs: float = 9.0, swatch_pt: float = 13.0) -> float:
    """Single column, low class at the top, high class at the bottom."""
    from matplotlib.patches import Rectangle

    ax.text(x, y, title, fontsize=fs_title, fontweight="bold", color=INK,
            transform=ax.transAxes, va="top", ha="left")
    wx, wy = _pt_to_frac(ax, swatch_pt)
    row = wy * 1.75
    y -= wy * 2.3

    rows = list(zip(colours, labels))
    if no_data_label:
        rows.append((no_data_colour, no_data_label))
    for colour, label in rows:
        ax.add_patch(Rectangle((x, y - wy), wx * 1.45, wy, facecolor=colour,
                               edgecolor="#b9c0c5", lw=0.5, transform=ax.transAxes,
                               clip_on=False, zorder=6))
        ax.text(x + wx * 1.9, y - wy * 0.52, label, fontsize=fs, color=INK,
                transform=ax.transAxes, va="center", ha="left")
        y -= row
    return y - wy * 0.6


#: Diameter in points of the largest mark in a size key, and therefore of the
#: largest dot a point map draws. The key and the map must read off the same
#: number: a legend built to one scale and a map drawn to another is a key that
#: is wrong for its own map, which has happened here once already.
SYMBOL_MAX_PT = 26.0

#: Smallest dot that still reads as a dot. A display floor only — it never
#: enters the scale, or the key would stop being true near the bottom.
SYMBOL_MIN_PT = 4.0


def symbol_legend(ax, x: float, y: float, values: Sequence[float], title: str,
                  *, format_value, max_points: float = SYMBOL_MAX_PT, fs_title: float = 9.5,
                  fs: float = 8.5, edge: str = SLATE) -> float:
    """Nested-free circle key. Drawn with scatter so circles stay circular."""
    ax.text(x, y, title, fontsize=fs_title, fontweight="bold", color=INK,
            transform=ax.transAxes, va="top", ha="left")
    if not values:
        return y - 0.05

    vmax = max(values)
    s_max = max_points ** 2
    rx, ry = _pt_to_frac(ax, max_points / 2)
    cy = y - ry * 2.6 - _pt_to_frac(ax, fs_title)[1]

    xs, sizes = [], []
    cx = x + rx
    for v in values:
        xs.append(cx)
        sizes.append(s_max * (v / vmax))
        cx += rx * 2.9
    ax.scatter(xs, [cy] * len(xs), s=sizes, facecolors="none", edgecolors=edge,
               linewidths=1.15, transform=ax.transAxes, clip_on=False, zorder=6)
    for cx, v in zip(xs, values):
        ax.text(cx, cy - ry - _pt_to_frac(ax, fs * 0.6)[1], format_value(v),
                fontsize=fs, color=INK, transform=ax.transAxes, ha="center", va="top")
    return cy - ry - _pt_to_frac(ax, fs * 2.4)[1]


def category_legend(ax, x: float, y: float, pairs: Sequence[tuple[str, str]], title: str,
                    *, no_data_label: str | None = None,
                    fs_title: float = 9.5, fs: float = 9.0) -> float:
    """Nothing calls this yet; the label is a parameter so nothing ever ships a
    Vietnamese caption onto an English map when something does."""
    colours = [c for c, _ in pairs]
    labels = [l for _, l in pairs]
    return colour_legend(ax, x, y, colours, labels, title,
                         no_data_label=no_data_label, fs_title=fs_title, fs=fs)


def nice_length(span_m: float) -> float:
    target = span_m * 0.25
    exp = math.floor(math.log10(max(target, 1.0)))
    for mult in (1, 2, 5):
        cand = mult * 10 ** exp
        if cand >= target * 0.62:
            return cand
    return 10 ** (exp + 1)


def scale_bar(ax, *, x_frac: float = 0.04, y_frac: float = 0.035, fs: float = 8.0,
              lang: str | None = None) -> None:
    from matplotlib.patches import Rectangle

    x0d, x1d = ax.get_xlim()
    y0d, y1d = ax.get_ylim()
    span = x1d - x0d
    length = nice_length(span)
    x0 = x0d + span * x_frac
    y0 = y0d + (y1d - y0d) * y_frac
    h = (y1d - y0d) * 0.0065
    half = length / 2
    ax.add_patch(Rectangle((x0, y0), half, h, facecolor=INK, edgecolor=INK, lw=0.5, zorder=9))
    ax.add_patch(Rectangle((x0 + half, y0), half, h, facecolor="white", edgecolor=INK,
                           lw=0.5, zorder=9))
    for xv, text in ((x0, "0"), (x0 + length, _km(length, lang))):
        ax.text(xv, y0 + h * 2.3, text, ha="center", va="bottom", fontsize=fs,
                color=INK, zorder=9)


def _km(metres: float, lang: str | None = None) -> str:
    """The scale bar's own number, grouped the way the rest of the map is.

    It used to be hard-wired to the Vietnamese convention, so a 1.000 km bar on
    an English map read as one kilometre.
    """
    from . import semantics as sem

    km = metres / 1000.0
    return (f"{sem.group_digits(km, lang)} km" if km >= 1
            else f"{sem.group_digits(metres, lang)} m")


#: The inset's caption. Fixed rather than derived: the shapefile carries only
#: province names, so nothing in the data says "Hoàng Sa". Left untranslated on
#: an English map for the same reason every other Vietnamese toponym is.
ARCHIPELAGO_LABEL = "Hoàng Sa · Trường Sa"

#: How far each island fragment is grown in the inset, as a share of the
#: archipelago region's width. Purely a legibility device — see the note in
#: ``archipelago_inset``.
ISLAND_MARK = 0.012


def archipelago_inset(ax, plan: dict, painted, *, label: str = ARCHIPELAGO_LABEL):
    """A framed corner box carrying the offshore island groups.

    The layers are repainted exactly as the main map painted them — same subset,
    same colours — so a province coloured by its value keeps that colour out at
    sea. Drawing the inset from its own colour logic would be a second place for
    the same decision, and the two would drift.

    Island fragments are a few hundred metres across at this scale, so they are
    stroked more heavily than on the main map. Without that they render as
    nothing at all: a box the reader cannot interpret is worse than no box.
    """
    x0, y0, w, h = plan["ô_khung_phụ"]
    iminx, iminy, imaxx, imaxy = plan["vùng_quần_đảo"]

    # position the child axes over that rectangle of the parent's data space
    bounds = _axes_fraction(ax, x0, y0, w, h)
    box = ax.inset_axes(bounds, transform=ax.transAxes, zorder=8)
    box.set_facecolor("white")
    for spine in box.spines.values():
        spine.set_edgecolor(SLATE)
        spine.set_linewidth(0.7)
    box.set_xticks([])
    box.set_yticks([])

    # A Trường Sa cay is a few hundred metres across. At this scale that is less
    # than one pixel, so drawing the geometry faithfully produces an empty box.
    # Enlarging the marks is standard practice for features too small to show at
    # the map's scale — the inset states position, not extent.
    import shapely.geometry as sg

    region = sg.box(iminx, iminy, imaxx, imaxy)
    grow = (imaxx - iminx) * ISLAND_MARK
    for rows, kwargs in painted:
        if not len(rows):
            continue
        marks = rows.geometry.intersection(region)
        keep = [i for i, geom in enumerate(marks) if not geom.is_empty]
        if not keep:
            continue                       # this layer has nothing out at sea

        options = dict(kwargs)
        options["linewidth"] = max(float(options.get("linewidth", 0.35)), 0.5)
        # the caller's colour list is positional, so it is filtered alongside
        colour = options.get("color")
        if isinstance(colour, (list, tuple)) and len(colour) == len(rows):
            options["color"] = [colour[i] for i in keep]
        rows.iloc[keep].set_geometry(marks.iloc[keep].buffer(grow)).plot(
            ax=box, **options)

    padx = (imaxx - iminx) * 0.06
    pady = (imaxy - iminy) * 0.06
    box.set_xlim(iminx - padx, imaxx + padx)
    box.set_ylim(iminy - pady, imaxy + pady)
    box.set_aspect("equal")

    box.text(0.5, 0.985, label, transform=box.transAxes, ha="center", va="top",
             fontsize=6.4, color=INK, zorder=9)
    return box


def _axes_fraction(ax, x0: float, y0: float, w: float, h: float) -> list[float]:
    """A data-space rectangle expressed in the axes' own 0–1 coordinates."""
    xlo, xhi = ax.get_xlim()
    ylo, yhi = ax.get_ylim()
    return [(x0 - xlo) / (xhi - xlo), (y0 - ylo) / (yhi - ylo),
            w / (xhi - xlo), h / (yhi - ylo)]


def north_arrow(ax, *, x_frac: float = 0.96, y_frac: float = 0.93, fs: float = 9.0,
                letter: str = "B") -> None:
    from matplotlib.patches import Polygon

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * x_frac
    y = y0 + (y1 - y0) * y_frac
    s = (y1 - y0) * 0.030
    pts = [[x, y + s], [x - s * 0.40, y - s * 0.55], [x, y - s * 0.20], [x + s * 0.40, y - s * 0.55]]
    ax.add_patch(Polygon(pts, closed=True, facecolor=INK, edgecolor="white", lw=0.6, zorder=9))
    ax.text(x, y + s * 1.30, letter, ha="center", va="bottom", fontsize=fs,
            fontweight="bold", color=INK, zorder=9)


#: Vietnam's bounding box is roughly 1 wide to 2.2 tall.
LOCATOR_ASPECT = 2.2


def locator(fig, rect, provinces, highlight: str, *, name_field: str = "ten_tinh",
            fs: float = 7.5, caption: str | None = None):
    """Small orientation map. ``rect`` must already respect LOCATOR_ASPECT."""
    ax = fig.add_axes(rect)
    provinces.plot(ax=ax, facecolor="#ccd4d9", edgecolor="white", linewidth=0.3)
    sel = provinces[provinces[name_field] == highlight]
    if not sel.empty:
        sel.plot(ax=ax, facecolor=HIGHLIGHT, edgecolor="#6d4700", linewidth=0.9)
    ax.set_axis_off()
    ax.set_aspect("equal")
    ax.text(0.5, -0.015, caption if caption is not None else highlight,
            transform=ax.transAxes, ha="center", va="top", fontsize=fs, color=MUTED)
    return ax


def locator_rect(fig, x: float, top: float, width_frac: float, *,
                 floor: float = 0.0, caption_frac: float = 0.022) -> list[float] | None:
    """Size a locator box so Vietnam is not squashed and never crosses ``floor``.

    ``floor`` is the bottom of the map band; the caption sits just under the box,
    so the box has to stop short of it. Returns None when there is no usable room
    rather than drawing over the footer.
    """
    fw, fh = fig.get_size_inches()
    available = top - floor - caption_frac
    if available <= 0.02:
        return None
    height = width_frac * (fw / fh) * LOCATOR_ASPECT
    if height > available:
        height = available
        width_frac = height / ((fw / fh) * LOCATOR_ASPECT)
    return [x, top - height, width_frac, height]
