"""Build a SIMULATED 2025 testing dataset for the wards and communes of Cần Thơ.

    uv run --with pandas --with openpyxl --with geopandas python tools/generate_testing_cantho.py

Two measures, which is the smallest table that still poses the mapping question
this project exists to answer: a count of people tested, and a count who tested
positive. Colouring by either count would draw population; the honest map
colours by the positivity rate and sizes circles by the count, and the skill has
to be the one to say so.

The place names are read out of the project's own commune shapefile rather than
typed here, so every row matches a real unit and the join cannot silently drop
anything. Everything else is invented.

**The figures are not real.** They are generated from population with a fixed
seed, so the file rebuilds identically, and they carry no relation to any actual
testing programme. The workbook says so on its own first sheet.
"""

from __future__ import annotations

import glob
import io
import os
import random
import sys
from pathlib import Path

import geopandas
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "input" / "xet_nghiem_can_tho_2025.xlsx"

PROVINCE = "Cần Thơ"
YEAR = 2025
SEED = 2025

#: Share of the population reached by testing in a year. Urban wards run a
#: standing service and reach more; rural communes rely on campaigns.
COVERAGE = {"phường": (0.055, 0.130), "xã": (0.020, 0.070)}

#: Positivity. Kept deliberately low and wide: the point of the file is that a
#: place with many tests is not the same as a place with a high positivity rate,
#: so the two must not move together.
POSITIVITY = {"phường": (0.004, 0.022), "xã": (0.002, 0.031)}


def shapefile() -> Path:
    root = os.environ.get("EASY_MAP_SHAPEFILES") or str(ROOT / "shapefiles")
    found = glob.glob(f"{root}/communes/*.shp")
    if not found:
        raise SystemExit(f"No commune shapefile under {root}. See shapefiles/README.md.")
    return Path(found[0])


def kind(row) -> str:
    """'phường' for an urban ward, 'xã' otherwise, from the shapefile's own
    classification rather than from the name, which is not reliable."""
    label = str(row.get("loai") or "").strip().lower()
    return "phường" if "phường" in label else "xã"


def main() -> int:
    log = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    rng = random.Random(SEED)

    gdf = geopandas.read_file(shapefile())
    here = gdf[gdf["ten_tinh"].astype(str).str.strip() == PROVINCE]
    if here.empty:
        raise SystemExit(f"No units for {PROVINCE} in the shapefile.")

    rows = []
    for _, unit in here.sort_values("ten_xa").iterrows():
        pop = int(unit["dan_so"])
        k = kind(unit)
        tested = round(pop * rng.uniform(*COVERAGE[k]))
        # Positivity is drawn independently of coverage on purpose: a ward that
        # tests a lot is not thereby a ward with a high positivity rate, and a
        # file where the two moved together would make the map's central
        # question disappear.
        positive = round(tested * rng.uniform(*POSITIVITY[k]))
        rows.append({
            "Tỉnh/thành phố": PROVINCE,
            "Xã/phường": str(unit["ten_xa"]).strip(),
            "Dân số": pop,
            "Số người được xét nghiệm": tested,
            "Số người có kết quả dương tính": min(positive, tested),
        })

    data = pd.DataFrame(rows)
    assert (data["Số người có kết quả dương tính"] <= data["Số người được xét nghiệm"]).all()

    dictionary = pd.DataFrame([
        ("Tỉnh/thành phố", "Chữ", "Tên tỉnh/thành phố, theo ranh giới sau sáp nhập 2025"),
        ("Xã/phường", "Chữ", "Tên xã/phường, lấy từ dữ liệu ranh giới hành chính"),
        ("Dân số", "Số nguyên", "Dân số của đơn vị, lấy từ dữ liệu ranh giới"),
        ("Số người được xét nghiệm", "Số nguyên", f"Số lượt người được xét nghiệm trong năm {YEAR}"),
        ("Số người có kết quả dương tính", "Số nguyên",
         "Số người có kết quả dương tính; luôn nhỏ hơn hoặc bằng số người được xét nghiệm"),
    ], columns=["Cột", "Kiểu", "Diễn giải"])

    notes = pd.DataFrame([
        ("CẢNH BÁO", "DỮ LIỆU MÔ PHỎNG. Không dùng cho báo cáo hoặc quyết định chương trình."),
        ("Nguồn số liệu", "Sinh tự động từ dân số bằng bộ sinh số ngẫu nhiên có hạt giống cố định."),
        ("Nguồn địa danh", "Tên xã/phường lấy từ dữ liệu ranh giới hành chính của dự án."),
        ("Phạm vi", f"{PROVINCE}, {len(data)} xã/phường, năm {YEAR}."),
        ("Dựng lại", "uv run --with pandas --with openpyxl --with geopandas "
                     "python tools/generate_testing_cantho.py"),
        ("Lưu ý khi vẽ bản đồ",
         "Hai cột đều là SỐ ĐẾM. Tô màu theo số đếm sẽ khiến bản đồ phản ánh dân số. "
         "Cách đọc đúng: tô màu theo tỷ lệ dương tính, thể hiện số lượng bằng kích thước vòng tròn."),
    ], columns=["Mục", "Nội dung"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as book:
        notes.to_excel(book, sheet_name="Hướng dẫn", index=False)
        data.to_excel(book, sheet_name=f"Dữ liệu xã {YEAR}", index=False)
        dictionary.to_excel(book, sheet_name="Từ điển dữ liệu", index=False)

    tested = data["Số người được xét nghiệm"].sum()
    positive = data["Số người có kết quả dương tính"].sum()
    print(f"  {OUT.relative_to(ROOT)}", file=log)
    print(f"  {len(data)} xã/phường · {tested:,} lượt xét nghiệm · {positive:,} dương tính "
          f"({100 * positive / tested:.2f}%)".replace(",", "."), file=log)
    log.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
