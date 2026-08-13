"""Which piece of a feature the detail panel should show.

Clicking a unit on the interactive page opens a panel: the unit drawn large at
the top, its numbers underneath. One geometry question has to be answered before
the page can do that, and it is answered here rather than in the browser — the
browser has no geometry library, and a decision taken at render time is the same
decision every time the page is opened.

**Which parts.** A province is rarely one polygon. Khánh Hòa carries Trường Sa,
390 km offshore and 393 separate fragments; enlarging its full extent gives a
frame that is 98% sea with two specks in it. So the far fragments are dropped and
only the main landmass is enlarged — the same judgement :mod:`insets` makes for
the printed map, reached independently because this one is about a single
feature rather than the whole frame.

The exception matters as much as the rule. Trường Sa is itself a commune, and so
is Hoàng Sa: they have no mainland, and "keep the biggest part" would reduce them
to a single islet and throw away 92% of the unit. When the main cluster holds
less than :data:`AREA_FLOOR` of the area, the feature simply has no dominant
piece and all of it is kept.

Parts are identified by **index**, not by geometry. The page already carries each
feature's outline as one subpath per part, so an index list marks the main
landmass without sending the coordinates a second time — on a national commune
map that is 3.321 outlines that would otherwise be duplicated.
"""

from __future__ import annotations

from typing import Any, Sequence

#: How far a fragment may sit from the main cluster and still belong to it,
#: measured in widths of the largest part. Chosen by measurement, not by taste:
#: at 0.75 Hạ Long keeps its whole bay (848 fragments) while Khánh Hòa still
#: drops Trường Sa. Below 0.35 the bay breaks up; above this nothing changes
#: because the next gap out is an order of magnitude wider.
REACH = 0.75

#: Below this share of the feature's area, the "main" cluster is not the main
#: anything. Trường Sa commune lands at 8%, Hoàng Sa at 22% — for them the
#: archipelago *is* the unit, and the whole geometry is kept.
AREA_FLOOR = 0.35


def parts(geom) -> list[Any]:
    """The polygons of a geometry, single or multi, in their own order."""
    return list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]


def _gap(a: Sequence[float], b: Sequence[float]) -> float:
    """Separation between two bounding boxes.

    Exact polygon distance answers the same question and costs 2.000 times more:
    clustering the 34 provinces took 78 seconds with ``distance()`` and 0,04
    seconds with this, because Quảng Ninh alone has 1.774 fragments and the
    comparison is pairwise. Bounding boxes cannot tell two touching islands
    apart, which does not matter — the question is whether a fragment is in the
    bay or 400 km out to sea.
    """
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


def main_parts(geom) -> tuple[list[int], float]:
    """Indices of the parts forming the main landmass, and their share of area.

    A share of 1.0 means everything was kept — either the feature is one polygon,
    or it is an archipelago with no dominant piece.
    """
    pieces = parts(geom)
    if len(pieces) == 1:
        return [0], 1.0

    order = sorted(range(len(pieces)), key=lambda i: -pieces[i].area)
    boxes = [p.bounds for p in pieces]
    reach = (pieces[order[0]].area ** 0.5) * REACH

    kept = {order[0]}
    hull = list(boxes[order[0]])
    grew = True
    while grew:                       # a fragment can join through another one
        grew = False
        for i in order:
            if i in kept or _gap(boxes[i], hull) > reach:
                continue
            kept.add(i)
            b = boxes[i]
            hull = [min(hull[0], b[0]), min(hull[1], b[1]),
                    max(hull[2], b[2]), max(hull[3], b[3])]
            grew = True

    total = geom.area
    share = (sum(pieces[i].area for i in kept) / total) if total else 1.0
    if share < AREA_FLOOR:
        return list(range(len(pieces))), 1.0
    return sorted(kept), share
