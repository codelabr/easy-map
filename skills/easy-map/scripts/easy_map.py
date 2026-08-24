#!/usr/bin/env python3
"""easy-map — deterministic engine behind the skill.

Commands
--------
``start-run``  open the folder for one user request and print its name
``list``       what is available: workbooks, sheets, shapefiles, remembered choices
``profile``    evidence about a dataset so the agent can reason like an analyst
``render``     draw and save the finished map(s)
``fix-match``  record a manual name match so future runs reuse it

Output contract: one request, one folder. Call ``start-run`` the moment the user
asks for a map — the folder is stamped ``yyyy-mm-dd_hh-mm-ss`` at *that* moment,
not when rendering finally happens — then pass its name as ``--run-folder`` to
every later command of the same request. Nothing is ever written loose in
``output/``.

``start-run`` is the only command that opens a folder. It leaves that run open,
so a later command that forgets ``--run-folder`` joins it instead of starting a
second one; the run closes itself after a few hours with nothing written to it,
so a new request cannot land in an old folder.

The agent does the talking; this script does the deciding-free work: reading,
matching, aggregating, checking and drawing.

Layout of the skill:

    scripts/easy_map.py   this CLI, the only entry point
    scripts/emap/         the engine, imported by the CLI

Development-only files live outside the skill, at the project root:
``tools/generate_complex_demo.py`` rebuilds the test workbook.
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from emap import (aggregate, animate, classify, confirm, crosswalk, dataio,  # noqa: E402
                  fonts, furniture, guardrails, i18n, interactive, matching, messages,
                  periods as period_utils,
                  layers, longform, prefs, profile as profiling, render,
                  semantics as sem,
                  tabular, webpage, wording)

PROVINCE_SERIES_THRESHOLD = 5


# --------------------------------------------------------------------------
def speak_utf8() -> None:
    """Print in UTF-8 whatever the console was set to.

    Every reply this engine writes carries Vietnamese - place names at the very
    least - and on Windows Python encodes stdout with the machine's legacy
    codepage rather than UTF-8, for a pipe as much as for a console. One
    accented character then ends the command in UnicodeEncodeError before the
    agent has read anything, and the traceback points at ``json.dumps`` rather
    than at the setting that caused it.

    Guarded rather than assumed: a caller may have replaced the stream with one
    that has no ``reconfigure``, which is what happens when tests capture it.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _shape_features(gdf, name_field: str) -> list[dict[str, Any]]:
    return [{"name": n, "shape_id": int(i)}
            for n, i in zip(gdf[name_field], gdf["__shape_id"])]


def _province_index(gdf, name_field: str):
    """Province lookup that also answers to the 63 pre-2025 province names."""
    return matching.build_index(crosswalk.alias_features(gdf, name_field=name_field))


def _commune_index_by_province(gdf, fields) -> dict[str, dict[str, list[dict[str, Any]]]]:
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for province, group in gdf.groupby(fields["province"]):
        out[str(province)] = matching.build_index(_shape_features(group, fields["commune"]))
    return out


#: The bar a commune column has to clear. Defined once in ``tabular`` so the
#: survey and this detector cannot disagree about the same sheet.
COMMUNE_NAME_COVERAGE = tabular.COMMUNE_SHARE


def _name_coverage(df, column, keys, exclude=frozenset()) -> float:
    """Share of the column's **distinct** names that exist at this level.

    Counting rows instead lets a handful of frequently-repeated names carry the
    vote, which is how 70.000 rows of one export decided it was commune data.
    """
    names = {matching.normalize(v) for v in df[column].tolist() if v is not None}
    names.discard("")
    if not names:
        return 0.0
    return sum(1 for k in names if k in keys and k not in exclude) / len(names)


def _fine_tier(deps, root, country, notes=None):
    """The finer of the two tiers, or nothing.

    A boundary set that stops at states is a complete boundary set, and the old
    two-folder layout could not express it: both folders had to be there or the
    lookup failed, so a country with one tier could not be drawn at all — not
    even at the tier it had.
    """
    try:
        shapes = dataio.load_shapes(deps, root, dataio.FINE, notes=notes,
                                    country=country)
    except SystemExit:
        return None, None
    return shapes, dataio.shape_fields(shapes, dataio.FINE)


def _detect_admin_level(df, provinces, communes) -> str:
    p_keys = {matching.normalize(n) for n in provinces}
    c_keys = {matching.normalize(n) for n in communes}
    best = max((_name_coverage(df, c, c_keys, exclude=p_keys) for c in df.columns),
               default=0.0)
    return "commune" if best >= COMMUNE_NAME_COVERAGE else "province"


# --------------------------------------------------------------------------
def command_start_run(args: argparse.Namespace) -> None:
    """Stamp the folder at the start of the request, before any questions."""
    root = Path(args.project_root).resolve()
    # the one command that is allowed to open a folder: everything else joins
    # the run this leaves open
    folder = dataio.create_run_dir(root, args.run_folder, fresh=True)
    emit({
        "run_folder": folder.name,
        "thư_mục_lần_chạy": str(folder),
        "hướng_dẫn": ("Truyền --run-folder " + folder.name +
                      " cho mọi lệnh profile/render của yêu cầu này. Quên truyền thì "
                      "lệnh vẫn ghi vào đúng thư mục này, miễn là gọi trong "
                      f"{dataio.OPEN_RUN_HOURS:g} giờ."),
    })


