"""Build two simulated HIV programme workbooks for testing the skill.

All numbers are generated, not observed. Every sheet says so, and the workbooks
carry a guidance sheet stating it again, so nobody mistakes these for
surveillance data.

    uv run --offline --with pandas --with openpyxl --with geopandas \
        python tools/generate_hiv_demo.py

Produces:
    input/chuong_trinh_hiv_tinh.xlsx       province level, all 34 provinces
    input/chuong_trinh_hiv_lao_xa.xlsx     commune level, 3 provinces, with clinic coordinates
"""

from __future__ import annotations

import random
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260805
DISCLAIMER = ("Dữ liệu giả lập phục vụ kiểm thử kỹ thuật. Không phải số liệu giám sát "
              "thật và không được dùng cho báo cáo hay quyết định chuyên môn.")

COMMUNE_PROVINCES = ["Hà Nội", "Hải Phòng", "Nghệ An"]
COMMUNES_PER_PROVINCE = 14

#: names that collapse onto each other once accents are dropped; including one
#: lets the fixture exercise the ambiguous-match guardrail against real geography
AMBIGUOUS_NAMES = {"Hải Phòng": ["Cẩm Giang", "Cẩm Giàng"]}


def load_shapes():
    """The two Vietnam tiers, found rather than named.

    This used to spell out ``shapefiles/provinces/Việt Nam (tỉnh thành) - 34.shp``
    and broke silently when the folders became ``viet-nam/province/`` — a path
    written once in a generator nothing else exercises. A tier folder holds
    exactly one dataset, so globbing it needs no filename at all.
    """
    def one(tier: str):
        folder = ROOT / "shapefiles" / "viet-nam" / tier
        found = sorted(folder.glob("*.shp"))
        if not found:
            raise SystemExit(
                f"no shapefile in {folder}. Install the boundaries first, or "
                f"point EASY_MAP_SHAPEFILES at them.")
        return gpd.read_file(found[0])

    return one("province"), one("commune")


# --------------------------------------------------------------------------
def build_province_sheet(provinces, rng) -> pd.DataFrame:
    rows = []
    for _, p in provinces.iterrows():
        population = int(p["dan_so"]) if pd.notna(p["dan_so"]) else rng.randint(400_000, 3_000_000)
        # key population estimated at a fraction of adults
        key_pop = int(population * rng.uniform(0.004, 0.011))
        tested = int(key_pop * rng.uniform(0.45, 0.95))
        positivity = rng.uniform(0.4, 3.2)
        new_2026 = max(3, int(tested * positivity / 100))
        new_2025 = max(3, int(new_2026 * rng.uniform(0.82, 1.24)))

        # 95-95-95 cascade, each step conditional on the previous one
        estimated_plhiv = max(new_2026 * 8, int(key_pop * rng.uniform(0.02, 0.09)))
        known_rate = rng.uniform(78.0, 96.5)
        known = int(estimated_plhiv * known_rate / 100)
        on_art_rate = rng.uniform(80.0, 97.0)
        on_art = int(known * on_art_rate / 100)
        suppressed_rate = rng.uniform(88.0, 98.5)

        prep_target = int(key_pop * rng.uniform(0.18, 0.45))
        prep_users = int(prep_target * rng.uniform(0.25, 0.92))
        prep_coverage = round(prep_users / prep_target * 100, 1) if prep_target else 0.0
        prep_change = round(rng.uniform(-6.5, 18.0), 1)

        rows.append({
            "Tỉnh/thành phố": p["ten_tinh"],
            "Kỳ báo cáo": "Năm 2026",
            "Dân số": population,
            "Quần thể đích ước tính": key_pop,
            "Số người xét nghiệm HIV 2026": tested,
            "Số ca HIV mới phát hiện 2025": new_2025,
            "Số ca HIV mới phát hiện 2026": new_2026,
            "Tỷ lệ dương tính (%)": round(positivity, 2),
            "Tỷ suất ca mới/100.000 dân": round(new_2026 / population * 100_000, 1),
            "Số người nhiễm HIV ước tính": estimated_plhiv,
            "Tỷ lệ biết tình trạng nhiễm (%)": round(known_rate, 1),
            "Số người đang điều trị ARV": on_art,
            "Tỷ lệ điều trị ARV (%)": round(on_art_rate, 1),
            "Tỷ lệ ức chế tải lượng vi rút (%)": round(suppressed_rate, 1),
            "Số người dùng PrEP 2026": prep_users,
            "Chỉ tiêu PrEP 2026": prep_target,
            "Tỷ lệ bao phủ PrEP (%)": prep_coverage,
            "Thay đổi bao phủ PrEP (điểm %)": prep_change,
            "Số cơ sở điều trị ARV": max(1, int(population / rng.uniform(180_000, 420_000))),
            "Ngân sách chương trình 2026 (VND)": int(on_art * rng.uniform(2.6e6, 5.4e6)),
            "Mức ưu tiên": rng.choices(
                ["Rất cao", "Cao", "Trung bình", "Thường quy"], weights=[2, 4, 5, 4])[0],
        })
    return pd.DataFrame(rows)


