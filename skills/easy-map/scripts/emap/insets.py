"""Keeping the offshore archipelagos on the map without letting them run it.

Vietnam's national map has to show Hoàng Sa and Trường Sa, and in the shapefile
they are not separate features: Hoàng Sa is eighteen fragments of Đà Nẵng and
Trường Sa is two hundred and ninety-seven fragments of Khánh Hòa. Framing the
whole geometry therefore stretches the map east to 117°E, and the mainland —
the part every reader is actually looking at — ends up with 56% of the width.
Provinces the size of Hà Nội become too small to label.

The cartographic answer is the one atlases have used for decades: frame the
mainland, and carry the archipelagos in an inset. Nothing is removed and nothing
is redrawn — this module only decides *where to look*.

Two rules make that safe, and both are checked here rather than assumed:

* **The geometry is never cut.** Clipping would move centroids, change areas and
  relocate label anchors — a province's label is placed at its representative
  point, and cutting Khánh Hòa would move that point. Only the view is narrowed.
* **One source of bounds.** The page's aspect ratio and the axes limits must come
  from the same numbers. Computing them separately is how a map ends up with the
  right shape and the wrong crop.
"""

from __future__ import annotations

from typing import Any

#: Meridian separating the mainland from the offshore archipelagos. East of it
#: there is no mainland territory at any latitude, so the split needs no
#: latitude term. Measured, not guessed: the easternmost mainland point in the
#: shapefile is 110.64°E and the westernmost island fragment is 111.45°E.
ARCHIPELAGO_LON = 111.0

#: Height of the inset as a share of the mainland's height. Large enough that
#: the island groups read as more than specks, small enough to leave the
#: mainland dominant.
INSET_HEIGHT_SHARE = 0.30

#: Gap between the inset and the edges of the map area, in shares of the
#: mainland's width.
INSET_MARGIN = 0.045


#: Latitude span the mask polygons cover. Wide enough for Vietnam and its seas,
#: narrow enough that projecting it stays well inside the projection's valid
#: area.
_MASK_LAT = (0.0, 30.0)
_MASK_LON = (95.0, 130.0)

#: Spacing, in degrees, at which the meridian is broken into segments before
#: projecting. The map is drawn in an equal-area projection where a meridian is
#: a curve, not a vertical line; a straight two-point edge would cut several
#: kilometres off at the ends.
_MASK_STEP = 0.25


def _masks(frame, lon: float):
    """West and east halves of the map's world, in the frame's own coordinates.

    The frame reaching this module is **projected** — metres, not degrees —
    because an equal-area projection is what makes province areas comparable.
    A meridian written as a number is therefore meaningless here until it has
    been projected too. Getting this wrong does not raise: it clips at "x = 111
    metres", which erases the middle of the country and leaves the mainland
    sitting inside the box meant for the islands.
    """
    import geopandas as gpd
    import shapely.geometry as sg

    lat0, lat1 = _MASK_LAT
    lon0, lon1 = _MASK_LON
    steps = [lat0 + i * _MASK_STEP
             for i in range(int((lat1 - lat0) / _MASK_STEP) + 1)] + [lat1]
    meridian = [(lon, lat) for lat in steps]

    # walk each ring in one direction: the meridian up, then back along the
    # outer edge. Threading the outer corners in the wrong order makes a
    # bow-tie, and intersecting with a self-crossing polygon raises deep inside
    # GEOS with a message that says nothing about which polygon was at fault.
    west = sg.Polygon([(lon0, lat0)] + meridian + [(lon0, lat1)])
    east = sg.Polygon(meridian + [(lon1, lat1), (lon1, lat0)])
    series = gpd.GeoSeries([west.buffer(0), east.buffer(0)], crs="EPSG:4326")
    if frame.crs is not None and frame.crs != series.crs:
        series = series.to_crs(frame.crs)
    return series.iloc[0], series.iloc[1]


