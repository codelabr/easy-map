"""Self-contained pages that carry every map from one request.

A request produces at most two of them and they never link to each other: one
holds the still maps, one holds the time series. Each carries its own images,
outlines and numbers inline, so a single file can be emailed on its own and
still work with no network, no shapefile and no sibling PNG next to it.

Outlines are the reason a page cannot be assembled from finished PNG files
alone: hit-testing a province needs its real polygon in image coordinates, and
that only exists while the figure is still open. So every render drops a payload
into a cache folder inside the request directory, and the page is rebuilt from
the whole cache each time. Rendering a second edition — another language,
another layout — therefore adds to the page instead of replacing it.
"""

from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path
from typing import Any, Sequence

from . import i18n, semantics as sem, spotlight

#: Screen resolution, not print resolution. The PNG files next to the page stay
#: at full DPI; embedding those would multiply the page size for detail nobody
#: can see until they zoom far past what the geometry supports.
HTML_DPI = 150

#: outline detail is reduced to keep the page small; 1.5 screen pixels is well
#: below what a reader can distinguish
SIMPLIFY_PIXELS = 1.5

CACHE_DIR = ".interactive"
STILL, SERIES = "still", "series"
PAGES = {STILL: "interactive_map.html", SERIES: "map_over_time.html"}

TEXT = {
    "vi": {
        "play": "Chạy", "pause": "Dừng", "period": "Kỳ",
        "map": "Bản đồ", "language": "Ngôn ngữ", "search": "Tìm đơn vị…",
        "download": "Tải ảnh bản đồ này",
        "zoom_in": "Phóng to", "zoom_out": "Thu nhỏ", "reset": "Về khung ban đầu",
        "nodata": "chưa có số liệu", "nomatch": "không tìm thấy",
        "area": "Diện tích", "population": "Dân số", "density": "Mật độ",
        "points": "Số điểm", "close": "Đóng",
        "unit_area": "km²", "unit_density": "người/km²",
        "hint_still": "Bấm vào một đơn vị để xem chi tiết. Rê chuột để xem nhanh số "
                      "liệu. Bấm nút + để phóng to (hoặc giữ Ctrl và lăn chuột), kéo "
                      "để di chuyển, bấm đúp để về khung ban đầu.",
        "hint_series": "Kéo thanh trượt hoặc dùng phím ← →. Rê chuột vào một đơn vị để "
                       "xem số liệu. Bấm nút + để phóng to (hoặc giữ Ctrl và lăn chuột), "
                       "bấm đúp để về khung ban đầu.",
    },
    "en": {
        "play": "Play", "pause": "Pause", "period": "Period",
        "map": "Map", "language": "Language", "search": "Find a unit…",
        "download": "Download this map image",
        "zoom_in": "Zoom in", "zoom_out": "Zoom out", "reset": "Reset the view",
        "nodata": "no data", "nomatch": "no match",
        "area": "Area", "population": "Population", "density": "Density",
        "points": "Locations", "close": "Close",
        "unit_area": "km²", "unit_density": "people/km²",
        "hint_still": "Click a unit for its details. Hover for a quick reading. "
                      "Use + to zoom (or Ctrl + scroll), drag to pan, double-click "
                      "to reset.",
        "hint_series": "Drag the slider or use ← →. Hover a unit to see its value. "
                       "Use + to zoom (or Ctrl + scroll), double-click to reset.",
    },
}

#: Inline so the page stays self-contained — an icon font would be one more
#: thing to fetch, and the whole point is that this file works with no network.
ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.5 5.6v12.8L19 12z"/></svg>'
ICON_PAUSE = ('<svg viewBox="0 0 24 24" aria-hidden="true">'
              '<rect x="7.6" y="5.6" width="3.4" height="12.8" rx="1.1"/>'
              '<rect x="13" y="5.6" width="3.4" height="12.8" rx="1.1"/></svg>')
ICON_IN = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5v12M5 11h12" '
           'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/></svg>')
ICON_OUT = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 11h12" '
            'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/></svg>')
ICON_RESET = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path '
              'd="M5.5 10a6.5 6.5 0 1 1 1.2 4.4M5.5 5.5V10h4.5" stroke="currentColor" '
              'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>')
ICON_SAVE = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path '
             'd="M12 4v10m0 0 4-4m-4 4-4-4M5 18h14" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>')


# --- capture -------------------------------------------------------------

