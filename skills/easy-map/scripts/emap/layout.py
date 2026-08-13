"""Page composition.

Two approved layouts:

``report``    print-first plate — thin primary-blue rule, serif headline,
              legend column on the left, map on the right.
``banner``  solid primary-blue title band, map on the left, legend
              rail on the right.

The figure is sized from the *geometry*, not from a fixed 16:9 canvas, and the
map axes is shrunk to hug the mapped area so no dead space is left beside it.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

from . import furniture as furn

LAYOUTS = ("report", "banner")

MARGIN_IN = 0.62
COLUMN_IN = 2.30
FOOTER_IN = 1.30          # room for a source line plus a two-line method note
SOURCE_Y_IN = 0.86
METHOD_Y_IN = 0.62
RULE_Y_IN = 1.08


@dataclass
class Plate:
    fig: Any
    map_ax: Any
    panel_ax: Any
    panel_left: float          # figure-fraction x of the panel
    panel_width: float
    map_bottom: float
    map_height: float
    layout: str
    fonts: dict[str, str]
    notes: list[str] = field(default_factory=list)
    #: band reserved under the map for an animation timeline, empty when unused
    timeline_rect: list[float] | None = None


def wrap(text: str, fontsize_pt: float, width_in: float, max_lines: int = 3) -> str:
    """Approximate wrap: a sans glyph averages ~0.52 em wide."""
    if not text:
        return ""
    # 0.58 em is a safe average for Open Sans carrying Vietnamese diacritics;
    # a generous estimate is what pushed the footer off the page previously.
    chars = max(12, int(width_in * 72 / (fontsize_pt * 0.58)))
    lines = textwrap.wrap(text, width=chars)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" ,;.") + "…"
    return "\n".join(lines)


def map_size(aspect: float, *, long_side_in: float = 8.6) -> tuple[float, float]:
    """Pick map width/height from the shape of the area being drawn."""
    aspect = max(0.25, min(4.0, aspect))
    if aspect >= 1.0:
        w = long_side_in
        h = long_side_in / aspect
    else:
        h = long_side_in
        w = long_side_in * aspect
    return max(4.2, min(10.5, w)), max(4.2, min(10.5, h))


def fit_rect(fig, rect, aspect, halign="center", valign="center") -> list[float]:
    x, y, w, h = rect
    fw, fh = fig.get_size_inches()
    aw, ah = w * fw, h * fh
    if ah <= 0 or aw <= 0:
        return list(rect)
    if aw / ah > aspect:
        new_w = (ah * aspect) / fw
        if halign == "center":
            x += (w - new_w) / 2
        elif halign == "right":
            x += w - new_w
        w = new_w
    else:
        new_h = (aw / aspect) / fh
        if valign == "center":
            y += (h - new_h) / 2
        elif valign == "top":
            y += h - new_h
        h = new_h
    return [x, y, w, h]


def build(layout: str, aspect: float, *, kicker: str, title: str, insight: str,
          source: str, method: str, fonts: dict[str, str], dpi: int = 220,
          side_panel: bool = True, timeline_in: float = 0.0) -> Plate:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    if layout not in LAYOUTS:
        layout = "report"
    map_w, map_h = map_size(aspect)
    notes: list[str] = []

    column_in = COLUMN_IN if side_panel else 0.0
    gutter_in = 0.30 if side_panel else 0.0

    footer_in = FOOTER_IN + timeline_in

    if layout == "report":
        fig_w = MARGIN_IN * 2 + column_in + gutter_in + map_w
        header_in = 1.95
        fig_h = header_in + map_h + footer_in
        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor="white")
        L = MARGIN_IN / fig_w
        R = 1 - MARGIN_IN / fig_w
        top = 1 - 0.42 / fig_h

        fig.add_artist(Line2D([L, R], [top, top], color=furn.PRIMARY, lw=3.0))
        fig.text(L, top - 0.30 / fig_h, kicker, fontsize=8.5, color=furn.PRIMARY,
                 fontweight="bold", va="top")
        title_text = wrap(title, 17.5, fig_w - MARGIN_IN * 2, 2)
        fig.text(L, top - 0.60 / fig_h, title_text, fontsize=17.5, color=furn.INK,
                 va="top", fontfamily=fonts["display"], fontweight="bold", linespacing=1.25)
        insight_in = 0.60 + (title_text.count("\n") + 1) * 0.32 + 0.14
        fig.text(L, top - insight_in / fig_h, wrap(insight, 10.5, fig_w - MARGIN_IN * 2, 2),
                 fontsize=10.5, color=furn.MUTED, va="top", linespacing=1.35)

        map_bottom = footer_in / fig_h
        map_height = top - (header_in - 0.42) / fig_h - map_bottom
        col_w = (column_in + gutter_in) / fig_w
        map_ax = fig.add_axes(fit_rect(fig, [L + col_w, map_bottom, R - L - col_w, map_height],
                                       aspect,
                                       halign="right" if side_panel else "center",
                                       valign="top"))
        panel_ax = fig.add_axes([L, map_bottom, max(col_w, 0.01), map_height])
        panel_ax.set_axis_off()
        panel_left, panel_width = L, column_in / fig_w if side_panel else 0.0

        fig.add_artist(Line2D([L, R], [RULE_Y_IN / fig_h, RULE_Y_IN / fig_h],
                              color=furn.HAIRLINE, lw=0.8))
        fig.text(L, SOURCE_Y_IN / fig_h, wrap(source, 8, fig_w - MARGIN_IN * 2, 1),
                 fontsize=8, color=furn.MUTED, va="top")
        fig.text(L, METHOD_Y_IN / fig_h, wrap(method, 8, fig_w - MARGIN_IN * 2, 2),
                 fontsize=8, color=furn.MUTED, va="top", linespacing=1.3)

    else:  # banner
        rail_in = COLUMN_IN + 0.55
        fig_w = MARGIN_IN * 2 + map_w + rail_in
        band_in = 1.05
        fig_h = band_in + 0.35 + map_h + footer_in
        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor="white")
        L = MARGIN_IN / fig_w
        R = 1 - MARGIN_IN / fig_w
        band_h = band_in / fig_h

        fig.add_artist(Rectangle((0, 1 - band_h), 1, band_h, facecolor=furn.PRIMARY,
                                 transform=fig.transFigure, zorder=0))
        fig.text(L, 1 - 0.24 / fig_h, kicker, fontsize=8.5, color="#bfe0f5",
                 fontweight="bold", va="top")
        fig.text(L, 1 - 0.44 / fig_h, wrap(title, 17, fig_w - MARGIN_IN * 2, 2),
                 fontsize=17, color="white", va="top", fontweight="bold", linespacing=1.2)

        map_bottom = footer_in / fig_h
        map_top = 1 - band_h - 0.28 / fig_h
        map_height = map_top - map_bottom
        rail_w = rail_in / fig_w
        map_ax = fig.add_axes(fit_rect(fig, [L, map_bottom, R - L - rail_w - 0.02, map_height],
                                       aspect, halign="center", valign="top"))
        panel_left = R - rail_w
        panel_ax = fig.add_axes([panel_left, map_bottom, rail_w, map_height])
        panel_ax.set_axis_off()
        panel_width = rail_w
        fig.add_artist(Line2D([panel_left - 0.012, panel_left - 0.012],
                              [map_bottom, map_top], color=furn.HAIRLINE, lw=0.9))
        panel_ax.text(0, 0.99, wrap(insight, 10, rail_in - 0.3, 4), fontsize=10,
                      color=furn.INK, transform=panel_ax.transAxes, va="top", ha="left",
                      linespacing=1.35)

        fig.add_artist(Line2D([L, R], [RULE_Y_IN / fig_h, RULE_Y_IN / fig_h],
                              color=furn.HAIRLINE, lw=0.8))
        fig.text(L, SOURCE_Y_IN / fig_h, wrap(source, 8, fig_w - MARGIN_IN * 2, 1),
                 fontsize=8, color=furn.MUTED, va="top")
        fig.text(L, METHOD_Y_IN / fig_h, wrap(method, 8, fig_w - MARGIN_IN * 2, 2),
                 fontsize=8, color=furn.MUTED, va="top", linespacing=1.3)

    timeline_rect = None
    if timeline_in > 0:
        # sits between the footer rule and the map, never on top of either
        box = map_ax.get_position()
        timeline_rect = [box.x0, (RULE_Y_IN + 0.18) / fig_h, box.width,
                         (timeline_in - 0.30) / fig_h]

    return Plate(fig=fig, map_ax=map_ax, panel_ax=panel_ax, panel_left=panel_left,
                 panel_width=panel_width, map_bottom=map_bottom, map_height=map_height,
                 layout=layout, fonts=fonts, notes=notes, timeline_rect=timeline_rect)


#: A text box may hang this far past the page edge before it is called
#: overflow. Anti-aliasing and font hinting put a glyph's measured box a
#: fraction of a point outside its ink, and reporting that as clipping would
#: cry wolf on every second map.
OVERFLOW_SLACK_PT = 1.0


def overflow(fig, *, slack: float = OVERFLOW_SLACK_PT, panels=()) -> list[dict[str, Any]]:
    """Text that has left the space it was given.

    Two ways that happens, and only the first is obvious. A title too long for
    a narrow layout runs past the **paper** and is cut when the file is written.
    A legend heading too long for its column stays on the paper but runs out of
    its **panel** and across the map — nothing is cut, the PNG looks finished,
    and the map now has a sentence lying over it. Both were found by looking at
    images rather than by anything raising.

    ``panels`` are axes whose contents must stay inside them; text elsewhere is
    measured against the page. Map labels are excluded on purpose — they have
    their own placement pass, which already reports what it could not fit.

    Returns one entry per offending piece of text, naming the side it left by
    and how far, in points.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    watched = [ax for ax in panels if ax is not None]

    # only text somebody put here on purpose. Walking every Text on the figure
    # also picks up each axes' tick labels, which sit outside their axes by
    # design — seven false reports on a panel carrying one sentence.
    items: list[tuple[Any, Any]] = [(t, None) for t in fig.texts]
    for ax in watched:
        items += [(t, ax) for t in ax.texts]

    out: list[dict[str, Any]] = []
    for artist, owner in items:
        if not artist.get_visible() or not str(artist.get_text()).strip():
            continue
        try:
            box = artist.get_window_extent(renderer=renderer)
        except Exception:                      # pragma: no cover - exotic artists
            continue
        if box.width <= 0 or box.height <= 0:
            continue
        frame = owner.bbox if owner is not None else fig.bbox
        sides = {"trái": frame.x0 - box.x0, "phải": box.x1 - frame.x1,
                 "dưới": frame.y0 - box.y0, "trên": box.y1 - frame.y1}
        side, over = max(sides.items(), key=lambda kv: kv[1])
        if over > slack:
            out.append({"chữ": str(artist.get_text())[:60], "phía": side,
                        "ra_khỏi": "trang" if owner is None else "cột chú giải",
                        "vượt_pt": round(over * 72.0 / fig.dpi, 1)})
    return out


def panel_start(plate: Plate) -> float:
    """Where legend stacking begins inside the side panel."""
    return 0.985 if plate.layout == "report" else 0.985 - _insight_drop(plate)


def _insight_drop(plate: Plate) -> float:
    # the banner rail carries the insight sentence above the legends
    return 0.14