def _bounds(geometries, box) -> tuple[float, float, float, float] | None:
    """Bounds of whatever falls inside ``box``, or None if nothing does.

    Uses intersection to *measure*, never to replace: the caller keeps the
    original geometry.
    """
    clipped = geometries.intersection(box)
    kept = clipped[~clipped.is_empty]
    if not len(kept):
        return None
    minx, miny, maxx, maxy = kept.total_bounds
    if minx != minx:                       # all-NaN bounds from an empty result
        return None
    return float(minx), float(miny), float(maxx), float(maxy)


#: How close two pieces of land have to be to count as one land mass. Small
#: enough that a strait is a gap; large enough that a border drawn twice with
#: slightly different vertices is not.
LAND_LINK_M = 2000.0

def land_masses(frame) -> dict[str, Any]:
    """The country broken into land masses, and how far the rest sits from the
    biggest one.

    This exists to *notice* detached territory, not to decide what to do about
    it. The distinction is the finding of this round: three measurements were
    made trying to derive Vietnam's split at 111°E from the geometry, and none
    of them can, because it is not in the geometry. The land masses west of
    that meridian reach 470 km from the mainland and are 2 to 36 km² in size;
    the nearest one east of it is 298 km away and 63 km². Neither distance nor
    area separates them. The meridian is a cartographic decision about which
    islands the map is *for*, and no amount of measuring recovers a decision.

    What can be measured is that a country has land a long way from its main
    body, which is exactly the question the United States map raised: it was
    framed to include Alaska, Hawaii and Puerto Rico, so the lower 48 kept a
    third of the page, and nothing said a word.

    Grouped with an index tree rather than by buffering every polygon — the
    buffer-and-union version of this took more than ten minutes on Vietnam's
    3,321 communes and never finished. This takes about five seconds on the
    province tier, which is why it is computed once into the country profile
    and not on every map.
    """
    import shapely

    parts = frame.explode(index_parts=False, ignore_index=True)
    geoms = parts.geometry.to_numpy()
    if not len(geoms):
        return {"số_khối": 0, "khối_rời": 0}

    tree = shapely.STRtree(geoms)
    left, right = tree.query(geoms, predicate="dwithin", distance=LAND_LINK_M)
    parent = list(range(len(geoms)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in zip(left, right):
        ra, rb = root(int(a)), root(int(b))
        if ra != rb:
            parent[ra] = rb

    grouped: dict[int, list[int]] = {}
    for i in range(len(geoms)):
        grouped.setdefault(root(i), []).append(i)

    areas = parts.geometry.area.to_numpy()
    masses = sorted(((float(sum(areas[i] for i in ix)), ix)
                     for ix in grouped.values()), key=lambda t: -t[0])

    minx, miny, maxx, maxy = (float(v) for v in frame.total_bounds)
    body = shapely.total_bounds(geoms[masses[0][1]])
    total = sum(area for area, _ in masses) or 1.0

    # Only the width is computed, and only the width is used. Two earlier
    # versions also measured how far each outlying mass sits from the main
    # body: unioning the main body and measuring against it took 276 seconds on
    # Vietnam, and routing the same measurement through an index still took 90.
    # Neither number reached the warning, which says what the reader loses —
    # that the main body keeps 47% of the page — and needs no distance to say
    # it. The cheapest correct thing is the one that was wanted all along.
    return {
        "số_khối": len(masses),
        "phần_diện_tích_khối_chính": round(masses[0][0] / total, 5),
        "phần_bề_ngang_khối_chính": round(
            float(body[2] - body[0]) / (maxx - minx), 4) if maxx > minx else 1.0,
    }


def split_bounds(frame, lon: float = ARCHIPELAGO_LON) -> dict[str, Any] | None:
    """Mainland bounds and archipelago bounds, or None if the split is pointless.

    Returns None — meaning "frame this the ordinary way" — when the frame holds
    no offshore fragments, or holds nothing but them. A single-province map of
    Khánh Hòa is a real case of the second: there is no mainland-versus-islands
    story to tell, the reader asked for Khánh Hòa.
    """
    minx, miny, maxx, maxy = (float(v) for v in frame.total_bounds)
    west_mask, east_mask = _masks(frame, lon)

    west = _bounds(frame.geometry, west_mask)
    east = _bounds(frame.geometry, east_mask)
    if west is None or east is None:
        return None

    # If the islands are a rounding error on the frame's width, the ordinary
    # framing is already fine and an inset would be ceremony.
    if (maxx - west[2]) < (west[2] - west[0]) * 0.15:
        return None
    return {"đất_liền": west, "quần_đảo": east, "mặt_nạ_tây": west_mask}


def view(frame, lon: float = ARCHIPELAGO_LON) -> dict[str, Any] | None:
    """Where the map should look, and where the inset goes inside that view.

    Both in data coordinates, so the caller can hand one to ``set_xlim`` and the
    other to ``inset_axes`` without a second opinion about the frame.
    """
    parts = split_bounds(frame, lon)
    if parts is None:
        return None

    lminx, lminy, lmaxx, lmaxy = parts["đất_liền"]
    iminx, iminy, imaxx, imaxy = parts["quần_đảo"]
    land_w, land_h = lmaxx - lminx, lmaxy - lminy

    # The inset keeps the archipelagos' own proportions, so island groups are
    # not stretched into shapes they do not have.
    island_w, island_h = imaxx - iminx, imaxy - iminy
    box_h = land_h * INSET_HEIGHT_SHARE
    box_w = box_h * (island_w / island_h) if island_h else box_h

    margin = land_w * INSET_MARGIN
    view_maxx = lmaxx + margin + box_w + margin

    # bottom-right of the map area: the scale bar sits bottom-left and the north
    # arrow top-right, so this corner is the one still free
    x0 = view_maxx - margin - box_w
    y0 = lminy + margin
    return {
        "khung_nhìn": (lminx, lminy, view_maxx, lmaxy),
        "ô_khung_phụ": (x0, y0, box_w, box_h),
        "vùng_quần_đảo": (iminx, iminy, imaxx, imaxy),
        # The strip cleared for the inset is out at sea, which is exactly where
        # the islands are: drawing the main layers unclipped would leave Hoàng
        # Sa sitting in the open beside the box that is supposed to hold it.
        # A projected polygon, not a rectangle of degrees — see _masks.
        "mặt_nạ_khi_vẽ": parts["mặt_nạ_tây"],
        "tỷ_lệ_so_với_khung_chính": round(box_w / island_w, 3),
        "phần_trăm_bề_ngang_đất_liền": round(land_w / (view_maxx - lminx) * 100, 1),
    }


def summary(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """The part of the plan worth reporting — numbers only.

    The plan carries a shapely mask, which cannot be written to the run's JSON;
    and the reader of a metadata file wants to know that an inset was drawn and
    how much of the width the mainland kept, not where the mask sits.
    """
    if plan is None:
        return None
    return {"có_khung_phụ": True,
            "vùng_quần_đảo": [round(v, 1) for v in plan["vùng_quần_đảo"]],
            "tỷ_lệ_so_với_khung_chính": plan["tỷ_lệ_so_với_khung_chính"],
            "phần_trăm_bề_ngang_đất_liền": plan["phần_trăm_bề_ngang_đất_liền"]}


def clip_for_drawing(rows, plan: dict[str, Any] | None):
    """The rows as they should be **drawn** on the main map.

    Only the drawing is clipped. Labels, symbols and every computed value still
    come from the untouched geometry, because a province's label is anchored at
    its representative point and cutting Khánh Hòa would move that point out of
    the province it belongs to.
    """
    if plan is None or not len(rows):
        return rows
    # Not GeoDataFrame.clip: it reorders the rows and drops the ones that miss
    # the mask. The caller draws with a list of colours built from the original
    # row order, so a reordered frame paints every province in some other
    # province's colour — a map that is wrong everywhere and looks fine.
    return rows.set_geometry(rows.geometry.intersection(plan["mặt_nạ_khi_vẽ"]))