def png_b64(fig, dpi: int = HTML_DPI) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, facecolor="white")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def outlines(ax, rows, name_field: str) -> list[dict[str, Any]]:
    """Feature outlines in percent-of-image coordinates, ready for an SVG overlay.

    Each shape also carries what the detail panel needs: which of its subpaths
    form the main landmass (``main``, left out when that is all of them) and the
    bounding box of those subpaths (``box``), in the same percent coordinates as
    ``d``.
    """
    fig = ax.figure
    width_px, height_px = fig.get_size_inches() * fig.dpi
    x0, x1 = ax.get_xlim()
    tolerance = (x1 - x0) / max(width_px, 1) * SIMPLIFY_PIXELS

    def to_percent(xy) -> list[tuple[float, float]]:
        return [(px / width_px * 100, (height_px - py) / height_px * 100)
                for px, py in ax.transData.transform(xy)]

    by_row = {}
    for position, (_, row) in enumerate(rows.iterrows()):
        geom = row.geometry
        if geom is not None and not geom.is_empty:
            by_row[position] = spotlight.parts(geom)
    simplified = _simplify_together(by_row, tolerance)

    shapes: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(rows.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pieces = by_row[position]
        keep, _ = spotlight.main_parts(geom)

        commands: list[str] = []
        drawn_from: list[int] = []        # geometry part behind each subpath
        for index, part in enumerate(pieces):
            simple = simplified[(position, index)]
            if simple.is_empty or not hasattr(simple, "exterior"):
                continue
            coords = list(simple.exterior.coords)
            if len(coords) < 3:
                continue
            commands.append("M" + "L".join(f"{x:.3f},{y:.3f}"
                                           for x, y in to_percent(coords)) + "Z")
            drawn_from.append(index)
        if not commands:
            continue

        shape: dict[str, Any] = {"id": str(int(row["__shape_id"])),
                                 "name": str(row[name_field]),
                                 "d": " ".join(commands)}

        # a simplified part can vanish, so the main list is expressed over the
        # subpaths that survived rather than over the original parts
        keep_set = set(keep)
        main = [i for i, part in enumerate(drawn_from) if part in keep_set]
        if main and len(main) < len(commands):
            shape["main"] = main
        chosen = [pieces[drawn_from[i]] for i in (main or range(len(drawn_from)))]
        if chosen:
            shape.update(_spot(chosen, to_percent))
        shapes.append(shape)
    return shapes


def _simplify_together(by_row: dict[int, Sequence[Any]], tolerance: float
                       ) -> dict[tuple[int, int], Any]:
    """Thin every outline, keeping the border between two units a single line.

    Simplifying each polygon on its own is what the page did, and it is wrong in
    a way that only shows on hover: two units share a border, each keeps a
    different subset of its points, and the two simplified edges no longer
    coincide. Where they cross, one unit's fill lies over its neighbour's — and
    the browser hands the pointer to whichever path is later in the document.
    Where they part, a strip belongs to neither and the pointer hits nothing.
    Measured on the 34 provinces: 13 of 789 interior probes named the wrong
    unit or no unit at all.

    ``coverage_simplify`` removes the same points from both sides of a shared
    edge, so the two stay one line. It needs the input to *be* a coverage —
    polygons that meet exactly and do not overlap — which a boundary file
    normally is and is checked here rather than assumed. When it is not, or when
    the installed Shapely predates the function, each part is thinned on its own
    as before: the page is then no worse than it was.
    """
    flat: list[Any] = []
    index: list[tuple[int, int]] = []
    for position, pieces in by_row.items():
        for i, part in enumerate(pieces):
            flat.append(part)
            index.append((position, i))
    if not flat:
        return {}

    try:
        import numpy as np
        import shapely

        array = np.array(flat, dtype=object)
        if shapely.coverage_is_valid(array):
            thinned = shapely.coverage_simplify(array, tolerance)
            return dict(zip(index, thinned))
    except Exception:                    # pragma: no cover - old Shapely, odd data
        pass
    return {key: part.simplify(tolerance, preserve_topology=True)
            for key, part in zip(index, flat)}


def _spot(pieces: Sequence[Any], to_percent) -> dict[str, Any]:
    """Bounding box of the main landmass, in the page's percent coordinates.

    The panel frames the unit by this box, so it is the only geometry the page
    needs: where the silhouette sits and how large it is.
    """
    corners = to_percent([(b[0], b[1]) for b in (p.bounds for p in pieces)]
                         + [(b[2], b[3]) for b in (p.bounds for p in pieces)])
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    return {"box": [round(min(xs), 3), round(min(ys), 3),
                    round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)]}


def cell(value: Any, info: dict[str, Any], lang: str, missing: str) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return missing
    return sem.format_value(value, info, lang=lang)


#: Shapefile columns behind the three facts the detail card adds to the mapped
#: value. They describe the unit itself, not the dataset, so they are the same on
#: every map of the same places — and they are what a reader reaches for first
#: when a number looks surprising.
FACT_FIELDS = (("area", "dtich_km2"), ("population", "dan_so"), ("density", "matdo_km2"))


def facts(rows, lang: str) -> dict[str, dict[str, str]]:
    """Area, population and density per feature, formatted for the map's language.

    A column the shapefile does not carry is left out rather than reported as
    zero: "0 people" is a claim, "not shown" is the truth.
    """
    out: dict[str, dict[str, str]] = {}
    present = [(key, col) for key, col in FACT_FIELDS if col in rows.columns]
    if not present:
        return out
    for _, row in rows.iterrows():
        found: dict[str, str] = {}
        for key, col in present:
            value = row[col]
            if value is None or value != value:          # NaN
                continue
            found[key] = (sem.group_digits(float(value), lang) if key == "population"
                          else sem.localise_digits(f"{float(value):,.1f}", lang))
        if found:
            out[str(int(row["__shape_id"]))] = found
    return out


def entry(*, kind: str, spec: dict[str, Any], family: str, label: str,
          images: Sequence[str], shapes: list[dict[str, Any]],
          periods: Sequence[Any] = (), values: dict[str, list[str]] | None = None,
          symbols: dict[str, list[str]] | None = None,
          fills: dict[str, str] | None = None,
          unit_facts: dict[str, dict[str, str]] | None = None,
          points: dict[str, str] | None = None) -> dict[str, Any]:
    """One selectable map inside a page."""
    return {
        "kind": kind,
        "lang": i18n.normalise(spec.get("language")),
        "family": family,
        "label": label,
        "layout": spec.get("layout", ""),
        "title": spec.get("title", ""),
        "periods": [str(p) for p in periods],
        "images": list(images),
        "shapes": shapes,
        "values": values or {},
        "symbols": symbols or {},
        "fills": fills or {},
        "facts": unit_facts or {},
        "points": points or {},
        "legend": {"value": spec.get("legend_title") or "",
                   "symbol": spec.get("symbol_legend_title") or ""},
    }


