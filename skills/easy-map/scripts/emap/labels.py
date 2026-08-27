"""Label placement that actually measures the text.

The previous renderer pushed every label radially away from the map centre and
then drew a leader line to a point a fixed distance *above* the text. Because
the text is anchored at its top edge, the line stopped in blank space — the user
saw lines pointing at nothing. In dense areas the radial push also sent a
label's leader straight across a neighbouring commune.

Here each label is tried in eight positions around its feature, the real text
bounding box is measured through the renderer, and a leader is drawn only when
the label had to leave its feature — ending exactly on the box edge nearest the
feature.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

# preference order: below, above, right, left, then diagonals.
# Each entry is (dx, dy, horizontal alignment, vertical alignment of the block).
_DIRECTIONS = [
    (0.0, -1.0, "center", "top"),
    (0.0, 1.0, "center", "bottom"),
    (1.0, 0.0, "left", "center"),
    (-1.0, 0.0, "right", "center"),
    (0.7, -0.7, "left", "top"),
    (-0.7, -0.7, "right", "top"),
    (0.7, 0.7, "left", "bottom"),
    (-0.7, 0.7, "right", "bottom"),
]
#: How far out to try, in multiples of a line of type. Ring 0 is the feature's
#: own anchor point — the name sits *on* the unit it belongs to, which is what
#: an atlas does and what makes a label need no explaining. It was missing:
#: every label started one ring out, already a symbol radius plus four points
#: plus a line of type from the anchor, and on a commune map that is enough to
#: land the name on the neighbour. Measured on 103 communes of Cần Thơ before
#: this was added: 19 of 42 names sat mostly on another unit, and one sat with
#: 2% of itself on the unit it named.
_RINGS = (0.0, 1.0, 1.9, 3.0, 4.4, 6.2)

#: The centred placement ring 0 uses. Kept out of ``_DIRECTIONS`` because the
#: other eight are offsets and this one is not.
_ON_ANCHOR = (0.0, 0.0, "center", "center")

HALO = 2.6


class _Box:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def overlaps(self, other: "_Box", pad: float = 2.0) -> bool:
        return not (self.x1 + pad < other.x0 or other.x1 + pad < self.x0
                    or self.y1 + pad < other.y0 or other.y1 + pad < self.y0)

    def nearest_edge_point(self, px: float, py: float) -> tuple[float, float]:
        x = min(max(px, self.x0), self.x1)
        y = min(max(py, self.y0), self.y1)
        # push the point onto the boundary, not the interior
        if self.x0 < x < self.x1 and self.y0 < y < self.y1:
            dists = {abs(x - self.x0): (self.x0, y), abs(self.x1 - x): (self.x1, y),
                     abs(y - self.y0): (x, self.y0), abs(self.y1 - y): (x, self.y1)}
            return dists[min(dists)]
        return x, y


def _extent(artist, renderer) -> _Box:
    bb = artist.get_window_extent(renderer=renderer)
    return _Box(bb.x0, bb.y0, bb.x1, bb.y1)


def _inside_axes(box: _Box, ax_box: _Box, pad: float = 3.0) -> bool:
    return (box.x0 >= ax_box.x0 + pad and box.x1 <= ax_box.x1 - pad
            and box.y0 >= ax_box.y0 + pad and box.y1 <= ax_box.y1 - pad)


def place(ax, items: Sequence[dict[str, Any]], *, colors: dict[str, str],
          fontsize: float = 8.0, value_fontsize: float | None = None,
          max_labels: int = 45,
          keepout_boxes: Sequence[tuple[float, float, float, float]] = ()) -> dict[str, Any]:
    """Draw labels for ``items``.

    Each item: ``{"x", "y", "name", "value_text", "keepout"}`` in data coords,
    where ``keepout`` is the radius (data units) of the symbol drawn at x, y.

    ``keepout_boxes`` are rectangles in data coords that no label may touch —
    the archipelago inset is one. They are obstacles the map draws itself, so
    nothing in ``items`` describes them.

    Returns a report describing what was drawn, moved or dropped.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_box = _Box(*ax.get_window_extent(renderer=renderer).extents)

    value_fontsize = value_fontsize or fontsize * 0.94
    ranked = sorted(items, key=lambda it: -float(it.get("rank", 0)))
    dropped: list[str] = []
    if len(ranked) > max_labels:
        dropped = [it["name"] for it in ranked[max_labels:]]
        ranked = ranked[:max_labels]

    occupied: list[_Box] = []
    for x0, y0, x1, y1 in keepout_boxes:
        (px0, py0), (px1, py1) = (ax.transData.transform((x0, y0)),
                                  ax.transData.transform((x1, y1)))
        occupied.append(_Box(min(px0, px1), min(py0, py1),
                             max(px0, px1), max(py0, py1)))
    # Features themselves are obstacles, so a label never sits on another
    # symbol. A feature with **no** symbol drawn holds its own box apart: there
    # is no ink at that point, a name belongs on the unit it names, and leaving
    # the box in stopped ring 0 from ever succeeding — every label began one
    # ring out whether it needed to or not.
    #
    # A feature that *does* draw a circle keeps its own box in the list. The
    # name must clear the circle; that is what keepout is for, and dropping it
    # put the name straight on top of the mark.
    own_box: dict[int, _Box] = {}
    for it in items:
        px, py = ax.transData.transform((it["x"], it["y"]))
        r = _radius_px(ax, it.get("keepout", 0.0))
        box = _Box(px - r, py - r, px + r, py + r)
        # asked of the *declared* keepout, not of ``r``: ``_radius_px`` floors
        # at three pixels so that a real symbol always has some clearance, and
        # reading that floor back would say every feature has a symbol
        if not it.get("keepout"):
            own_box[id(it)] = box
        occupied.append(box)

    placed, moved = 0, 0
    import matplotlib.patheffects as pe

    halo = [pe.withStroke(linewidth=HALO, foreground="white")]

    crowded_out: list[str] = []
    name_only: list[str] = []
    for it in ranked:
        px, py = ax.transData.transform((it["x"], it["y"]))
        r = _radius_px(ax, it.get("keepout", 0.0))

        # A name alone fits where a name over its value will not, so a crowded
        # cluster loses the numbers before it loses the place names.
        mine = own_box.get(id(it))
        others = [b for b in occupied if b is not mine]
        best = _search(ax, it, px, py, r, others, ax_box, renderer, fontsize,
                       value_fontsize, colors, halo, with_value=True)
        if best is None and it.get("value_text"):
            best = _search(ax, it, px, py, r, others, ax_box, renderer, fontsize,
                           value_fontsize, colors, halo, with_value=False)
            if best is not None:
                # the reader sees a name with no number next to it and has no way
                # to tell that from a unit whose value is genuinely missing
                name_only.append(it["name"])
        if best is None:
            # Parking it anyway is how a map ends up with one label written over
            # another while the report claims nothing was dropped. Saying so is
            # more useful than drawing it.
            crowded_out.append(it["name"])
            continue

        group, box, ring, dx, dy = best
        occupied.append(box)
        placed += 1
        # A leader says "this name belongs to that place". It is needed
        # exactly when nothing else already says so.
        #
        # On a plain map the anchor is unmarked, so the name has to cover it —
        # anything short of that needs a line. The rule used to be ``ring >
        # 1.0``, which called the first offset "not moved" and drew nothing, so
        # 45% of the names on a commune map sat mostly on somebody else with
        # nothing tying them back.
        #
        # Where a symbol *is* drawn the circle marks the place, and a name
        # resting against it reads as its own without help. Requiring the name
        # to cover the anchor there would put a leader under every label on a
        # proportional-symbol map — measured, 33 of 33 — which is clutter, not
        # explanation.
        covers_anchor = (box.x0 <= px <= box.x1) and (box.y0 <= py <= box.y1)
        against_symbol = bool(it.get("keepout")) and ring <= 1.0
        if not covers_anchor and not against_symbol:
            moved += 1
            ex, ey = box.nearest_edge_point(px, py)
            sx, sy = _edge_of_symbol(px, py, ex, ey, r)
            inv = ax.transData.inverted()
            (dsx, dsy), (dex, dey) = inv.transform((sx, sy)), inv.transform((ex, ey))
            ax.plot([dsx, dex], [dsy, dey], color=colors.get("leader", "#8a969e"),
                    lw=0.7, zorder=7, solid_capstyle="round")

    return {"drawn": placed, "moved": moved, "skipped": dropped,
            "dropped_no_room": crowded_out, "name_only": name_only}


