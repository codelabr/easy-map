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

#: Where a country's offshore territory is declared to begin. Vietnam's 111°E
#: used to be a module constant here, which is the same as saying every country
#: splits at 111°E — and every country that does not simply never got an inset.
#:
#: The number is a **declaration**, not a measurement, and that is the whole
#: reason this is a table with reasons in it rather than a rule. Three attempts
#: were made to derive 111°E from Vietnam's own geometry and none can: the land
#: masses west of it reach 470 km from the mainland and are 2–36 km² in size,
#: while the nearest one east of it is 298 km away and 63 km². Neither distance
#: nor area separates them. The meridian says which islands the map is *for*.
#:
#: Keyed the way ``detect._COUNTRY_LANGUAGE`` is keyed — on the country name the
#: boundary file reports — and holding one row for the same reason: this is the
#: country whose cartography the project can speak for. A country not listed
#: gets no inset, and gets a warning instead when its scattered land costs the
#: reader enough of the page to matter.
_VIETNAM = {
    "meridian": 111.0,
    # What the box is captioned. It cannot come from the data — the shapefile
    # carries province names, and the islands are fragments of two of them — so
    # it is declared with the meridian, and a country that declares a meridian
    # without a caption gets an unlabelled box rather than Vietnam's caption.
    "label": "Hoàng Sa · Trường Sa",
    "source": "built in for Vietnam",
    "evidence": "the easternmost mainland point in the shapefile is "
                "110.64°E; the westernmost island fragment is 111.45°E",
}

_DECLARED: dict[str, dict[str, Any]] = {
    "viet nam": _VIETNAM, "vietnam": _VIETNAM, "việt nam": _VIETNAM,
    "vnm": _VIETNAM, "vn": _VIETNAM,
}

#: The key a person writes to declare a meridian for a country the table does
#: not cover. It goes in the profile's ``declared`` block — the one part of that
#: file the builder copies forward instead of computing.
HAND_KEY = "inset_meridian"

#: The caption for that country's box, declared beside the meridian. Optional:
#: without it the box is drawn unlabelled, which is the honest default — no
#: other country's islands are called Hoàng Sa.
HAND_LABEL_KEY = "inset_label"

#: Height of the inset as a share of the mainland's height. Large enough that
#: the island groups read as more than specks, small enough to leave the
#: mainland dominant.
INSET_HEIGHT_SHARE = 0.30

#: Gap between the inset and the edges of the map area, in shares of the
#: mainland's width.
INSET_MARGIN = 0.045


#: How far past the country's own extent the mask polygons reach, as a share of
#: that extent. Only the meridian in the middle does any cutting; the outer
#: edges exist to be somewhere the geometry is not, and half again each way is
#: comfortably that for a country of any size.
_MASK_PAD = 0.5

#: Spacing, in degrees, at which each vertical edge is broken into segments
#: before projecting. The map is drawn in an equal-area projection where a
#: meridian is a curve, not a vertical line; a straight two-point edge would cut
#: several kilometres off at the ends.
_MASK_STEP = 0.25

#: Room left below the poles. A polygon touching ±90° projects badly in the
#: conic projections this engine infers.
_MASK_LAT_LIMIT = 89.0


