"""Build the second-country fixture the multi-country work is measured against.

    uv run --offline --with geopandas python tools/generate_fixture_country.py

Every one of the project's tests is built on Vietnam. Generalise the engine and
they all stay green while proving nothing at all about any other country — the
failure mode the handbook has already recorded three times. This fixture is the
control case: a country that is **not** Vietnam in the specific ways the engine
currently assumes it is.

Fictavia is invented. Its ISO code ``XFA`` comes from the user-assigned
``XAA``–``XZZ`` range precisely so it can never collide with a real country.
Four properties are deliberate, and each one breaks a pinned constant:

* **Landscape, not portrait.** Roughly 27 degrees wide by 7 tall, where Vietnam
  is 8.5 by 16. ``furniture.LOCATOR_ASPECT = 2.2`` would squash it by a factor
  of eight.
* **Nowhere near Vietnam.** Latitudes in the forties, so the coordinate rule in
  ``semantics.py`` — ``lon 100..115``, ``lat 7..24`` — silently declines to
  recognise a coordinate column.
* **GADM naming, not Vietnamese.** ``NAME_1`` and ``NAME_2`` where the engine
  looks for ``ten_tinh`` and ``ten_xa``, and no ``dan_so`` or ``dtich_km2`` at
  all, because GADM carries no population or area.
* **Detached territory of its own.** Two island squares far to the east, so that
  inferring a central meridian from the whole bounding box is wrong here for the
  same reason it is wrong for Vietnam — and by a much wider margin, 3.70 degrees
  against 0.39.

The name column also repeats across regions, six times out of forty, so that
guessing the name column by counting distinct values picks the identifier
instead. Vietnam has the same trap at 2,849 distinct names over 3,321 communes;
a fixture without it would let a wrong heuristic through.

Written three times over — shapefile, GeoJSON, KML — under three separate roots,
because a tier folder holds exactly one dataset. The three must draw the same
map; that is what wave 1 is for.

All three carry the whole attribute table, KML included. An earlier version of
this file threw the columns away before writing the KML and then reported the
loss as a property of the format; it was a property of this script. A real KML
declares a ``<Schema>`` of ``SimpleField`` entries and hangs the values off each
feature, and every column survives. What KML does do is quieter and worth the
fixture carrying honestly: it adds twelve presentation fields of its own, it
promotes a column literally called ``NAME`` into its own ``<name>`` element so
that the column disappears under that heading, and the writer here declares
every field as ``type="string"`` — so a count read back from KML is text.
"""

from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import shapely.geometry as sg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "countries"

COUNTRY = "Fictavia"
ISO3 = "XFA"

#: Mainland extent. Wide and short on purpose — see the module docstring.
WEST, EAST = 12.0, 39.0
SOUTH, NORTH = 44.0, 51.0

#: Two offshore squares, far enough east that no mainland territory reaches
#: them at any latitude. The same shape of problem as Hoang Sa and Truong Sa,
#: which is the point: the fix has to be general, not Vietnamese.
ISLANDS = [(45.2, 46.1, 45.7, 46.6), (46.0, 47.0, 46.4, 47.4)]

#: Meridian separating mainland from islands, by the same measured rule the
#: Vietnam constant uses: east of it there is no mainland at any latitude.
ISLAND_LON = 42.0

REGIONS = ["Ardenne", "Beluar", "Corvin", "Dunmar",
           "Estrel", "Fanolt", "Girene", "Halvik"]

#: How many districts each region is cut into. Uneven so that nothing can be
#: derived from a constant, and 40 in total.
SPLIT = [4, 5, 6, 4, 5, 6, 5, 5]

#: Thirty-four names for forty districts. Walked in order and wrapped, so the
#: last six repeat names already used in the first region — a duplicate name in
#: two different regions, which is the join hazard worth having in a fixture.
DISTRICTS = [
    "Alder", "Brann", "Calvet", "Dorne", "Elmarch", "Ferro", "Glenmar",
    "Harrow", "Ilvenn", "Jorund", "Kestrel", "Lomond", "Marek", "Norga",
    "Oquin", "Pelmar", "Quarn", "Rhoven", "Sylde", "Torval", "Urbek",
    "Vandel", "Welkin", "Xanthe", "Ylora", "Zorenn", "Amble", "Brisco",
    "Cadrin", "Dalvik", "Ennor", "Fellorn", "Grismar", "Halloway",
]

#: GADM writes the kind of unit in its own column rather than into the name.
TYPE_1, ENGTYPE_1 = "Regiune", "Region"
TYPE_2, ENGTYPE_2 = "Districtul", "District"

FORMATS = {
    "shp": ("ESRI Shapefile", ".shp"),
    "geojson": ("GeoJSON", ".geojson"),
    "kml": ("KML", ".kml"),
}


def grid():
    """Region rectangles, two rows of four across the mainland."""
    cols, rows = 4, 2
    w = (EAST - WEST) / cols
    h = (NORTH - SOUTH) / rows
    out = []
    for i, name in enumerate(REGIONS):
        r, c = divmod(i, cols)
        x0 = WEST + c * w
        y0 = NORTH - (r + 1) * h
        out.append((name, x0, y0, x0 + w, y0 + h))
    return out