# --------------------------------------------------------------------------
def command_list(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    deps = dataio.load(require_geo=False)
    workbooks = []
    for path in dataio.find_excel_files(root):
        try:
            sheets = dataio.read_sheets(deps, path)
        except Exception as exc:  # pragma: no cover - depends on the workbook
            sheets = [f"<không đọc được: {exc}>"]
        workbooks.append({"tệp": str(path.relative_to(root)), "sheet": sheets})

    boundary_root = dataio.shapefile_root(root)
    moved = dataio.migrate_legacy_layout(boundary_root)
    available = {}
    for name in dataio.countries(boundary_root):
        entry = {"tầng": [{k: v for k, v in tier.items() if not k.startswith("__")}
                          for tier in dataio.tiers(boundary_root, name)]}
        # Reading a country means opening its boundary files, which needs
        # geopandas. ``list`` is the command someone runs when something is
        # wrong, so it answers what it can without it rather than refusing.
        if deps.gpd is None:
            entry["hồ_sơ"] = messages.text("liet-ke.chưa-có-geopandas")
        else:
            try:
                reading = dataio.read_country(deps, boundary_root, name)
                entry.update({k: v for k, v in reading.items()
                              if k not in ("__nguồn", "tầng")})
            except Exception as exc:        # a country that cannot be read is
                entry["không_đọc_được"] = str(exc)   # reported, not fatal
        available[name] = entry

    # The per-tier paths are only meaningful when there is one country to be
    # meaningful about. With several installed, "quốc_gia" above already says
    # what is there, and repeating the same refusal twice under a heading that
    # promises a file is noise dressed as an error.
    shapefiles = {}
    if len(available) == 1:
        for level in (dataio.COARSE, dataio.FINE):
            try:
                found = dataio.find_boundaries(root, level)
                # the boundaries may sit outside the project now, so a path
                # relative to it is not always expressible
                try:
                    shapefiles[level] = str(found.relative_to(root))
                except ValueError:
                    shapefiles[level] = str(found)
            except SystemExit as exc:
                shapefiles[level] = str(exc)

    emit({
        "thư_mục_dự_án": str(root),
        "workbook": workbooks,
        "quốc_gia": available,
        **({"đã_chuyển_bố_cục": moved} if moved else {}),
        "shapefile": shapefiles,
        "font_thiếu": fonts.missing_files(),
        "lựa_chọn_đã_ghi_nhớ": prefs._load(root / prefs.FOLDER / prefs.CHOICES),
    })


# --------------------------------------------------------------------------
def command_import(args: argparse.Namespace) -> None:
    """Take a file the user attached to the chat and put it where the rest of
    the skill can find it — then say what is inside it, in one step.

    Two things happen together on purpose. Copying alone would leave the agent
    to run ``survey`` next and the user waiting through two round trips for one
    obvious question; and a file that copies successfully but turns out to hold
    no place-name column is not really an import that succeeded.
    """
    root = Path(args.project_root).resolve()
    result = dataio.adopt_file(root, Path(args.file))

    # record it against the request when one is open, but never open one:
    # importing a file is not itself a reason to create an output folder
    run_name = args.run_folder or dataio.open_run(root)
    if run_name:
        _append_manifest(dataio.create_run_dir(root, run_name), "tệp_đã_nhập", result)

    survey = argparse.Namespace(project_root=args.project_root, excel=result["tệp"])
    emit({**result, "khảo_sát": _survey_payload(survey)})


def command_survey(args: argparse.Namespace) -> None:
    emit(_survey_payload(args))


def _survey_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Which sheets in this workbook can become a map — before choosing one.

    Asking the user "which sheet?" before anyone knows which sheets are usable
    pushes the job back onto them, and they will pick the one whose name reads
    best. On a real export that is the pivot summary, not the data.

    Reads only a sample of each sheet: a place column is recognisable from a few
    hundred rows, and a workbook may hold sheets far too large to read in full
    just to decide whether they are worth reading.
    """
    from openpyxl import load_workbook

    root = Path(args.project_root).resolve()
    deps = dataio.load(require_geo=True)
    if args.excel:
        one = dataio.project_path(root, args.excel)
        if one is None or not one.exists():
            raise SystemExit(f"Không tìm thấy workbook: {args.excel}")
        books = [one]
    else:
        # No file named: survey everything, so the question that follows can name
        # what each file holds. Asking "which file?" against a list of file names
        # is the same mistake as asking "which sheet?" — one level further out.
        books = dataio.find_excel_files(root)
        if not books:
            raise SystemExit(messages.text("khao-sat.không-có-workbook"))

    country = getattr(args, "country", None)
    province_shapes = dataio.load_shapes(deps, root, dataio.COARSE, country=country)
    p_field = dataio.shape_fields(province_shapes, dataio.COARSE)["province"]
    province_keys = {matching.normalize(v) for v in province_shapes[p_field]}
    province_keys |= {matching.normalize(n) for n in
                      crosswalk.build(province_shapes, name_field=p_field)}

    commune_shapes, c_fields = _fine_tier(deps, root, country)
    commune_keys = set()
    if commune_shapes is not None:
        commune_keys = {matching.normalize(v)
                        for v in commune_shapes[c_fields["commune"]]}

    limit = tabular.SURVEY_ROWS + tabular.MAX_HEADER_SCAN
    files = []
    for path in books:
        if dataio.is_text_table(path):
            try:
                sample, total = _sample_text_table(path, limit)
            except Exception as exc:
                files.append({"tệp": _short(path, root), "lỗi": str(exc), "sheet": [],
                              "nên_dùng": []})
                continue
            sheets = [_survey_sheet(dataio.SINGLE_SHEET, total, sample,
                                    province_keys, commune_keys)]
            files.append(_survey_file(path, root, sheets))
            continue
        try:
            book = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:      # a workbook the reader cannot open at all
            files.append({"tệp": _short(path, root), "lỗi": str(exc), "sheet": [],
                          "nên_dùng": []})
            continue
        sheets = []
        try:
            for ws in book.worksheets:
                sample = []
                for row in ws.iter_rows(values_only=True):
                    sample.append(list(row))
                    if len(sample) >= limit:
                        break
                sheets.append(_survey_sheet(ws.title, int(ws.max_row or 0), sample,
                                            province_keys, commune_keys))
        finally:
            book.close()
        files.append(_survey_file(path, root, sheets))

    with_maps = [f for f in files if f["nên_dùng"]]
    payload: dict[str, Any] = {
        "workbook": files,
        "nên_dùng": [{"tệp": f["tệp"], "sheet": f["nên_dùng"]} for f in with_maps],
        # A ready-made menu. Without it the agent lists what it finds in prose
        # and the reader has to copy a file name back — which is what happened
        # on the first real run, and it is a poor way to choose between nine
        # files. One number is the whole answer.
        "chọn_nhanh": _quick_pick(files),
        "tóm_tắt": (messages.text("khao-sat.có-sheet-vẽ-được", total=len(files),
                                  files=len(with_maps))
                    if len(files) > 1 else
                    (files[0].get("tóm_tắt")
                     or messages.text("khao-sat.không-đọc-được"))),
        "ghi_chú": messages.text("doc.chỉ-đọc-mẫu", rows=tabular.SURVEY_ROWS),
    }
    if len(files) == 1:
        payload["sheet"] = files[0]["sheet"]      # unchanged shape for one file
    return payload


def _quick_pick(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Every mappable sheet in the folder as a finished question.

    Sheets that cannot become a map are left out: offering them costs the reader
    a decision that only ends in a refusal. The last option is always to send a
    file instead — the folder holds fixtures and other people's work, and a menu
    with no way off it invites someone to map a table that is not theirs.
    """
    picks: list[dict[str, Any]] = []
    for f in files:
        for sheet in f.get("sheet", []):
            if not sheet.get("dùng_được"):
                continue
            rows = sheet.get("số_dòng_ước_tính") or 0
            level = sheet.get("cấp_gợi_ý")
            picks.append({
                "số": len(picks) + 1,
                "nhãn": f["tệp"],
                "mô_tả": messages.text(
                    "chọn.tệp.mô_tả", sheet=sheet["sheet"],
                    rows=wording.count("bảng.số-dòng", "rows", rows),
                    level=messages.text({"commune": "cap.xa", "province": "cap.tinh"}
                                        .get(level, "bảng.không-áp-dụng"))),
                "tệp": f["tệp"], "sheet": sheet["sheet"],
                "số_dòng": sheet.get("số_dòng_ước_tính"), "cấp": level,
            })
    picks.append({"số": len(picks) + 1,
                  "nhãn": messages.text("chọn.tệp.tải-lên.nhãn"),
                  "mô_tả": messages.text("chọn.tệp.tải-lên.mô_tả"),
                  "tệp": None, "sheet": None})
    return {"câu_hỏi": messages.text("chọn.tệp.câu_hỏi"), "lựa_chọn": picks}


def _short(path: Path, root: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def _append_manifest(run_dir: Path, key: str, entry: dict[str, Any]) -> None:
    """Add one entry to the request's manifest, leaving the other keys alone.

    The manifest is the record of what a request did, and a request now does
    more than render: it may also have taken in a file the user attached. A
    corrupt or hand-edited manifest is rebuilt rather than allowed to stop a run
    that has already produced its maps.
    """
    path = run_dir / "run_manifest.json"
    manifest: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                manifest = existing
        except (json.JSONDecodeError, OSError):
            pass
    manifest["thư_mục"] = str(run_dir)
    if not isinstance(manifest.get(key), list):
        manifest[key] = []
    manifest[key].append(entry)
    dataio.write_json(path, manifest)


def _sample_text_table(path: Path, limit: int) -> tuple[list[list[Any]], int]:
    """The first rows of a delimited file, plus how many rows it really has.

    Read with the same dialect detection the full reader uses, so the survey
    cannot disagree with what ``profile`` will see a moment later.
    """
    dialect = dataio._text_dialect(path)
    sample: list[list[Any]] = []
    total = 0
    with open(path, encoding=dialect["encoding"], newline="") as handle:
        for row in csv.reader(handle, delimiter=dialect["sep"]):
            total += 1
            if len(sample) < limit:
                sample.append(list(row))
    return sample, total


def _survey_file(path: Path, root: Path, sheets: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [s["sheet"] for s in sheets if s["dùng_được"]]
    return {
        "tệp": _short(path, root), "sheet": sheets, "nên_dùng": usable,
        "tóm_tắt": (messages.text("khao-sat.sheet-vẽ-được", sheets=len(sheets),
                                  usable=len(usable), names=", ".join(usable))
                    if usable else
                    messages.text("khao-sat.không-sheet-nào", sheets=len(sheets))),
    }


def _several_tables(sample: list[list[Any]]) -> dict[str, Any]:
    """Whether this sheet holds more than one table, and where they start.

    Reported, never acted on. Read plainly, a sheet with a summary table above a
    budget table comes back as one table whose lower half has different columns
    — and no error. Which table the reader wants is their decision.
    """
    blocks = tabular.table_blocks(sample)
    if len(blocks) < 2:
        return {}
    return {
        "số_bảng_trong_sheet": len(blocks),
        "vị_trí_các_bảng": [{"dòng_đầu": a + 1, "dòng_cuối": b + 1} for a, b in blocks],
        "lưu_ý": messages.text("doc.nhiều-bảng", count=len(blocks)),
    }


def _tables_in_sheet(excel: Path, sheet: str | None) -> dict[str, Any]:
    """``_several_tables`` for one chosen sheet, for the profile to carry.

    ``survey`` reports a sheet holding two tables; ``profile`` did not, and the
    warning was lost the moment somebody named the sheet they wanted. Measured
    on a fixture with a second table appended below the first: the profile read
    straight through, and the second table's heading row — the literal string
    "Tỉnh/thành phố" — was fuzzy-matched onto Thanh Hóa at 88.9%.

    A delimited file cannot hold two tables the way a worksheet can. The suffix
    check is a short cut, not a correctness condition — ``load_workbook`` on a
    CSV raises and the answer would be the same either way.
    """
    if excel.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
        return {}
    try:
        from openpyxl import load_workbook

        book = load_workbook(excel, read_only=True, data_only=True)
    except Exception:            # unreadable here is reported by the reader itself
        return {}
    try:
        ws = book[sheet] if sheet else book.worksheets[0]
        sample = []
        for row in ws.iter_rows(values_only=True):
            sample.append(list(row))
            if len(sample) >= tabular.SURVEY_ROWS:
                break
    except Exception:
        return {}
    finally:
        book.close()
    return _several_tables(sample)


def _survey_sheet(title: str, max_row: int, sample: list[list[Any]],
                  province_keys: set[str], commune_keys: set[str]) -> dict[str, Any]:
    """One sheet's verdict. Takes the title and row count rather than a
    worksheet object, so a delimited text file — which has neither sheets nor
    an openpyxl reader — goes through exactly the same judgement."""
    if not any(any(not tabular.is_blank(c) for c in row) for row in sample):
        return {"sheet": title, "dùng_được": False, "số_dòng_ước_tính": 0,
                "lý_do": messages.text("sheet-rong.lý_do"),
                "nên_làm": messages.text("sheet-rong.nên_làm")}

    start = tabular.header_row(sample)
    columns = [c for c in sample[start]] if start < len(sample) else []
    body = [r for r in sample[start + 1:] if any(not tabular.is_blank(c) for c in r)]
    names = [str(c).strip() if not tabular.is_blank(c) else f"Unnamed: {i}"
             for i, c in enumerate(columns)]

    places = tabular.place_columns(names, body, province_keys, commune_keys)
    place_column = places["xã"] or places["tỉnh"]
    total = max(int(max_row or 0) - start - 1, len(body))
    blocked = tabular.usability(names, len(body), place_column)

    out: dict[str, Any] = {
        "sheet": title,
        "dùng_được": blocked is None,
        "số_dòng_ước_tính": total,
        "số_cột": len(names),
        "dòng_tiêu_đề": start + 1,
        "cột_địa_danh": {"tỉnh": places["tỉnh"], "xã": places["xã"]},
        **_several_tables(sample),
        "cấp_gợi_ý": ("commune" if places["xã"] else
                      "province" if places["tỉnh"] else None),
    }
    if blocked:
        out.update(blocked)
    return out


# --------------------------------------------------------------------------
def command_profile(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    deps = dataio.load(require_geo=True)
    excel = dataio.project_path(root, args.excel)
    if excel is None or not excel.exists():
        raise SystemExit(f"Không tìm thấy workbook: {args.excel}")

    sheets = dataio.read_sheets(deps, excel)
    reading: list[dict[str, Any]] = []
    df = dataio.read_table(deps, excel, args.sheet, notes=reading)
    dictionary = dataio.read_data_dictionary(deps, excel, sheets)

    boundary_notes: list[dict[str, Any]] = []
    country = getattr(args, "country", None)
    province_shapes = dataio.load_shapes(deps, root, dataio.COARSE,
                                         notes=boundary_notes, country=country)
    p_fields = dataio.shape_fields(province_shapes, dataio.COARSE)
    province_names = [str(v) for v in province_shapes[p_fields["province"]]]

    commune_shapes, c_fields = _fine_tier(deps, root, country, boundary_notes)
    commune_names = ([str(v) for v in commune_shapes[c_fields["commune"]]]
                     if commune_shapes is not None else [])

    admin_level = args.admin_level
    if admin_level in (None, "auto"):
        admin_level = _detect_admin_level(df, province_names, commune_names)

    report = profiling.build(deps, df, sheet=args.sheet, admin_level=admin_level,
                             province_names=province_names, commune_names=commune_names,
                             dictionary=dictionary)
    report["sheet_khả_dụng"] = sheets
    report["lựa_chọn_đã_ghi_nhớ"] = prefs.recall_choices(root, excel, args.sheet)
    tables = _tables_in_sheet(excel, args.sheet)
    if tables:
        report["nhiều_bảng_trong_sheet"] = tables
        reading.append({"việc": "nhiều_bảng", **tables})

    province_column = args.province_column or _first(report["cột_địa_danh"]["tỉnh"])
    commune_column = args.commune_column or _first(report["cột_địa_danh"]["xã"])
    report["cột_tỉnh_đề_xuất"] = province_column
    report["cột_xã_đề_xuất"] = commune_column

    place_column = commune_column if admin_level == "commune" else province_column
    report["cách_đọc_sheet"] = reading
    # A repaired codepage changes place names, so it is never left unsaid: the
    # user has to be able to tell a name the skill corrected from one they typed.
    if boundary_notes:
        report["sửa_bảng_mã_ranh_giới"] = boundary_notes

    # Before anything else is said about this sheet: can it become a map at all?
    # Without this, a pivot table read with the wrong header row still came back
    # with a map option beside twenty columns called "Unnamed: 3".
    blocked = tabular.usability(list(df.columns), len(df), place_column)
    if blocked:
        report["dùng_được"] = False
        report["phương_án_bản_đồ"] = []
        report["cảnh_báo_chất_lượng"].insert(0, guardrails._issue(
            "sheet-khong-ve-duoc", guardrails.CRITICAL,
            fmt={"why": blocked["lý_do"], "fix": blocked["nên_làm"]},
            extra={k: v for k, v in blocked.items() if k not in ("lý_do", "nên_làm")}))
        report["run_folder"] = dataio.create_run_dir(root, args.run_folder).name
        emit(report)
        return
    report["dùng_được"] = True

    long_report = _long_format_report(df, report["cột"], place_column)
    if long_report:
        report["dữ_liệu_dạng_dài"] = long_report
        # the wide-format map options were computed on the assumption that a
        # column is a measure; here they are noise at best and misleading at worst
        report["phương_án_bản_đồ"] = []
        report["cảnh_báo_chất_lượng"].extend(long_report.pop("cảnh_báo", []))

    # the unit being mapped comes first: on commune data the province column is
    # the same value on every row and proves nothing
    places = ([commune_column, province_column] if admin_level == "commune"
              else [province_column, commune_column])
    report["mẫu_dữ_liệu"] = _sample_rows(df, report["cột"], places, long_report)

    review: list[dict[str, Any]] = []
    if admin_level == "province" and province_column:
        index = _province_index(province_shapes, p_fields["province"])
        review = matching.review_province(
            [{"province": v} for v in df[province_column].tolist()], index)
    elif admin_level == "commune" and commune_column:
        index = _province_index(province_shapes, p_fields["province"])
        by_province = _commune_index_by_province(commune_shapes, c_fields)
        rows = [{"province": (df[province_column].iloc[i] if province_column else None),
                 "commune": df[commune_column].iloc[i]} for i in range(len(df))]
        review = matching.review_commune(rows, index, by_province,
                                         prefs.recall_overrides(root, "commune"))

    # every artefact of this request belongs to its run folder
    run_dir = dataio.create_run_dir(root, args.run_folder)
    summary = matching.summarize(review) if review else {}
    review_path = run_dir / review_filename(admin_level, excel, args.sheet)
    if review:
        dataio.write_csv(review_path, review)
    report["ghép_địa_danh"] = {
        "tóm_tắt": summary,
        "tệp_duyệt": str(review_path) if review else None,
        "cần_xem_lại": matching.rows_needing_attention(review)[:25],
    }
    if summary:
        report["cảnh_báo_chất_lượng"].extend(guardrails.check_matching(summary))
        report["cảnh_báo_chất_lượng"].extend(
            guardrails.check_admin_level(summary, admin_level, commune_column))

    report["run_folder"] = run_dir.name
    report["thư_mục_lần_chạy"] = str(run_dir)
    profile_path = run_dir / "dataset_profile.json"
    dataio.write_json(profile_path, report)
    report["tệp_hồ_sơ"] = str(profile_path)
    emit(report)


def _first(entries: list[dict[str, Any]]) -> str | None:
    return entries[0]["cột"] if entries else None


LONG_SAMPLE = 5000
TOP_INDICATORS = 12

#: rows of one indicator read before deciding what kind of quantity it is —
#: enough to see whether the values are whole numbers or shares, cheap on a
#: sheet where one indicator can hold ten thousand rows
SEMANTIC_SAMPLE = 500

#: rows shown as evidence for what the agent claims the sheet is
SAMPLE_ROWS = 5
#: how many columns fit in a chat window before the table stops being readable
SAMPLE_COLUMNS = 7


def _sample_rows(df, columns: list[dict[str, Any]], place_columns: list[str],
                 long_report: dict[str, Any] | None) -> dict[str, Any]:
    """A few real rows, narrow enough to read, to back up the summary.

    A claim about a dataset is worth more with the dataset under it, but a
    twenty-one column table pasted into a chat window is unreadable and the
    reader skips it. So the columns that carry the meaning are chosen and the
    rest are counted, not hidden: the ellipsis column and the ellipsis row say
    plainly that there is more.
    """
    by_name = {c["column"]: c for c in columns}

    def take(names, into):
        for name in names:
            if name and name in df.columns and name not in into:
                into.append(name)

    # One place column is enough to show the grain; a second eats a slot that
    # the pinning columns need more. Those are what explain why one place
    # appears on many rows, so they come before the period columns.
    wanted: list[str] = []
    take([c for c in place_columns if c][:1], wanted)

    if long_report:
        take([long_report.get("cột_chỉ_số"), long_report.get("cột_giá_trị")], wanted)
        take([a["cột"] for a in long_report.get("cột_phải_ghăm", [])][:2], wanted)
        take(long_report.get("cột_thời_gian", [])[:2], wanted)
    else:
        for info in columns:
            if len(wanted) >= SAMPLE_COLUMNS:
                break
            if info["column"] in wanted or not info.get("mappable"):
                continue
            if info["semantic"] in longform.MEASURE_SEMANTICS:
                wanted.append(info["column"])

    for info in columns:                       # top up with whatever is left
        if len(wanted) >= SAMPLE_COLUMNS:
            break
        if info["column"] not in wanted:
            wanted.append(info["column"])
    wanted = wanted[:SAMPLE_COLUMNS]

    hidden = [str(c) for c in df.columns if c not in wanted]
    rows = []
    for _, row in df.head(SAMPLE_ROWS).iterrows():
        rows.append([sem.format_value(row[c], by_name.get(c, {}))
                     if by_name.get(c, {}).get("semantic") in longform.MEASURE_SEMANTICS
                     else ("" if tabular.is_blank(row[c]) else str(row[c]))
                     for c in wanted])
    return {
        "cột": wanted,
        "dòng": rows,
        "số_cột_ẩn": len(hidden),
        "tên_cột_ẩn": hidden,
        "số_dòng_còn_lại": max(len(df) - len(rows), 0),
        "cách_hiển_thị": ("Thêm một cột '…' ở cuối nếu còn cột ẩn, và một dòng '…' "
                          "ở dưới nếu bảng còn dài, kèm con số cụ thể."),
    }


def _apply_where(df, expressions):
    """Keep only the rows the user asked for, comparing as text.

    A filter that matches nothing stops the run and lists the values that do
    exist. Silently drawing an empty map because a value was typed 'Q02' is the
    kind of failure that costs an hour before anyone thinks to check the spelling.
    """
    pairs = longform.parse_where(expressions or [])
    if not pairs:
        return df, None
    for column, wanted in pairs:
        if column not in df.columns:
            raise SystemExit(f"--where trỏ vào cột không có: {column!r}. "
                             f"Các cột hiện có: {', '.join(map(str, df.columns))}")
        near = longform.unknown_values(column, wanted, df[column].tolist())
        if near is not None:
            raise SystemExit(
                f"--where '{column}={wanted}' không khớp dòng nào. "
                f"Giá trị đang có: {', '.join(repr(v) for v in near)}")
        df = df[df[column].astype(str).str.strip() == wanted]
    df = df.reset_index(drop=True)
    if df.empty:
        raise SystemExit("Sau khi lọc --where không còn dòng nào.")
    return df, longform.describe_filters(pairs)


def _units_shown(frame, has_fill: bool, has_symbol: bool) -> int:
    """Units the finished map shows something for, on any channel.

    A unit counts once whether it is coloured, circled or both — the question
    being answered is "how much of this map carries data", not "how many values
    are there".
    """
    mask = None
    for column, present in (("__value", has_fill), ("__symbol", has_symbol)):
        if not present or column not in frame.columns:
            continue
        here = frame[column].notna()
        mask = here if mask is None else (mask | here)
    return 0 if mask is None else int(mask.sum())


#: separates numerator from denominator in ``--layer "TX_PVLS Num / TX_PVLS Den"``
RATIO_SEPARATOR = "/"

#: separates an indicator from its own pins, as in
#: ``--layer "HTS_TST_POS|Status/Result=Positive"``. A bar rather than a slash,
#: because column names in real exports contain slashes ("Status/Result") and
#: indicator codes do not contain bars.
PIN_SEPARATOR = "|"


def _layer_requests(args, deps, frame) -> list[dict[str, Any]]:
    """What each ``--layer`` refers to, on a wide sheet and on a long one.

    Wide: a column name, and its semantic is already known from the heading.
    Long: a value inside ``--indicator-column``, because every indicator shares
    one numeric column — asking for a column name there is meaningless, and
    used to be a dead end with a good error message and no way forward.
    """
    axis = args.indicator_column
    if not axis:
        known = {c["column"]: c for c in profiling.describe_columns(deps, frame, None)}
        out = []
        for name in args.layer:
            if name not in known:
                raise SystemExit(f"--layer trỏ vào cột không có: {name!r}. "
                                 f"Các cột hiện có: {', '.join(map(str, frame.columns))}")
            out.append({"tên": name, "semantic": known[name]["semantic"], "cột": name})
        return out

    if axis not in frame.columns:
        raise SystemExit(f"--indicator-column trỏ vào cột không có: {axis!r}. "
                         f"Các cột hiện có: {', '.join(map(str, frame.columns))}")
    if not args.value_column:
        raise SystemExit("Bảng dạng dài cần --value-column trỏ vào cột chứa số.")

    codes = frame[axis].astype(str).str.strip()
    present = set(codes)

    def require(value: str) -> None:
        if value in present:
            return
        near = longform.unknown_values(axis, value, frame[axis].tolist()) or []
        raise SystemExit(f"--layer '{value}' không có trong cột {axis!r}. "
                         f"Giá trị gần đúng: {', '.join(repr(v) for v in near)}")

    out = []
    for raw in args.layer:
        # pins first: a column name may contain a slash ("Status/Result"), so
        # splitting on the ratio separator before this would misread the pin
        head, *pins = (part.strip() for part in raw.split(PIN_SEPARATOR))
        if RATIO_SEPARATOR in head:
            num, den = (p.strip() for p in head.split(RATIO_SEPARATOR, 1))
            require(num)
            require(den)
            # a quotient is normalised by construction, so it belongs to the fill
            out.append({"tên": f"{num} ÷ {den} (%)", "semantic": sem.PERCENT,
                        "tử_số": num, "mẫu_số": den, "lát": pins})
            continue
        require(head)
        rows = frame[codes == head]
        for column, value in longform.parse_where(pins):
            if column not in rows.columns:
                raise SystemExit(f"Lát của --layer '{head}' trỏ vào cột không có: {column!r}")
            rows = rows[rows[column].astype(str).str.strip() == value]
        info = indicator_semantic(rows[args.value_column].tolist(), head)
        out.append({"tên": head, "semantic": info["semantic"], "chỉ_số": head, "lát": pins})
    return out


def _render_layers(args: argparse.Namespace) -> None:
    """Draw however many maps the requested variables need.

    A map holds two quantitative channels. Asking for three variables is not an
    error and should not be answered with one — the surplus goes to a second
    map in the same folder, behind the same picker on the interactive page.

    Each map is rendered by a full pass of ``command_render`` rather than by
    looping inside it. That costs a re-read of the workbook, and buys the one
    thing that matters here: every map computes its own class breaks and its own
    circle scale, which is correct because two different variables have no
    business sharing either.
    """
    root = Path(args.project_root).resolve()
    deps = dataio.load(require_geo=False)
    excel = dataio.project_path(root, args.excel)
    frame, _ = _apply_where(dataio.read_table(deps, excel, args.sheet), args.where)

    requests = _layer_requests(args, deps, frame)
    plan = layers.allocate(requests)
    if not plan["bản_đồ"]:
        raise SystemExit(messages.text("loi.khong-bien-nao-ve-duoc")
                         + " ".join(r["vì_sao"] for r in plan["không_xếp_được"]))

    # one folder for the whole set, resolved once so every pass writes together
    run_folder = args.run_folder or dataio.create_run_dir(root).name
    emit({"kế_hoạch_lớp": layers.summary_lines(plan),
          "vì_sao_tách": plan.get("vì_sao_tách"),
          "không_xếp_được": plan["không_xếp_được"],
          "cảnh_báo_lớp": layers.conflicts(requests),
          "thư_mục": run_folder,
          "số_bản_đồ_sẽ_vẽ": len(plan["bản_đồ"])})

    for item in plan["bản_đồ"]:
        fill, symbol = item["màu_vùng"], item["vòng_tròn"]
        step = argparse.Namespace(**vars(args))
        step.layer = None
        step.run_folder = run_folder
        step.map_type = item["loại"]
        if args.indicator_column:
            # each channel names its own slice; the numeric column stays shared
            step.numerator = (fill or {}).get("tử_số")
            step.denominator = (fill or {}).get("mẫu_số")
            step.fill_indicator = (fill or {}).get("chỉ_số")
            step.symbol_indicator = (symbol or {}).get("chỉ_số")
            step.fill_where = (fill or {}).get("lát") or args.fill_where
            step.symbol_where = (symbol or {}).get("lát") or args.symbol_where
            step.symbol_column = None
        else:
            step.value_column = fill["cột"] if fill else None
            step.symbol_column = symbol["cột"] if symbol else None
        # the file name is built from the title, so a fixed title across several
        # maps would have each pass overwrite the one before it
        if len(plan["bản_đồ"]) > 1:
            lead = (fill or symbol)["tên"]
            step.title = f"{args.title} — {lead}" if args.title else lead
        command_render(step)


def indicator_semantic(values: list[Any], name: str) -> dict[str, Any]:
    """What kind of quantity one indicator's own rows hold.

    On a long sheet the column heading says nothing — every indicator shares the
    same ``Value`` column — so the semantic has to be read off the numbers.
    """
    clean = [v for v in values if v is not None and v == v][:SEMANTIC_SAMPLE]
    return sem.infer(name, clean, True)


def _drawn_table(run_dir: Path, base: str, frame, name_field: str,
                 value_column: str | None, value_info: dict[str, Any],
                 symbol_info: dict[str, Any], args, bins) -> str | None:
    """The numbers the map was drawn from, as a CSV beside the image.

    Not the input sheet: this is what survived name matching, filtering and
    aggregation — the values actually behind the colours and the circles.
    Anybody checking a figure in a report needs that table, and reconstructing
    it from the workbook means repeating every step by hand and hoping.

    Both the raw value and the formatted one are written: the first to compute
    with, the second to check against what the reader sees on the plate.
    """
    if name_field not in frame.columns:
        return None
    rows: list[dict[str, Any]] = []
    lang = args.language
    # the same number of decimals the plate's labels use. Formatting the table
    # independently made the map say 99,74% and the table 99,7% about one value
    # — the column exists to be checked against the plate, so it has to agree
    # with it down to the last digit.
    decimals = classify.label_decimals(bins)
    for _, row in frame.iterrows():
        entry: dict[str, Any] = {"đơn_vị": row[name_field]}
        if "__value" in frame.columns:
            raw = row["__value"]
            entry[value_column or "giá_trị"] = "" if raw != raw else raw
            entry["hiển_thị"] = ("" if raw != raw
                                 else sem.format_value(raw, value_info,
                                                       decimals=decimals, lang=lang))
        if "__symbol" in frame.columns:
            raw = row["__symbol"]
            entry[args.symbol_column or "vòng_tròn"] = "" if raw != raw else raw
            entry["hiển_thị_vòng_tròn"] = (
                "" if raw != raw else sem.format_value(raw, symbol_info, decimals=0,
                                                       lang=lang))
        rows.append(entry)
    if not rows:
        return None
    path = run_dir / f"{base}_so-lieu.csv"
    dataio.write_csv(path, rows)
    return str(path)


def _dress_points(points: dict[str, Any], rows, args, by_name) -> None:
    """Give the dots a colour and a size, when the user named columns for them.

    Same rule as the area map, for the same reason: a category chooses colour, a
    magnitude chooses size. Sizing dots by a category would invent an order the
    data does not have, and colouring them by a count would ask a reader to
    judge quantity from hue.
    """
    colour_col = args.point_color_column
    if colour_col:
        if colour_col not in rows.columns:
            raise SystemExit(f"--point-color-column trỏ vào cột không có: {colour_col!r}")
        labels = [str(v) for v in rows[colour_col]]
        cats, mapping = classify.category_colours(labels)
        points["colours"] = [mapping[v] for v in labels]
        points["legend_pairs"] = [(mapping[c], c) for c in cats]
        points["màu_theo"] = colour_col

    size_col = args.point_size_column
    if size_col:
        if size_col not in rows.columns:
            raise SystemExit(f"--point-size-column trỏ vào cột không có: {size_col!r}")
        values = [None if v != v else float(v) for v in rows[size_col]]
        finite = [v for v in values if v is not None and v > 0]
        vmax = max(finite) if finite else 1.0
        s_max, s_min = furniture.SYMBOL_MAX_PT ** 2, furniture.SYMBOL_MIN_PT ** 2
        # the floor is a display minimum and stays out of the scale, or the key
        # would stop being true for the smallest dots
        points["sizes"] = [s_min if not v else max(s_min, s_max * (v / vmax))
                           for v in values]
        points["size_scale"] = {"max_value": vmax,
                                "title": args.symbol_legend_title or size_col}
        points["size_info"] = by_name.get(size_col, {})
        points["cỡ_theo"] = size_col


def _build_long_columns(args, joined, by_name):
    """Columns the sheet does not have: one per channel, each from its own rows.

    On a long sheet "viral suppression" and "patients on treatment" are not two
    columns, they are two sets of rows. So each channel of the map has to be
    built from its own slice, and neither can be read off a column that exists
    in the file.

    TX_PVLS Num and TX_PVLS Den are separate rows, and neither is a map. Their
    quotient is viral suppression, and the division happens **after** summing
    each side within a unit — dividing row by row and averaging the quotients is
    a different, wrong number whenever the units differ in size.
    """
    axis = args.indicator_column or args.ratio_column
    if not axis:
        raise SystemExit("Cần --indicator-column (hoặc --ratio-column) để biết "
                         "cột nào chứa tên chỉ số.")
    if axis not in joined.columns:
        raise SystemExit(f"--indicator-column trỏ vào cột không có: {axis!r}")
    if not args.value_column:
        raise SystemExit("Bảng dạng dài cần --value-column trỏ vào cột chứa số.")

    codes = joined[axis].astype(str).str.strip()

    def rows_for(label: str, wanted: str, pins: list[str] | None = None):
        """The rows of one indicator, pinned on its own terms.

        Two indicators on one map can need different pins on the same column:
        in a PEPFAR extract TX_CURR carries a pre-computed 'Total' row beside
        its detail, while HTS_TST_POS has no Total at all and is pinned on
        'Positive'. A single --where would have to choose one and lose the
        other, so each channel pins its own slice here instead.
        """
        part = joined[codes == wanted]
        if part.empty:
            near = longform.unknown_values(axis, wanted, joined[axis].tolist()) or []
            raise SystemExit(f"Không có dòng nào cho {label} '{wanted}'. "
                             f"Giá trị đang có: {', '.join(repr(v) for v in near)}")
        for column, value in longform.parse_where(pins or []):
            if column not in part.columns:
                raise SystemExit(f"Lát của '{wanted}' trỏ vào cột không có: {column!r}")
            pinned = part[part[column].astype(str).str.strip() == value]
            if pinned.empty:
                have = sorted({str(v).strip() for v in part[column].tolist()})[:8]
                raise SystemExit(
                    f"Lát '{column}={value}' không khớp dòng nào của '{wanted}'. "
                    f"Giá trị đang có: {', '.join(map(repr, have))}")
            part = pinned
        return part

    frame = joined.drop_duplicates("__shape_id").copy()
    note: dict[str, Any] = {"cột_chỉ_số": axis}
    name = None

    if args.numerator or args.denominator:
        if not (args.numerator and args.denominator):
            raise SystemExit("Chế độ tỷ số cần đủ --numerator và --denominator.")
        top = rows_for("tử số", args.numerator, args.fill_where) \
            .groupby("__shape_id")[args.value_column].sum()
        bottom = rows_for("mẫu số", args.denominator, args.fill_where) \
            .groupby("__shape_id")[args.value_column].sum()
        share = (top / bottom.replace(0, float("nan")) * 100.0).dropna()
        name = f"{args.numerator} ÷ {args.denominator} (%)"
        frame = frame[frame["__shape_id"].isin(share.index)]
        frame[name] = frame["__shape_id"].map(share)
        by_name[name] = sem._pack(sem.PERCENT, name, "phần trăm", scale="percent")
        note.update({"tử_số": args.numerator, "mẫu_số": args.denominator,
                     "lát_màu_vùng": list(args.fill_where or []),
                     "số_đơn_vị_tính_được": int(len(share)),
                     "đơn_vị_mẫu_số_bằng_0": len(set(bottom.index) - set(share.index)),
                     "cách_tính": "Cộng tử số và mẫu số trong từng đơn vị rồi mới chia, "
                                  "không lấy trung bình của các tỷ lệ."})
    elif args.fill_indicator:
        rows = rows_for("màu vùng", args.fill_indicator, args.fill_where)
        totals = rows.groupby("__shape_id")[args.value_column].sum()
        name = str(args.fill_indicator)
        frame[name] = frame["__shape_id"].map(totals)
        by_name[name] = indicator_semantic(rows[args.value_column].tolist(), name)
        note["màu_vùng"] = {"chỉ_số": name, "số_đơn_vị": int(frame[name].notna().sum()),
                            "tổng": float(totals.sum()),
                            "lát": list(args.fill_where or [])}

    # The circles come from a different slice of the same sheet. Without this the
    # symbol column would be read off whatever single row survived the
    # de-duplication above — a real value from the wrong indicator, drawn at a
    # believable size, with nothing on the map to say so.
    if args.symbol_indicator:
        rows = rows_for("vòng tròn", args.symbol_indicator, args.symbol_where)
        totals = rows.groupby("__shape_id")[args.value_column].sum()
        symbol_name = str(args.symbol_indicator)
        frame[symbol_name] = frame["__shape_id"].map(totals)
        by_name[symbol_name] = sem._pack(sem.COUNT, symbol_name, "số đếm", integer=True)
        args.symbol_column = symbol_name
        note["vòng_tròn"] = {"chỉ_số": symbol_name,
                             "số_đơn_vị": int(frame[symbol_name].notna().sum()),
                             "tổng": float(totals.sum()),
                             "lát": list(args.symbol_where or [])}
    return name, frame, note


def _long_format_report(df, columns: list[dict[str, Any]],
                        place_column: str | None) -> dict[str, Any] | None:
    """What an analyst would need to know before choosing anything.

    A long sheet cannot be described by listing its columns: the map-worthy
    question is which indicator, over which period, from which disaggregation.
    This works that out from the data and, just as importantly, names the
    columns that must be pinned before any number is trustworthy.
    """
    if not place_column or place_column not in df.columns:
        return None
    shape = longform.looks_long(columns, len(df), int(df[place_column].nunique()))
    if not shape:
        return None

    samples = {c: df[c].dropna().astype(str).head(LONG_SAMPLE).tolist()
               for c in df.columns}
    axis = longform.indicator_axis(columns, samples)
    value_column = shape["cột_giá_trị"]
    time_columns = [c["column"] for c in columns if c.get("semantic") == sem.TIME]
    period_column = time_columns[0] if time_columns else None

    out: dict[str, Any] = {
        **shape,
        "cột_chỉ_số": axis,
        "cột_thời_gian": time_columns,
        "cột_phải_ghăm": [],
        "chỉ_số": [],
        "cặp_tử_mẫu": [],
        "cách_dùng": None,
        "cảnh_báo": [],
    }

    axes = {c: df[c].tolist() for c in df.columns
            if c not in {place_column, value_column} and df[c].nunique() > 1}
    risky = longform.double_counting_axes(df[place_column].tolist(), axes)
    out["cột_phải_ghăm"] = risky
    warning = longform.pin_warning(risky, int(df[place_column].nunique()))
    if warning:
        out["cảnh_báo"].append(guardrails._issue(
            "dem-trung-dang-dai", guardrails.CRITICAL, fmt={"why": warning}))

    if not axis:
        return out

    # plain lists, not Series: a filtered Series keeps the original index, so
    # positional access silently becomes a label lookup
    out["chỉ_số"] = longform.indicator_slices(
        df[axis].tolist(), df[place_column].tolist(), df[value_column].tolist(),
        df[period_column].tolist() if period_column else None)[:TOP_INDICATORS]
    out["cặp_tử_mẫu"] = longform.ratio_pairs(df[axis].dropna().unique())

    # Naming the dangerous columns is not enough: the agent still has to know
    # which value to pin, and the data can answer that better than a guess.
    # Time first. A stock indicator like "patients currently on treatment" is
    # not additive across quarters: summing six reporting periods counted every
    # patient six times and produced 433.681 where the quarter alone is 49.706.
    pin_columns = time_columns + [a["cột"] for a in risky if a["cột"] not in time_columns]
    for entry in out["chỉ_số"]:
        entry.update(_recommend_slice(df, axis, entry["chỉ_số"], place_column,
                                      value_column, pin_columns, time_columns))

    if out["chỉ_số"]:
        out["cách_dùng"] = out["chỉ_số"][0]["lệnh"]
    return out


def _recommend_slice(df, axis: str, indicator: str, place_column: str,
                     value_column: str, pin_columns: list[str],
                     time_columns: list[str]) -> dict[str, Any]:
    """For one indicator: which value to pin on each column, and why.

    Measured on the indicator's own rows, because the right disaggregation for
    TX_CURR is not the right one for HTS_TST — a recommendation taken from the
    whole sheet would be confidently wrong for most of the list.
    """
    rows = df[df[axis].astype(str).str.strip() == indicator]
    if rows.empty:
        return {"lát_đề_xuất": [], "lệnh": None, "chưa_ghăm": []}

    chosen: list[dict[str, Any]] = []
    kept = rows
    for column in pin_columns:
        if column not in rows.columns:
            continue
        if column in time_columns:
            pick, same = _latest_period(kept, column, place_column, value_column), []
        else:
            options = longform.pin_options(kept[column].tolist(),
                                           kept[place_column].tolist(),
                                           kept[value_column].tolist())
            pick = longform.recommend_pin(options)
            same = longform.duplicated_totals(options)
        if not pick:
            continue
        chosen.append({
            "cột": column, "ghăm": pick["giá_trị"], "vì_sao": pick["vì_sao"],
            "số_đơn_vị": pick["số_đơn_vị"], "tổng": pick["tổng"],
            "phương_án_khác": pick["phương_án_khác"],
            "giá_trị_cùng_một_tổng": same,
        })
        kept = kept[kept[column].astype(str).str.strip() == pick["giá_trị"]]

    # Whatever still splits a place after all that is a decision, not a default:
    # say so instead of summing across it and reporting the total as settled.
    leftover = {c: kept[c].tolist() for c in kept.columns
                if c not in {place_column, value_column, axis}
                and c not in {p["cột"] for p in chosen} and kept[c].nunique() > 1}
    remaining = [a["cột"] for a in
                 longform.varying_axes(kept[place_column].tolist(), leftover)]

    pins = " ".join(f'--where "{c["cột"]}={c["ghăm"]}"' for c in chosen)
    command = (f'--value-column "{value_column}" --where "{axis}={indicator}" '
               f'{pins}').strip()
    return {"lát_đề_xuất": chosen,
            "tổng_sau_khi_ghăm": chosen[-1]["tổng"] if chosen else None,
            "chưa_ghăm": remaining[:6],
            "lệnh": command}


def _latest_period(rows, column: str, place_column: str,
                   value_column: str) -> dict[str, Any] | None:
    """The most recent value of a time column, in real chronological order.

    Alphabetical order puts Q4 before Q1 of the next year and 'Target' after
    both, so the ordering has to come from the period reader, not from sorting
    the strings.
    """
    values = [v for v in rows[column].dropna().tolist()]
    if not values:
        return None
    ordered = period_utils.ordered(values)
    if not ordered:
        return None
    latest = str(ordered[-1]).strip()
    hit = rows[rows[column].astype(str).str.strip() == latest]
    return {
        "giá_trị": latest,
        "số_đơn_vị": int(hit[place_column].nunique()),
        "tổng": round(float(deps_sum(hit[value_column])), 1),
        "vì_sao": messages.text("dai.ky-moi-nhat", count=len(ordered)),
        "phương_án_khác": [str(p) for p in reversed(ordered[:-1])][:6],
    }


def _points_per_unit(deps, frame, points: dict[str, Any] | None) -> dict[str, int]:
    """How many plotted locations fall inside each administrative unit.

    On a point map the mapped quantity belongs to the dots, not to the areas, so
    a unit's detail card would otherwise have nothing to report but its own size.
    This is a count of what is actually drawn on that map — derived from the same
    coordinates — rather than an estimate.
    """
    if not points or not points.get("x"):
        return {}
    located = deps.gpd.GeoDataFrame(
        geometry=deps.gpd.points_from_xy(points["x"], points["y"]),
        crs=frame.crs)
    hit = deps.gpd.sjoin(located, frame[["__shape_id", "geometry"]],
                         how="inner", predicate="within")
    return {str(int(sid)): int(n) for sid, n in hit["__shape_id"].value_counts().items()}


def deps_sum(series) -> float:
    total = series.sum()
    try:
        return float(total)
    except (TypeError, ValueError):
        return 0.0


def review_filename(admin_level: str, excel: Path, sheet: str | None) -> str:
    """One review per dataset *and* level.

    A single request may map two different workbooks — a province table and a
    commune table — into the same folder. One shared file name meant the second
    render picked up the first render's review and failed on a missing column.
    """
    slug = dataio.slugify(f"{Path(excel).stem} {sheet or ''}", fallback="dataset")
    return f"match_review_{admin_level}_{slug}.csv"


def _review_is_usable(review: list[dict[str, Any]], admin_level: str) -> bool:
    if not review:
        return False
    needed = {"dataset_province"}
    if admin_level == "commune":
        needed.add("dataset_commune")
    return needed.issubset(review[0].keys())


# --------------------------------------------------------------------------
def command_fix_match(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    deps = dataio.load(require_geo=True)
    gdf = dataio.load_shapes(deps, root, args.admin_level,
                             country=getattr(args, "country", None))
    fields = dataio.shape_fields(gdf, args.admin_level)
    field = fields["commune"] if args.admin_level == "commune" else fields["province"]
    row = gdf[gdf["__shape_id"] == int(args.shape_id)]
    if row.empty:
        raise SystemExit(f"Không có đơn vị nào mang shape_id={args.shape_id}")
    path = prefs.remember_override(root, args.admin_level, args.province, args.name,
                                   int(args.shape_id), str(row.iloc[0][field]))
    emit({"đã_ghi_nhớ": {"tên_trong_bảng": args.name,
                         "ghép_với": str(row.iloc[0][field]),
                         "shape_id": int(args.shape_id)},
          "tệp": str(path)})


# --------------------------------------------------------------------------
def _contexts(args, shapes, fields, review, admin_level):
    """Decide what gets drawn: one national map, one province, or a series."""
    matched = [r for r in review if str(r.get("shape_id", "")) != ""]
    ids = {int(r["shape_id"]) for r in matched}
    scope = args.map_scope or "auto"

    if admin_level == "province":
        frame = shapes if scope != "matched-only" else shapes[shapes["__shape_id"].isin(ids)]
        return "national", [{"tên": "toàn quốc", "frame": frame, "locator": None}]

    provinces = sorted({r.get("matched_province", "") for r in matched
                        if r.get("matched_province")})
    if not provinces:
        # nothing was matched by name (e.g. a coordinate-only point map)
        return "national", [{"tên": "toàn quốc", "frame": shapes, "locator": None}]
    if scope == "matched-only":
        return "matched-only", [{"tên": "các đơn vị có số liệu",
                                 "frame": shapes[shapes["__shape_id"].isin(ids)],
                                 "locator": provinces[0] if len(provinces) == 1 else None}]
    if scope == "national" or (scope == "auto"
                               and len(provinces) > args.province_series_threshold):
        return "national", [{"tên": "toàn quốc", "frame": shapes, "locator": None}]
    if scope == "single-province" or len(provinces) == 1:
        name = provinces[0] if provinces else ""
        return "single-province", [{"tên": name,
                                    "frame": shapes[shapes[fields["province"]] == name],
                                    "locator": name}]
    return "province-series", [
        {"tên": name, "frame": shapes[shapes[fields["province"]] == name], "locator": name}
        for name in provinces
    ]


def _command_line() -> str:
    """This invocation, as the agent would type it again."""
    return " ".join(shlex.quote(a) for a in sys.argv)


#: Settings the person is meant to decide, not the skill. When one of these was
#: not supplied on the command line its question goes into ``phải_hỏi``, so the
#: agent asks about that rather than presenting a guess as a decision. The map's
#: language is here because a real run inferred it from the chat and never asked
#: — the reader may well want a Vietnamese map while writing in English.
THEIRS_TO_CHOOSE = ("language", "layout")


def _among(value_column, args, scope) -> dict[str, tuple[str, ...]]:
    """Alternatives that only apply to some tables, worked out from this one.

    :mod:`wording` will offer a menu for anything, and for most settings that is
    safe. These two are not: whether another map type or another framing is
    available depends on the columns and on where the rows fall, so the pool is
    narrowed here rather than guessed at by the agent.

    ``matched-only`` is never among them. It is a real flag and it stays
    reachable when a person asks for it by name, but a menu that offers it turns
    "we surveyed 12 of 34 provinces" into a picture of a country with 12
    provinces, and no reader of that picture would know.
    """
    among: dict[str, tuple[str, ...]] = {}
    if value_column and args.symbol_column:
        # both channels are filled, so all three area maps can be drawn from
        # exactly these columns
        among["map_type"] = ("choropleth-symbol", "choropleth", "graduated-symbol")
    if scope in ("national", "province-series"):
        among["map_scope"] = ("national", "province-series")
    return among


def _plan(args, excel, joined, value_column, scope, prepared, method, bins):
    """The numbered table the person agrees to, and the settings it stands for.

    Every value is written in the language of the conversation and in ordinary
    words — a table reading ``choropleth-symbol`` and ``weighted-mean`` can only
    be agreed to, never weighed. Rows the reader can still change carry their
    own question and their own alternatives, ready to hand to a picker.

    The table and the hash are built from the same values on purpose: what the
    reader saw is exactly what unlocks the drawing.
    """
    maps = ", ".join(str(c["tên"]) for c in prepared)
    auto = messages.text("bảng.tự-chọn")
    chosen = getattr(args, "chosen_explicitly", set())
    among = _among(value_column, args, scope)
    unknown = messages.text("bảng.không-áp-dụng")

    # a CSV has no sheet, and "sheet None" is worse jargon than any flag value
    sheet = f" › sheet {args.sheet}" if args.sheet else ""
    counted = wording.count("bảng.số-tấm", "maps", len(prepared))
    # "Một tấm toàn quốc — toàn quốc" says the same thing twice; the place names
    # only earn their space when they are not already the scope's own name
    reach = wording.label("map_scope", scope)
    if len(prepared) > 1:
        reach += f" — {counted}: {maps}"
    elif scope != "national":
        reach += f" — {maps}"

    # (row name, what it says, which setting it stands for)
    rows: list[tuple[str, str, str | None]] = [
        ("dữ-liệu", f"{Path(excel).name}{sheet} "
                    f"({wording.count('bảng.số-dòng', 'rows', len(joined))})", None),
    ]
    if args.where:
        rows.append(("lát-dữ-liệu", " · ".join(args.where), None))
    rows += [
        ("loại-bản-đồ", wording.label("map_type", args.map_type), "map_type"),
        ("tô-màu-theo", value_column or "—", None),
    ]
    if args.symbol_column:
        rows.append(("vòng-tròn-theo", args.symbol_column, None))
    rows += [
        ("phạm-vi", reach, "map_scope"),
        ("bố-cục", wording.label("layout", args.layout), "layout"),
        ("ngôn-ngữ", wording.label("language", args.language), "language"),
        ("chia-nhóm", (f"{wording.label('classification', args.classification)} — "
                       f"{wording.count('bảng.số-nhóm', 'classes', bins['classes'])}"
                       if bins else unknown), "classification"),
        ("nhãn", wording.label("labels", args.labels), "labels"),
        ("gộp-dòng", (wording.label("aggregate", method)
                      if method in wording.VALUES["aggregate"] else unknown), "aggregate"),
        ("đầu-ra", (f"{args.formats.upper()} {args.dpi} dpi"
                    + ("" if args.no_html else messages.text("bảng.kèm-html"))), "formats"),
    ]

    numbered = []
    for number, (name, value, setting) in enumerate(rows, 1):
        row: dict[str, Any] = {"số": number, "mục": wording.field(name),
                               "giá_trị": str(value)}
        if setting and setting not in chosen:
            row["ghi_chú"] = auto
        if setting in wording.ALWAYS_SAFE or setting in among:
            offer = wording.menu(setting, _current(args, setting, scope, method),
                                 among=among.get(setting))
            if offer:
                row.update(câu_hỏi=offer["câu_hỏi"], lựa_chọn=offer["lựa_chọn"])
        numbered.append(row)

    settings = {wording.field(name): str(value) for name, value, _ in rows}
    must_ask = [wording.ask(setting, getattr(args, setting, None))
                for setting in THEIRS_TO_CHOOSE if setting not in chosen]
    return settings, numbered, must_ask


def _current(args, setting: str, scope: str, method: str) -> str | None:
    """What a setting resolved to, which is not always what was typed.

    ``--map-scope auto`` becomes a real framing and ``--aggregate auto`` becomes
    a real method. The menu has to mark the resolved value as the current one,
    or the reader is offered, as an alternative, the thing they already have.
    """
    if setting == "map_scope":
        return scope
    if setting == "aggregate":
        return method
    return getattr(args, setting, None)


def _map_label(args, value_column, ctx) -> str:
    """What the interactive page's map picker shows.

    A province name comes from the shapefile and stays Vietnamese in any
    language; "toàn quốc" is the script's own word, so it gets translated.
    """
    lang = i18n.normalise(args.language)
    where = i18n.t(lang, "scope_national") if ctx["tên"] == "toàn quốc" else ctx["tên"]
    return f"{args.title or value_column or ''} — {where}".strip(" —")


def _animation(deps, args, run_dir, joined, contexts, thematic, provinces_gdf,
               value_column, value_info, symbol_info, name_field, font_info,
               issues) -> dict[str, Any]:
    """The series as video, on one classification shared by every frame.

    Several map frames — one per province, say — each become their own video,
    but the class breaks and the circle scale are computed once across the whole
    set. That is the point: a colour has to mean the same thing in Nghệ An as in
    Hà Nội, and across every period of both, or the series cannot be compared
    with itself.
    """
    if not args.period_column:
        raise SystemExit("Bản đồ video cần --period-column để biết đâu là trục thời gian.")

    frames = period_utils.ordered(joined[args.period_column])
    if len(frames) < 2:
        raise SystemExit(f"Cột '{args.period_column}' chỉ có {len(frames)} kỳ; "
                         "cần ít nhất 2 kỳ để dựng video.")
    unreadable = period_utils.unreadable(joined[args.period_column])
    if unreadable:
        issues.append(guardrails._issue(
            "ky-khong-doc-duoc", guardrails.WARNING, counts=len(unreadable),
            fmt={"count": len(unreadable),
                 "periods": ", ".join(str(u) for u in unreadable[:5])}))

    values_by_period: dict[Any, dict[int, float]] = {}
    symbols_by_period: dict[Any, dict[int, float]] | None = ({} if args.symbol_column else None)
    for period in frames:
        sub = joined[joined[args.period_column].astype(str) == str(period)]
        if sub.empty:
            values_by_period[period] = {}
            if symbols_by_period is not None:
                symbols_by_period[period] = {}
            continue
        values_by_period[period] = aggregate.combine(
            deps, sub, "__shape_id", value_column, value_info, args.aggregate).to_dict()
        if symbols_by_period is not None:
            symbols_by_period[period] = aggregate.combine(
                deps, sub, "__shape_id", args.symbol_column, symbol_info, "auto").to_dict()

    pooled = [v for table in values_by_period.values() for v in table.values()
              if v is not None and not (isinstance(v, float) and v != v)]
    if not pooled:
        raise SystemExit("Không còn giá trị nào sau khi ghép địa danh và tách kỳ.")
    bins = classify.compute_bins(pooled, args.classification, args.classes, value_info,
                                 center_zero=(args.map_type == "change"))
    bins["notes"].append(messages.text("doc.dùng-chung-nhóm-video"))
    issues += guardrails.check_classes(bins, len(pooled))

    symbol_scale: dict[str, float] = {}
    if symbols_by_period is not None:
        symbol_scale = classify.symbol_scale(
            [v for table in symbols_by_period.values() for v in table.values()
             if v is not None and not (isinstance(v, float) and v != v)])

    wanted = args.animation_formats
    shared: dict[str, Any] = {"kỳ": [str(p) for p in frames],
                              "phân_lớp_dùng_chung": bins,
                              "thang_ký_hiệu_dùng_chung": symbol_scale}
    made: list[dict[str, Any]] = []
    for ctx in contexts:
        ids = set(ctx["frame"]["__shape_id"])
        frame = thematic[thematic["__shape_id"].isin(ids)].copy()
        # coverage is counted against this frame, not the whole series: a
        # province's video should not claim units that belong to another one
        with_data = len({sid for table in values_by_period.values()
                         for sid in table} & ids)
        spec = _build_spec(args, ctx, value_column, value_info, symbol_info, bins,
                           symbol_scale, name_field,
                           aggregate.resolve(args.aggregate, value_info),
                           with_data, frame)
        spec["labels"] = "off"
        spec["diverging"] = args.map_type == "change"
        base = (dataio.slugify(f"{args.title or value_column} {ctx['tên']}")
                + f"_{args.layout}_{i18n.suffix(args.language)}")

        common = dict(frame=frame, periods=frames, values_by_period=values_by_period,
                      symbols_by_period=symbols_by_period, spec=spec, fonts=font_info,
                      provinces=provinces_gdf, locator_name=ctx["locator"],
                      out_dir=run_dir, name=base)
        one: dict[str, Any] = {"tên_bản_đồ": ctx["tên"], "đơn_vị_có_số_liệu": with_data}
        if wanted in ("video", "both"):
            one["video"] = animate.build(deps, **common)
        if wanted in ("html", "both"):
            one["html"] = interactive.build(
                deps, label=_map_label(args, value_column, ctx), **common)
        dataio.write_json(run_dir / f"{base}_metadata.json",
                          {**shared, **one, "tham_số": vars(args)})
        made.append(one)

    if len(made) == 1:
        return {**shared, **made[0]}
    return {**shared, "khung": made, "số_khung": len(made)}


def _settle_language(args: argparse.Namespace) -> None:
    """Give ``--language`` a real value, once, at the entrance to drawing.

    The flag carries no argparse default so the gate can tell "the user chose
    Vietnamese" from "nobody asked" — ``chosen_explicitly`` answers that, and
    everything downstream wants an actual language. Filling it in here rather
    than in ``main`` keeps the two facts in one place: whoever reaches a render
    gets the resolved value, whichever way they arrived.
    """
    if getattr(args, "language", None) is None:
        args.language = i18n.DEFAULT


def command_render(args: argparse.Namespace) -> None:
    _settle_language(args)
    if getattr(args, "layer", None):
        return _render_layers(args)
    root = Path(args.project_root).resolve()
    deps = dataio.load(require_geo=True, require_plot=True)
    font_info = fonts.install(deps.matplotlib)

    excel = dataio.project_path(root, args.excel)
    df = dataio.read_table(deps, excel, args.sheet)
    sheets = dataio.read_sheets(deps, excel)
    dictionary = dataio.read_data_dictionary(deps, excel, sheets)

    # Slice before anything else: the match review, the aggregation and every
    # warning should describe the rows actually being drawn, not the whole sheet.
    df, slice_note = _apply_where(df, args.where)

    country = getattr(args, "country", None)
    tier = dataio.resolve_tier(root, args.admin_level, country=country)
    admin_level = tier["vai_trò"]
    boundary_notes: list[dict[str, Any]] = []
    shapes = dataio.load_shapes(deps, root, admin_level, notes=boundary_notes,
                                country=country)
    fields = dataio.shape_fields(shapes, admin_level)
    # Resolved once, from the province tier, and used for every frame on the
    # page: the map and the locator beside it have to agree.
    thematic_crs = dataio.run_thematic_crs(deps, root, country=country)
    name_field = fields["commune"] if admin_level == "commune" else fields["province"]

    # --- match ------------------------------------------------------------
    # a coordinate-only point map needs no name matching at all
    coordinates_only = (args.map_type == "point" and not args.province_column
                        and not args.commune_column)
    review_path = dataio.project_path(root, args.match_review) if args.match_review else None
    if review_path is None and args.run_folder:
        # reuse exactly the table the user reviewed during profiling
        candidate = (root / "output" / args.run_folder
                     / review_filename(admin_level, excel, args.sheet))
        if candidate.exists():
            review_path = candidate

    review: list[dict[str, Any]] = []
    if coordinates_only:
        review = []
    elif review_path and review_path.exists():
        review = dataio.read_csv(review_path)
        if not _review_is_usable(review, admin_level):
            review = []          # belongs to another dataset; recompute below
    if not review and not coordinates_only:
        province_shapes = dataio.load_shapes(deps, root, dataio.COARSE,
                                             country=country)
        p_fields = dataio.shape_fields(province_shapes, dataio.COARSE)
        index = _province_index(province_shapes, p_fields["province"])
        if admin_level == "province":
            review = matching.review_province(
                [{"province": v} for v in df[args.province_column].tolist()], index)
        else:
            by_province = _commune_index_by_province(shapes, fields)
            rows = [{"province": (df[args.province_column].iloc[i]
                                  if args.province_column else None),
                     "commune": df[args.commune_column].iloc[i]} for i in range(len(df))]
            review = matching.review_commune(rows, index, by_province,
                                             prefs.recall_overrides(root, "commune"))
    match_summary = matching.summarize(review)

    # --- attach shape ids -------------------------------------------------
    drop_ambiguous = args.ambiguous == "drop"
    match_summary["ambiguous_dropped"] = drop_ambiguous
    lookup = matching.shape_lookup(review, admin_level, drop_ambiguous=drop_ambiguous)

    def row_key(i: int) -> str:
        if admin_level == "province":
            return str(df[args.province_column].iloc[i]).strip()
        p = str(df[args.province_column].iloc[i]).strip() if args.province_column else ""
        return f"{p}|{str(df[args.commune_column].iloc[i]).strip()}"

    df = df.copy()
    if args.period_column and args.period and not args.animate:
        df = df[df[args.period_column].astype(str) == str(args.period)].reset_index(drop=True)
    if coordinates_only:
        df["__shape_id"] = None
        joined = df.copy()
    else:
        df["__shape_id"] = [lookup.get(row_key(i)) for i in range(len(df))]
        joined = df[df["__shape_id"].notna()].copy()
        joined["__shape_id"] = joined["__shape_id"].astype(int)
        if joined.empty:
            raise SystemExit("Không ghép được dòng nào với bản đồ. Xem lại match_review.csv.")

    # --- semantics + aggregation -----------------------------------------
    columns = profiling.describe_columns(deps, df, dictionary)
    weight_series = {c["column"]: df[c["column"]].tolist() for c in columns
                     if c["semantic"] in {sem.COUNT, sem.PERCENT, sem.RATE_PER, sem.POINT}}
    for info in columns:
        if info["semantic"] in {sem.PERCENT, sem.RATE_PER, sem.POINT}:
            info["cột_trọng_số"] = sem.find_denominator(info["column"], columns,
                                                        weight_series)
    by_name = {c["column"]: c for c in columns}

    value_column = args.value_column or args.category_column
    ratio_note = None
    if args.numerator or args.denominator or args.fill_indicator or args.symbol_indicator:
        value_column, joined, ratio_note = _build_long_columns(args, joined, by_name)
    if args.map_type == "change":
        if not (args.baseline_column and args.comparison_column):
            raise SystemExit("Bản đồ thay đổi cần cả --baseline-column và --comparison-column.")
        value_column = f"Thay đổi: {args.comparison_column} − {args.baseline_column}"
        joined[value_column] = joined[args.comparison_column] - joined[args.baseline_column]
        by_name[value_column] = sem._pack(sem.POINT, value_column, "điểm phần trăm")
    if args.map_type == "graduated-symbol" and not args.symbol_column:
        raise SystemExit("Bản đồ ký hiệu tỷ lệ cần --symbol-column.")
    # a proportional-symbol map needs only the symbol column; area fills need a value
    if not value_column and args.map_type not in ("boundary", "point", "graduated-symbol"):
        raise SystemExit("Cần --value-column (hoặc --category-column) cho loại bản đồ này.")

    # --- coordinates for point maps --------------------------------------
    points = None
    if args.map_type == "point":
        lon_col, lat_col = args.lon_column, args.lat_column
        if not (lon_col and lat_col):
            coords = profiling.coordinate_candidates(columns)
            lon_col = lon_col or coords["kinh_độ"]
            lat_col = lat_col or coords["vĩ_độ"]
        if not (lon_col and lat_col):
            raise SystemExit(
                "Bản đồ điểm cần cột kinh độ và vĩ độ. Chỉ định --lon-column và --lat-column."
            )
        valid = joined[joined[lon_col].notna() & joined[lat_col].notna()]
        if valid.empty:
            raise SystemExit(f"Không có dòng nào có đủ toạ độ trong '{lon_col}' và '{lat_col}'.")
        located = deps.gpd.GeoSeries(
            deps.gpd.points_from_xy(valid[lon_col], valid[lat_col]), crs="EPSG:4326"
        ).to_crs(thematic_crs)
        points = {"x": located.x.tolist(), "y": located.y.tolist(),
                  "bỏ_qua_thiếu_toạ_độ": int(len(joined) - len(valid))}
        _dress_points(points, valid, args, by_name)

    value_info = by_name.get(value_column, {"semantic": sem.UNKNOWN, "column": value_column})
    duplicates = aggregate.duplicate_count(joined, "__shape_id") if not coordinates_only else 0

    issues: list[dict[str, Any]] = list(guardrails.check_matching(match_summary))
    detached = dataio.read_country(
        deps, dataio.shapefile_root(root), tier["quốc_gia"]).get("lãnh_thổ_rời")
    values = None
    method = "n/a"
    if value_column and args.map_type != "boundary" and not coordinates_only:
        method = aggregate.resolve(args.aggregate, value_info)
        issues += guardrails.check_aggregation(value_info, method, duplicates)
        issues += guardrails.check_colour_choice(value_info, args.map_type)
        values = aggregate.combine(deps, joined, "__shape_id", value_column, value_info,
                                   args.aggregate)
        issues += guardrails.check_percent_range(values.tolist(), value_info)
        issues += guardrails.check_diverging(values.tolist(), value_info)

    symbol_info = by_name.get(args.symbol_column, {}) if args.symbol_column else {}
    symbols = None
    if args.symbol_column:
        symbols = aggregate.combine(deps, joined, "__shape_id", args.symbol_column,
                                    symbol_info, "auto")

    # --- what gets drawn --------------------------------------------------
    scope, contexts = _contexts(args, shapes, fields, review, admin_level)
    thematic = dataio.to_thematic_crs(shapes, thematic_crs)
    provinces_gdf = dataio.to_thematic_crs(
        dataio.load_shapes(deps, root, dataio.COARSE, country=country), thematic_crs)

    prepared = []
    for ctx in contexts:
        keep = set(ctx["frame"]["__shape_id"])
        frame = thematic[thematic["__shape_id"].isin(keep)].copy()
        frame["__value"] = frame["__shape_id"].map(values) if values is not None else None
        if symbols is not None:
            frame["__symbol"] = frame["__shape_id"].map(symbols)
        prepared.append({**ctx, "frame": frame})

    # one classification and one symbol scale for the whole job, so the same
    # colour and the same circle size mean the same thing on every sheet
    bins = None
    if values is not None and args.map_type in {"choropleth", "choropleth-symbol", "change"}:
        groups = {c["tên"]: c["frame"]["__value"].dropna().tolist() for c in prepared}
        pooled = [v for vals in groups.values() for v in vals]
        if not pooled:
            raise SystemExit("Sau khi ghép địa danh, không còn giá trị nào để vẽ.")
        center_zero = args.map_type == "change"
        bins = (classify.shared_bins(groups, args.classification, args.classes,
                                     value_info, center_zero)
                if len(prepared) > 1
                else classify.compute_bins(pooled, args.classification, args.classes,
                                           value_info, center_zero))
        issues += guardrails.check_classes(bins, len(pooled))

    symbol_scale: dict[str, float] = {}
    if symbols is not None:
        pooled = [v for c in prepared for v in c["frame"]["__symbol"].dropna().tolist()]
        symbol_scale = classify.symbol_scale(pooled)

    # --- the gate ---------------------------------------------------------
    # Everything above decided what the map will be; nothing above drew it. The
    # plan goes to the person first, and only the code derived from it unlocks
    # the drawing. Placed before the run folder is opened, so a plan that is
    # never agreed leaves nothing behind.
    settings, numbered, must_ask = _plan(args, excel, joined, value_column,
                                         scope, prepared, method, bins)
    # No code unlocks a plan that still has a question open in it. The hash
    # covers the settings, and a defaulted language reads the same in the table
    # as a chosen one — so without this an agent could take the code from its own
    # planning run, never ask, and draw the default it invented. The settings the
    # person owns have to arrive on the command line, and they only can once
    # somebody has been asked.
    if must_ask or not confirm.matches(args.confirmed, settings):
        emit(confirm.gate(settings, numbered,
                          guardrails.summarize(issues)["danh_sách"], must_ask,
                          _command_line(),
                          language_stated="messages" in getattr(
                              args, "chosen_explicitly", set())))
        return

    # --- draw -------------------------------------------------------------
    run_dir = dataio.create_run_dir(root, args.run_folder)

    if args.animate:
        series = _animation(deps, args, run_dir, joined, prepared, thematic, provinces_gdf,
                            value_column, value_info, symbol_info, name_field, font_info,
                            issues)
        emit({"thư_mục_kết_quả": str(run_dir), "theo_thời_gian": series,
              "mở_tệp": dataio.openable(run_dir),
              "cảnh_báo": guardrails.summarize(issues)["danh_sách"]})
        return

    outputs, per_map = [], []
    for ctx in prepared:
        frame = ctx["frame"]
        # Two different questions, and they used to share one answer. Coverage is
        # about the fill: grey area reads as "surveyed and found nothing". What
        # the report calls đơn_vị_có_số_liệu is about the map as a whole, and
        # counting only the fill made a proportional-symbol map drawing fourteen
        # circles report zero — while its own subtitle said 14/126.
        filled = int(frame["__value"].notna().sum()) if values is not None else 0
        with_data = _units_shown(frame, values is not None, symbols is not None)
        issues_ctx = list(issues)
        # coverage only matters when areas are filled by colour
        if args.map_type in {"choropleth", "choropleth-symbol", "change", "categorized"}:
            issues_ctx += guardrails.check_coverage(filled, len(frame))

        spec = _build_spec(args, ctx, value_column, value_info, symbol_info,
                           bins, symbol_scale, name_field, method, with_data, frame,
                           points_count=len(points["x"]) if points else None)
        spec["points"] = points
        result = render.draw(deps, frame=frame, spec=spec, fonts=font_info,
                             provinces=provinces_gdf, locator_name=ctx["locator"])
        if symbol_scale:
            span_y = frame.total_bounds[3] - frame.total_bounds[1]
            radii = render.symbol_radii(frame["__symbol"].dropna().tolist(),
                                        symbol_scale, span_y)
            issues_ctx += guardrails.check_symbol_occlusion(
                max(radii) if radii else 0.0, render.median_feature_width(frame))

        # the language suffix makes a Vietnamese and an English edition of the
        # same map sit side by side in one folder without clashing
        # the layout belongs in the name: without it a second render of the same
        # map in the other layout overwrites the first, silently, while
        # run_manifest still lists both
        family = (dataio.slugify(f"{args.title or value_column or 'ban do'} {ctx['tên']}")
                  + f"_{args.layout}")
        base = f"{family}_{i18n.suffix(args.language)}"
        # the page needs the live axes, so capture before save() closes the figure
        if not args.no_html:
            webpage.stash(run_dir, base, webpage.capture_still(
                result["plate"], frame, spec, family=family,
                label=_map_label(args, value_column, ctx),
                fills=result["fills"],
                point_counts=_points_per_unit(deps, frame, points)))
        written = render.save(result["plate"], run_dir, base, args.formats, dpi=args.dpi)
        outputs.extend(str(p) for p in written)
        table = _drawn_table(run_dir, base, frame, name_field, value_column,
                             value_info, symbol_info, args, bins)
        # Whether an inset was drawn is only known once the map is drawn, and
        # the warning is about the two together: land far from the main body,
        # and nothing done about it.
        if scope == "national":
            issues_ctx = issues_ctx + guardrails.check_detached_territory(
                detached, result.get("khung_phụ") is not None, lang=args.messages)
        meta = {"tên_bản_đồ": ctx["tên"], "tệp": [str(p) for p in written],
                "bảng_số_liệu": table,
                "đơn_vị_có_số_liệu": with_data, "đơn_vị_trong_khung": int(len(frame)),
                "nhãn": result["labels"], "khung_phụ": result.get("khung_phụ"),
                "tràn_khung": result.get("tràn_khung") or [],
                "lãnh_thổ_rời": detached,
                "cảnh_báo": guardrails.summarize(issues_ctx)}
        dataio.write_json(run_dir / f"{base}_metadata.json", {**meta, "tham_số": vars(args)})
        per_map.append(meta)

    if review:
        dataio.write_csv(run_dir / review_filename(admin_level, excel, args.sheet), review)
    prefs.remember_choices(root, excel, args.sheet, {
        "admin_level": admin_level, "map_type": args.map_type, "layout": args.layout,
        "value_column": args.value_column, "symbol_column": args.symbol_column,
        "province_column": args.province_column, "commune_column": args.commune_column,
        "classification": args.classification, "classes": args.classes,
        "labels": args.labels, "map_scope": scope, "language": args.language,
    })

    job = {
        "phạm_vi": scope, "bản_đồ": per_map,
        "ngôn_ngữ": i18n.normalise(args.language), "layout": args.layout,
        "phân_lớp_dùng_chung": bins, "thang_ký_hiệu_dùng_chung": symbol_scale,
        "cách_tổng_hợp": aggregate.describe(args.aggregate, value_info,
                                            value_info.get("cột_trọng_số"),
                                            args.language),
        "ghép_địa_danh": match_summary, "font": font_info, "tham_số": vars(args),
        # what slice of a long sheet this map actually drew; without it a PNG
        # from a 70.000-row export cannot be traced back to its rows
        "lát_dữ_liệu": slice_note, "tỷ_số": ratio_note,
    }
    # one request may render several times (two languages, two layouts); the
    # manifest keeps every job instead of the last one overwriting the rest
    _append_manifest(run_dir, "lần_render", job)

    # rebuilt from every capture in this request folder, so a second render —
    # the English edition, another layout — extends the page instead of
    # replacing what the first one produced
    page = None if args.no_html else webpage.build(run_dir, webpage.STILL)

    emit({"thư_mục_kết_quả": str(run_dir), "tệp_ảnh": outputs, "trang_tương_tác": page,
          # ready-made addresses, so nothing is left for the agent to construct
          "mở_tệp": dataio.openable(run_dir),
          **({"sửa_bảng_mã_ranh_giới": boundary_notes} if boundary_notes else {}),
          "phép_chiếu": thematic_crs,
          "cảnh_báo": guardrails.summarize(issues)["danh_sách"], "bản_đồ": per_map})


def _build_spec(args, ctx, value_column, value_info, symbol_info, bins,
                symbol_scale, name_field, method, with_data, frame,
                points_count: int | None = None) -> dict[str, Any]:
    lang = i18n.normalise(args.language)
    kicker = args.subtitle or i18n.kicker(lang, args.admin_level)
    if ctx["locator"] and ctx["locator"].upper() not in kicker.upper():
        kicker = f"{kicker}  ·  {ctx['locator'].upper()}"

    title = args.title or (value_column or args.symbol_column or "")
    # a proportional-symbol map describes itself through the symbol column
    if value_column:
        insight_col, insight_info = "__value", value_info
    elif args.symbol_column:
        insight_col, insight_info = "__symbol", symbol_info
    else:
        insight_col, insight_info = None, {}
    insight = args.insight or _auto_insight(frame, insight_col, insight_info, name_field,
                                            lang, points_count)
    source = args.source_note or i18n.t(lang, "source", file=Path(args.excel).name)
    fills_areas = args.map_type in {"choropleth", "choropleth-symbol", "change", "categorized"}
    method_note = args.footnote or _auto_method(args, bins, method, fills_areas, lang)
    # the side column also hosts the locator, so keep it whenever one is drawn;
    # otherwise its caption would sit alone in the margin
    wants_locator = bool(ctx["locator"]) and args.locator != "off"

    return {
        "language": lang,
        "side_panel": bool(fills_areas or args.symbol_column or wants_locator),
        "layout": args.layout, "map_type": args.map_type,
        "value_column": "__value" if value_column else None,
        "value_info": value_info,
        "symbol_column": "__symbol" if args.symbol_column else None,
        "symbol_info": symbol_info,
        "bins": bins, "symbol_scale": symbol_scale,
        "name_field": name_field,
        "labels": args.labels, "label_fontsize": args.label_fontsize,
        "legend_title": (args.legend_title
                         or (i18n.t(lang, "change_legend") if args.map_type == "change"
                             else value_column or "")),
        "symbol_legend_title": args.symbol_legend_title or args.symbol_column or "",
        "kicker": kicker, "title": title, "insight": insight,
        "source": source, "method": method_note,
        "locator": args.locator != "off",
        "province_name_field": "ten_tinh",
        "dpi": args.dpi,
    }


def _auto_insight(frame, column, info, name_field, lang: str | None = None,
                  points_count: int | None = None) -> str:
    """One descriptive sentence, taken only from what the map actually shows."""
    total = len(frame)
    if points_count is not None:
        return i18n.t(lang, "insight_points", points=points_count, total=total)
    if not column or column not in frame.columns:
        return i18n.t(lang, "insight_frame", total=total)
    data = frame[frame[column].notna()]
    with_data = len(data)
    if not with_data:
        return i18n.t(lang, "insight_frame", total=total)

    if info.get("semantic") == sem.CATEGORY or data[column].dtype == object:
        counts = data[column].astype(str).value_counts()
        return i18n.t(lang, "insight_category", with_data=with_data, total=total,
                      name=counts.index[0], count=int(counts.iloc[0]))
    try:
        top = data.loc[data[column].idxmax()]
    except (TypeError, ValueError):
        return i18n.t(lang, "insight_plain", with_data=with_data, total=total)
    return i18n.t(lang, "insight_values", with_data=with_data, total=total,
                  name=top[name_field],
                  value=sem.format_value(top[column], info, lang=lang))


def _auto_method(args, bins, method, fills_areas: bool, lang: str | None = None) -> str:
    parts = []
    if bins:
        name = i18n.t(lang, f"class_{args.classification}")
        if name == f"class_{args.classification}":
            name = args.classification
        parts.append(i18n.t(lang, "method_classes", classes=bins["classes"], method=name))
    if args.symbol_column:
        parts.append(i18n.t(lang, "method_symbol"))
    if method not in ("n/a", "sum"):
        label = i18n.t(lang, f"agg_{method}")
        parts.append(i18n.t(lang, "method_aggregate",
                            method=label if label != f"agg_{method}" else method))
    if args.map_type == "point":
        parts.append(i18n.t(lang, "method_points"))
    if fills_areas:
        parts.append(i18n.t(lang, "method_grey"))
    return " ".join(parts)


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="easy-map engine")
    parser.add_argument("--project-root", default=".",
                        help="cũng chấp nhận sau tên lệnh, ví dụ: list --project-root .")
    parser.add_argument("--messages", default=messages.DEFAULT,
                        choices=list(messages.LANGUAGES),
                        help="ngôn ngữ của cảnh báo và lý do trả về cho agent — tức "
                             "ngôn ngữ cuộc trò chuyện. Khác với --language, vốn là "
                             "ngôn ngữ chữ in trên bản đồ")
    sub = parser.add_subparsers(dest="command", required=True)

    sr = sub.add_parser("start-run",
                        help="mở thư mục cho một yêu cầu và in ra tên thư mục")
    sr.add_argument("--run-folder",
                    help="đặt tên thủ công; bỏ trống thì lấy timestamp hiện tại")

    sub.add_parser("list", help="liệt kê workbook, sheet, shapefile")

    im = sub.add_parser("import",
                        help="đưa tệp người dùng đính kèm vào input/ và khảo sát luôn")
    im.add_argument("--file", required=True,
                    help="đường dẫn tới tệp người dùng đính kèm vào cuộc trò chuyện")
    im.add_argument("--run-folder",
                    help="ghi việc nhập tệp vào manifest của yêu cầu này; bỏ trống "
                         "thì dùng thư mục start-run đang mở, nếu có")

    sv = sub.add_parser("survey",
                        help="sheet nào trong workbook vẽ được bản đồ; đọc mẫu nên rất nhanh")
    sv.add_argument("--country", help="thư mục quốc gia trong shapefiles/; bỏ trống "
                                      "khi chỉ có một quốc gia")
    sv.add_argument("--excel",
                    help="bỏ trống thì khảo sát mọi workbook trong input/")

    p = sub.add_parser("profile", help="phân tích dataset và đề xuất bản đồ")
    p.add_argument("--country", help="thư mục quốc gia trong shapefiles/; bỏ trống "
                                     "khi chỉ có một quốc gia")
    p.add_argument("--excel", required=True)
    p.add_argument("--sheet")
    p.add_argument("--admin-level", default="auto",
                   help="vai trò (province/commune) hoặc tên thư mục cấp, ví dụ state")
    p.add_argument("--province-column")
    p.add_argument("--commune-column")
    p.add_argument("--run-folder",
                   help="thư mục của yêu cầu này; bỏ trống thì dùng lại thư mục "
                        "start-run đang mở")

    f = sub.add_parser("fix-match", help="ghi nhớ một cách ghép tên do người dùng xác nhận")
    f.add_argument("--country")
    f.add_argument("--admin-level", default="commune",
                   help="vai trò hoặc tên thư mục cấp")
    f.add_argument("--province")
    f.add_argument("--name", required=True)
    f.add_argument("--shape-id", required=True)

    r = sub.add_parser("render", help="vẽ và lưu bản đồ")
    r.add_argument("--country", help="thư mục quốc gia trong shapefiles/; bỏ trống "
                                     "khi chỉ có một quốc gia")
    r.add_argument("--excel", required=True)
    r.add_argument("--sheet")
    r.add_argument("--admin-level", required=True,
                   help="vai trò (province/commune) hoặc tên thư mục cấp, ví dụ state")
    r.add_argument("--province-column")
    r.add_argument("--commune-column")
    r.add_argument("--match-review")
    r.add_argument("--map-type", default="choropleth",
                   choices=["choropleth", "choropleth-symbol", "graduated-symbol",
                            "categorized", "boundary", "change", "point"])
    r.add_argument("--value-column")
    r.add_argument("--symbol-column")
    r.add_argument("--category-column")
    r.add_argument("--baseline-column")
    r.add_argument("--comparison-column")
    r.add_argument("--period-column")
    r.add_argument("--period")
    r.add_argument("--animate", action="store_true",
                   help="dựng bản đồ theo thời gian thay vì ảnh tĩnh; cần --period-column")
    r.add_argument("--animation-formats", default="both", choices=["video", "html", "both"],
                   help="video MP4/GIF, trang HTML tương tác, hoặc cả hai")
    r.add_argument("--lon-column", help="cột kinh độ cho bản đồ điểm")
    r.add_argument("--lat-column", help="cột vĩ độ cho bản đồ điểm")
    r.add_argument("--point-color-column", metavar="CỘT",
                   help="bản đồ điểm: cột phân loại quyết định màu chấm "
                        "(loại cơ sở, mức ưu tiên)")
    r.add_argument("--point-size-column", metavar="CỘT",
                   help="bản đồ điểm: cột số quyết định cỡ chấm; diện tích tỷ lệ "
                        "với giá trị, cùng thang với chú giải")
    r.add_argument("--aggregate", default="auto", choices=list(aggregate.METHODS))
    r.add_argument("--map-scope", default="auto",
                   choices=["auto", "national", "single-province", "province-series",
                            "matched-only"])
    r.add_argument("--province-series-threshold", type=int, default=PROVINCE_SERIES_THRESHOLD)
    # default None, not "vi": the gate needs to tell "the user chose Vietnamese"
    # apart from "nobody asked", and those are different things to report
    r.add_argument("--language", default=None, choices=list(i18n.LANGUAGES),
                   help="ngôn ngữ của chữ do máy sinh trên bản đồ; cũng là hậu tố tên "
                        "tệp. KHÔNG suy ra từ ngôn ngữ hội thoại — phải hỏi người dùng")
    r.add_argument("--confirmed", metavar="MÃ",
                   help="mã lấy từ lần chạy trước của chính lệnh này, sau khi người "
                        "dùng đã xem bảng phương án và đồng ý. Thiếu nó thì lệnh chỉ "
                        "trả về bảng phương án chứ không vẽ")
    r.add_argument("--layout", default="report", choices=["report", "banner"])
    r.add_argument("--classification", default="quantile", choices=list(classify.METHODS))
    r.add_argument("--classes", type=int, default=5)
    r.add_argument("--labels", default="both", choices=["off", "names", "values", "both"])
    r.add_argument("--label-fontsize", type=float, default=8.0)
    r.add_argument("--formats", default="png", choices=["png", "svg", "both"])
    r.add_argument("--dpi", type=int, default=220)
    r.add_argument("--layer", action="append", metavar="BIẾN",
                   help="biến cần thể hiện; lặp lại được. Skill tự phân kênh "
                        "(màu vùng / vòng tròn) và tách sang tấm thứ hai nếu tràn. "
                        "Bảng rộng: tên cột. Bảng dài (có --indicator-column): giá trị "
                        "chỉ số, hoặc 'TỬ SỐ / MẪU SỐ' để lấy tỷ lệ")
    r.add_argument("--indicator-column", metavar="CỘT",
                   help="bảng dạng dài: cột chứa tên chỉ số. Có nó thì --layer và "
                        "--fill-indicator/--symbol-indicator nhận giá trị chỉ số "
                        "thay vì tên cột")
    r.add_argument("--fill-indicator",
                   help="giá trị chỉ số dùng cho màu vùng, khi màu không phải tỷ số")
    r.add_argument("--fill-where", action="append", metavar="CỘT=GIÁ_TRỊ",
                   help="lát riêng của chỉ số vẽ màu vùng; lặp lại được. Dùng khi hai "
                        "chỉ số trên cùng tấm cần ghăm khác nhau trên cùng một cột")
    r.add_argument("--symbol-where", action="append", metavar="CỘT=GIÁ_TRỊ",
                   help="lát riêng của chỉ số vẽ vòng tròn; lặp lại được")
    r.add_argument("--where", action="append", metavar="CỘT=GIÁ_TRỊ",
                   help="giữ lại các dòng khớp; lặp lại được. Bắt buộc với bảng "
                        "dạng dài để không đếm trùng")
    r.add_argument("--ratio-column",
                   help="tên cũ của --indicator-column, giữ lại cho các lệnh đã viết")
    r.add_argument("--numerator", help="giá trị chỉ số làm tử số")
    r.add_argument("--symbol-indicator",
                   help="chế độ tỷ số: giá trị chỉ số dùng cho vòng tròn, lấy từ "
                        "lát dữ liệu khác với tử/mẫu số")
    r.add_argument("--denominator", help="giá trị chỉ số làm mẫu số")
    r.add_argument("--ambiguous", default="drop", choices=["drop", "keep"],
                   help="dòng có tên trùng nhiều xã: 'drop' để ra ngoài bản đồ (mặc định), "
                        "'keep' vẽ theo ứng viên đầu tiên")
    r.add_argument("--no-html", action="store_true",
                   help="bỏ qua trang HTML tương tác; mặc định mỗi yêu cầu đều có một trang")
    r.add_argument("--locator", default="auto", choices=["auto", "off"])
    r.add_argument("--title")
    r.add_argument("--subtitle")
    r.add_argument("--insight")
    r.add_argument("--legend-title")
    r.add_argument("--symbol-legend-title",
                   help="tiêu đề chú giải vòng tròn; mặc định lấy tên cột")
    r.add_argument("--source-note")
    r.add_argument("--footnote")
    r.add_argument("--run-folder",
                   help="thư mục của yêu cầu này; bỏ trống thì dùng lại thư mục "
                        "start-run đang mở")

    # accept --project-root and --messages either before or after the subcommand
    for child in (sub.choices.values()):
        child.add_argument("--project-root", dest="project_root_sub", default=None)
        child.add_argument("--messages", dest="messages_sub", default=None,
                           choices=list(messages.LANGUAGES))
    return parser


#: Flags whose presence means "the person decided this", as opposed to the skill
#: falling back to a default. argparse throws that distinction away, so it is
#: recovered from the raw argument list before parsing.
def _explicit(argv: list[str]) -> set[str]:
    named = {a.split("=", 1)[0] for a in argv if a.startswith("--")}
    return {flag.lstrip("-").replace("-", "_") for flag in named}


def main(argv: list[str] | None = None) -> None:
    speak_utf8()
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    args.chosen_explicitly = _explicit(raw)
    if getattr(args, "project_root_sub", None):
        args.project_root = args.project_root_sub
    if getattr(args, "messages_sub", None):
        args.messages = args.messages_sub
    # the language of the conversation, which is not the language of the map:
    # an English-speaking officer often needs a Vietnamese map for a Vietnamese
    # audience, so --messages and --language are set independently
    messages.use(args.messages)
    {"start-run": command_start_run, "list": command_list, "import": command_import,
     "survey": command_survey, "profile": command_profile,
     "render": command_render, "fix-match": command_fix_match}[args.command](args)


if __name__ == "__main__":
    main()