def _extent(frame, lon: float) -> tuple[float, float, float, float]:
    """The country's own bounds in degrees, padded, and sure to contain ``lon``.

    This used to be two constants — ``lat 0..30``, ``lon 95..130`` — described in
    a comment as "wide enough for Vietnam and its seas". It was, and it was
    nowhere near anywhere else: a country outside that window put both mask
    polygons somewhere its geometry is not, so both halves came back empty, so
    the split returned None and no inset was ever drawn. Nothing raised. The
    declared meridian would have been read, honoured, and quietly discarded.

    **Not handled: a country straddling the antimeridian.** Its bounds in
    degrees come back as the whole world, so the mask is the whole world and a
    meridian near 180° puts almost everything on one side. Fiji and Kiribati are
    the real cases. The honest position is that this is undone rather than
    solved; nothing here pretends otherwise, and the projection this engine
    infers has its own answer to the same wrap that this does not share.
    """
    import geopandas as gpd
    import shapely.geometry as sg

    minx, miny, maxx, maxy = (float(v) for v in frame.total_bounds)
    corners = gpd.GeoSeries([sg.box(minx, miny, maxx, maxy)],
                            crs=frame.crs or "EPSG:4326")
    lon0, lat0, lon1, lat1 = (float(v) for v in
                              corners.to_crs("EPSG:4326").total_bounds)
    padx = max((lon1 - lon0) * _MASK_PAD, 1.0)
    pady = max((lat1 - lat0) * _MASK_PAD, 1.0)
    # The meridian has to sit inside the ring it divides. When a declaration
    # falls outside the country's own longitudes the side beyond it comes back
    # empty and the split declines — which is the right answer, and better than
    # a bow-tie polygon raising from inside GEOS.
    return (max(min(lon0 - padx, lon - 1.0), -180.0),
            max(lat0 - pady, -_MASK_LAT_LIMIT),
            min(max(lon1 + padx, lon + 1.0), 180.0),
            min(lat1 + pady, _MASK_LAT_LIMIT))


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

    lon0, lat0, lon1, lat1 = _extent(frame, lon)
    steps = [lat0 + i * _MASK_STEP
             for i in range(int((lat1 - lat0) / _MASK_STEP) + 1)] + [lat1]
    down = list(reversed(steps))

    def edge(at: float, lats):
        return [(at, lat) for lat in lats]

    # walk each ring in one direction: up one edge and down the other. Threading
    # the corners in the wrong order makes a bow-tie, and intersecting with a
    # self-crossing polygon raises deep inside GEOS with a message that says
    # nothing about which polygon was at fault. Both vertical edges are broken
    # into segments, not just the dividing meridian: a country wide enough for
    # its outer edge to matter is exactly the country this used to fail on.
    west = sg.Polygon(edge(lon0, steps) + edge(lon, down))
    east = sg.Polygon(edge(lon, steps) + edge(lon1, down))
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
        return {"mass_count": 0, "detached_masses": 0}

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
        "mass_count": len(masses),
        "main_mass_area_share": round(masses[0][0] / total, 5),
        "main_mass_width_share": round(
            float(body[2] - body[0]) / (maxx - minx), 4) if maxx > minx else 1.0,
    }


def declared(country: str | None) -> dict[str, Any] | None:
    """The built-in declaration for a country, or None if there is not one.

    Hyphens and underscores read as spaces, because the name reaching this
    function is sometimes the one the boundary file reports ("Việt Nam") and
    sometimes the folder it sits in ("viet-nam").
    """
    if not country:
        return None
    name = str(country).strip().lower().replace("-", " ").replace("_", " ")
    return _DECLARED.get(name)


def declaration(country: str | None, by_hand: dict[str, Any] | None = None,
                where: str | None = None) -> dict[str, Any]:
    """What the country profile should record about this country's inset.

    Three outcomes, and the profile says which of them happened rather than only
    what the number is. A reader who finds ``"source": "undeclared"`` knows the map
    was framed the ordinary way because nobody has decided otherwise — not
    because the geometry was examined and found not to need an inset.

    A hand-written declaration wins over the built-in table, including when it
    is written as ``null``: turning Vietnam's inset off is a decision somebody
    is allowed to make, and it has to be expressible.
    """
    if by_hand and HAND_KEY in by_hand:
        lon = by_hand[HAND_KEY]
        if lon is None:
            return {"meridian": None, "label": None,
                    "source": "declared_as_none",
                    "evidence": f"the profile reads {HAND_KEY} = null"}
        if isinstance(lon, bool) or not isinstance(lon, (int, float)) \
                or not -180.0 <= float(lon) <= 180.0:
            from . import messages as msg

            raise SystemExit(msg.text("error.bad-inset-declaration",
                                      field=HAND_KEY, given=repr(lon),
                                      file=where or "country_profiles.json"))
        label = by_hand.get(HAND_LABEL_KEY)
        return {"meridian": float(lon),
                "label": str(label) if label else None,
                "source": "declared_by_user",
                "evidence": f"the profile reads {HAND_KEY} = {float(lon)}"}
    known = declared(country)
    if known is not None:
        return dict(known)
    return {
        "meridian": None,
        "label": None,
        "source": "undeclared",
        "evidence": f"no row for '{country}' in the built-in table, and the "
                    f"profile has no {HAND_KEY}",
        "how_to_declare": f"write \"declared\": {{\"{HAND_KEY}\": <longitude>, "
                          f"\"{HAND_LABEL_KEY}\": \"<caption, optional>\"}} "
                          f"into this country's entry in "
                          f"{where or 'country_profiles.json'}",
    }