def regions_frame():
    rows, geoms = [], []
    for i, (name, x0, y0, x1, y1) in enumerate(grid(), start=1):
        shape = sg.box(x0, y0, x1, y1)
        # The last region owns the islands, exactly as Da Nang owns Hoang Sa:
        # a detached territory is a fragment of an ordinary unit, not a unit of
        # its own, and any code that assumes otherwise breaks on Vietnam too.
        if name == REGIONS[-1]:
            shape = sg.MultiPolygon([shape] + [sg.box(*b) for b in ISLANDS])
        rows.append({
            "GID_1": f"{ISO3}.{i}_1",
            "GID_0": ISO3,
            "COUNTRY": COUNTRY,
            "NAME_1": name,
            "VARNAME_1": "",
            "NL_NAME_1": "",
            "TYPE_1": TYPE_1,
            "ENGTYPE_1": ENGTYPE_1,
            "CC_1": f"{i:02d}",
            "HASC_1": f"{ISO3[:2]}.{name[:2].upper()}",
            "ISO_1": "",
        })
        geoms.append(shape)
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")


def districts_frame():
    rows, geoms, n = [], [], 0
    for i, (region, x0, y0, x1, y1) in enumerate(grid(), start=1):
        parts = SPLIT[i - 1]
        step = (x1 - x0) / parts
        for j in range(parts):
            name = DISTRICTS[n % len(DISTRICTS)]
            n += 1
            shape = sg.box(x0 + j * step, y0, x0 + (j + 1) * step, y1)
            # the islands hang off the easternmost district of the last region
            if region == REGIONS[-1] and j == parts - 1:
                shape = sg.MultiPolygon([shape] + [sg.box(*b) for b in ISLANDS])
            rows.append({
                "GID_2": f"{ISO3}.{i}.{j + 1}_1",
                "GID_0": ISO3,
                "COUNTRY": COUNTRY,
                "GID_1": f"{ISO3}.{i}_1",
                "NAME_1": region,
                "NL_NAME_1": "",
                "NAME_2": name,
                "VARNAME_2": "",
                "NL_NAME_2": "",
                "TYPE_2": TYPE_2,
                "ENGTYPE_2": ENGTYPE_2,
                "CC_2": f"{i:02d}{j + 1:02d}",
                "HASC_2": f"{ISO3[:2]}.{region[:2].upper()}.{name[:2].upper()}",
            })
            geoms.append(shape)
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")


def health_table(districts) -> str:
    """A user's spreadsheet, written the way a user would write it.

    The place names carry the English administrative word — "Alder District",
    "Region of Ardenne" — because that is what arrives in real tables and
    because ``matching._PREFIXES`` holds Vietnamese words only. The plan keeps
    that list Vietnamese for now, so this is here to be measured, not fixed.

    Figures are invented from the row position, with no random component at all,
    so the file is byte-identical on every rebuild.
    """
    lines = ["Region,District,Tested,Positive"]
    for n, (_, row) in enumerate(districts.iterrows()):
        tested = 1200 + (n * 137) % 3400
        positive = 3 + (n * 29) % 84
        lines.append(f"Region of {row['NAME_1']},{row['NAME_2']} District,"
                     f"{tested},{positive}")
    return "\n".join(lines) + "\n"


def write(frame, kind: str, tier: str, log) -> None:
    driver, suffix = FORMATS[kind]
    folder = OUT / kind / "fictavia" / tier
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{COUNTRY}_{tier}{suffix}"
    frame.to_file(path, driver=driver)
    kept = ", ".join(c for c in frame.columns if c != "geometry")
    print(f"  {path.relative_to(ROOT)}  ({len(frame)} features; {kept})", file=log)


def main() -> int:
    log = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    regions, districts = regions_frame(), districts_frame()

    assert len(regions) == len(REGIONS)
    assert len(districts) == sum(SPLIT)
    # the two traps this fixture exists to carry, checked rather than trusted
    assert districts["NAME_2"].nunique() < districts["GID_2"].nunique()
    assert regions.total_bounds[2] > ISLAND_LON > EAST

    for tier, frame in (("region", regions), ("district", districts)):
        for kind in FORMATS:
            write(frame, kind, tier, log)

    table = OUT / "fictavia_testing.csv"
    table.write_text(health_table(districts), encoding="utf-8", newline="\n")
    print(f"  {table.relative_to(ROOT)}  ({len(districts)} rows)", file=log)

    full = regions.total_bounds
    mainland = regions.explode(index_parts=False, ignore_index=True)
    mainland = mainland[mainland.geometry.bounds["minx"] < ISLAND_LON]
    mb = mainland.total_bounds
    print(f"\n  lon_0 from the whole bounding box : {(full[0] + full[2]) / 2:.4f}",
          file=log)
    print(f"  lon_0 from the mainland only      : {(mb[0] + mb[2]) / 2:.4f}",
          file=log)
    print(f"  mainland aspect (height / width)  : "
          f"{(mb[3] - mb[1]) / (mb[2] - mb[0]):.4f}  "
          f"(Vietnam 1.9032, LOCATOR_ASPECT 2.2)", file=log)
    log.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
