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
- **KML keeps only the name.** Of thirteen columns, one survives as content;
  what comes back instead is KML's own presentation fields — `tessellate`,
  `extrude`, `visibility`, `icon`. There is no place in KML for a `dan_so`
  column, so a map drawn from KML cannot show population, and the detail panel
  has to omit the row rather than print a zero.
- Geometry and bounds are identical across all three.

## The GADM schema here is not yet verified against a downloaded file

The column names are written as GADM 4.1 shapefiles are understood to carry
them — `GID_1`, `GID_0`, `COUNTRY`, `NAME_1`, `VARNAME_1`, `NL_NAME_1`,
`TYPE_1`, `ENGTYPE_1`, `CC_1`, `HASC_1`, `ISO_1`. GADM's own metadata page
lists `NAME_0` for the country, which is what version 3.6 used; the level-1 and
level-2 files are believed to carry `COUNTRY` instead.

**Both readings cannot be right, and no real GADM file has been opened to
settle it.** Until one is, a detector must accept either name. The plan records
this as the first task of the detector work, not of this fixture.

`XFA` is the country code, taken from the user-assigned `XAA`–`XZZ` range so it
can never collide with a real one.