def capture_still(plate, frame, spec: dict[str, Any], *, family: str, label: str,
                  fills: dict[str, str] | None = None,
                  point_counts: dict[str, int] | None = None) -> dict[str, Any]:
    """Payload for one finished still map. Call before the figure is closed."""
    lang = i18n.normalise(spec.get("language"))
    missing = TEXT[lang]["nodata"]
    shapes = outlines(plate.map_ax, frame, spec["name_field"])

    def column(col: str | None, info: dict[str, Any]) -> dict[str, list[str]]:
        if not col or col not in frame.columns:
            return {}
        table = {str(int(sid)): value for sid, value in zip(frame["__shape_id"], frame[col])}
        return {s["id"]: [cell(table.get(s["id"]), info, lang, missing)] for s in shapes}

    return entry(
        kind=STILL, spec=spec, family=family, label=label,
        images=[png_b64(plate.fig)], shapes=shapes,
        values=column(spec.get("value_column"), spec.get("value_info", {})),
        symbols=column(spec.get("symbol_column"), spec.get("symbol_info", {})),
        fills=fills or {},
        unit_facts=facts(frame, lang),
        points={str(k): sem.group_digits(v, lang)
                for k, v in (point_counts or {}).items()},
    )


def stash(run_dir: Path, key: str, payload: dict[str, Any]) -> Path:
    folder = run_dir / CACHE_DIR / payload["kind"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# --- assembly ------------------------------------------------------------

def _name_apart(entries: list[dict[str, Any]]) -> None:
    """Give two maps that share a label something to tell them apart by.

    The same map drawn in both layouts reaches the page under one title, and a
    picker offering the same line twice is worse than no picker at all. The
    layout is only mentioned when it is doing that work.
    """
    seen: dict[tuple[str, str], int] = {}
    for e in entries:
        key = (e["lang"], e["label"])
        seen[key] = seen.get(key, 0) + 1
    for e in entries:
        if seen[(e["lang"], e["label"])] > 1 and e.get("layout"):
            e["label"] = f"{e['label']}  ·  {e['layout']}"


def build(run_dir: Path, kind: str) -> dict[str, Any] | None:
    """Rebuild one page from every payload captured in this request so far."""
    folder = run_dir / CACHE_DIR / kind
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not files:
        return None
    entries = []
    for path in files:
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    if not entries:
        return None

    _name_apart(entries)
    languages = sorted({e["lang"] for e in entries})
    preferred = "vi" if "vi" in languages else languages[0]
    title = next((e["title"] for e in entries if e["lang"] == preferred and e["title"]),
                 entries[0]["title"])

    path = run_dir / PAGES[kind]
    path.write_text(_page(title, {"entries": entries, "text": TEXT},
                          lang=preferred), encoding="utf-8")
    return {
        "files": str(path),
        "format": "html",
        "maps_in_page": len(entries),
        "language": languages,
        "size_mb": round(path.stat().st_size / 1_048_576, 2),
        "note": "One self-contained file: send it on its own and it still opens, with nothing else beside it.",
    }


def _page(title: str, payload: dict[str, Any], lang: str = "vi") -> str:
    # The page's own text follows the reader's language already; the document's
    # lang attribute did not, so an English page told the browser and every
    # screen reader it was Vietnamese.
    return (PAGE
            .replace("__LANG__", html.escape(lang))
            .replace("__TITLE__", html.escape(title or TEXT[lang]["map"]))
            .replace("__ICON_PLAY__", ICON_PLAY)
            .replace("__ICON_PAUSE__", ICON_PAUSE)
            .replace("__ICON_IN__", ICON_IN)
            .replace("__ICON_OUT__", ICON_OUT)
            .replace("__ICON_RESET__", ICON_RESET)
            .replace("__ICON_SAVE__", ICON_SAVE)
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False)))


