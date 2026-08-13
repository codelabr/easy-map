"""Language of the finished map.

Only machine-generated text is translated: the kicker, the auto insight, legend
furniture, the source and method footer, and the north arrow letter.

Three things are deliberately **not** translated:

* place names — they come from the shapefile and a Vietnamese toponym stays
  Vietnamese in any language,
* the title, legend title and any user-supplied note — those come from the user
  or from the workbook's own column names,
* the warnings in ``guardrails.py`` — those are spoken to the user in chat, not
  printed on the map, so the agent relays them in whatever language it is
  conversing in.
"""

from __future__ import annotations

from typing import Any

DEFAULT = "vi"
LANGUAGES = ("vi", "en")

#: suffix appended to every output file name, e.g. ``ban-do_vi.png``
def suffix(lang: str) -> str:
    return normalise(lang)


def normalise(lang: str | None) -> str:
    lang = (lang or DEFAULT).strip().lower()
    return lang if lang in LANGUAGES else DEFAULT


STRINGS: dict[str, dict[str, str]] = {
    "vi": {
        "north": "B",
        "no_data": "Chưa có số liệu",
        "kicker_commune": "BẢN ĐỒ CẤP XÃ/PHƯỜNG",
        "kicker_province": "BẢN ĐỒ CẤP TỈNH/THÀNH PHỐ",
        "scope_national": "toàn quốc",
        "change_legend": "Thay đổi (điểm %)",
        "unit_point": "điểm %",
        "insight_values": "{with_data}/{total} đơn vị có số liệu. Cao nhất là {name} với {value}.",
        "insight_frame": "{total} đơn vị hành chính trong khung bản đồ.",
        "insight_points": "{points} vị trí được chấm theo toạ độ trên nền {total} đơn vị hành chính.",
        "insight_plain": "{with_data}/{total} đơn vị có số liệu.",
        "insight_category": "{with_data}/{total} đơn vị có số liệu. Nhóm phổ biến nhất là {name} ({count} đơn vị).",
        "source": "Nguồn: {file}; ranh giới hành chính từ shapefile của dự án.",
        "method_classes": "Màu chia {classes} nhóm theo {method}.",
        "method_symbol": "Diện tích vòng tròn tỷ lệ với số lượng.",
        "method_aggregate": "Dòng trùng địa danh được gộp bằng {method}.",
        "method_points": "Mỗi chấm là một vị trí theo toạ độ trong bảng dữ liệu.",
        "method_grey": "Đơn vị màu xám là chưa có số liệu, không phải bằng 0.",
        "class_quantile": "phân vị",
        "class_equal-interval": "khoảng đều",
        "class_natural-breaks": "ngắt tự nhiên",
        "agg_sum": "cộng tổng",
        "agg_mean": "trung bình đơn giản",
        "agg_median": "trung vị",
        "agg_max": "lấy giá trị lớn nhất",
        "agg_min": "lấy giá trị nhỏ nhất",
        "agg_mode": "lấy nhóm xuất hiện nhiều nhất",
        "agg_first": "lấy dòng đầu tiên",
        "agg_weighted-mean": "trung bình có trọng số",
        "agg_by": "{method} theo '{column}'",
    },
    "en": {
        "north": "N",
        "no_data": "No data",
        "kicker_commune": "COMMUNE-LEVEL MAP",
        "kicker_province": "PROVINCE-LEVEL MAP",
        "scope_national": "nationwide",
        "change_legend": "Change (percentage points)",
        "unit_point": "pp",
        "insight_values": "{with_data} of {total} units have data. Highest is {name} at {value}.",
        "insight_frame": "{total} administrative units in the map frame.",
        "insight_points": "{points} locations plotted from coordinates over {total} administrative units.",
        "insight_plain": "{with_data} of {total} units have data.",
        "insight_category": "{with_data} of {total} units have data. The most common group is {name} ({count} units).",
        "source": "Source: {file}; administrative boundaries from the project shapefile.",
        "method_classes": "Colour is split into {classes} classes by {method}.",
        "method_symbol": "Circle area is proportional to the count.",
        "method_aggregate": "Rows sharing a place name are combined using {method}.",
        "method_points": "Each dot is one location from the coordinates in the table.",
        "method_grey": "Grey units have no data, which is not the same as zero.",
        "class_quantile": "quantiles",
        "class_equal-interval": "equal intervals",
        "class_natural-breaks": "natural breaks",
        "agg_sum": "a sum",
        "agg_mean": "an unweighted mean",
        "agg_median": "a median",
        "agg_max": "the maximum",
        "agg_min": "the minimum",
        "agg_mode": "the most frequent category",
        "agg_first": "the first row",
        "agg_weighted-mean": "a weighted mean",
        "agg_by": "{method} on '{column}'",
    },
}


def t(lang: str | None, key: str, **fields: Any) -> str:
    """Look up a string; falls back to Vietnamese, then to the key itself."""
    code = normalise(lang)
    text = STRINGS[code].get(key) or STRINGS[DEFAULT].get(key) or key
    return text.format(**fields) if fields else text


def kicker(lang: str | None, admin_level: str) -> str:
    return t(lang, "kicker_commune" if admin_level == "commune" else "kicker_province")
