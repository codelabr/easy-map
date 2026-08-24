"""Capturing a time series for the interactive page.

A video needs hundreds of frames to look smooth. A page where the reader drives
time needs exactly one frame per period, so the interactive export is *smaller*
than the video, not larger.

The frames are the same renders used everywhere else. Everything
about turning them into a page — the shell, the player, zoom, hover — lives in
``webpage``, which the still maps share, so the two exported files behave the
same way and cannot drift apart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from . import i18n, render as render_mod, webpage


def build(deps, *, frame, periods: Sequence[Any],
          values_by_period: dict[Any, dict[int, float]],
          symbols_by_period: dict[Any, dict[int, float]] | None,
          spec: dict[str, Any], fonts: dict[str, str], provinces=None,
          locator_name: str | None = None, out_dir: Path, name: str,
          label: str | None = None) -> dict[str, Any]:
    import matplotlib.pyplot as plt

    lang = i18n.normalise(spec.get("language"))
    missing = webpage.TEXT[lang]["nodata"]
    name_field = spec["name_field"]

    still = dict(spec)
    still["labels"] = "off"
    still["timeline_in"] = 0.0        # the slider replaces the drawn timeline

    images: list[str] = []
    shapes: list[dict[str, Any]] = []
    for index, period in enumerate(periods):
        f = frame.copy()
        f["__value"] = f["__shape_id"].map(values_by_period[period])
        if symbols_by_period is not None:
            f["__symbol"] = f["__shape_id"].map(symbols_by_period[period])
        result = render_mod.draw(deps, frame=f, spec=still, fonts=fonts,
                                 provinces=provinces, locator_name=locator_name)
        plate = result["plate"]
        if index == 0:
            shapes = webpage.outlines(plate.map_ax, f, name_field)
        images.append(webpage.png_b64(plate.fig))
        plt.close(plate.fig)

    def table(source: dict[Any, dict[int, float]] | None,
              column_info: dict[str, Any]) -> dict[str, list[str]]:
        if source is None:
            return {}
        return {shape["id"]: [webpage.cell(source[p].get(int(shape["id"])), column_info,
                                           lang, missing)
                              for p in periods]
                for shape in shapes}

    suffix = f"_{lang}"
    family = name[: -len(suffix)] if name.endswith(suffix) else name
    payload = webpage.entry(
        kind=webpage.SERIES, spec=spec, family=family,
        label=label or spec.get("title") or family,
        images=images, shapes=shapes, periods=periods,
        values=table(values_by_period, spec.get("value_info", {})),
        symbols=table(symbols_by_period, spec.get("symbol_info", {})),
    )
    webpage.stash(out_dir, name, payload)
    report = webpage.build(out_dir, webpage.SERIES) or {}
    report["period_count"] = len(periods)
    report["hoverable_units"] = len(shapes)
    return report
