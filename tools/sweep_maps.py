"""Draw several hundred maps across every combination the skill offers, and
report which ones failed.

The unit tests check pieces. This checks that the whole command, on real
boundaries and real-shaped tables, produces a file and does not raise — across
programmes, administrative levels, map types, layouts, languages,
classifications, label modes, aggregations, scopes and time series.

It is not part of ``python -m unittest``: one province map costs about 28
seconds of geometry (``union_all`` alone is 8), so the full sweep is hours of
CPU. It is run deliberately, in parallel, and writes a report:

    uv run --offline --with pandas --with openpyxl --with geopandas \
        --with matplotlib --with mapclassify --with rapidfuzz \
        python tools/sweep_maps.py

    python tools/sweep_maps.py --list            # what would run, and how many
    python tools/sweep_maps.py --only commune    # one group
    python tools/sweep_maps.py --limit 12        # a smoke test
    python tools/sweep_maps.py --workers 8

Needs ``tools/generate_programme_data.py`` to have been run first.

**What counts as a failure.** An exception, a non-zero exit, or no image on
disk. A guardrail warning does not: warnings are the skill working. A run that
stops at the confirmation gate *is* a failure here, because every case supplies
the answers the gate asks for — if one still blocks, either the gate changed or
this file is not answering it, and both are worth knowing.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = "input/_sweep"
OUT = ROOT / "output" / "_sweep"
REPORT = ROOT / "output" / "_sweep" / "report.json"

PROGRAMMES = ("hiv", "viem-gan-b", "lao", "tiem-chung", "sot-ret",
              "sot-xuat-huyet", "dinh-duong")

#: Column vocabulary per programme, mirroring generate_programme_data.py. Read
#: from the workbook rather than duplicated here would be tidier, but a worker
#: opening 34 workbooks to build a case list costs more than the list is worth.
COLUMNS = {
    "hiv": {"mau_so": "Dân số", "quan_the": "Quần thể đích ước tính",
            "dem": "Số ca HIV mới phát hiện", "dem_2": "Số người điều trị ARV",
            "ty_le": "Tỷ lệ điều trị ARV (%)",
            "suat": "Tỷ suất ca mới trên 100.000 dân", "nhom": "Mức ưu tiên"},
    "viem-gan-b": {"mau_so": "Số trẻ sinh sống",
                   "quan_the": "Số phụ nữ mang thai được quản lý",
                   "dem": "Số trẻ tiêm vắc xin trong 24 giờ đầu",
                   "dem_2": "Số ca HBsAg dương tính",
                   "ty_le": "Tỷ lệ tiêm vắc xin viêm gan B sơ sinh (%)",
                   "suat": "Tỷ lệ HBsAg dương tính ở thai phụ (%)",
                   "nhom": "Xếp loại tiến độ"},
    "lao": {"mau_so": "Dân số", "quan_the": "Số người được khám sàng lọc lao",
            "dem": "Số ca lao các thể được phát hiện",
            "dem_2": "Số ca lao kháng thuốc",
            "ty_le": "Tỷ lệ điều trị lao thành công (%)",
            "suat": "Tỷ suất lao trên 100.000 dân", "nhom": "Mức gánh nặng"},
    "tiem-chung": {"mau_so": "Số trẻ dưới 1 tuổi",
                   "quan_the": "Số trẻ trong diện tiêm chủng",
                   "dem": "Số trẻ tiêm đủ mũi", "dem_2": "Số trẻ bỏ mũi",
                   "ty_le": "Tỷ lệ tiêm chủng đầy đủ (%)",
                   "suat": "Tỷ lệ bỏ mũi (%)", "nhom": "Nguy cơ dịch"},
    "sot-ret": {"mau_so": "Dân số vùng nguy cơ",
                "quan_the": "Số lượt xét nghiệm ký sinh trùng",
                "dem": "Số ca sốt rét", "dem_2": "Số ca sốt rét nội địa",
                "ty_le": "Tỷ lệ ngủ màn tẩm hóa chất (%)",
                "suat": "Tỷ suất mắc trên 1.000 dân nguy cơ",
                "nhom": "Phân vùng dịch tễ"},
    "sot-xuat-huyet": {"mau_so": "Dân số",
                       "quan_the": "Số hộ được giám sát véc tơ",
                       "dem": "Số ca mắc", "dem_2": "Số ổ dịch được xử lý",
                       "ty_le": "Tỷ lệ ổ dịch được xử lý trong 48 giờ (%)",
                       "suat": "Tỷ suất mắc trên 100.000 dân",
                       "nhom": "Cấp độ dịch"},
    "dinh-duong": {"mau_so": "Số trẻ dưới 5 tuổi",
                   "quan_the": "Số trẻ được cân đo",
                   "dem": "Số trẻ suy dinh dưỡng thể thấp còi",
                   "dem_2": "Số trẻ suy dinh dưỡng thể gầy còm",
                   "ty_le": "Tỷ lệ suy dinh dưỡng thấp còi (%)",
                   "suat": "Tỷ lệ suy dinh dưỡng gầy còm (%)",
                   "nhom": "Mức can thiệp"},
}

COMMUNE_FILES = {"ha-noi": "Hà Nội", "khanh-hoa": "Khánh Hòa",
                 "nghe-an": "Nghệ An"}


# --------------------------------------------------------------------------
# the case list
#
# Every case is (group, name, argv-tail). The common head — project root,
# country, language, layout, title — is added by `full_argv`, so a case says
# only what makes it different from every other case.

def province(programme, sheet="Dữ liệu tỉnh", workbook=None):
    return ["--excel", f"{DATA}/{workbook or programme + '-tinh'}.xlsx",
            "--sheet", sheet, "--admin-level", "province",
            "--province-column", "Tỉnh/thành phố"]


def commune(programme, slug):
    return ["--excel", f"{DATA}/{programme}-xa-{slug}.xlsx",
            "--sheet", "Dữ liệu xã", "--admin-level", "commune",
            "--province-column", "Tỉnh/thành phố", "--commune-column", "Xã/phường"]


def cases() -> list[tuple[str, str, list[str]]]:
    out: list[tuple[str, str, list[str]]] = []

    def add(group, name, tail):
        out.append((group, name, tail))

    # 1. the core grid: every programme, every map type, both layouts, both
    #    languages. This is the bulk of the sweep and the part that would catch
    #    a defect in the drawing itself.
    for programme in PROGRAMMES:
        cols = COLUMNS[programme]
        for kind, tail in (
            ("choropleth", ["--map-type", "choropleth",
                            "--value-column", cols["ty_le"]]),
            ("choropleth-symbol", ["--map-type", "choropleth-symbol",
                                   "--value-column", cols["ty_le"],
                                   "--symbol-column", cols["dem"]]),
            # sized by --symbol-column: a proportional-symbol map has no fill
            # to colour, so --value-column is refused rather than ignored
            ("graduated-symbol", ["--map-type", "graduated-symbol",
                                  "--symbol-column", cols["dem"]]),
            ("categorized", ["--map-type", "categorized",
                             "--value-column", cols["nhom"]]),
            ("boundary", ["--map-type", "boundary",
                          "--value-column", cols["ty_le"]]),
        ):
            for layout in ("report", "banner"):
                for language in ("vi", "en"):
                    add("core", f"{programme}-{kind}-{layout}-{language}",
                        province(programme) + tail
                        + ["--map-scope", "national", "--layout", layout,
                           "--language", language])

    # 2. classification and class count, on every programme. The distributions
    #    are deliberately unalike -- a share bounded at 100, a rate with a long
    #    tail, a count with a floor of zero -- and a classifier that copes with
    #    one can still produce an empty or a one-value class on another.
    for programme in PROGRAMMES:
        cols = COLUMNS[programme]
        for method in ("quantile", "equal-interval", "natural-breaks"):
            for classes in (3, 4, 5, 6, 7):
                add("classes", f"{programme}-{method}-{classes}",
                    province(programme)
                    + ["--map-type", "choropleth", "--value-column", cols["suat"],
                       "--map-scope", "national", "--classification", method,
                       "--classes", str(classes)])

    # 3. label modes, at both levels. The label pass is where the commune maps
    #    hurt, so it is exercised there rather than only on 34 provinces.
    for mode in ("off", "names", "values", "both"):
        for programme in ("hiv", "lao", "tiem-chung"):
            add("labels", f"province-{programme}-{mode}",
                province(programme)
                + ["--map-type", "choropleth",
                   "--value-column", COLUMNS[programme]["ty_le"],
                   "--map-scope", "national", "--labels", mode])
        # Khánh Hòa for its islands, Hà Nội because inner-city communes are the
        # case no arrangement of labels fits and the honest answer is a warning
        for slug in ("khanh-hoa", "ha-noi"):
            add("labels", f"commune-{slug}-{mode}",
                commune("hiv", slug)
                + ["--map-type", "choropleth",
                   "--value-column", COLUMNS["hiv"]["ty_le"],
                   "--map-scope", "single-province", "--labels", mode])

    # 4. a third of the units with no row at all: the grey class, the coverage
    #    warning, and the legend row that explains grey.
    for programme in PROGRAMMES:
        cols = COLUMNS[programme]
        for kind in ("choropleth", "choropleth-symbol", "graduated-symbol",
                     "categorized"):
            if kind == "graduated-symbol":
                tail = ["--map-type", kind, "--symbol-column", cols["dem"]]
            elif kind == "categorized":
                tail = ["--map-type", kind, "--value-column", cols["nhom"]]
            else:
                tail = ["--map-type", kind, "--value-column", cols["ty_le"]]
                if kind == "choropleth-symbol":
                    tail += ["--symbol-column", cols["dem"]]
            add("missing", f"{programme}-{kind}",
                province(programme, sheet="Thiếu số liệu",
                         workbook=f"{programme}-tinh-thieu")
                + tail + ["--map-scope", "national"])

    # 5. commune level, three provinces of very different shape.
    for programme in ("hiv", "lao", "tiem-chung"):
        cols = COLUMNS[programme]
        for slug, province_name in COMMUNE_FILES.items():
            for kind, tail in (
                ("choropleth", ["--map-type", "choropleth",
                                "--value-column", cols["ty_le"]]),
                ("choropleth-symbol", ["--map-type", "choropleth-symbol",
                                       "--value-column", cols["ty_le"],
                                       "--symbol-column", cols["dem"]]),
                ("categorized", ["--map-type", "categorized",
                                 "--value-column", cols["nhom"]]),
            ):
                for layout in ("report", "banner"):
                    add("commune", f"{programme}-{slug}-{kind}-{layout}",
                        commune(programme, slug) + tail
                        + ["--map-scope", "single-province", "--layout", layout])

    # 6. a period column, drawn one period at a time and as a series.
    for programme in PROGRAMMES:
        cols = COLUMNS[programme]
        base = province(programme, sheet="Theo năm",
                        workbook=f"{programme}-tinh-theo-nam")
        for year in (2022, 2023, 2024, 2025, 2026):
            add("period", f"{programme}-{year}",
                base + ["--map-type", "choropleth", "--value-column", cols["ty_le"],
                        "--map-scope", "national", "--period-column", "Năm",
                        "--period", str(year)])
        # change between two years: the diverging ramp.
        #
        # From the *wide* workbook, not the five-year one. The two flags take
        # column names; the first version of this case wrote the years, which
        # reached pandas as `KeyError: '2026'`. The engine now refuses that with
        # a sentence, and this case exercises the shape that works.
        tyle = cols["ty_le"]
        add("period", f"{programme}-change",
            ["--excel", f"{DATA}/{programme}-tinh-hai-nam.xlsx",
             "--sheet", "Hai năm", "--admin-level", "province",
             "--province-column", "Tỉnh/thành phố",
             "--map-type", "change", "--map-scope", "national",
             "--baseline-column", f"{tyle} 2022",
             "--comparison-column", f"{tyle} 2026"])

    # 7. the aggregations. A five-year table collapsed to one map has to be
    #    told how, and each method is a different arithmetic.
    for method in ("sum", "mean", "median", "max", "min", "first"):
        add("aggregate", f"count-{method}",
            province("hiv", sheet="Theo năm", workbook="hiv-tinh-theo-nam")
            + ["--map-type", "choropleth", "--value-column", COLUMNS["hiv"]["dem"],
               "--map-scope", "national", "--aggregate", method])
    for method in ("mean", "median", "weighted-mean"):
        tail = ["--map-type", "choropleth",
                "--value-column", COLUMNS["hiv"]["ty_le"],
                "--map-scope", "national", "--aggregate", method]
        if method == "weighted-mean":
            tail += ["--weight-column", COLUMNS["hiv"]["mau_so"]]
        add("aggregate", f"rate-{method}",
            province("hiv", sheet="Theo năm", workbook="hiv-tinh-theo-nam") + tail)
    # a weighted mean whose weight is a different programme's denominator, and
    # the two methods that pick a row rather than combine rows
    add("aggregate", "rate-weighted-by-target",
        province("hiv", sheet="Theo năm", workbook="hiv-tinh-theo-nam")
        + ["--map-type", "choropleth", "--value-column", COLUMNS["hiv"]["ty_le"],
           "--map-scope", "national", "--aggregate", "weighted-mean",
           "--weight-column", COLUMNS["hiv"]["quan_the"]])
    for method in ("max", "min"):
        add("aggregate", f"rate-{method}",
            province("lao", sheet="Theo năm", workbook="lao-tinh-theo-nam")
            + ["--map-type", "choropleth", "--value-column", COLUMNS["lao"]["ty_le"],
               "--map-scope", "national", "--aggregate", method])
    add("aggregate", "symbol-sum",
        province("lao", sheet="Theo năm", workbook="lao-tinh-theo-nam")
        + ["--map-type", "graduated-symbol",
           "--symbol-column", COLUMNS["lao"]["dem"],
           "--map-scope", "national", "--aggregate", "sum"])
    add("aggregate", "category-mode",
        province("hiv", sheet="Theo năm", workbook="hiv-tinh-theo-nam")
        + ["--map-type", "categorized", "--value-column", COLUMNS["hiv"]["nhom"],
           "--map-scope", "national", "--aggregate", "mode"])

    # 8. long form: the shape a programme export arrives in, where the same unit
    #    appears on many rows and a ratio has to be built from two of them.
    for name, tail in (
        ("ratio", ["--map-type", "choropleth", "--value-column", "Giá trị",
                   "--indicator-column", "Chỉ số",
                   "--numerator", "TX_PVLS Num", "--denominator", "TX_PVLS Den"]),
        ("one-indicator", ["--map-type", "choropleth", "--value-column", "Giá trị",
                           "--indicator-column", "Chỉ số",
                           "--where", "Chỉ số=TX_CURR"]),
        ("one-indicator-one-sex", ["--map-type", "graduated-symbol",
                                   "--symbol-column", "Giá trị",
                                   "--indicator-column", "Chỉ số",
                                   "--where", "Chỉ số=TX_CURR",
                                   "--where", "Giới tính=Nữ"]),
    ):
        for layout in ("report", "banner"):
            for language in ("vi", "en"):
                add("longform", f"{name}-{layout}-{language}",
                    ["--excel", f"{DATA}/dai-chi-so.xlsx", "--sheet", "DATA",
                     "--admin-level", "province",
                     "--province-column", "Tỉnh/thành phố"]
                    + tail + ["--map-scope", "national", "--layout", layout,
                              "--language", language])

    # a ratio whose numerator is larger than its denominator. Real exports do
    # arrive like this, and the sweep should keep meeting the warning: the
    # ordinary ratio case above no longer trips it, now that the generator
    # builds a numerator that fits inside its denominator.
    for layout in ("report", "banner"):
        add("longform", f"impossible-ratio-{layout}",
            ["--excel", f"{DATA}/dai-chi-so-loi.xlsx", "--sheet", "DATA",
             "--admin-level", "province", "--province-column", "Tỉnh/thành phố",
             "--map-type", "choropleth", "--value-column", "Giá trị",
             "--indicator-column", "Chỉ số",
             "--numerator", "TX_PVLS Num", "--denominator", "TX_PVLS Den",
             "--map-scope", "national", "--layout", layout])

    # 9. point maps, from coordinates rather than names.
    for name, tail in (
        ("plain", []),
        ("coloured", ["--point-color-column", "Loại hình"]),
        ("sized", ["--point-size-column", "Số lượt khám"]),
        ("coloured-and-sized", ["--point-color-column", "Loại hình",
                                "--point-size-column", "Số lượt khám"]),
    ):
        for layout in ("report", "banner"):
            for language in ("vi", "en"):
                add("point", f"{name}-{layout}-{language}",
                    ["--excel", f"{DATA}/co-so-toa-do.xlsx", "--sheet", "Cơ sở",
                     "--admin-level", "province", "--map-type", "point",
                     "--lon-column", "Kinh độ", "--lat-column", "Vĩ độ"]
                    + tail + ["--map-scope", "national", "--layout", layout,
                              "--language", language])

    for name, tail in (
        ("sized-quantile", ["--point-size-column", "Số lượt khám",
                            "--classification", "quantile"]),
        ("sized-equal-interval", ["--point-size-column", "Số lượt khám",
                                  "--classification", "equal-interval"]),
        ("coloured-labels-off", ["--point-color-column", "Loại hình",
                                 "--labels", "off"]),
        ("coloured-labels-names", ["--point-color-column", "Loại hình",
                                   "--labels", "names"]),
        ("satisfaction-sized", ["--point-size-column", "Tỷ lệ hài lòng (%)"]),
        ("by-province-column", ["--point-color-column", "Tỉnh/thành phố"]),
    ):
        for language in ("vi", "en"):
            add("point", f"{name}-{language}",
                ["--excel", f"{DATA}/co-so-toa-do.xlsx", "--sheet", "Cơ sở",
                 "--admin-level", "province", "--map-type", "point",
                 "--lon-column", "Kinh độ", "--lat-column", "Vĩ độ"]
                + tail + ["--map-scope", "national", "--language", language])

    # 10. names that need matching work: prefixes and dropped accents.
    for kind in ("choropleth", "graduated-symbol"):
        for ambiguous in ("drop", "keep"):
            add("matching", f"{kind}-{ambiguous}",
                ["--excel", f"{DATA}/ten-lech.xlsx", "--sheet", "Tên lệch",
                 "--admin-level", "province", "--province-column", "Tỉnh/thành phố",
                 "--map-type", kind,
                 *(["--value-column", COLUMNS["hiv"]["ty_le"]]
                   if kind == "choropleth"
                   else ["--symbol-column", COLUMNS["hiv"]["dem"]]),
                 "--map-scope", "national", "--ambiguous", ambiguous])

    # 11. the furniture and the output options.
    cols = COLUMNS["lao"]
    for name, tail in (
        ("locator-off", ["--locator", "off"]),
        ("svg", ["--formats", "svg"]),
        ("both-formats", ["--formats", "both"]),
        ("dpi-150", ["--dpi", "150"]),
        ("dpi-300", ["--dpi", "300"]),
        ("label-fontsize-5", ["--label-fontsize", "5"]),
        ("label-fontsize-9", ["--label-fontsize", "9"]),
        ("subtitle", ["--subtitle", "Số liệu giả lập"]),
        ("footnote", ["--footnote", "Ghi chú kiểm thử"]),
        ("source-note", ["--source-note", "Nguồn: dữ liệu giả lập"]),
        ("insight", ["--insight", "Một câu nhận định do người dùng viết"]),
        ("legend-title", ["--legend-title", "Tỷ lệ (%)"]),
        ("html", ["--map-scope", "national"]),
        ("classes-3", ["--classes", "3"]),
        ("classes-7", ["--classes", "7"]),
        ("labels-values", ["--labels", "values"]),
        ("symbol-legend-title", ["--symbol-legend-title", "Số ca"]),
        ("dpi-220", ["--dpi", "220"]),
        ("banner-svg", ["--layout", "banner", "--formats", "svg"]),
        ("banner-locator-off", ["--layout", "banner", "--locator", "off"]),
        ("map-text", ["--map-text", "no_data=Không có số liệu"]),
    ):
        with_html = name == "html"
        add("options", name,
            province("lao") + ["--map-type", "choropleth",
                               "--value-column", cols["ty_le"],
                               "--map-scope", "national"] + tail
            + ([] if with_html else ["--no-html"]))

    # 12. scopes. `province-series` draws one map per province and is the most
    #     expensive thing the skill does, so it appears once.
    cols = COLUMNS["tiem-chung"]
    add("scope", "matched-only",
        province("tiem-chung", sheet="Thiếu số liệu",
                 workbook="tiem-chung-tinh-thieu")
        + ["--map-type", "choropleth", "--value-column", cols["ty_le"],
           "--map-scope", "matched-only"])
    add("scope", "auto",
        province("tiem-chung") + ["--map-type", "choropleth",
                                  "--value-column", cols["ty_le"],
                                  "--map-scope", "auto"])
    for programme, slug in (("hiv", "ha-noi"), ("lao", "nghe-an")):
        add("scope", f"single-province-{slug}",
            commune(programme, slug)
            + ["--map-type", "graduated-symbol",
               "--symbol-column", COLUMNS[programme]["dem"],
               "--map-scope", "single-province"])
    add("scope", "single-province-commune",
        commune("tiem-chung", "nghe-an")
        + ["--map-type", "choropleth", "--value-column", cols["ty_le"],
           "--map-scope", "single-province"])

    # 13. a commune-level series: four quarters of one province.
    for quarter in ("Q1/2026", "Q2/2026", "Q3/2026", "Q4/2026"):
        add("commune-series", quarter.replace("/", "-"),
            ["--excel", f"{DATA}/sot-xuat-huyet-xa-theo-quy.xlsx",
             "--sheet", "Theo quý", "--admin-level", "commune",
             "--province-column", "Tỉnh/thành phố",
             "--commune-column", "Xã/phường",
             "--map-type", "choropleth",
             "--value-column", COLUMNS["sot-xuat-huyet"]["ty_le"],
             "--map-scope", "single-province",
             "--period-column", "Kỳ báo cáo", "--period", quarter])

    # 14. the conversation language, which is not the map language. Both
    #     directions, because an English-speaking officer often needs a
    #     Vietnamese map and the two settings are independent.
    for messages in ("vi", "en"):
        for language in ("vi", "en"):
            add("messages", f"messages-{messages}-map-{language}",
                province("dinh-duong")
                + ["--map-type", "choropleth",
                   "--value-column", COLUMNS["dinh-duong"]["ty_le"],
                   "--map-scope", "national", "--language", language,
                   "--messages", messages])
            add("messages", f"commune-messages-{messages}-map-{language}",
                commune("lao", "khanh-hoa")
                + ["--map-type", "choropleth",
                   "--value-column", COLUMNS["lao"]["ty_le"],
                   "--map-scope", "single-province", "--language", language,
                   "--messages", messages])

    # 15. the commune level again, across both languages, on the map type most
    #     likely to run out of room: two channels on units a few pixels wide.
    for programme in ("hiv", "lao", "tiem-chung"):
        for slug in COMMUNE_FILES:
            for language in ("vi", "en"):
                add("commune-language", f"{programme}-{slug}-{language}",
                    commune(programme, slug)
                    + ["--map-type", "choropleth-symbol",
                       "--value-column", COLUMNS[programme]["ty_le"],
                       "--symbol-column", COLUMNS[programme]["dem"],
                       "--map-scope", "single-province", "--language", language])

    return out


# --------------------------------------------------------------------------
def full_argv(name: str, tail: list[str]) -> list[str]:
    """One case's complete command line.

    ``--title`` is always supplied, and so are ``--language`` and ``--layout``
    unless the case sets them: those three are what the confirmation gate asks
    for, and a sweep that let the gate block would measure the gate rather than
    the drawing.
    """
    argv = ["render", "--project-root", str(ROOT), "--country", "viet-nam",
            "--run-folder", f"_sweep/{name}", "--title", f"Kiểm thử {name}"]
    if "--language" not in tail:
        argv += ["--language", "vi"]
    if "--layout" not in tail:
        argv += ["--layout", "report"]
    # The interactive page costs seconds and is exercised deliberately by the
    # `options/html` case rather than by all 503. Opting out has to be the
    # case's own decision: keying it off "--map-scope in tail" silenced the one
    # case whose whole point was to build a page, and the sweep reported "0
    # pages" for a full run without anything looking wrong.
    if "--no-html" not in tail and name != "html":
        argv += ["--no-html"]
    return argv + tail


def run_one(case: tuple[str, str, list[str]]) -> dict:
    """One map, start to finish, in this worker's own process."""
    group, name, tail = case
    import matplotlib
    matplotlib.use("Agg")
    sys.path.insert(0, str(ROOT / "tests"))
    import context

    cli = context.cli()
    folder = OUT / name
    shutil.rmtree(folder, ignore_errors=True)
    started = time.time()

    def once(argv):
        args = cli.build_parser().parse_args(argv)
        args.chosen_explicitly = cli._explicit(argv)
        if getattr(args, "project_root_sub", None):
            args.project_root = args.project_root_sub
        if getattr(args, "messages_sub", None):
            args.messages = args.messages_sub
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.command_render(args)
        return json.loads(out.getvalue())

    argv = full_argv(name, tail)
    result = {"group": group, "name": name, "argv": argv[4:]}
    try:
        plan = once(argv)
        code = plan.get("confirm_code")
        if not code:
            result.update(status="blocked",
                          detail=[q.get("item") for q in plan.get("must_ask", [])])
            return result
        drawn = once(argv + ["--confirmed", code])
    except SystemExit as exc:
        result.update(status="refused", detail=str(exc))
        return result
    except BaseException as exc:                      # noqa: BLE001 -- reporting
        result.update(status="error", detail=f"{type(exc).__name__}: {exc}",
                      traceback=traceback.format_exc()[-1600:])
        return result

    images = sorted(folder.rglob("*.png")) + sorted(folder.rglob("*.svg"))
    result.update(
        status="drawn" if images else "no-image",
        seconds=round(time.time() - started, 1),
        images=len(images),
        pages=len(sorted(folder.rglob("*.html"))),
        warnings=sorted({w.get("id") for w in drawn.get("warnings", [])
                         if isinstance(w, dict)}),
        critical=sorted({w.get("id") for w in drawn.get("warnings", [])
                         if isinstance(w, dict) and w.get("severity") == "critical"}),
    )
    return result


