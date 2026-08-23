# Administrative boundaries

The two boundary sets ship with this repository, as zips:

| File | Packed | Unpacked | Contents |
|---|---|---|---|
| `provinces.zip` | 13.0 MB | 20.1 MB | 34 provinces and centrally-run cities |
| `communes.zip` | 74.7 MB | 114.4 MB | 3,321 wards and communes |

They are zipped because the commune `.shp` is **111.3 MB**, over GitHub's
100 MB per-file limit. Compressed it fits, though GitHub still warns above
50 MB.

**The installer unpacks them for you** into `~/.easy-map/shapefiles/` and
records that path in `EASY_MAP_SHAPEFILES`. Nothing here needs doing by hand
unless you want the boundaries somewhere else. Pass `-SkipShapefiles` /
`--skip-shapefiles` to leave them packed.

## Unpacking them yourself

```bash
python -c "import zipfile; zipfile.ZipFile('shapefiles/provinces.zip').extractall('shapefiles/viet-nam/province')"
python -c "import zipfile; zipfile.ZipFile('shapefiles/communes.zip').extractall('shapefiles/viet-nam/commune')"
```

## The layout

One folder per country, one folder per tier inside it:

```text
shapefiles/
├── viet-nam/
│   ├── province/     .shp + .shx + .dbf + .prj, OR one .geojson, OR one .kml
│   └── commune/
└── <another-country>/
    └── <its own tier names>/
```

**A tier folder holds exactly one dataset**, in any of `.shp`, `.geojson`,
`.json` or `.kml`. Two datasets in one folder is refused by name rather than
resolved by sorting, because drawing the wrong one of two files looks like
nothing at all.

**Tier folder names are yours to choose.** Which is the coarser tier is decided
by counting features, never by reading the name: `region` sorts before
`district` and `comuna` sorts before `judet`, and only one of those orders is
right. A country with a single tier is fine — it is drawn at that tier.

Boundaries left in the old `shapefiles/provinces/` and `shapefiles/communes/`
are **moved to `viet-nam/province/` and `viet-nam/commune/` on the first
command**, by rename rather than by copy. Nothing is overwritten: if the new
place already holds something, the old folder is left alone and reported.

With more than one country present, a command has to say which to draw —
`--country viet-nam`. With one, it does not.

The engine looks for the root in this order: the `--shapefile-root` flag, then
`EASY_MAP_SHAPEFILES`, then `shapefiles/` inside the working folder. Check what
it resolved, and what countries and tiers it found:

```bash
python skills/easy-map/scripts/easy_map.py list --project-root .
```

The reply carries a `shapefile` block naming the two files it found.

## What the data is

Administrative boundaries **as they stand after the 2025 reform to a two-tier
local government model**. Those two tiers, province and commune, are the only
ones the skill draws; the district tier the reform abolished is not supported.

Attribute fields the engine reads:

| Level | Field | Used for |
|---|---|---|
| province | `ten_tinh` | place-name matching |
| province | `sap_nhap` | the crosswalk from the 63 pre-2025 province names onto the 34 current units |
| commune | `ten_xa`, `ten_tinh` | two-level name matching |
| both | `dtich_km2`, `dan_so`, `matdo_km2` | the detail panel on the interactive page; if absent the entry is dropped rather than shown as zero |

`sap_nhap` records which former provinces were merged into each current one.
Without that field, a series spanning the 2025 boundary cannot be joined on
place name.

## Provenance and terms of use

Downloaded from <https://gis.vn/ban-do-hanh-chinh-viet-nam>, the **34-province**
set (post-reform). The page states no licence.

**These files are redistributed here on the judgement of this repository's
owner, not under any licence granted by the source.** They are not covered by
the MIT licence that covers the source code — see
[`../THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md). If you intend to
publish maps drawn from them, or to redistribute the data again, settle the
terms with the provider yourself.

## Using a different source

Any source works as long as the geometry is the post-2025 34-province and
3,321-commune division and the fields above are present, spelled that way. Print
what a download actually contains:

```bash
uv run --with geopandas python -c "import geopandas, glob; [print(t, list(geopandas.read_file(glob.glob(f'shapefiles/viet-nam/{t}/*')[0], rows=1).columns)) for t in ('province','commune')]"
```

The set this project was built against reads:

```text
province   ma_tinh ten_tinh sap_nhap quy_mo tru_so loai cap stt dtich_km2 dan_so matdo_km2 geometry
commune    ma_xa ten_xa sap_nhap tru_so loai cap stt dtich_km2 dan_so matdo_km2 ma_tinh ten_tinh geometry
```
