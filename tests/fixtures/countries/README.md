# Fictavia — the second-country fixture

**Invented. Not a real country, and not real data.** Built by
`tools/generate_fixture_country.py`, which is deterministic: rebuilding it
produces the same bytes.

Every other test in this project is built on Vietnam. Generalise the engine and
they all stay green while proving nothing at all about any other country. This
fixture is the control case, and it exists so that the multi-country work can be
measured rather than believed.

## What makes it a control case

Four properties are deliberate. Each one breaks a constant the engine currently
pins to Vietnam.

| Property | Fictavia | Vietnam | What it breaks |
|---|---|---|---|
| Shape | 27° wide × 7° tall, aspect **0.2593** | 8.5 × 16.2, aspect **1.9032** | `furniture.LOCATOR_ASPECT = 2.2` |
| Position | lon 12–46, lat 44–51 | lon 102–117, lat 7–23 | `semantics.py` coordinate rule, `lon 100–115` / `lat 7–24` |
| Schema | `NAME_1`, `NAME_2`, no population, no area | `ten_tinh`, `ten_xa`, `dan_so`, `dtich_km2` | `dataio.PROVINCE_NAME_FIELDS` / `COMMUNE_NAME_FIELDS` |
| Detached territory | two islands east of 42°E | Hoàng Sa, Trường Sa east of 111°E | `insets.ARCHIPELAGO_LON = 111.0` |

The islands are fragments of an ordinary region, not a region of their own —
the same arrangement Vietnam has, where Hoàng Sa is eighteen fragments of Đà
Nẵng. They pull the central meridian derived from the whole bounding box to
29.20 when the mainland's own is 25.50: a gap of **3.70°**, against Vietnam's
0.39°. A projection inferred the naive way is visibly wrong here.

The name column also repeats: **34 distinct names over 40 districts**, so
guessing the name column by counting distinct values picks `GID_2` instead.
Vietnam carries the same trap at 2,849 over 3,321.

## Layout

Three roots, one per format, because a tier folder holds exactly one dataset:

```text
tests/fixtures/countries/
├── shp/fictavia/{region,district}/       .shp .shx .dbf .prj .cpg
├── geojson/fictavia/{region,district}/   .geojson
├── kml/fictavia/{region,district}/       .kml
└── fictavia_testing.csv                  a user's table, 40 rows
```

Tier folder names are `region` and `district` — GADM's words, not Vietnam's.
Tier **order** is not readable from those names; it comes from the feature
count, 8 before 40.

## Measured differences between the three formats

Not guesses. Read back and checked in `tests/test_boundaries.py`:

- **Shapefile turns an empty string into `None`; GeoJSON keeps `""`.** Code
  that treats the two as the same value will behave differently depending on
  which file the user dropped in.
- **KML keeps the whole table**, contrary to what the plan assumed. It declares
  a `<Schema>` of `SimpleField` entries and hangs the values off each feature.
  A map drawn from KML can show population like any other. Three quieter things
  do happen, and all three were measured:
  - it adds twelve presentation fields of its own — `id`, `Name`,
    `description`, `timestamp`, `tessellate`, `extrude`, `visibility`, `icon`
    and four more — which look like data and are not;
  - a column literally called `NAME` is **promoted into KML's own `<name>`
    element** and disappears under that heading, coming back as `Name`. GADM's
    `NAME_1` is not promoted; a widely used US state boundary file spells the
    column `NAME` and does lose it. The same reader therefore has to look for
    two different headings depending on the file;
  - the writer used here declares **every field as `type="string"`**, so a count
    comes back as text. A KML written by another tool can declare `int` and
    `float` properly — the US file does — so nothing can be trusted either way
    and the reader has to coerce.
- Geometry, bounds and per-part areas are identical across all three.

## The GADM schema was verified against a real download

Checked on 2026-08-23 against `gadm41_VNM_1.shp` from
`geodata.ucdavis.edu/gadm/gadm4.1/shp/`. The fixture's column list was right:
level-1 and level-2 files carry `GID_1`, `GID_0`, **`COUNTRY`**, `NAME_1`,
`VARNAME_1`, `NL_NAME_1`, `TYPE_1`, `ENGTYPE_1`, `CC_1`, `HASC_1`, `ISO_1`.

**`NAME_0` does not appear at any level.** GADM's metadata page lists it, and
that page describes an older version of the database; the level-0 file itself
holds only `GID_0` and `COUNTRY`. A detector should still accept `NAME_0`, for
anyone drawing from a 3.6-era download.

What the check did change is how GADM writes an empty cell: **the two-letter
string `NA`**, not an empty cell and not a null. `NL_NAME_1` and `CC_1` read
`NA` in all 63 rows and `ISO_1` in 59 of them. A detector testing for emptiness
sees a value; one testing for the string sees a gap. The fixture now carries
that rather than a tidier version of it.

`VARNAME_*` carries an unaccented variant of the name — `Bà Rịa - Vũng Tàu`
against `Ba Ria - Vung Tau` — which is worth knowing for name matching.

**GADM forbids redistribution**, so no GADM file can ever become a fixture in
this repository: *"Redistribution or commercial use is not allowed without
prior permission."* The fixture is written to GADM's shape, not copied from it.

## geoBoundaries, also verified

`geoBoundaries-VNM-ADM1.shp` carries exactly the five columns the plan
expected: `shapeName`, `shapeISO`, `shapeID`, `shapeGroup`, `shapeType`.
Licensed ODbL 1.0.

Two things about that file are worth carrying into any detector work: it ships
**no `.cpg`**, so 58 of its 64 names come back as mojibake to a plain reader —
the third real download in a row with this fault — and one of its names is
`'Hà Nội	'`, with a trailing tab.

`XFA` is the country code, taken from the user-assigned `XAA`–`XZZ` range so it
can never collide with a real one.