# --------------------------------------------------------------------------
def default_workers() -> int:
    """How many processes this machine can actually draw with.

    Not the core count. Every worker loads its own geopandas and, for a commune
    map, its own 115 MB boundary layer; twenty of them on a machine with 12 GB
    free exhausted memory and the workers were killed. The first full run of
    this sweep reported 366 of 503 cases as ``worker-died``, which reads exactly
    like a catastrophic regression in the skill and was nothing of the kind.

    So: cores minus two, capped by free memory at roughly 1.6 GB a worker, and
    never fewer than two.
    """
    workers = max(1, (os.cpu_count() or 4) - 2)
    free_gb = None
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        free_gb = status.ullAvailPhys / 2 ** 30
    except Exception:                                 # noqa: BLE001 -- not Windows
        try:
            free_gb = (os.sysconf("SC_AVPHYS_PAGES")
                       * os.sysconf("SC_PAGE_SIZE")) / 2 ** 30
        except (AttributeError, ValueError, OSError):
            free_gb = None
    if free_gb is None:
        return min(workers, 6)
    return max(2, min(workers, int(free_gb / 1.6)))


def run_all(chosen, workers, chunk=24, per_case_seconds=600):
    """Draw every case, in chunks, with a fresh pool for each chunk.

    Three things went wrong before this shape, and each one is a reason for a
    piece of it:

    * **One pool for all 503 cases died and took 366 results with it.** Twenty
      workers, each with its own geopandas and its own 115 MB commune layer, on
      a machine with 12.5 GB free. ``BrokenProcessPool`` does not fail one case;
      it fails every case in flight and every case not yet started. Read
      quickly, that is indistinguishable from a catastrophic regression.
    * **``max_tasks_per_child`` hung.** It was meant to recycle a worker before
      it grew into the memory limit. Instead the run stalled after 28 cases with
      every worker gone and the parent waiting for futures that could never
      complete. Recycling by chunk does the same job in code that can be read.
    * **A hung case would stall the rest.** Each future now has a deadline.

    A chunk that breaks is retried once on half the workers; what still fails is
    recorded with the reason, not silently dropped.
    """
    results = []
    total = len(chosen)
    for index in range(0, total, chunk):
        batch = chosen[index:index + chunk]
        for attempt in (0, 1):
            size = max(2, workers // 2) if attempt else workers
            done_names = {r["name"] for r in results}
            batch = [c for c in batch if c[1] not in done_names]
            if not batch:
                break
            broke = False
            try:
                with ProcessPoolExecutor(max_workers=size) as pool:
                    futures = {pool.submit(run_one, case): case for case in batch}
                    for future in as_completed(futures, timeout=per_case_seconds * len(batch)):
                        group, name, _ = futures[future]
                        try:
                            result = future.result(timeout=per_case_seconds)
                        except BrokenExecutor:
                            broke = True
                            break
                        except BaseException as exc:      # noqa: BLE001
                            result = {"group": group, "name": name,
                                      "status": "error",
                                      "detail": f"{type(exc).__name__}: {exc}"}
                        results.append(result)
                        report(result, len(results), total)
            except (BrokenExecutor, TimeoutError):
                broke = True
            if not broke:
                break
            print(f"  the pool broke; retrying {len(batch)} cases on "
                  f"{max(2, workers // 2)} workers", flush=True)
        done_names = {r["name"] for r in results}
        for group, name, _ in batch:
            if name not in done_names:
                results.append({"group": group, "name": name,
                                "status": "worker-died",
                                "detail": "the pool broke twice on this chunk, "
                                          "most likely memory. Try fewer "
                                          "--workers."})
                report(results[-1], len(results), total)
    return results, len(results)


def report(result, done, total) -> None:
    if result["status"] != "drawn":
        print(f"  [{done:4}/{total}] {result['status'].upper():12} "
              f"{result['group']}/{result['name']}: "
              f"{str(result.get('detail'))[:150]}", flush=True)
    elif done % 25 == 0:
        print(f"  [{done:4}/{total}] ...", flush=True)


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=default_workers(),
                        help="processes to draw with; the default comes from "
                             "free memory, not from the core count")
    parser.add_argument("--only", action="append",
                        help="run one group only; repeatable")
    parser.add_argument("--limit", type=int, help="first N cases, for a smoke test")
    parser.add_argument("--list", action="store_true",
                        help="print the case list and stop")
    parser.add_argument("--keep", action="store_true",
                        help="keep the drawn maps instead of deleting them")
    args = parser.parse_args(argv)

    chosen = cases()
    if args.only:
        chosen = [c for c in chosen if c[0] in set(args.only)]
    if args.limit:
        chosen = chosen[:args.limit]

    groups = {}
    for group, _, _ in chosen:
        groups[group] = groups.get(group, 0) + 1
    print(f"{len(chosen)} cases in {len(groups)} groups")
    for group, count in sorted(groups.items(), key=lambda kv: -kv[1]):
        print(f"  {group:16} {count:4}")
    if args.list:
        return 0

    if not (ROOT / DATA).exists():
        print(f"\n{DATA} is missing. Run tools/generate_programme_data.py first.",
              file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"\nrunning on {args.workers} workers\n")
    started = time.time()
    results, _ = run_all(chosen, args.workers)

    elapsed = time.time() - started
    by_status: dict[str, int] = {}
    for result in results:
        by_status[result["status"]] = by_status.get(result["status"], 0) + 1

    drawn = [r for r in results if r["status"] == "drawn"]
    images = sum(r.get("images", 0) for r in drawn)
    print(f"\n{'=' * 62}")
    print(f"{len(results)} cases in {elapsed / 60:.1f} minutes "
          f"({images} image files, {sum(r.get('pages', 0) for r in drawn)} pages)")
    for status, count in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {status:14} {count:4}")
    if drawn:
        slowest = sorted(drawn, key=lambda r: -r.get("seconds", 0))[:5]
        print("  slowest: " + ", ".join(
            f"{r['name']} {r.get('seconds')}s" for r in slowest))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(
        {"cases": len(results), "seconds": round(elapsed, 1),
         "by_status": by_status, "results": sorted(results, key=lambda r: r["name"])},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nreport: {REPORT}")

    if not args.keep:
        for result in drawn:
            shutil.rmtree(OUT / result["name"], ignore_errors=True)

    failed = len(results) - by_status.get("drawn", 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