#: Written as a plain string rather than an f-string: the page is mostly CSS and
#: JavaScript, and doubling every brace to survive formatting is how a working
#: page becomes an unmaintainable one.
PAGE = """<!doctype html>
<html lang="__LANG__">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { --ink:#1b1b1b; --muted:#6b7780; --blue:#005eaa; --line:#d7dde1;
          --amber:#fbab18; --paper:#fff; }
  * { box-sizing:border-box; }
  body { margin:0; padding:18px; background:#fff; color:var(--ink);
         font-family:"Open Sans","Segoe UI",Arial,sans-serif; }
  .wrap { max-width:1180px; margin:0 auto; }

  .topbar { display:flex; align-items:center; gap:12px; flex-wrap:wrap;
            margin:0 0 14px; }
  .topbar label { font-size:11px; letter-spacing:.08em; text-transform:uppercase;
                  color:var(--muted); }
  select, .find { font:inherit; font-size:13.5px; color:var(--ink); background:#fff;
                  border:1px solid var(--line); border-radius:4px; padding:7px 10px; }
  select { max-width:min(520px, 60vw); }
  select:focus-visible, .find:focus-visible { outline:2px solid var(--blue);
                                              outline-offset:1px; }
  .find { width:190px; }
  .grow { flex:1 1 auto; }
  .langs { display:flex; border:1px solid var(--line); border-radius:4px; overflow:hidden; }
  /* a single-language request leaves this empty; without the rule the border
     alone still draws a stray sliver next to the download button */
  .langs:empty { display:none; }
  .langs button { font:inherit; font-size:12.5px; font-weight:600; letter-spacing:.04em;
                  text-transform:uppercase; border:0; background:#fff; color:var(--muted);
                  padding:7px 12px; cursor:pointer; }
  .langs button + button { border-left:1px solid var(--line); }
  .langs button[aria-pressed="true"] { background:var(--blue); color:#fff; }
  .icon { border:1px solid var(--line); background:#fff; color:var(--muted);
          border-radius:4px; width:34px; height:34px; padding:0; cursor:pointer;
          display:grid; place-items:center; transition:color .15s, border-color .15s; }
  .icon:hover { color:var(--blue); border-color:var(--blue); }
  .icon svg { width:19px; height:19px; display:block; }

  .viewport { position:relative; overflow:hidden; background:#fff;
              border:1px solid var(--line); border-radius:3px;
              touch-action:pan-y; }
  .canvas { position:relative; transform-origin:0 0; line-height:0; }
  .canvas img { width:100%; height:auto; display:block; }
  .canvas svg { position:absolute; inset:0; width:100%; height:100%; }
  /* pointer-events:fill — the hover target is the shape, not its outline.
     SVG's default stroke-width is 1 *user unit*, and this viewBox is 100 wide
     against an image some 700px wide, so an invisible 7px-thick outline was
     collecting the mouse. Near a border the stroke of whichever feature is
     drawn later sat over its neighbour's interior, and the tooltip named the
     wrong province. Measured: 45 of 131 interior points resolved to another
     feature. */
  .canvas path { fill:transparent; stroke:transparent; stroke-width:0;
                 pointer-events:fill; cursor:pointer; }
  .canvas path:hover { fill:rgba(251,171,24,.34); stroke:#8a5a00; stroke-width:.14; }
  /* A search hit has to read against the darkest end of a blue ramp, so it is
     nearly opaque amber rather than a tint — a translucent wash disappeared
     exactly on the units a reader is most likely to be hunting for. */
  .canvas path.found { fill:rgba(247,148,10,.80); stroke:#6d3b00; stroke-width:.34; }
  .viewport[data-grab="1"] .canvas path { cursor:grab; }
  .viewport[data-drag="1"] .canvas path { cursor:grabbing; }

  /* top right, not bottom right: a national map is taller than the window, and
     controls parked at its foot are below the fold exactly when they are wanted */
  .zoombar { position:absolute; right:10px; top:10px; display:flex; gap:6px; }
  .zoombar .icon { background:rgba(255,255,255,.94); box-shadow:0 1px 4px rgba(0,0,0,.14); }

  /* the player sits above the map for the same reason */
  .bar { display:flex; align-items:center; gap:20px; margin:0 0 4px;
         padding-top:14px; border-top:1px solid var(--line); }
  .bar[hidden] { display:none; }

  /* round icon button, sized by touch guidance rather than by its glyph */
  .play { flex:none; width:46px; height:46px; border:0; border-radius:50%;
          background:var(--blue); color:#fff; cursor:pointer; padding:0;
          display:grid; place-items:center;
          transition:background .15s, transform .1s, box-shadow .15s;
          box-shadow:0 1px 3px rgba(0,0,0,.18); }
  .play:hover { background:#004a86; box-shadow:0 2px 7px rgba(0,0,0,.22); }
  .play:active { transform:scale(.94); }
  .play:focus-visible { outline:3px solid var(--amber); outline-offset:3px; }
  .play svg { width:22px; height:22px; fill:currentColor; display:block; }
  .play svg:last-child { display:none; }
  .play[data-playing="1"] svg:first-child { display:none; }
  .play[data-playing="1"] svg:last-child { display:block; }

  .track { flex:1; position:relative; }
  input[type=range] { -webkit-appearance:none; appearance:none; width:100%;
                      height:22px; margin:0; background:transparent; cursor:pointer;
                      display:block; }
  input[type=range]::-webkit-slider-runnable-track {
      height:6px; border-radius:3px;
      background:linear-gradient(to right, var(--blue) var(--pct,0%),
                                 var(--line) var(--pct,0%)); }
  input[type=range]::-moz-range-track { height:6px; border-radius:3px;
      background:linear-gradient(to right, var(--blue) var(--pct,0%),
                                 var(--line) var(--pct,0%)); }
  /* the amber knob echoes the marker on the video's timeline */
  input[type=range]::-webkit-slider-thumb { -webkit-appearance:none; appearance:none;
      width:18px; height:18px; margin-top:-6px; border-radius:50%;
      background:var(--amber); border:2px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.32); transition:transform .1s; }
  input[type=range]::-moz-range-thumb { width:18px; height:18px; border-radius:50%;
      background:var(--amber); border:2px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.32); }
  input[type=range]:active::-webkit-slider-thumb { transform:scale(1.18); }
  input[type=range]:focus-visible { outline:none; }
  input[type=range]:focus-visible::-webkit-slider-thumb {
      box-shadow:0 0 0 4px rgba(251,171,24,.45); }

  /* notches cut into the track itself, so they read against the filled blue
     and the empty grey alike; the two ends are hidden because the track edge
     already marks them */
  .ticks { position:absolute; left:9px; right:9px; top:8px; height:6px;
           display:flex; justify-content:space-between; pointer-events:none; }
  .ticks i { width:2px; height:6px; border-radius:1px; background:#fff; opacity:.9; }
  .ticks i:first-child, .ticks i:last-child { opacity:0; }
  .ends { display:flex; justify-content:space-between; margin:3px 9px 0;
          font-size:11px; color:var(--muted); }

  .readout { flex:none; min-width:104px; text-align:right; }
  .readout small { display:block; font-size:11px; letter-spacing:.08em;
                   text-transform:uppercase; color:var(--muted); }
  .readout b { font-size:26px; font-weight:700; line-height:1.15;
               font-variant-numeric:tabular-nums; }
  .hint { color:var(--muted); font-size:12.5px; margin:10px 0 14px; }
  .tip { position:fixed; pointer-events:none; background:#fff; border:1px solid var(--line);
         border-left:3px solid var(--blue); border-radius:3px; padding:7px 11px;
         font-size:13px; line-height:1.45; box-shadow:0 2px 10px rgba(0,0,0,.13);
         opacity:0; transition:opacity .1s; z-index:9; }
  .tip b { display:block; font-size:14px; }
  .tip span { color:var(--muted); }

  /* --- the detail panel -----------------------------------------------
     Clicking a unit opens a panel: the unit drawn large above, its numbers
     below. The panel grows out of the unit's own place on the map — it starts
     the size and position of the shape the reader just clicked, so the eye
     follows one movement instead of losing the thread and finding a dialog. */
  .spot { position:fixed; inset:0; z-index:20; display:grid;
          place-items:center; padding:16px; }
  .spot[hidden] { display:none; }
  .veil { position:absolute; inset:0; background:rgba(255,255,255,.89);
          opacity:0; transition:opacity .26s ease; }
  .spot.on .veil { opacity:1; }

  .panel { position:relative; width:min(462px, 86%); background:#fff;
           border:1px solid var(--ink); box-shadow:0 10px 34px rgba(0,0,0,.22);
           /* the flight: the panel is laid out at full size and drawn small at
              the unit's position, so nothing reflows while it moves */
           transform-origin:50% 50%; will-change:transform;
           transition:transform .34s cubic-bezier(.22,.72,.28,1); }
  .panel > * { opacity:0; transition:opacity .2s ease .14s; }
  .spot.on .panel > * { opacity:1; }

  /* overflow:hidden is a guard, not decoration. An <svg> sized only by inset
     takes its height from the viewBox's own ratio, not from `bottom` — the
     silhouette came out 766px tall in a 368px frame and covered the page. */
  .portrait { position:relative; aspect-ratio:5 / 4; overflow:hidden;
              border-bottom:1px solid var(--ink); }
  .portrait h3 { position:absolute; left:15px; top:12px; right:44px; margin:0;
                 font-size:16.5px; line-height:1.25; font-weight:700;
                 letter-spacing:-.01em; }
  .stage { position:absolute; left:15px; right:15px; top:34px; bottom:15px; }
  .stage svg { display:block; width:100%; height:100%; }
  .portrait path { stroke:#3b4c56; stroke-width:1.1; stroke-linejoin:round;
                   vector-effect:non-scaling-stroke; }
  /* A point map fills its areas with #f4f6f7, which against white is no shape
     at all. The fill stays honest — it is what the map was painted — so the
     outline carries the form instead. */
  .portrait.pale path { stroke:#5d707b; stroke-width:1.6; }

  .facts { margin:0; display:grid; grid-template-columns:1fr 1fr; }
  .facts .col { padding:13px 16px 14px; display:grid; gap:11px;
                align-content:start; }
  .facts .col + .col { border-left:1px solid var(--blue); }
  .stat span { display:block; font-size:10.5px; letter-spacing:.08em;
               text-transform:uppercase; color:var(--muted); margin-bottom:2px; }
  .stat b { font-size:17px; font-weight:700; line-height:1.2;
            font-variant-numeric:tabular-nums; }
  /* a missing value is a fact about the data, so it is stated, not emphasised */
  .stat b.none { font-weight:400; font-style:italic; color:var(--muted);
                 font-size:14px; }
  .stat u { text-decoration:none; font-weight:400; font-size:11.5px;
            color:var(--muted); margin-left:4px; }

  .panel .x { position:absolute; top:8px; right:8px; width:28px; height:28px;
              border:0; background:none; color:var(--ink); font-size:20px;
              line-height:1; cursor:pointer; border-radius:3px; padding:0;
              z-index:2; }
  .panel .x:hover { background:rgba(0,0,0,.06); }
  .panel .x:focus-visible { outline:2px solid var(--blue); outline-offset:1px; }
  @media (prefers-reduced-motion:reduce) {
    .veil, .panel, .panel > * { transition-duration:.01ms; }
  }
</style>
<div class="wrap">
  <div class="topbar">
    <label for="pick" id="pickLabel"></label>
    <select id="pick"></select>
    <span class="grow"></span>
    <input class="find" id="find" type="search" autocomplete="off">
    <div class="langs" id="langs"></div>
    <button class="icon" id="save">__ICON_SAVE__</button>
  </div>
  <div class="bar" id="player" hidden>
    <button class="play" id="toggle" data-playing="0">__ICON_PLAY____ICON_PAUSE__</button>
    <div class="track">
      <input id="slider" type="range" min="0" value="0" step="1">
      <div class="ticks" id="ticks"></div>
      <div class="ends"><span id="first"></span><span id="last"></span></div>
    </div>
    <div class="readout"><small id="periodLabel"></small><b id="period"></b></div>
  </div>
  <p class="hint" id="hint"></p>
  <div class="viewport" id="viewport">
    <div class="canvas" id="canvas">
      <img id="frame" alt="" draggable="false">
      <svg id="hit" viewBox="0 0 100 100" preserveAspectRatio="none"></svg>
    </div>
    <div class="zoombar" id="zoombar">
      <button class="icon" id="zoomOut">__ICON_OUT__</button>
      <button class="icon" id="zoomIn">__ICON_IN__</button>
      <button class="icon" id="zoomReset">__ICON_RESET__</button>
    </div>
  </div>
</div>
<div class="tip" id="tip"></div>
<!-- Outside the map: a national map is taller than the window, so a panel
     centred on the map itself can open below the fold. -->
<div class="spot" id="spot" hidden>
  <div class="veil" id="veil"></div>
  <div class="panel" id="panel" role="dialog" aria-modal="true" aria-labelledby="cardName">
    <div class="portrait" id="portrait">
      <h3 id="cardName"></h3>
      <button class="x" id="spotClose">&times;</button>
      <div class="stage">
        <svg id="lift" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          <g id="liftG"><path id="lifted"></path></g>
        </svg>
      </div>
    </div>
    <div class="facts" id="cardRows"></div>
  </div>
</div>
<script>
const D = __DATA__;
const E = D.entries;
const $ = id => document.getElementById(id);
const img = $('frame'), hit = $('hit'), tip = $('tip'), pick = $('pick');
const viewport = $('viewport'), canvas = $('canvas'), find = $('find');
const player = $('player'), slider = $('slider'), toggle = $('toggle');

let lang = E.some(e => e.lang === 'vi') ? 'vi' : E[0].lang;
let cur = 0, at = 0, timer = null, hovering = null;
let z = 1, tx = 0, ty = 0, dragging = false, moved = false, px = 0, py = 0;

const plain = s => (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                            .replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();

/* --- language and map selection ------------------------------------- */
const langs = [...new Set(E.map(e => e.lang))];
if (langs.length > 1) {
  $('langs').innerHTML = langs.map(l =>
    `<button data-lang="${l}">${l}</button>`).join('');
  $('langs').addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (!b) return;
    /* Matching by slug alone is not enough: the slug comes from the title, and
       an English edition is titled by the agent, not translated from the
       Vietnamese one. So fall back to the same position in the other
       language's list, which is the order the maps were rendered in. */
    const family = E[cur].family;
    const here = E.map((e, i) => i).filter(i => E[i].lang === lang).indexOf(cur);
    lang = b.dataset.lang;
    const there = E.map((e, i) => i).filter(i => E[i].lang === lang);
    const twin = E.findIndex(e => e.lang === lang && e.family === family);
    fillPicker();
    select(twin >= 0 ? twin : (there[here] !== undefined ? there[here] : there[0]), true);
  });
}

function words() { return D.text[lang] || D.text.vi; }

function fillPicker() {
  const w = words();
  const mine = E.map((e, i) => [e, i]).filter(([e]) => e.lang === lang);
  pick.innerHTML = mine.map(([e, i]) => `<option value="${i}"></option>`).join('');
  mine.forEach(([e], k) => { pick.options[k].textContent = e.label; });
  /* Hidden on how many maps the PAGE holds, not how many this language holds.
     Keying it to the language made the box vanish when switching to an edition
     that had only one map — the toolbar reshuffled and the reader was left
     wondering where the list went. */
  const alone = E.length < 2;
  pick.hidden = alone;
  $('pickLabel').hidden = alone;
  $('pickLabel').textContent = w.map;
  find.placeholder = w.search;
  $('save').title = w.download;
  $('zoomIn').title = w.zoom_in;
  $('zoomOut').title = w.zoom_out;
  $('zoomReset').title = w.reset;
  $('spotClose').title = w.close;
  $('spotClose').setAttribute('aria-label', w.close);
  $('periodLabel').textContent = w.period;
  langs.forEach(l => {
    const b = $('langs').querySelector(`[data-lang="${l}"]`);
    if (b) b.setAttribute('aria-pressed', String(l === lang));
  });
}

function select(index, keepPeriod) {
  if (index < 0) index = 0;
  closeSpot(true);      /* the panel belongs to one unit on one map */
  cur = index;
  const e = E[cur];
  lang = e.lang;
  const w = words();
  pick.value = String(cur);
  hit.innerHTML = e.shapes.map(s =>
    `<path d="${s.d}" data-id="${s.id}"></path>`).join('');
  const series = e.periods.length > 1;
  player.hidden = !series;
  $('hint').textContent = series ? w.hint_series : w.hint_still;
  if (series) {
    slider.max = e.periods.length - 1;
    slider.setAttribute('aria-label', w.period);
    $('ticks').innerHTML = e.periods.map(() => '<i></i>').join('');
    $('first').textContent = e.periods[0];
    $('last').textContent = e.periods[e.periods.length - 1];
  }
  at = keepPeriod ? Math.min(at, Math.max(e.images.length - 1, 0)) : 0;
  reset();
  show(at);
  mark();
}

/* --- frame ----------------------------------------------------------- */
function show(i) {
  const e = E[cur];
  at = i;
  img.src = 'data:image/png;base64,' + e.images[i];
  img.alt = e.periods[i] || e.label;
  if (e.periods.length > 1) {
    $('period').textContent = e.periods[i];
    slider.value = i;
    slider.setAttribute('aria-valuetext', e.periods[i]);
    const last = e.periods.length - 1;
    slider.style.setProperty('--pct', (last ? (i / last) * 100 : 0) + '%');
  }
  if (hovering) fill(hovering);
}

function fill(id) {
  const e = E[cur];
  const shape = e.shapes.find(s => s.id === id);
  if (!shape) return;
  let body = `<b>${shape.name}</b>`;
  if (e.values[id]) body += `<span>${e.legend.value}:</span> ${e.values[id][at]}`;
  if (e.symbols[id]) body += `<br><span>${e.legend.symbol}:</span> ${e.symbols[id][at]}`;
  tip.innerHTML = body;
}

/* --- zoom and pan ---------------------------------------------------- */
function apply() {
  /* clientWidth, not getBoundingClientRect: the rect includes the 1px border,
     and using it leaves the map sitting a pixel off its own frame at rest */
  const vw = viewport.clientWidth, vh = viewport.clientHeight;
  const w = canvas.offsetWidth * z, h = canvas.offsetHeight * z;
  tx = w <= vw ? (vw - w) / 2 : Math.min(0, Math.max(vw - w, tx));
  ty = h <= vh ? (vh - h) / 2 : Math.min(0, Math.max(vh - h, ty));
  canvas.style.transform = `translate(${tx}px, ${ty}px) scale(${z})`;
  viewport.dataset.grab = z > 1 ? '1' : '0';
}
function reset() { z = 1; tx = 0; ty = 0; apply(); }
function zoomAt(factor, cx, cy) {
  const next = Math.min(8, Math.max(1, z * factor));
  if (next === z) return;
  tx = cx - (cx - tx) * (next / z);
  ty = cy - (cy - ty) * (next / z);
  z = next;
  apply();
}
function center(factor) {
  zoomAt(factor, viewport.clientWidth / 2, viewport.clientHeight / 2);
}
/* The map fills most of the page, so swallowing the wheel would trap the reader
   above the player. Ctrl+wheel is also what a trackpad pinch sends, so pinching
   zooms the map and a plain scroll still scrolls the page. */
viewport.addEventListener('wheel', ev => {
  if (spotOn()) return;
  if (!ev.ctrlKey && !ev.metaKey) return;
  ev.preventDefault();
  const box = viewport.getBoundingClientRect();
  zoomAt(ev.deltaY < 0 ? 1.18 : 1 / 1.18,
         ev.clientX - box.left - viewport.clientLeft,
         ev.clientY - box.top - viewport.clientTop);
}, { passive: false });
viewport.addEventListener('pointerdown', ev => {
  moved = false;               /* every press starts a fresh click-or-drag */
  if (spotOn() || z <= 1) return;
  dragging = true; px = ev.clientX; py = ev.clientY;
  viewport.dataset.drag = '1';
  viewport.setPointerCapture(ev.pointerId);
});
viewport.addEventListener('pointermove', ev => {
  if (!dragging) return;
  tx += ev.clientX - px; ty += ev.clientY - py;
  px = ev.clientX; py = ev.clientY;
  moved = true; tip.style.opacity = 0;
  apply();
});
function endDrag() { dragging = false; viewport.dataset.drag = '0'; }
viewport.addEventListener('pointerup', endDrag);
viewport.addEventListener('pointercancel', endDrag);
viewport.addEventListener('dblclick', () => { if (!spotOn()) reset(); });
$('zoomIn').addEventListener('click', () => center(1.5));
$('zoomOut').addEventListener('click', () => center(1 / 1.5));
$('zoomReset').addEventListener('click', reset);
/* The buttons live inside the map, so without this the map's own gestures eat
   them: a second quick click on + reaches the viewport as a dblclick and resets
   the zoom, and holding a button starts a pan the moment the mouse twitches. */
['pointerdown', 'mousedown', 'dblclick'].forEach(kind =>
  $('zoombar').addEventListener(kind, ev => ev.stopPropagation()));
addEventListener('resize', apply);

/* --- hover ----------------------------------------------------------- */
hit.addEventListener('mousemove', ev => {
  if (dragging || spotOn()) return;
  const id = ev.target.dataset ? ev.target.dataset.id : null;
  if (!id) { tip.style.opacity = 0; hovering = null; return; }
  hovering = id; fill(id);
  tip.style.opacity = 1;
  tip.style.left = Math.min(ev.clientX + 16, innerWidth - tip.offsetWidth - 12) + 'px';
  tip.style.top = (ev.clientY + 16) + 'px';
});
hit.addEventListener('mouseleave', () => { tip.style.opacity = 0; hovering = null; });

/* --- detail view ------------------------------------------------------
   The unit is redrawn from the outline the page already carries: `main` names
   the subpaths of the main landmass, so a province that reaches 400 km out to
   sea is enlarged on its mainland instead of on a frame that is mostly water.
   Nothing here re-measures geometry — every number was decided at render time,
   so the same click gives the same view every time the file is opened. */
const spot = $('spot'), panel = $('panel'), lifted = $('lifted');
const portrait = $('portrait'), liftG = $('liftG'), lift = $('lift');
let flying = null;         /* the shape the open panel belongs to */

/* Rough perceived brightness of a #rrggbb fill, 0 dark to 1 white. */
function luminance(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return 0;
  const n = parseInt(m[1], 16);
  return (0.299 * (n >> 16 & 255) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255;
}

/* Two columns, filled down the left one first, as many rows as there are facts.
   The number of facts changes with the map — five on a choropleth with circles,
   three on a boundary map — so the grid follows the content rather than padding
   itself out to a fixed six. */
function facts(e, id) {
  const w = words(), items = [];
  /* A value the dataset does not carry arrives here already spelled "no data" by
     the renderer, whichever column it came from. One test decides that, so the
     colour row and the circle row cannot end up disagreeing about how the same
     absence looks — which they did: one stated it, the other shouted it. */
  const gone = v => !v || v === w.nodata;
  /* The unit is guarded too, though no row today can be both missing and
     carrying one — the shapefile facts leave a fact out rather than emit an
     empty one. It is here so that "no data km²" cannot appear if that changes. */
  const add = (label, value, unit) => items.push(
    `<div class="stat"><span>${label}</span>` +
    `<b class="${gone(value) ? 'none' : ''}">${gone(value) ? w.nodata : value}` +
    (unit && !gone(value) ? `<u>${unit}</u>` : '') + `</b></div>`);

  if (e.legend.value) add(e.legend.value, e.values[id] ? e.values[id][at] : null, '');
  if (e.symbols[id]) add(e.legend.symbol, e.symbols[id][at], '');
  if (e.points[id]) add(w.points, e.points[id], '');
  const f = e.facts[id] || {};
  if (f.area) add(w.area, f.area, w.unit_area);
  if (f.population) add(w.population, f.population, '');
  if (f.density) add(w.density, f.density, w.unit_density);

  const split = Math.ceil(items.length / 2);
  const left = items.slice(0, split).join('');
  const right = items.slice(split).join('');
  return `<div class="col">${left}</div>` + (right ? `<div class="col">${right}</div>` : '');
}

/* Where the unit is on screen right now, in window coordinates.

   Measured from `box` — the main landmass — and NOT from the outline's own
   bounding rectangle. The outline covers every fragment a unit owns, so for
   Khánh Hòa it reaches out to Trường Sa: a rectangle 378px wide centred at sea,
   while the land the reader clicked is a third of that and elsewhere. The panel
   would then fly from a place nobody pointed at.

   Read through the canvas's live rectangle, which already carries the zoom and
   the pan, so the flight starts where the reader is actually looking. */
function unitOnScreen(s) {
  const c = canvas.getBoundingClientRect();
  const [bx, by, bw, bh] = s.box;
  return {left: c.left + bx / 100 * c.width, top: c.top + by / 100 * c.height,
          width: Math.max(bw / 100 * c.width, 1),
          height: Math.max(bh / 100 * c.height, 1)};
}

/* The panel's rectangle at rest, worked out rather than measured.

   Measuring meant clearing the transform and reading the rectangle back, which
   is wrong twice over: mid-flight the read returns wherever the animation has
   got to, and the clearing itself starts a transition towards nothing. Both
   showed up as a closing flight that ended hundreds of pixels from the unit.

   ``offsetWidth``/``offsetHeight`` are layout sizes, untouched by any transform,
   and the panel is centred in ``.spot`` — which never moves. */
function panelAtRest() {
  const box = spot.getBoundingClientRect();
  const w = panel.offsetWidth, h = panel.offsetHeight;
  return {left: box.left + (box.width - w) / 2, top: box.top + (box.height - h) / 2,
          width: w, height: h};
}

function startTransform(s) {
  const from = unitOnScreen(s);
  const to = panelAtRest();
  if (!to.width) return 'scale(.9)';
  const k = Math.max(Math.min(from.width / to.width, from.height / to.height), .04);
  return `translate(${(from.left + from.width / 2) - (to.left + to.width / 2)}px,` +
         `${(from.top + from.height / 2) - (to.top + to.height / 2)}px) scale(${k})`;
}

function openSpot(id) {
  const e = E[cur];
  const s = e.shapes.find(x => x.id === id);
  if (!s || !s.box) return;

  const subs = s.d.trim().split(/(?=M)/);
  const use = s.main ? s.main.map(i => subs[i]).filter(Boolean) : subs;
  lifted.setAttribute('d', use.join(' '));
  const paint = e.fills[id] || '#e9edef';
  lifted.setAttribute('fill', paint);
  portrait.classList.toggle('pale', luminance(paint) > 0.90);

  /* The outline's x is a share of the image width and its y a share of the
     height, so the two axes are not the same unit. Multiplying x by the image's
     aspect puts both in one square unit, and the viewBox is written in those —
     otherwise every silhouette arrives stretched. */
  const [bx, by, bw, bh] = s.box;
  const a = (img.naturalWidth || 1) / (img.naturalHeight || 1);
  liftG.setAttribute('transform', `scale(${a} 1)`);
  lift.setAttribute('viewBox', `${bx * a} ${by} ${Math.max(bw * a, .001)} ${Math.max(bh, .001)}`);

  $('cardName').textContent = s.name;
  $('cardRows').innerHTML = facts(e, id);

  spot.hidden = false;
  flying = s;
  panel.style.transform = startTransform(s);
  /* one frame at the starting size, or the browser coalesces both states and
     the panel simply appears */
  requestAnimationFrame(() => requestAnimationFrame(() => {
    spot.classList.add('on');
    panel.style.transform = 'none';
  }));
  $('spotClose').focus();
}

function closeSpot(instant) {
  if (spot.hidden) return;
  spot.classList.remove('on');
  const done = () => { spot.hidden = true; lifted.removeAttribute('d'); flying = null; };
  if (instant === true) { panel.style.transform = 'none'; done(); return; }
  /* Worked out again now, not reused from the opening. The page can be scrolled
     or the window resized while the panel is up, and either moves the unit under
     it — a stored transform would then land the panel next to the unit rather
     than on it. */
  panel.style.transform = flying ? startTransform(flying) : 'scale(.9)';
  panel.addEventListener('transitionend', done, {once: true});
  setTimeout(done, 500);          /* a tab in the background fires no transition */
}
const spotOn = () => !spot.hidden;

hit.addEventListener('click', ev => {
  if (moved) return;                       /* the end of a pan is not a click */
  const id = ev.target.dataset ? ev.target.dataset.id : null;
  if (id) { tip.style.opacity = 0; openSpot(id); }
});
$('veil').addEventListener('click', closeSpot);
$('spotClose').addEventListener('click', closeSpot);
addEventListener('keydown', ev => { if (ev.key === 'Escape') closeSpot(); });

/* --- find a unit ------------------------------------------------------ */
function mark() {
  const q = plain(find.value.trim());
  let hits = 0;
  hit.querySelectorAll('path').forEach(p => {
    const shape = E[cur].shapes.find(s => s.id === p.dataset.id);
    const on = q.length > 0 && shape && plain(shape.name).includes(q);
    p.classList.toggle('found', !!on);
    if (on) hits++;
  });
  find.style.borderColor = (q && !hits) ? '#c1272d' : '';
  find.title = (q && !hits) ? words().nomatch : '';
}
find.addEventListener('input', mark);

/* --- player ----------------------------------------------------------- */
function stop() {
  clearInterval(timer); timer = null;
  toggle.dataset.playing = '0';
  toggle.setAttribute('aria-label', words().play);
  toggle.title = words().play;
}
function play() {
  toggle.dataset.playing = '1';
  toggle.setAttribute('aria-label', words().pause);
  toggle.title = words().pause;
  timer = setInterval(() => show(at >= E[cur].periods.length - 1 ? 0 : at + 1), 1400);
}
toggle.addEventListener('click', () => timer ? stop() : play());
slider.addEventListener('input', () => { stop(); show(+slider.value); });
addEventListener('keydown', ev => {
  if (document.activeElement === find) return;
  if (E[cur].periods.length < 2) return;
  if (ev.key === 'ArrowRight') { stop(); show(Math.min(at + 1, E[cur].periods.length - 1)); }
  if (ev.key === 'ArrowLeft') { stop(); show(Math.max(at - 1, 0)); }
});

pick.addEventListener('change', () => { stop(); select(+pick.value); });
$('save').addEventListener('click', () => {
  const a = document.createElement('a');
  const e = E[cur];
  a.href = img.src;
  a.download = e.family + '_' + e.lang + (e.periods[at] ? '_' + e.periods[at] : '') + '.png';
  a.click();
});

fillPicker();
stop();
select(E.findIndex(e => e.lang === lang));
</script>
</html>
"""
