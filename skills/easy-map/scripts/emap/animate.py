"""Turning a period-by-period map into a slow, readable video.

Two rules keep an animated map honest:

* **One classification for the whole series.** If breaks were recomputed per
  frame the colours would flicker without the data changing, and a viewer would
  read movement that is not there.
* **No invented in-between values.** Each period is held long enough to read,
  and periods are joined by a short cross-dissolve. The dissolve is a visual
  transition, not a claim about a measurement between two reporting periods —
  which is why it is brief and the timeline marker moves through it.

MP4 needs ffmpeg. When it is missing the writer falls back to GIF and says so;
it never fails silently.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from . import (classify, furniture as furn, i18n, messages as msg,
               render as render_mod, semantics as sem)

HOLD_SECONDS = 1.8
FADE_SECONDS = 0.35
FPS = 25
#: vertical band reserved under the map for the timeline
TIMELINE_INCHES = 0.95

TIMELINE_TRACK = "#d7dde1"
TIMELINE_DONE = furn.PRIMARY
TIMELINE_MARK = furn.HIGHLIGHT


def available_writer(matplotlib_module) -> tuple[str, str]:
    """Return ``(writer, container)`` — mp4 when ffmpeg is usable, else gif."""
    from matplotlib import animation

    if animation.writers.is_available("ffmpeg"):
        return "ffmpeg", "mp4"
    return "pillow", "gif"


def _hex_to_rgb(colour: str) -> tuple[float, float, float]:
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _blend(a: str, b: str, t: float) -> tuple[float, float, float]:
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return (ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def _frame_plan(periods: Sequence[Any]) -> list[tuple[int, int, float]]:
    """(from index, to index, blend) for every video frame."""
    hold = max(1, int(round(HOLD_SECONDS * FPS)))
    fade = max(1, int(round(FADE_SECONDS * FPS)))
    plan: list[tuple[int, int, float]] = []
    for i in range(len(periods)):
        plan.extend((i, i, 0.0) for _ in range(hold))
        if i < len(periods) - 1:
            plan.extend((i, i + 1, (step + 1) / (fade + 1)) for step in range(fade))
    return plan


class Timeline:
    """A track under the map so the viewer always knows where in time they are."""

    def __init__(self, fig, rect, periods: Sequence[Any], fonts: dict[str, str]):
        self.ax = fig.add_axes(rect)
        self.ax.set_axis_off()
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)
        self.periods = list(periods)
        n = max(1, len(self.periods) - 1)
        self.positions = [i / n for i in range(len(self.periods))]

        self.ax.plot([0, 1], [0.55, 0.55], color=TIMELINE_TRACK, lw=2.4,
                     solid_capstyle="round", zorder=1)
        self.done, = self.ax.plot([0, 0], [0.55, 0.55], color=TIMELINE_DONE, lw=2.4,
                                  solid_capstyle="round", zorder=2)
        self.ax.scatter(self.positions, [0.55] * len(self.positions), s=14,
                        facecolors="white", edgecolors=TIMELINE_TRACK, linewidths=1.0,
                        zorder=3)
        self.mark = self.ax.scatter([0], [0.55], s=90, facecolors=TIMELINE_MARK,
                                    edgecolors="#6d4700", linewidths=0.8, zorder=4)
        self.label = self.ax.text(0, 0.02, "", ha="left", va="bottom", fontsize=15,
                                  fontweight="bold", color=furn.INK,
                                  fontfamily=fonts["display"])
        for pos, period in zip(self.positions, self.periods):
            self.ax.text(pos, 0.95, str(period), ha="center", va="bottom", fontsize=6.5,
                         color=furn.MUTED, rotation=0 if len(self.periods) <= 10 else 40)

    def update(self, index: int, blend: float, target: int) -> None:
        here = self.positions[index]
        there = self.positions[target]
        pos = here + (there - here) * blend
        self.done.set_data([0, pos], [0.55, 0.55])
        self.mark.set_offsets([[pos, 0.55]])
        self.label.set_text(str(self.periods[target if blend >= 0.5 else index]))


def build(deps, *, frame, periods: Sequence[Any], values_by_period: dict[Any, dict[int, float]],
          symbols_by_period: dict[Any, dict[int, float]] | None,
          spec: dict[str, Any], fonts: dict[str, str], provinces=None,
          locator_name: str | None = None, out_dir: Path, name: str) -> dict[str, Any]:
    """Render the whole series to one video file."""
    import matplotlib.pyplot as plt
    from matplotlib import animation

    lang = i18n.normalise(spec.get("language"))
    edges = spec["bins"]["edges"]
    colours = classify.palette(len(edges) - 1, diverging=spec.get("diverging", False))
    info = spec.get("value_info", {})

    # a still frame first, so layout, legend, locator and footer are already set
    first = dict(spec)
    first["labels"] = "off"
    first["timeline_in"] = TIMELINE_INCHES
    frame = frame.copy()
    frame["__value"] = frame["__shape_id"].map(values_by_period[periods[0]])
    if symbols_by_period is not None:
        frame["__symbol"] = frame["__shape_id"].map(symbols_by_period[periods[0]])

    result = render_mod.draw(deps, frame=frame, spec=first, fonts=fonts,
                             provinces=provinces, locator_name=locator_name)
    plate = result["plate"]
    ax = plate.map_ax

    data_layer = result["data_layer"]
    data_rows = result["data_rows"]
    ordered_ids = list(data_rows["__shape_id"])
    # one colour per drawn path, not per province: islands make the two differ
    repeats = render_mod.part_counts(data_rows)

    if plate.timeline_rect is None:
        raise RuntimeError(msg.text("video.thiếu-chỗ-thanh-thời-gian"))
    timeline = Timeline(plate.fig, plate.timeline_rect, periods, fonts)

    symbol_artist = None
    symbol_ids: list[int] = []
    if symbols_by_period is not None:
        pts = frame[frame["__symbol"].notna()].geometry.representative_point()
        symbol_ids = list(frame[frame["__symbol"].notna()]["__shape_id"])
        symbol_artist = ax.scatter(pts.x, pts.y, s=[0] * len(symbol_ids),
                                   facecolors="none", edgecolors=furn.SLATE,
                                   linewidths=1.2, zorder=6)

    span_y = frame.total_bounds[3] - frame.total_bounds[1]
    scale = spec.get("symbol_scale", {})

    def colour_of(period, shape_id):
        value = values_by_period[period].get(shape_id)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return render_mod.NO_DATA_FILL
        return colours[classify.class_index(value, edges)]

    def radius_of(period, shape_id):
        if symbols_by_period is None:
            return 0.0
        value = symbols_by_period[period].get(shape_id)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0.0
        return render_mod.symbol_radii([value], scale, span_y)[0]

    plan = _frame_plan(periods)

    def update(frame_index: int):
        i, j, blend = plan[frame_index]
        a, b = periods[i], periods[j]
        if data_layer is not None:
            per_feature = [_blend(colour_of(a, sid), colour_of(b, sid), blend)
                           for sid in ordered_ids]
            data_layer.set_facecolors(
                [colour for colour, times in zip(per_feature, repeats)
                 for _ in range(times)])
        if symbol_artist is not None:
            sizes = []
            for sid in symbol_ids:
                ra, rb = radius_of(a, sid), radius_of(b, sid)
                r = ra + (rb - ra) * blend
                sizes.append(_radius_to_points(ax, r) ** 2)
            symbol_artist.set_sizes(sizes)
        timeline.update(i, blend, j)
        return []

    writer_name, container = available_writer(deps.matplotlib)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.{container}"
    anim = animation.FuncAnimation(plate.fig, update, frames=len(plan), interval=1000 / FPS,
                                   blit=False)
    if writer_name == "ffmpeg":
        writer = animation.FFMpegWriter(fps=FPS, bitrate=4200,
                                        extra_args=["-pix_fmt", "yuv420p"])
    else:
        writer = animation.PillowWriter(fps=min(FPS, 15))
    anim.save(str(path), writer=writer, dpi=spec.get("dpi", 140))
    plt.close(plate.fig)

    return {
        "files": str(path),
        "format": container,
        "ffmpeg": writer_name == "ffmpeg",
        "period_count": len(periods),
        "frame_count": len(plan),
        "duration_s": round(len(plan) / FPS, 1),
        "note": msg.text("video.mp4-bằng-ffmpeg" if writer_name == "ffmpeg"
                            else "video.không-có-ffmpeg"),
    }


def _radius_to_points(ax, radius_data: float) -> float:
    if radius_data <= 0:
        return 0.0
    x0, _ = ax.transData.transform((0, 0))
    x1, _ = ax.transData.transform((radius_data, 0))
    return abs(x1 - x0) * 72.0 / ax.figure.dpi * 2