def build_province_quarters(df: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        base_tested = r["Số người xét nghiệm HIV 2026"] / 4
        base_new = r["Số ca HIV mới phát hiện 2026"] / 4
        for quarter in ("Quý I/2026", "Quý II/2026", "Quý III/2026", "Quý IV/2026"):
            factor = rng.uniform(0.78, 1.24)
            tested = max(1, int(base_tested * factor))
            new_cases = max(0, int(base_new * factor))
            rows.append({
                "Tỉnh/thành phố": r["Tỉnh/thành phố"],
                "Kỳ báo cáo": quarter,
                "Số người xét nghiệm HIV": tested,
                "Số ca HIV mới phát hiện": new_cases,
                "Tỷ lệ dương tính (%)": round(new_cases / tested * 100, 2) if tested else 0.0,
                "Số người dùng PrEP": max(0, int(r["Số người dùng PrEP 2026"] / 4 * factor)),
            })
    return pd.DataFrame(rows)


PROVINCE_DICTIONARY = [
    ("Tỉnh/thành phố", "Tên đơn vị hành chính cấp tỉnh sau sắp xếp", "văn bản", "không cộng gộp"),
    ("Kỳ báo cáo", "Kỳ số liệu", "văn bản", "không cộng gộp"),
    ("Dân số", "Dân số toàn tỉnh", "người", "cộng tổng"),
    ("Quần thể đích ước tính", "Ước tính quần thể nguy cơ cao", "người", "cộng tổng"),
    ("Số người xét nghiệm HIV 2026", "Lượt người được xét nghiệm HIV trong năm", "người", "cộng tổng"),
    ("Số ca HIV mới phát hiện 2025", "Ca nhiễm mới phát hiện năm 2025", "ca", "cộng tổng"),
    ("Số ca HIV mới phát hiện 2026", "Ca nhiễm mới phát hiện năm 2026", "ca", "cộng tổng"),
    ("Tỷ lệ dương tính (%)", "Số ca dương tính trên số người xét nghiệm", "%", "trung bình có trọng số theo số người xét nghiệm"),
    ("Tỷ suất ca mới/100.000 dân", "Ca mới trên 100.000 dân", "trên 100.000 dân", "tính lại từ tử số và mẫu số"),
    ("Số người nhiễm HIV ước tính", "Ước tính tổng số người sống chung với HIV", "người", "cộng tổng"),
    ("Tỷ lệ biết tình trạng nhiễm (%)", "Chỉ số 95 thứ nhất", "%", "trung bình có trọng số theo số người nhiễm ước tính"),
    ("Số người đang điều trị ARV", "Người đang điều trị kháng vi rút", "người", "cộng tổng"),
    ("Tỷ lệ điều trị ARV (%)", "Chỉ số 95 thứ hai, trong nhóm đã biết tình trạng", "%", "trung bình có trọng số"),
    ("Tỷ lệ ức chế tải lượng vi rút (%)", "Chỉ số 95 thứ ba, trong nhóm đang điều trị", "%", "trung bình có trọng số"),
    ("Số người dùng PrEP 2026", "Người sử dụng dự phòng trước phơi nhiễm", "người", "cộng tổng"),
    ("Chỉ tiêu PrEP 2026", "Mẫu số của tỷ lệ bao phủ PrEP", "người", "cộng tổng"),
    ("Tỷ lệ bao phủ PrEP (%)", "Người dùng PrEP trên chỉ tiêu", "%", "trung bình có trọng số theo chỉ tiêu"),
    ("Thay đổi bao phủ PrEP (điểm %)", "Chênh lệch bao phủ PrEP so với năm trước", "điểm %", "trung bình có trọng số"),
    ("Số cơ sở điều trị ARV", "Số cơ sở cung cấp điều trị ARV", "cơ sở", "cộng tổng"),
    ("Ngân sách chương trình 2026 (VND)", "Ngân sách phân bổ cho chương trình", "VND", "cộng tổng"),
    ("Mức ưu tiên", "Mức ưu tiên can thiệp do chương trình xếp loại", "nhóm", "không cộng gộp"),
]


# --------------------------------------------------------------------------
def build_commune_sheet(communes, rng) -> pd.DataFrame:
    rows = []
    for province in COMMUNE_PROVINCES:
        pool = communes[communes["ten_tinh"] == province].reset_index(drop=True)
        step = max(1, len(pool) // COMMUNES_PER_PROVINCE)
        picked = pool.iloc[::step].head(COMMUNES_PER_PROVINCE)
        # make sure a genuinely ambiguous name is in the sample, so the review
        # step has a real case to catch rather than a contrived one
        forced = pool[pool["ten_xa"].isin(AMBIGUOUS_NAMES.get(province, []))]
        if not forced.empty:
            keep = picked[~picked["ten_xa"].isin(forced["ten_xa"])].head(
                COMMUNES_PER_PROVINCE - len(forced))
            picked = pd.concat([forced, keep])
        picked = picked.reset_index(drop=True)
        points = picked.geometry.representative_point()

        for i, row in picked.iterrows():
            population = int(row["dan_so"]) if pd.notna(row["dan_so"]) else rng.randint(5_000, 90_000)
            plhiv = max(2, int(population * rng.uniform(0.0008, 0.0042)))
            screened = int(plhiv * rng.uniform(0.55, 0.99))
            screening_rate = round(screened / plhiv * 100, 1)
            coinfection = max(0, int(screened * rng.uniform(0.02, 0.11)))
            tpt_eligible = max(1, screened - coinfection)
            tpt = int(tpt_eligible * rng.uniform(0.3, 0.95))

            rows.append({
                "Tỉnh/thành phố": province,
                "Xã/phường": row["ten_xa"],
                "Kỳ báo cáo": "Năm 2026",
                "Dân số": population,
                "Số người nhiễm HIV đang quản lý": plhiv,
                "Số người nhiễm HIV được sàng lọc lao": screened,
                "Tỷ lệ sàng lọc lao ở người nhiễm HIV (%)": screening_rate,
                "Số ca đồng nhiễm HIV/Lao": coinfection,
                "Tỷ lệ đồng nhiễm HIV/Lao (%)": round(coinfection / screened * 100, 1) if screened else 0.0,
                "Tỷ suất đồng nhiễm/100.000 dân": round(coinfection / population * 100_000, 1),
                "Số người đủ điều kiện điều trị lao tiềm ẩn": tpt_eligible,
                "Số người được điều trị lao tiềm ẩn": tpt,
                "Tỷ lệ bao phủ điều trị lao tiềm ẩn (%)": round(tpt / tpt_eligible * 100, 1),
                "Tỷ lệ điều trị lao thành công (%)": round(rng.uniform(72.0, 96.0), 1),
                "Số ca tử vong do lao ở người nhiễm HIV": max(0, int(coinfection * rng.uniform(0.0, 0.16))),
                "Trạng thái can thiệp": rng.choices(
                    ["Đang triển khai", "Mở rộng", "Duy trì"], weights=[4, 2, 4])[0],
                "Kinh độ phòng khám": round(points.iloc[i].x + rng.uniform(-0.004, 0.004), 5),
                "Vĩ độ phòng khám": round(points.iloc[i].y + rng.uniform(-0.004, 0.004), 5),
            })
    df = pd.DataFrame(rows)

    # deliberate messiness, so the matching review has something real to catch
    def rewrite(province: str, index: int, value: str, note: str) -> None:
        mask = df["Tỉnh/thành phố"] == province
        if mask.sum() > index:
            df.loc[df[mask].index[index], "Xã/phường"] = value
            print(f"  gài lỗi: {province} -> '{value}' ({note})")

    hp = df[df["Tỉnh/thành phố"] == "Hải Phòng"]["Xã/phường"].tolist()
    if "Cẩm Giang" in hp or "Cẩm Giàng" in hp:
        target = "Cẩm Giang" if "Cẩm Giang" in hp else "Cẩm Giàng"
        idx = hp.index(target)
        rewrite("Hải Phòng", idx, "Cam Giang", "không dấu, trùng với hai xã khác nhau")
    rewrite("Hà Nội", 0, "P. " + str(df[df["Tỉnh/thành phố"] == "Hà Nội"]["Xã/phường"].iloc[0]),
            "tiền tố viết tắt")
    return df


COMMUNE_DICTIONARY = [
    ("Tỉnh/thành phố", "Tên tỉnh/thành phố", "văn bản", "không cộng gộp"),
    ("Xã/phường", "Tên xã/phường, không có mã hành chính", "văn bản", "không cộng gộp"),
    ("Kỳ báo cáo", "Kỳ số liệu", "văn bản", "không cộng gộp"),
    ("Dân số", "Dân số toàn xã", "người", "cộng tổng"),
    ("Số người nhiễm HIV đang quản lý", "Người nhiễm HIV đang được quản lý tại địa bàn", "người", "cộng tổng"),
    ("Số người nhiễm HIV được sàng lọc lao", "Trong số đang quản lý, số được sàng lọc lao", "người", "cộng tổng"),
    ("Tỷ lệ sàng lọc lao ở người nhiễm HIV (%)", "Số được sàng lọc trên số đang quản lý", "%", "trung bình có trọng số theo số đang quản lý"),
    ("Số ca đồng nhiễm HIV/Lao", "Ca xác định đồng nhiễm HIV và lao", "ca", "cộng tổng"),
    ("Tỷ lệ đồng nhiễm HIV/Lao (%)", "Ca đồng nhiễm trên số được sàng lọc", "%", "trung bình có trọng số theo số được sàng lọc"),
    ("Tỷ suất đồng nhiễm/100.000 dân", "Ca đồng nhiễm trên 100.000 dân", "trên 100.000 dân", "tính lại từ tử số và mẫu số"),
    ("Số người đủ điều kiện điều trị lao tiềm ẩn", "Mẫu số của bao phủ điều trị lao tiềm ẩn", "người", "cộng tổng"),
    ("Số người được điều trị lao tiềm ẩn", "Người đã bắt đầu điều trị lao tiềm ẩn", "người", "cộng tổng"),
    ("Tỷ lệ bao phủ điều trị lao tiềm ẩn (%)", "Được điều trị trên số đủ điều kiện", "%", "trung bình có trọng số"),
    ("Tỷ lệ điều trị lao thành công (%)", "Kết quả điều trị lao thành công", "%", "trung bình có trọng số"),
    ("Số ca tử vong do lao ở người nhiễm HIV", "Tử vong do lao trong nhóm nhiễm HIV", "ca", "cộng tổng"),
    ("Trạng thái can thiệp", "Tình trạng triển khai can thiệp tại xã", "nhóm", "không cộng gộp"),
    ("Kinh độ phòng khám", "Toạ độ phòng khám ngoại trú", "độ", "không cộng gộp"),
    ("Vĩ độ phòng khám", "Toạ độ phòng khám ngoại trú", "độ", "không cộng gộp"),
]


# --------------------------------------------------------------------------
MERGER_YEAR = 2025
SERIES_YEARS = range(2019, 2027)


def build_year_series(provinces, rng) -> pd.DataFrame:
    """A long series that crosses the 2025 merger, reported as it really would be.

    Years before the merger name the 63 former provinces; 2025 onward name the 34
    current ones. Drawing this without converting the old names would silently
    drop more than half the country for the early years.
    """
    old_to_new: dict[str, str] = {}
    for _, row in provinces.iterrows():
        current = str(row["ten_tinh"]).strip()
        raw = str(row["sap_nhap"]).strip()
        formers = ([current] if raw.lower().startswith("không sáp nhập")
                   else [p.strip() for p in raw.split(",") if p.strip()])
        for former in formers:
            old_to_new[former] = current

    trend = {name: rng.uniform(0.90, 1.14) for name in old_to_new}
    base = {name: rng.randint(40, 900) for name in old_to_new}
    rows = []
    for year in SERIES_YEARS:
        reporting = (sorted(old_to_new) if year < MERGER_YEAR
                     else sorted(set(old_to_new.values())))
        for unit in reporting:
            if year < MERGER_YEAR:
                cases = base[unit] * trend[unit] ** (year - 2019)
                population = rng.randint(600_000, 4_000_000)
            else:
                parts = [o for o, n in old_to_new.items() if n == unit]
                cases = sum(base[p] * trend[p] ** (year - 2019) for p in parts)
                population = sum(rng.randint(600_000, 4_000_000) for _ in parts)
            cases = max(5, int(cases * rng.uniform(0.92, 1.08)))
            tested = int(cases * rng.uniform(45, 110))
            rows.append({
                "Tỉnh/thành phố": unit,
                "Năm": year,
                "Số ca HIV mới phát hiện": cases,
                "Số người xét nghiệm HIV": tested,
                "Dân số": population,
                "Tỷ suất ca mới/100.000 dân": round(cases / population * 100_000, 1),
                "Tỷ lệ dương tính (%)": round(cases / tested * 100, 2),
            })
    return pd.DataFrame(rows)


SERIES_DICTIONARY = [
    ("Tỉnh/thành phố", "Tên tỉnh tại thời điểm báo cáo: 63 tỉnh cũ trước 2025, 34 tỉnh từ 2025",
     "văn bản", "không cộng gộp"),
    ("Năm", "Năm báo cáo", "năm", "không cộng gộp"),
    ("Số ca HIV mới phát hiện", "Ca nhiễm mới phát hiện trong năm", "ca", "cộng tổng"),
    ("Số người xét nghiệm HIV", "Lượt xét nghiệm trong năm", "người", "cộng tổng"),
    ("Dân số", "Dân số của đơn vị báo cáo", "người", "cộng tổng"),
    ("Tỷ suất ca mới/100.000 dân", "Ca mới trên 100.000 dân", "trên 100.000 dân",
     "tính lại từ tử số và mẫu số"),
    ("Tỷ lệ dương tính (%)", "Ca mới trên số người xét nghiệm", "%",
     "trung bình có trọng số theo số người xét nghiệm"),
]


def dictionary_frame(entries) -> pd.DataFrame:
    return pd.DataFrame(entries, columns=["Cột", "Ý nghĩa", "Đơn vị", "Cách tổng hợp phù hợp"])


def guidance_frame(lines) -> pd.DataFrame:
    return pd.DataFrame({"Hướng dẫn": [DISCLAIMER] + list(lines)})


def write(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    print(f"{path.relative_to(ROOT)}: " +
          ", ".join(f"{n} ({len(f)} dòng)" for n, f in sheets.items()))


def main() -> None:
    rng = random.Random(SEED)
    provinces, communes = load_shapes()

    print("Sinh bộ dữ liệu chương trình HIV cấp tỉnh…")
    province_df = build_province_sheet(provinces, rng)
    write(ROOT / "input" / "chuong_trinh_hiv_tinh.xlsx", {
        "Dữ liệu tỉnh 2026": province_df,
        "Diễn biến theo quý": build_province_quarters(province_df, rng),
        "Từ điển dữ liệu": dictionary_frame(PROVINCE_DICTIONARY),
        "Hướng dẫn": guidance_frame([
            "Phạm vi: 34 tỉnh/thành phố sau sắp xếp.",
            "Dùng để thử bản đồ toàn quốc cấp tỉnh, bản đồ thay đổi và lọc theo kỳ.",
            "Sheet 'Diễn biến theo quý' có nhiều kỳ trong một bảng: phải lọc kỳ trước khi vẽ.",
        ]),
    })

    print("Sinh chuỗi HIV theo năm 2019-2026 (vượt mốc sáp nhập 2025)…")
    series = build_year_series(provinces, rng)
    before = series[series["Năm"] < MERGER_YEAR]["Tỉnh/thành phố"].nunique()
    after = series[series["Năm"] >= MERGER_YEAR]["Tỉnh/thành phố"].nunique()
    print(f"  tên tỉnh trước 2025: {before} | từ 2025: {after}")
    write(ROOT / "input" / "hiv_ca_moi_theo_nam.xlsx", {
        "Ca mới theo năm": series,
        "Từ điển dữ liệu": dictionary_frame(SERIES_DICTIONARY),
        "Hướng dẫn": guidance_frame([
            "Chuỗi 2019-2026 để thử bản đồ video theo thời gian.",
            f"Trước {MERGER_YEAR} dùng tên 63 tỉnh cũ; từ {MERGER_YEAR} dùng 34 tỉnh hiện nay.",
            "Phải quy đổi tên tỉnh cũ về tỉnh hiện nay, cộng tổng số đếm và tính lại tỷ lệ.",
        ]),
    })

    print("Sinh bộ dữ liệu chương trình HIV/Lao cấp xã…")
    commune_df = build_commune_sheet(communes, rng)
    write(ROOT / "input" / "chuong_trinh_hiv_lao_xa.xlsx", {
        "Dữ liệu xã 2026": commune_df,
        "Từ điển dữ liệu": dictionary_frame(COMMUNE_DICTIONARY),
        "Hướng dẫn": guidance_frame([
            f"Phạm vi: {', '.join(COMMUNE_PROVINCES)}.",
            "Có cột kinh độ/vĩ độ phòng khám để thử bản đồ điểm.",
            "Bảng cố ý chứa tên viết tắt và tên không dấu để thử bước duyệt ghép địa danh.",
        ]),
    })


if __name__ == "__main__":
    main()
