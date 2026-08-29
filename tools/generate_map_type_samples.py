"""One simulated HIV workbook per kind of map the skill can draw.

**Every number here is invented.** Nothing was observed, nothing was reported by
anybody, and none of it may be used for a report or a programme decision. Each
workbook says so on its own guidance sheet.

The point is to have, for each map type, the smallest table that makes that map
possible - so somebody trying the skill can see what shape of data each kind of
map needs, rather than guessing. The eight files differ only in their columns:

===============================  ==========================================
file                             what the columns give the map
===============================  ==========================================
``_test_data_choropleth``        one rate: area fill
``_test_data_choropleth_symbol`` a rate and a count: fill plus circles
``_test_data_graduated_symbol``  one count: circles only, no fill
``_test_data_categorized``       an ordered group: one colour per group
``_test_data_boundary``          names only: outlines, nothing shaded
``_test_data_change``            the same rate in two columns, two years
``_test_data_point``             coordinates: one dot per facility
``_test_data_time_series``       a period column: one map per year, or video
===============================  ==========================================

Province names are read out of the installed boundary files rather than typed,
so no row can fail to match for a reason this file is responsible for. Figures
are a settled function of the province name - no randomness, so the same
workbook comes out of every run.

    uv run --offline --with pandas --with openpyxl --with geopandas \
        python tools/generate_map_type_samples.py

Writes into ``input/``, which is not tracked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "easy-map" / "scripts"))

OUT = ROOT / "input"
PREFIX = "_test_data_"

DISCLAIMER = ("Dữ liệu giả lập phục vụ kiểm thử kỹ thuật. Không phải số liệu "
              "giám sát HIV thật và không được dùng cho báo cáo hay quyết định "
              "chuyên môn.")

#: Facilities are placed at each province's own representative point, nudged
#: apart. Coordinates invented outside the country would exercise the renderer
#: against a case no user has.
FACILITIES_PER_PROVINCE = 2

YEARS = (2022, 2023, 2024, 2025, 2026)

PRIORITY = ("Thấp", "Trung bình", "Cao", "Rất cao")


def settled(name: str, low: float, high: float, salt: int = 0) -> float:
    """A fixed value for a name: same name, same number, every run.

    Not ``random`` with a seed. A seeded generator gives the same *sequence*, so
    inserting one province shifts every number after it and every workbook looks
    changed. Keying on the name means a province's figures depend on nothing but
    the province.
    """
    h = 0
    for ch in f"{name}|{salt}":
        h = (h * 131 + ord(ch)) % 1_000_003
    return round(low + (high - low) * (h / 1_000_003), 2)


def pick(name: str, options, salt: int = 0):
    h = 0
    for ch in f"{name}|{salt}":
        h = (h * 131 + ord(ch)) % 1_000_003
    return options[h % len(options)]


def provinces() -> gpd.GeoDataFrame:
    """The province layer, read the way the engine reads it.

    A boundary set shipped without ``.cpg`` has its UTF-8 attribute table
    decoded as Latin-1 by a plain reader, and a generator that does not notice
    invents figures for a province the map has never heard of. The run then
    reports an unmatched row and the reader goes looking at their spreadsheet
    for a fault that is not there.
    """
    from emap import dataio

    root = dataio.shapefile_root(ROOT)
    folder = root / "viet-nam" / "province"
    if not folder.is_dir():
        raise SystemExit(
            f"No province boundaries at {folder}. Install them first, or point "
            f"{dataio.SHAPEFILE_ENV} at them.")
    shp = next(folder.glob("*.shp"))
    frame = gpd.read_file(shp)
    if dataio._encoding_repair(frame, shp) is not None:
        frame = gpd.read_file(shp, encoding="utf-8")
    return frame


def guidance(what: str, command: str) -> pd.DataFrame:
    return pd.DataFrame({"Hướng dẫn": [
        DISCLAIMER,
        f"Dùng cho: {what}",
        "Sinh bởi tools/generate_map_type_samples.py, không có yếu tố ngẫu nhiên.",
        f"Cờ chính: {command}",
    ]})


def write(kind: str, sheet: str, frame: pd.DataFrame, what: str,
          command: str) -> Path:
    path = OUT / f"{PREFIX}{kind}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet[:31], index=False)
        guidance(what, command).to_excel(writer, sheet_name="Hướng dẫn",
                                         index=False)
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = provinces()
    names = [str(v) for v in frame["ten_tinh"]]
    written: list[tuple[Path, str]] = []

    def add(kind, sheet, table, what, command):
        written.append((write(kind, sheet, table, what, command), command))

    # -- one rate: the plainest map there is -------------------------------
    add("choropleth", "Dữ liệu tỉnh", pd.DataFrame([{
        "Tỉnh/thành phố": n,
        "Kỳ báo cáo": "2026",
        "Tỷ lệ điều trị ARV (%)": settled(n, 41.0, 98.5, 1),
    } for n in names]),
        "Bản đồ tô màu vùng theo một tỷ lệ",
        '--map-type choropleth --value-column "Tỷ lệ điều trị ARV (%)"')

    # -- a rate and a count: two channels on one plate ---------------------
    #
    # The rate colours the area and the count sizes a circle. Putting the count
    # in the colour instead is the classic error: a big province is dark because
    # it is big, not because it is worse off.
    add("choropleth_symbol", "Dữ liệu tỉnh", pd.DataFrame([{
        "Tỉnh/thành phố": n,
        "Kỳ báo cáo": "2026",
        "Tỷ lệ điều trị ARV (%)": settled(n, 41.0, 98.5, 1),
        "Số ca HIV mới phát hiện": int(settled(n, 5, 900, 2)),
    } for n in names]),
        "Tô màu theo tỷ lệ, vòng tròn theo số ca",
        '--map-type choropleth-symbol --value-column "Tỷ lệ điều trị ARV (%)" '
        '--symbol-column "Số ca HIV mới phát hiện"')

    # -- a count alone: circles, no fill -----------------------------------
    add("graduated_symbol", "Dữ liệu tỉnh", pd.DataFrame([{
        "Tỉnh/thành phố": n,
        "Kỳ báo cáo": "2026",
        "Số ca HIV mới phát hiện": int(settled(n, 5, 900, 2)),
        "Số người điều trị ARV": int(settled(n, 40, 12_000, 3)),
    } for n in names]),
        "Bản đồ ký hiệu tỷ lệ - diện tích vòng tròn theo số ca",
        '--map-type graduated-symbol --symbol-column "Số ca HIV mới phát hiện"')

    # -- an ordered group --------------------------------------------------
    #
    # Ordered on purpose: the legend must run Thấp -> Rất cao, not alphabetically.
    add("categorized", "Dữ liệu tỉnh", pd.DataFrame([{
        "Tỉnh/thành phố": n,
        "Kỳ báo cáo": "2026",
        "Mức ưu tiên": pick(n, PRIORITY, 4),
    } for n in names]),
        "Bản đồ phân loại - một màu cho mỗi nhóm, thang có thứ tự",
        '--map-type categorized --value-column "Mức ưu tiên"')

    # -- names only --------------------------------------------------------
    add("boundary", "Danh sách tỉnh", pd.DataFrame([{
        "Tỉnh/thành phố": n,
        "Kỳ báo cáo": "2026",
        "Có cơ sở điều trị ARV": pick(n, ("Có", "Không"), 5),
    } for n in names]),
        "Bản đồ ranh giới - chỉ vẽ đường biên, không tô số liệu",
        '--map-type boundary --value-column "Có cơ sở điều trị ARV"')

    # -- the same rate twice, in two columns -------------------------------
    #
    # Two COLUMNS, not two rows under a period column. --baseline-column and
    # --comparison-column take column names; writing a year there reaches pandas
    # as a KeyError.
    #
    # The later year is the earlier one plus a change that can be NEGATIVE.
    # Drawing the two years independently from ranges that do not overlap made
    # every province improve, which leaves a diverging scale with nothing to
    # diverge about: red then means "improved least" rather than "got worse",
    # and a sample that teaches the wrong reading is worse than no sample.
    first, last = YEARS[0], YEARS[-1]
    change_rows = []
    for n in names:
        base = settled(n, 45.0, 92.0, first)
        later = round(min(99.0, max(5.0, base + settled(n, -12.0, 14.0, last))), 2)
        change_rows.append({
            "Tỉnh/thành phố": n,
            f"Tỷ lệ điều trị ARV (%) {first}": base,
            f"Tỷ lệ điều trị ARV (%) {last}": later,
        })
    add("change", "Hai năm", pd.DataFrame(change_rows),
        "Bản đồ thay đổi - hiệu giữa hai cột, thang màu hai chiều",
        f'--map-type change --baseline-column "Tỷ lệ điều trị ARV (%) {first}" '
        f'--comparison-column "Tỷ lệ điều trị ARV (%) {last}"')

    # -- coordinates -------------------------------------------------------
    centres = frame.geometry.representative_point()
    rows = []
    for index, n in enumerate(names):
        centre = centres.iloc[index]
        for k in range(FACILITIES_PER_PROVINCE):
            key = f"{n}#{k}"
            rows.append({
                "Tên cơ sở": f"Phòng khám ngoại trú {k + 1} - {n}",
                "Tỉnh/thành phố": n,
                "Loại hình": pick(key, ("Bệnh viện tỉnh", "Trung tâm y tế",
                                        "Phòng khám ngoại trú"), 6),
                "Kinh độ": round(centre.x + (k - 0.5) * 0.12, 5),
                "Vĩ độ": round(centre.y + (k - 0.5) * 0.09, 5),
                "Số bệnh nhân đang điều trị": int(settled(key, 40, 4_200, 7)),
            })
    add("point", "Cơ sở điều trị", pd.DataFrame(rows),
        "Bản đồ điểm - một chấm cho mỗi cơ sở, theo toạ độ",
        '--map-type point --lon-column "Kinh độ" --lat-column "Vĩ độ" '
        '--point-color-column "Loại hình" '
        '--point-size-column "Số bệnh nhân đang điều trị"')

    # -- a period column ---------------------------------------------------
    series = []
    for year in YEARS:
        for n in names:
            tested = int(settled(n, 4_000, 90_000, year))
            series.append({
                "Tỉnh/thành phố": n,
                "Năm": year,
                "Số người xét nghiệm HIV": tested,
                "Số ca HIV mới phát hiện": int(settled(n, 5, 900, year + 1)),
                "Tỷ lệ điều trị ARV (%)": settled(n, 41.0, 98.5, year + 2),
            })
    add("time_series", "Theo năm", pd.DataFrame(series),
        "Chuỗi thời gian - một tấm cho mỗi năm, hoặc video",
        '--value-column "Tỷ lệ điều trị ARV (%)" --period-column "Năm" '
        '--period 2026   (thêm --animate để xuất video)')

    print(f"{len(written)} workbooks in {OUT}\n")
    for path, command in written:
        print(f"  {path.name:38} {path.stat().st_size / 1024:6.0f} KB")
        print(f"  {'':38} {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