def _search(ax, item, px, py, r, occupied, ax_box, renderer, fontsize,
            value_fontsize, colors, halo, *, with_value: bool):
    """First position, working outwards, where the real text box hits nothing."""
    drawn = dict(item) if with_value else {**item, "value_text": None}
    for ring in _RINGS:
        # ring 0 is one position, not eight: the anchor has no direction
        for dx, dy, ha, va in ([_ON_ANCHOR] if ring == 0.0 else _DIRECTIONS):
            gap = r + 4 + ring * fontsize * 1.15
            cx, cy = px + dx * gap, py + dy * gap
            group = _draw_label(ax, drawn, cx, cy, ha, va, fontsize, value_fontsize,
                                colors, halo)
            box = _union(group, renderer)
            if not any(box.overlaps(o) for o in occupied) and _inside_axes(box, ax_box):
                return group, box, ring, dx, dy
            for a in group:
                a.remove()
    return None


def _radius_px(ax, radius_data: float) -> float:
    if not radius_data:
        return 3.0
    x0, y0 = ax.transData.transform((0, 0))
    x1, _ = ax.transData.transform((radius_data, 0))
    return max(3.0, abs(x1 - x0))


def _draw_label(ax, item, cx, cy, ha, va, fontsize, value_fontsize, colors, halo):
    """Draw name over value as one block whose ``va`` edge sits at ``cy``."""
    inv = ax.transData.inverted()
    has_value = bool(item.get("value_text"))
    line = fontsize * 1.28 * ax.figure.dpi / 72.0  # display px per text line

    if not has_value:
        name_y, name_va = cy, ("center" if va == "center" else va)
        value_y = value_va = None
    elif va == "top":            # whole block hangs below cy
        name_y, name_va = cy, "top"
        value_y, value_va = cy - line, "top"
    elif va == "bottom":         # whole block stands above cy
        name_y, name_va = cy + line, "bottom"
        value_y, value_va = cy, "bottom"
    else:                        # straddles cy
        name_y, name_va = cy, "bottom"
        value_y, value_va = cy, "top"

    nx, ny = inv.transform((cx, name_y))
    artists = [ax.text(nx, ny, item["name"], ha=ha, va=name_va, fontsize=fontsize,
                       color=colors.get("name", "#1b1b1b"), fontweight="semibold",
                       zorder=8, path_effects=halo)]
    if value_y is not None:
        vx, vy = inv.transform((cx, value_y))
        artists.append(ax.text(vx, vy, item["value_text"], ha=ha, va=value_va,
                               fontsize=value_fontsize, color=colors.get("value", "#005eaa"),
                               fontweight="bold", zorder=8, path_effects=halo))
    return artists


def _union(artists, renderer) -> _Box:
    boxes = [_extent(a, renderer) for a in artists]
    return _Box(min(b.x0 for b in boxes), min(b.y0 for b in boxes),
                max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def _edge_of_symbol(px, py, tx, ty, r) -> tuple[float, float]:
    dx, dy = tx - px, ty - py
    n = math.hypot(dx, dy) or 1.0
    return px + dx / n * r, py + dy / n * r