def meridian(profile: dict[str, Any] | None) -> float | None:
    """The declared meridian a country profile carries, or None.

    Read, never re-derived — the same rule the projection follows. A map that
    worked out its own meridian would be a second chance to answer differently
    from the profile the plan was shown from.
    """
    return ((profile or {}).get("inset") or {}).get("meridian")


def inset_label(profile: dict[str, Any] | None) -> str | None:
    """The caption declared for that country's box, or None for no caption."""
    return ((profile or {}).get("inset") or {}).get("label")


def split_bounds(frame, lon: float | None) -> dict[str, Any] | None:
    """Mainland bounds and archipelago bounds, or None if the split is pointless.

    Returns None — meaning "frame this the ordinary way" — when the country has
    declared no meridian, when the frame holds no offshore fragments, or when it
    holds nothing but them. A single-province map of Khánh Hòa is a real case of
    the last: there is no mainland-versus-islands story to tell, the reader asked
    for Khánh Hòa.

    ``lon`` has no default on purpose. Every caller has to say which meridian it
    means, because the version of this that defaulted to Vietnam's gave every
    other country the same split silently, and silently is how the United States
    map came out with two thirds of its page at sea and nothing said.
    """
    if lon is None:
        return None
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
    return {"mainland": west, "archipelago": east, "west_mask": west_mask}


def view(frame, lon: float | None) -> dict[str, Any] | None:
    """Where the map should look, and where the inset goes inside that view.

    Both in data coordinates, so the caller can hand one to ``set_xlim`` and the
    other to ``inset_axes`` without a second opinion about the frame.
    """
    parts = split_bounds(frame, lon)
    if parts is None:
        return None

    lminx, lminy, lmaxx, lmaxy = parts["mainland"]
    iminx, iminy, imaxx, imaxy = parts["archipelago"]
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
        "view_bounds": (lminx, lminy, view_maxx, lmaxy),
        "inset_box": (x0, y0, box_w, box_h),
        "archipelago_bounds": (iminx, iminy, imaxx, imaxy),
        # The strip cleared for the inset is out at sea, which is exactly where
        # the islands are: drawing the main layers unclipped would leave Hoàng
        # Sa sitting in the open beside the box that is supposed to hold it.
        # A projected polygon, not a rectangle of degrees — see _masks.
        "draw_mask": parts["west_mask"],
        "scale_vs_main": round(box_w / island_w, 3),
        "mainland_width_pct": round(land_w / (view_maxx - lminx) * 100, 1),
    }


def summary(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """The part of the plan worth reporting — numbers only.

    The plan carries a shapely mask, which cannot be written to the run's JSON;
    and the reader of a metadata file wants to know that an inset was drawn and
    how much of the width the mainland kept, not where the mask sits.
    """
    if plan is None:
        return None
    return {"has_inset": True,
            "archipelago_bounds": [round(v, 1) for v in plan["archipelago_bounds"]],
            "scale_vs_main": plan["scale_vs_main"],
            "mainland_width_pct": plan["mainland_width_pct"]}


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
    return rows.set_geometry(rows.geometry.intersection(plan["draw_mask"]))
