"""Simulated workbooks for seven public-health programmes, in every shape the
skill is meant to read.

**Every number here is invented.** Nothing was observed, nothing was reported by
anybody, and none of it may be used for a report or a programme decision. Each
sheet says so in its own guidance tab.

The point is coverage, not realism. ``tools/sweep_maps.py`` draws several
hundred maps from these files, and a map can only fail in a way this generator
makes possible: if no workbook here carries a category column, no map is ever
drawn from one, and the sweep proves nothing about that path. So the shapes are
enumerated deliberately:

===================== ==========================================================
shape                 what it exercises
===================== ==========================================================
``tinh``              province level, one period, count + rate + share + group
``tinh-theo-nam``     province level, five years -- a series
``tinh-hai-nam``      two years in two COLUMNS -- what a change map needs
``tinh-thieu``        a third of the units missing, to exercise the grey class
``xa``                commune level, one period, for three provinces
``xa-theo-quy``       commune level, four quarters, for one province
``dai-chi-so``        long form: an indicator column, numerator and denominator
``dai-chi-so-loi``    the same, with the numerator deliberately over the
                      denominator, so the "a share cannot exceed 100%" warning
                      keeps being met
``co-so-toa-do``      facility coordinates -- point maps, coloured and sized
``ten-lech``          names with prefixes and dropped accents, to exercise matching
===================== ==========================================================

Unit names are read out of the installed boundary files rather than typed, so
nothing can fail to match for a reason that is this file's fault. Numbers are a
settled function of the unit's name: the same workbook comes out of every run,
because a sweep whose input moves cannot tell a regression from the weather.

    uv run --offline --with pandas --with openpyxl --with geopandas \
        python tools/generate_programme_data.py

Writes into ``input/_sweep/``, which is not tracked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "easy-map" / "scripts"))

OUT = ROOT / "input" / "_sweep"

DISCLAIMER = ("Dữ liệu giả lập phục vụ kiểm thử kỹ thuật. Không phải số liệu "
              "giám sát thật và không được dùng cho báo cáo hay quyết định "
              "chuyên môn.")

#: Communes are drawn for these three provinces. Chosen for contrast rather than
#: for importance: one dense city, one province with detached islands, one
#: ordinary mainland province. A sweep that only ever saw compact inland units
#: would never meet the label crowding or the inset logic.
COMMUNE_PROVINCES = ("Hà Nội", "Khánh Hòa", "Nghệ An")

#: The province whose communes get a four-quarter series. One is enough: the
#: series machinery does not care which province it is, and every extra one
#: multiplies the sweep's running time by a full commune render.
SERIES_PROVINCE = "Cần Thơ"

YEARS = (2022, 2023, 2024, 2025, 2026)
QUARTERS = ("Q1/2026", "Q2/2026", "Q3/2026", "Q4/2026")


def settled(name: str, low: float, high: float, salt: int = 0) -> float:
    """A fixed value for a name: same name, same number, every run.

    Not ``random`` with a seed. A seeded generator gives the same *sequence*,
    so inserting one province shifts every number after it and the whole sweep
    looks changed. Keying on the name itself means a unit's figures depend on
    nothing but the unit.
    """
    h = 0
    for ch in f"{name}|{salt}":
        h = (h * 131 + ord(ch)) % 1_000_003
    return round(low + (high - low) * (h / 1_000_003), 2)


def pick(name: str, options: "tuple[str, ...]", salt: int = 0) -> str:
    """One of ``options``, settled on the name.

    By modulo on the hash, not by scaling ``settled`` into a range: ``settled``
    rounds to two places, so a value a whisker under the top of the range rounds
    *up* to it and the index runs one past the end. That is not a rare edge —
    it happened on the first province of the first programme.
    """
    h = 0
    for ch in f"{name}|{salt}":
        h = (h * 131 + ord(ch)) % 1_000_003
    return options[h % len(options)]


# --------------------------------------------------------------------------
# the seven programmes
#
# Each is a column vocabulary, not a data set: the same shapes are generated for
# all of them, so a defect that only shows up on, say, a per-100,000 rate is met
# seven times rather than once.

PROGRAMMES = {
    "hiv": {
        "ten": "HIV/AIDS",
        "mau_so": ("Dân số", 60_000, 2_400_000),
        "quan_the": ("Quần thể đích ước tính", 400, 42_000),
        "dem": ("Số ca HIV mới phát hiện", 5, 900),
        "dem_2": ("Số người điều trị ARV", 40, 12_000),
        "ty_le": ("Tỷ lệ điều trị ARV (%)", 41.0, 98.5),
        "suat": ("Tỷ suất ca mới trên 100.000 dân", 1.2, 34.0),
        "nhom": ("Mức ưu tiên", ("Thấp", "Trung bình", "Cao", "Rất cao")),
    },
    "viem-gan-b": {
        "ten": "Viêm gan B",
        "mau_so": ("Số trẻ sinh sống", 900, 46_000),
        "quan_the": ("Số phụ nữ mang thai được quản lý", 700, 39_000),
        "dem": ("Số trẻ tiêm vắc xin trong 24 giờ đầu", 500, 43_000),
        "dem_2": ("Số ca HBsAg dương tính", 3, 1_400),
        "ty_le": ("Tỷ lệ tiêm vắc xin viêm gan B sơ sinh (%)", 52.0, 99.2),
        "suat": ("Tỷ lệ HBsAg dương tính ở thai phụ (%)", 0.4, 12.6),
        "nhom": ("Xếp loại tiến độ", ("Chưa đạt", "Cận đạt", "Đạt", "Vượt")),
    },
    "lao": {
        "ten": "Phòng chống lao",
        "mau_so": ("Dân số", 60_000, 2_400_000),
        "quan_the": ("Số người được khám sàng lọc lao", 2_000, 180_000),
        "dem": ("Số ca lao các thể được phát hiện", 8, 2_100),
        "dem_2": ("Số ca lao kháng thuốc", 0, 96),
        "ty_le": ("Tỷ lệ điều trị lao thành công (%)", 68.0, 96.4),
        "suat": ("Tỷ suất lao trên 100.000 dân", 22.0, 198.0),
        "nhom": ("Mức gánh nặng", ("Thấp", "Trung bình", "Cao")),
    },
    "tiem-chung": {
        "ten": "Tiêm chủng mở rộng",
        "mau_so": ("Số trẻ dưới 1 tuổi", 800, 44_000),
        "quan_the": ("Số trẻ trong diện tiêm chủng", 780, 43_500),
        "dem": ("Số trẻ tiêm đủ mũi", 600, 42_800),
        "dem_2": ("Số trẻ bỏ mũi", 2, 3_100),
        "ty_le": ("Tỷ lệ tiêm chủng đầy đủ (%)", 61.0, 99.6),
        "suat": ("Tỷ lệ bỏ mũi (%)", 0.3, 18.4),
        "nhom": ("Nguy cơ dịch", ("Thấp", "Trung bình", "Cao", "Rất cao")),
    },
    "sot-ret": {
        "ten": "Phòng chống sốt rét",
        "mau_so": ("Dân số vùng nguy cơ", 1_200, 320_000),
        "quan_the": ("Số lượt xét nghiệm ký sinh trùng", 300, 74_000),
        "dem": ("Số ca sốt rét", 0, 260),
        "dem_2": ("Số ca sốt rét nội địa", 0, 88),
        "ty_le": ("Tỷ lệ ngủ màn tẩm hóa chất (%)", 35.0, 97.0),
        "suat": ("Tỷ suất mắc trên 1.000 dân nguy cơ", 0.0, 6.4),
        "nhom": ("Phân vùng dịch tễ", ("Không lưu hành", "Nguy cơ thấp",
                                       "Lưu hành nhẹ", "Lưu hành nặng")),
    },
    "sot-xuat-huyet": {
        "ten": "Sốt xuất huyết",
        "mau_so": ("Dân số", 60_000, 2_400_000),
        "quan_the": ("Số hộ được giám sát véc tơ", 400, 62_000),
        "dem": ("Số ca mắc", 4, 9_400),
        "dem_2": ("Số ổ dịch được xử lý", 0, 420),
        "ty_le": ("Tỷ lệ ổ dịch được xử lý trong 48 giờ (%)", 44.0, 100.0),
        "suat": ("Tỷ suất mắc trên 100.000 dân", 3.0, 640.0),
        "nhom": ("Cấp độ dịch", ("Bình thường", "Cảnh báo", "Bùng phát")),
    },
    "dinh-duong": {
        "ten": "Dinh dưỡng trẻ em",
        "mau_so": ("Số trẻ dưới 5 tuổi", 3_000, 190_000),
        "quan_the": ("Số trẻ được cân đo", 2_400, 180_000),
        "dem": ("Số trẻ suy dinh dưỡng thể thấp còi", 90, 34_000),
        "dem_2": ("Số trẻ suy dinh dưỡng thể gầy còm", 20, 9_800),
        "ty_le": ("Tỷ lệ suy dinh dưỡng thấp còi (%)", 6.4, 34.8),
        "suat": ("Tỷ lệ suy dinh dưỡng gầy còm (%)", 1.1, 12.9),
        "nhom": ("Mức can thiệp", ("Duy trì", "Tăng cường", "Ưu tiên")),
    },
}


# --------------------------------------------------------------------------
def unit_names(tier: str, column: str) -> pd.DataFrame:
    """Unit names as the *engine* reads them, not as geopandas reads them.

    A boundary set shipped without ``.cpg`` has its UTF-8 attribute table
    decoded as Latin-1 by a plain reader, and a generator that does not notice
    invents figures for a place the map has never heard of. The run then reports
    one unmatched row and the reader goes looking at their spreadsheet for a
    fault that is not there.
    """
    from emap import dataio

    folder = ROOT / "shapefiles" / "viet-nam" / tier
    shp = next(folder.glob("*.shp"))
    frame = gpd.read_file(shp)
    if dataio._encoding_repair(frame, shp) is not None:
        frame = gpd.read_file(shp, encoding="utf-8")
    return frame[[c for c in frame.columns if c != "geometry"]]


def guidance(extra: str = "") -> pd.DataFrame:
    return pd.DataFrame({"Hướng dẫn": [
        DISCLAIMER,
        "Sinh bởi tools/generate_programme_data.py, không có yếu tố ngẫu nhiên.",
        "Mỗi lần chạy lại cho ra đúng cùng một tệp.",
        extra or "Dùng cho tools/sweep_maps.py.",
    ]})


def write(name: str, sheets: "dict[str, pd.DataFrame]", note: str = "") -> Path:
    path = OUT / f"{name}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet[:31], index=False)
        guidance(note).to_excel(writer, sheet_name="Hướng dẫn", index=False)
    return path


# --------------------------------------------------------------------------
def province_rows(names, spec, salt=0, drop_every=0):
    """One row per province. ``drop_every`` leaves gaps, on purpose.

    A map where every unit has data never draws the grey class, never triggers
    the coverage warning, and never tests the legend row that explains grey —
    all three of which a real programme table exercises constantly.
    """
    mau_so, mau_lo, mau_hi = spec["mau_so"]
    qt, qt_lo, qt_hi = spec["quan_the"]
    dem, d_lo, d_hi = spec["dem"]
    dem2, d2_lo, d2_hi = spec["dem_2"]
    tyle, t_lo, t_hi = spec["ty_le"]
    suat, s_lo, s_hi = spec["suat"]
    nhom, groups = spec["nhom"]

    rows = []
    for index, name in enumerate(names):
        if drop_every and index % drop_every == 0:
            continue
        rows.append({
            "Tỉnh/thành phố": name,
            "Kỳ báo cáo": "2026",
            mau_so: int(settled(name, mau_lo, mau_hi, salt + 1)),
            qt: int(settled(name, qt_lo, qt_hi, salt + 2)),
            dem: int(settled(name, d_lo, d_hi, salt + 3)),
            dem2: int(settled(name, d2_lo, d2_hi, salt + 4)),
            tyle: settled(name, t_lo, t_hi, salt + 5),
            suat: settled(name, s_lo, s_hi, salt + 6),
            nhom: pick(name, groups, salt + 7),
        })
    return pd.DataFrame(rows)


def commune_rows(frame, province, spec, salt=0):
    part = frame[frame["ten_tinh"].astype(str) == province]
    mau_so, mau_lo, mau_hi = spec["mau_so"]
    dem, d_lo, d_hi = spec["dem"]
    tyle, t_lo, t_hi = spec["ty_le"]
    nhom, groups = spec["nhom"]
    rows = []
    for name in part["ten_xa"].astype(str):
        key = f"{province}/{name}"
        rows.append({
            "Tỉnh/thành phố": province,
            "Xã/phường": name,
            "Kỳ báo cáo": "2026",
            mau_so: int(settled(key, mau_lo / 40, mau_hi / 40, salt + 1)),
            dem: int(settled(key, d_lo, max(d_hi / 30, d_lo + 2), salt + 2)),
            tyle: settled(key, t_lo, t_hi, salt + 3),
            nhom: pick(key, groups, salt + 4),
        })
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    provinces = unit_names("province", "ten_tinh")
    communes = unit_names("commune", "ten_xa")
    names = [str(v) for v in provinces["ten_tinh"]]
    written = []

    for slug, spec in PROGRAMMES.items():
        # -- province, one period ------------------------------------------
        written.append(write(f"{slug}-tinh", {
            "Dữ liệu tỉnh": province_rows(names, spec),
        }, f"Chương trình {spec['ten']}, cấp tỉnh, một kỳ."))

        # -- province, five years ------------------------------------------
        series = []
        for year in YEARS:
            block = province_rows(names, spec, salt=year)
            block["Năm"] = year
            series.append(block)
        written.append(write(f"{slug}-tinh-theo-nam", {
            "Theo năm": pd.concat(series, ignore_index=True),
        }, f"Chương trình {spec['ten']}, cấp tỉnh, {len(YEARS)} năm."))

        # -- a third of the provinces absent -------------------------------
        written.append(write(f"{slug}-tinh-thieu", {
            "Thiếu số liệu": province_rows(names, spec, drop_every=3),
        }, "Một phần ba số tỉnh không có dòng nào, để bản đồ phải vẽ ô xám."))

        # -- two years side by side, in columns ----------------------------
        #
        # The shape a change map needs, and a shape the five-year sheet above
        # cannot stand in for: --baseline-column and --comparison-column take
        # COLUMN NAMES. Writing a year there instead used to reach pandas and
        # come back as ``KeyError: '2026'``.
        tyle = spec["ty_le"][0]
        first, last = YEARS[0], YEARS[-1]
        wide = province_rows(names, spec, salt=first)[["Tỉnh/thành phố"]].copy()
        wide[f"{tyle} {first}"] = province_rows(names, spec, salt=first)[tyle]
        wide[f"{tyle} {last}"] = province_rows(names, spec, salt=last)[tyle]
        written.append(write(f"{slug}-tinh-hai-nam", {
            "Hai năm": wide,
        }, f"Hai năm nằm ở hai CỘT, dùng cho bản đồ thay đổi."))

    # -- commune level, three provinces, three programmes -------------------
    for slug in ("hiv", "lao", "tiem-chung"):
        spec = PROGRAMMES[slug]
        for province in COMMUNE_PROVINCES:
            block = commune_rows(communes, province, spec)
            if block.empty:
                print(f"  skipped {slug}/{province}: no communes found", file=sys.stderr)
                continue
            slug_p = {"Hà Nội": "ha-noi", "Khánh Hòa": "khanh-hoa",
                      "Nghệ An": "nghe-an"}[province]
            written.append(write(f"{slug}-xa-{slug_p}", {
                "Dữ liệu xã": block,
            }, f"Chương trình {spec['ten']}, cấp xã, {province}."))

    # -- commune level, four quarters, one province -------------------------
    spec = PROGRAMMES["sot-xuat-huyet"]
    quarters = []
    for index, quarter in enumerate(QUARTERS):
        block = commune_rows(communes, SERIES_PROVINCE, spec, salt=index * 11)
        block["Kỳ báo cáo"] = quarter
        quarters.append(block)
    written.append(write("sot-xuat-huyet-xa-theo-quy", {
        "Theo quý": pd.concat(quarters, ignore_index=True),
    }, f"Cấp xã, {SERIES_PROVINCE}, {len(QUARTERS)} quý."))

    # -- long form: one indicator column, numerator and denominator ---------
    #
    # The shape a real programme export arrives in, and the one that most easily
    # counts a unit three times: every disaggregation is another row.
    #
    # The numerator is drawn as a SHARE of the denominator, not independently.
    # Drawn independently -- as the first version did -- it exceeds the
    # denominator often enough that the ratio comes out above 100%, and the
    # sweep's guardrail said so on all four ratio cases. The guardrail was
    # right; the data was nonsense. A viral-suppression rate of 130% is not a
    # case worth having as the default one.
    long_rows = []
    for slug in ("hiv", "lao"):
        spec = PROGRAMMES[slug]
        for name in names:
            for sex in ("Nam", "Nữ"):
                key = f"{name}{sex}{slug}"
                denominator = int(settled(key, 40, 12_000, 3))
                values = {
                    "TX_CURR": int(settled(key, 40, 12_000, 4)),
                    "TX_PVLS Den": denominator,
                    "TX_PVLS Num": int(denominator * settled(key, 0.55, 0.98, 5)),
                }
                for indicator, value in values.items():
                    long_rows.append({
                        "Tỉnh/thành phố": name,
                        "Chương trình": spec["ten"],
                        "Chỉ số": indicator,
                        "Giới tính": sex,
                        "Kỳ": "Q2/2026",
                        "Giá trị": value,
                    })
    written.append(write("dai-chi-so", {
        "DATA": pd.DataFrame(long_rows),
    }, "Dạng bảng dài: một cột chỉ số, tử số và mẫu số nằm ở các dòng khác nhau."))

    # The same shape with the numerator deliberately larger than the
    # denominator, so the "a share cannot exceed 100%" guardrail keeps being
    # exercised now that the ordinary case no longer trips it. A real programme
    # export does arrive like this -- two indicators counted over different
    # populations, or a denominator reported late.
    broken = []
    for row in long_rows:
        if row["Chỉ số"] == "TX_PVLS Num":
            row = dict(row, **{"Giá trị": int(row["Giá trị"] * 1.6) + 40})
        broken.append(row)
    written.append(write("dai-chi-so-loi", {
        "DATA": pd.DataFrame(broken),
    }, "Tử số CỐ Ý lớn hơn mẫu số, để chạy qua cảnh báo tỷ lệ vượt 100%."))

    # -- facility coordinates ----------------------------------------------
    #
    # Placed at each province's own centroid, nudged apart, so every point falls
    # inside the country: a point map drawn from coordinates in the sea would
    # test the renderer against a case no user has.
    points = []
    frame = gpd.read_file(next((ROOT / "shapefiles" / "viet-nam" / "province").glob("*.shp")))
    centres = frame.geometry.representative_point()
    for index, name in enumerate(names):
        centre = centres.iloc[index]
        for k in range(3):
            key = f"{name}#{k}"
            points.append({
                "Tên cơ sở": f"Cơ sở {k + 1} - {name}",
                "Tỉnh/thành phố": name,
                "Loại hình": pick(key, ("Bệnh viện", "Trung tâm y tế",
                                        "Trạm y tế", "Phòng khám"), 8),
                "Kinh độ": round(centre.x + (k - 1) * 0.08, 5),
                "Vĩ độ": round(centre.y + (k - 1) * 0.06, 5),
                "Số lượt khám": int(settled(key, 300, 84_000, 9)),
                "Tỷ lệ hài lòng (%)": settled(key, 62.0, 99.0, 10),
            })
    written.append(write("co-so-toa-do", {
        "Cơ sở": pd.DataFrame(points),
    }, "Toạ độ cơ sở y tế, dùng cho bản đồ điểm."))

    # -- names that need matching work --------------------------------------
    #
    # Prefixes and dropped accents, which is how a real spreadsheet arrives.
    messy = province_rows(names, PROGRAMMES["hiv"], salt=77)
    import unicodedata

    def bare(text: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", text)
                       if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")

    messy["Tỉnh/thành phố"] = [
        bare(n) if i % 3 == 0 else (f"Tỉnh {n}" if i % 3 == 1 else n)
        for i, n in enumerate(messy["Tỉnh/thành phố"])]
    written.append(write("ten-lech", {
        "Tên lệch": messy,
    }, "Một phần ba tên bỏ dấu, một phần ba thêm tiền tố 'Tỉnh'."))

    print(f"{len(written)} workbooks in {OUT}")
    for path in sorted(written):
        print(f"  {path.name:34} {path.stat().st_size / 1024:7.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
