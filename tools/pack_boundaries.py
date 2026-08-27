# -*- coding: utf-8 -*-
"""Pack a country's boundary folders into release assets.

The boundary data does not live in the repository. It is attached to a GitHub
release and fetched by the installer, for three reasons measured on the set we
had: the two Vietnam archives came to 88 MB, the commune one alone was 74.7 MB
against GitHub's 50 MB warning and its 100 MB hard limit, and every country
added would have gone into the history of every clone for ever.

One archive per country and tier, named ``<country>-<tier>.zip``, and the
folder structure lives **inside** the archive::

    viet-nam-commune.zip
      viet-nam/commune/Việt Nam (phường xã) - 34.shp
      ...

so unpacking is ``extractall`` into the shapefile root and the layout comes out
right. The installer needs to know no layout at all, and a country added later
needs no change to it.

    python tools/pack_boundaries.py                 # every country present
    python tools/pack_boundaries.py viet-nam        # just one

Writes into ``dist/boundaries/``, which is not tracked: these are release
assets, uploaded once, not repository content.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shapefiles"
OUT = ROOT / "dist" / "boundaries"

#: The pieces a shapefile needs to be readable. ``.cpg`` is not optional in
#: practice: without it a reader guesses the code page and Vietnamese names come
#: back as mojibake — a defect this project has already been bitten by.
PARTS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def tiers(country: Path):
    for tier in sorted(p for p in country.iterdir() if p.is_dir()):
        files = [f for f in sorted(tier.iterdir())
                 if f.is_file() and f.suffix.lower() in PARTS]
        if files:
            yield tier.name, files


def codepage_warning(files: list[Path]) -> str | None:
    """A shapefile whose attribute table does not say how it is encoded.

    Found on the Canada set: no ``.cpg``, so a plain reader decodes its UTF-8
    names as Latin-1 and Québec arrives as ``QuÃ©bec`` — a province that can
    never match a spreadsheet. The engine detects this and re-reads, so a map
    still comes out right; but anything else that opens the archive gets the
    mojibake, and packing it away spreads the problem rather than the fix.

    Reported, not repaired. Writing a ``.cpg`` means asserting an encoding, and
    this script has not read the file to find out which one.
    """
    shapefiles = [f for f in files if f.suffix.lower() == ".shp"]
    naked = [f for f in shapefiles if not f.with_suffix(".cpg").exists()]
    if not naked:
        return None
    return ("no .cpg beside " + ", ".join(f.name for f in naked)
            + " — readers will guess the codepage, and non-ASCII names come "
              "out wrong. Add one holding the encoding, e.g. UTF-8.")


def pack(country: Path) -> list[Path]:
    written = []
    for tier_name, files in tiers(country):
        target = OUT / f"{country.name}-{tier_name}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            for f in files:
                # the path inside the archive is the layout the engine expects
                archive.write(f, f"{country.name}/{tier_name}/{f.name}")
        raw = sum(f.stat().st_size for f in files)
        print(f"  {target.name:<28} {target.stat().st_size / 1048576:6.1f} MB"
              f"  (from {raw / 1048576:.1f} MB, {len(files)} files)")
        warning = codepage_warning(files)
        if warning:
            print(f"    warning: {warning}")
        written.append(target)
    return written


def main(argv: list[str]) -> int:
    wanted = argv or [p.name for p in sorted(SOURCE.iterdir())
                      if p.is_dir() and not p.name.startswith(".")]
    if not wanted:
        print("no country folders under shapefiles/", file=sys.stderr)
        return 1
    total = []
    for name in wanted:
        country = SOURCE / name
        if not country.is_dir():
            print(f"  skipped {name}: no such folder", file=sys.stderr)
            continue
        print(f"{name}:")
        total += pack(country)
    if total:
        size = sum(p.stat().st_size for p in total) / 1048576
        print(f"\n{len(total)} archives, {size:.1f} MB, in {OUT}")
        print("Attach these to a GitHub release; do not commit them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
