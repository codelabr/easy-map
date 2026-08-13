# Administrative boundaries

This folder is **deliberately empty** in the repository. Without the shapefiles
the skill cannot draw anything, but they cannot be committed either:

| File | Size | Problem |
|---|---|---|
| `communes/Việt Nam (phường xã) - 34.shp` | 111.3 MB | over GitHub's **100 MB per-file limit** |
| `communes/` (zipped) | 74.7 MB | under the limit, but GitHub still warns above 50 MB |
| `provinces/Việt Nam (tỉnh thành) - 34.shp` | 20.0 MB | committable, but kept with the other for consistency |

## What is needed

Two folders, each a complete shapefile set (`.shp`, `.shx`, `.dbf`, `.prj`,
`.cpg`) on the administrative boundaries **as they stand after the 2025 reform
to a two-tier local government model**. Those two tiers, province and commune,
are the only ones the skill draws; the district tier the reform abolished is not
supported:

```text
shapefiles/
├── provinces/      34 provinces and centrally-run cities
└── communes/    3,321 wards and communes
```

Required attribute fields:

| Level | Field | Used for |
|---|---|---|
| province | `ten_tinh` | place-name matching |
| province | `sap_nhap` | the crosswalk from the 63 pre-2025 province names onto the 34 current units |
| commune | `ten_xa`, `ten_tinh` | two-level name matching |
| both | `dtich_km2`, `dan_so`, `matdo_km2` | the detail panel on the interactive page; if absent the entry is dropped rather than shown as zero |

`sap_nhap` records which former provinces were merged into each current one.
Without that field, a series spanning the 2025 boundary cannot be joined on
place name.

## Where to get them

One source that publishes Vietnamese administrative boundaries is
<https://gis.vn/ban-do-hanh-chinh-viet-nam>. At the time of writing it offers
both a **34-province** set (post-reform) and a 63-province one, with shapefile
among the formats, and its attribute list includes a merger-status field of the
kind the crosswalk needs. Take the **34-province** set.

Two things to check yourself before relying on it:

- **Field names.** The skill looks for the names in the table above, spelled
  exactly that way. A download carrying the same information under different
  column names has to be renamed first. Print what you actually got:

  ```bash
  uv run --with geopandas python -c "import geopandas, glob; [print(lvl, list(geopandas.read_file(glob.glob(f'shapefiles/{lvl}/*.shp')[0], rows=1).columns)) for lvl in ('provinces','communes')]"
  ```

  The set this project was built against reads:

  ```text
  provinces  ma_tinh ten_tinh sap_nhap quy_mo tru_so loai cap stt dtich_km2 dan_so matdo_km2 geometry
  communes   ma_xa ten_xa sap_nhap tru_so loai cap stt dtich_km2 dan_so matdo_km2 ma_tinh ten_tinh geometry
  ```
- **Terms of use.** The page states no licence, and access may require
  registration. Whether you may redistribute the files, or use them in published
  material, is between you and the provider. This repository ships no boundary
  data and makes no claim about any provider's terms.

Any source works as long as the geometry is the post-2025 34-province and
3,321-commune division and the fields above are present.

## Putting them in place

Put the two folders where the tree above shows. If you keep them zipped — in the
repository's Releases, or on an internal share — unzip before running:

```bash
python -c "import zipfile; zipfile.ZipFile('provinces.zip').extractall('shapefiles/provinces')"
python -c "import zipfile; zipfile.ZipFile('communes.zip').extractall('shapefiles/communes')"
```

Check that the skill finds them:

```bash
python skills/easy-map/scripts/easy_map.py list --project-root .
```

The reply carries a `shapefile` block naming the two files it resolved. That
confirms the files are in place; it does not check the attribute fields, which
is what the command in the previous section is for.
