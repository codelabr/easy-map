"""Reading a spreadsheet a person actually made.

The three cases here all came out of one real workbook: a pivot sheet whose
header sits seven rows down, an empty sheet, and numbers typed with Vietnamese
thousands separators. None of them raised an error — the pivot sheet came back
as twenty columns called "Unnamed: 2" and the profile offered a map for it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import tabular


class TestMergedCells(unittest.TestCase):
    """An agency report writes a province once and merges it down.

    Read plainly, the province appears on the first of its rows and the rest
    come back blank — and blank there means "same as above", not "missing". The
    header does the opposite: a group name spans two columns, so the second
    column arrives with no name at all and the tier below it ("Nam", "Nữ") is
    read as a row of data.
    """

    #: the fixture's shape: title block, header on rows 4-5, provinces merged
    #: down over their two quarterly rows
    ROWS = [
        ["BÁO CÁO TỔNG HỢP", None, None, None, None, None],
        [None, None, None, None, None, None],
        ["TT", "Tỉnh/thành phố", "Kỳ báo cáo", "Số ca phát hiện", None, "Tỷ lệ (%)"],
        [None, None, None, "Nam", "Nữ", None],
        [1, "Hà Nội", "Quý I", 128, 94, 91.4],
        [None, None, "Quý II", 141, 88, 92.6],
        [2, "Nghệ An", "Quý I", 76, 52, 84.2],
        [None, None, "Quý II", 81, 49, 85.9],
    ]
    #: (row0, col0, row1, col1), zero-based inclusive — as openpyxl reports them
    RANGES = [(0, 0, 0, 5),                       # the title, spanning the page
              (2, 0, 3, 0), (2, 1, 3, 1), (2, 2, 3, 2), (2, 5, 3, 5),
              (2, 3, 2, 4),                       # the group heading, sideways
              (4, 0, 5, 0), (4, 1, 5, 1),         # Hà Nội over its two rows
              (6, 0, 7, 0), (6, 1, 7, 1)]         # Nghệ An over its two rows

    def filled(self):
        return tabular.fill_merged(self.ROWS, self.RANGES)

    def test_a_province_reaches_every_row_it_covers(self):
        rows = self.filled()
        self.assertEqual([r[1] for r in rows[4:]],
                         ["Hà Nội", "Hà Nội", "Nghệ An", "Nghệ An"])

    def test_the_original_rows_are_left_alone(self):
        self.filled()
        self.assertIsNone(self.ROWS[5][1])

    def test_a_range_reaching_past_the_last_row_does_not_raise(self):
        rows = tabular.fill_merged([["Hà Nội", 1]], [(0, 0, 9, 1)])
        self.assertEqual(rows, [["Hà Nội", "Hà Nội"]])

    def test_the_header_is_taken_from_its_top_tier(self):
        """Filling makes the upper tier repeat, and the header scorer marks
        repeats down — so it picks the lower tier and the group name is lost."""
        rows = self.filled()
        self.assertEqual(tabular.header_top(tabular.header_row(rows), self.RANGES), 2)

    def test_a_header_with_one_tier_stays_where_it_is(self):
        self.assertEqual(tabular.header_top(0, [(0, 0, 0, 3)]), 0)

    def test_the_depth_comes_from_the_merges_not_the_contents(self):
        self.assertEqual(tabular.header_depth(2, self.RANGES), 2)
        self.assertEqual(tabular.header_depth(0, [(0, 0, 0, 5)]), 1)

    def test_grouped_columns_keep_their_parent_name(self):
        names = tabular.join_header(self.filled(), 2, 2)
        self.assertEqual(names, ["TT", "Tỉnh/thành phố", "Kỳ báo cáo",
                                 "Số ca phát hiện - Nam", "Số ca phát hiện - Nữ",
                                 "Tỷ lệ (%)"])

    def test_a_column_named_the_same_on_both_tiers_is_not_doubled(self):
        rows = [["Tỉnh", "Tỉnh"], ["a", "b"]]
        self.assertEqual(tabular.join_header(rows, 0, 1), ["Tỉnh", "Tỉnh"])


class TestWhenToLookForMerges(unittest.TestCase):
    """Re-reading for merges costs about eleven seconds per megabyte, so the
    question of when to bother is worth its own decision."""

    def test_a_group_heading_leaves_a_gap_next_to_a_named_column(self):
        self.assertTrue(tabular.looks_merged(
            ["TT", "Tỉnh", "Kỳ", "Số ca phát hiện", "Unnamed: 4", "Tỷ lệ"],
            ["Hà Nội"] * 6))

    def test_a_pivot_sheet_of_nothing_but_unnamed_columns_is_not_grouped(self):
        """Three side sheets of one export looked like this and cost 220
        seconds between them, finding no merges at all."""
        self.assertFalse(tabular.looks_merged([f"Unnamed: {i}" for i in range(22)],
                                              [None] * 20))
        self.assertFalse(tabular.looks_merged(
            ["Duplicate", "(All)"] + [f"Unnamed: {i}" for i in range(18)],
            [None] * 20))

    def test_gaps_under_filled_cells_look_like_a_merged_column(self):
        self.assertTrue(tabular.looks_merged(
            ["Tỉnh", "Kỳ", "Số ca"],
            ["Hà Nội", None, "Nghệ An", None, "Huế", None]))

    def test_a_tidy_sheet_is_left_alone(self):
        self.assertFalse(tabular.looks_merged(
            ["Tỉnh", "Số ca", "Tỷ lệ"], ["Hà Nội", "Nghệ An", "Huế", "Cần Thơ"]))

    def test_a_column_that_is_merely_incomplete_does_not_trigger_it(self):
        """One missing value is a gap in the data, not a merge."""
        self.assertFalse(tabular.looks_merged(
            ["Tỉnh", "Số ca"], ["Hà Nội", "Nghệ An", "Huế", None, "Cần Thơ"]))


class TestSeveralTablesInOneSheet(unittest.TestCase):
    """Somebody appends a second table under the first rather than opening a
    new sheet. Read plainly that is one table whose lower half carries the
    upper half's column names, and nothing raises."""

    TWO = [
        ["Bảng 1. Số ca theo tỉnh", None],
        ["Tỉnh/thành phố", "Số ca"],
        ["Hà Nội", 451],
        ["Nghệ An", 258],
        [None, None],
        [None, None],
        [None, None],
        ["Bảng 2. Ngân sách theo tỉnh", None],
        ["Tỉnh/thành phố", "Ngân sách"],
        ["Hà Nội", 4_820_000_000],
        ["Nghệ An", 2_150_000_000],
    ]

    def test_two_tables_are_found_with_their_row_ranges(self):
        self.assertEqual(tabular.table_blocks(self.TWO), [(0, 3), (7, 10)])

    def test_a_single_table_stays_single(self):
        rows = [["Tỉnh", "Số ca"], ["Hà Nội", 451], ["Huế", 120]]
        self.assertEqual(tabular.table_blocks(rows), [(0, 2)])

    def test_one_blank_row_is_spacing_not_a_divider(self):
        rows = [["Tỉnh", "Số ca"], ["Hà Nội", 451], [None, None], ["Huế", 120]]
        self.assertEqual(len(tabular.table_blocks(rows)), 1)

    def test_a_title_block_above_the_data_is_not_a_table(self):
        """One column wide and nothing under it — a heading, not a table."""
        rows = [["BÁO CÁO TỔNG HỢP NĂM 2026", None],
                [None, None], [None, None],
                ["Tỉnh", "Số ca"], ["Hà Nội", 451], ["Huế", 120]]
        self.assertEqual(tabular.table_blocks(rows), [(3, 5)])

    def test_an_empty_sheet_holds_no_tables(self):
        self.assertEqual(tabular.table_blocks([[None, None], [None, None]]), [])


class TestHeaderRow(unittest.TestCase):
    def test_a_tidy_sheet_keeps_its_first_row(self):
        rows = [["Tỉnh", "Dân số", "Bao phủ (%)"],
                ["Hà Nội", 102136, 51.3],
                ["Huế", 59973, 86.0]]
        self.assertEqual(tabular.header_row(rows), 0)

    def test_a_pivot_block_is_skipped_to_reach_the_real_header(self):
        """Exactly the shape of the 'Q4 Summary' sheet."""
        rows = [
            ["Duplicate", "(All)", None, None, None],
            ["Result/Target", "(All)", None, None, None],
            ["Fiscal Year", 2026, None, None, None],
            ["Quarter", "Q2", None, None, None],
            [None, None, None, None, None],
            ["SNU1", "TX_CURR", "TX_NEW", "HTS_TST", "PrEP_NEW"],
            ["Ha Noi", 2941, 300, 1200, 80],
            ["Hai Phong", 4845, 410, 1500, 95],
        ]
        self.assertEqual(tabular.header_row(rows), 5)

    def test_a_title_line_above_the_table_is_skipped(self):
        rows = [["BÁO CÁO TỔNG HỢP QUÝ I/2026", None, None],
                [None, None, None],
                ["Tỉnh/thành phố", "Số ca", "Tỷ lệ (%)"],
                ["Hà Nội", 120, 51.3],
                ["Huế", 80, 60.2]]
        self.assertEqual(tabular.header_row(rows), 2)

    def test_an_empty_sheet_does_not_invent_a_header(self):
        self.assertEqual(tabular.header_row([[None] * 5 for _ in range(20)]), 0)

    def test_a_repeated_row_is_not_mistaken_for_names(self):
        """Column names are distinct; a row of the same word is data."""
        rows = [["Result", "Result", "Result", "Result"],
                ["Tỉnh", "Số ca", "Tỷ lệ", "Dân số"],
                ["Hà Nội", 1, 2, 3],
                ["Huế", 4, 5, 6]]
        self.assertEqual(tabular.header_row(rows), 1)

    def test_a_header_with_nothing_under_it_is_not_chosen(self):
        rows = [["Tỉnh", "Số ca"], ["Hà Nội", 12], ["Huế", 9],
                ["Ghi chú", "Nguồn: ..."]]
        self.assertEqual(tabular.header_row(rows), 0)


class TestParseNumber(unittest.TestCase):
    def test_a_real_number_passes_through(self):
        self.assertEqual(tabular.parse_number(1234), 1234.0)
        self.assertEqual(tabular.parse_number(51.3), 51.3)

    def test_vietnamese_thousands_are_read_as_thousands(self):
        self.assertEqual(tabular.parse_number("1.234"), 1234.0)
        self.assertEqual(tabular.parse_number("35.156"), 35156.0)
        self.assertEqual(tabular.parse_number("1.234.567"), 1234567.0)

    def test_english_thousands_are_read_as_thousands(self):
        self.assertEqual(tabular.parse_number("1,234"), 1234.0)
        self.assertEqual(tabular.parse_number("35,156"), 35156.0)

    def test_a_decimal_comma_is_not_a_thousands_separator(self):
        self.assertEqual(tabular.parse_number("12,5"), 12.5)

    def test_a_plain_decimal_point_still_works(self):
        self.assertEqual(tabular.parse_number("51.3"), 51.3)

    def test_the_words_people_type_for_missing_are_not_zero(self):
        for word in ("", "-", "N/A", "n.a.", "không có", "…", "..."):
            self.assertIsNone(tabular.parse_number(word), word)

    def test_text_is_left_alone(self):
        self.assertIsNone(tabular.parse_number("Hà Nội"))
        self.assertIsNone(tabular.parse_number("12 ca"))

    def test_a_trailing_percent_sign_is_dropped(self):
        self.assertEqual(tabular.parse_number("51.3%"), 51.3)


class TestCoerceColumn(unittest.TestCase):
    def test_a_text_column_of_numbers_is_converted_and_reported(self):
        out, note = tabular.coerce_column(["1.234", "2.500", "-", "980"])
        self.assertEqual(out, [1234.0, 2500.0, None, 980.0])
        self.assertEqual(note["số_ô_đã_đổi"], 3)
        self.assertEqual(note["số_ô_không_đọc_được"], 0)

    def test_a_genuine_text_column_is_left_alone(self):
        self.assertIsNone(tabular.coerce_column(["Hà Nội", "Huế", "1.234"]))

    def test_the_cells_it_could_not_read_are_named(self):
        result = tabular.coerce_column(["1.234"] * 19 + ["khoảng 500"])
        self.assertIsNotNone(result)
        _, note = result
        self.assertEqual(note["số_ô_không_đọc_được"], 1)
        self.assertEqual(note["ví_dụ_không_đọc_được"], ["khoảng 500"])

    def test_an_empty_column_converts_nothing(self):
        self.assertIsNone(tabular.coerce_column([None, "", "-"]))


class TestUsability(unittest.TestCase):
    def test_a_workable_sheet_says_nothing(self):
        self.assertIsNone(tabular.usability(
            ["Tỉnh", "Dân số"], row_count=34, place_column="Tỉnh"))

    def test_mostly_unnamed_columns_are_called_out_as_a_pivot(self):
        columns = ["Duplicate", "(All)"] + [f"Unnamed: {i}" for i in range(2, 20)]
        found = tabular.usability(columns, row_count=97, place_column=None)
        self.assertIsNotNone(found)
        self.assertIn("không có tên", found["lý_do"])
        self.assertIn("pivot", found["nên_làm"])

    def test_a_sheet_with_no_rows_is_refused(self):
        found = tabular.usability(["A", "B"], row_count=0, place_column="A")
        self.assertIn("không có dòng dữ liệu", found["lý_do"])

    def test_a_clean_sheet_with_no_place_column_is_refused_for_that_reason(self):
        found = tabular.usability(["Ngày", "Số ca"], row_count=50, place_column=None)
        self.assertIn("tên tỉnh", found["lý_do"])
        self.assertIn("--province-column", found["nên_làm"])



class TestPlaceColumns(unittest.TestCase):
    """Finding the place column from a sample, before reading the whole sheet."""

    PROVINCES = {"ha noi", "hai phong", "thai nguyen", "tay ninh"}
    COMMUNES = {"cam giang", "an duong", "vinh bao", "ha noi"}

    def test_a_province_column_is_recognised_by_its_values(self):
        rows = [["Ha Noi", 12], ["Hai Phong", 9], ["Thai Nguyen", 4]]
        found = tabular.place_columns(["SNU1", "Value"], rows,
                                      self.PROVINCES, self.COMMUNES)
        self.assertEqual(found["tỉnh"], "SNU1")
        self.assertIsNone(found["xã"])

    def test_a_name_that_is_both_does_not_make_a_commune_column(self):
        """'Hà Nội' is in both lists; that alone must not imply commune data."""
        rows = [["Ha Noi", 1], ["Hai Phong", 2]]
        found = tabular.place_columns(["Tỉnh", "Value"], rows,
                                      self.PROVINCES, self.COMMUNES)
        self.assertIsNone(found["xã"])

    def test_a_commune_column_is_found_beside_a_province_column(self):
        rows = [["Hai Phong", "Cam Giang"], ["Hai Phong", "An Duong"],
                ["Hai Phong", "Vinh Bao"]]
        found = tabular.place_columns(["SNU1", "SNU2"], rows,
                                      self.PROVINCES, self.COMMUNES)
        self.assertEqual(found["tỉnh"], "SNU1")
        self.assertEqual(found["xã"], "SNU2")

    def test_a_column_of_something_else_is_not_a_place(self):
        rows = [["TX_CURR", 1], ["HTS_TST", 2], ["TX_NEW", 3]]
        found = tabular.place_columns(["Indicator", "Value"], rows,
                                      self.PROVINCES, self.COMMUNES)
        self.assertIsNone(found["tỉnh"])
        self.assertIsNone(found["xã"])

    def test_one_place_repeated_is_one_piece_of_evidence(self):
        """Counting cells would let a single name outvote three wrong ones."""
        rows = [["Ha Noi", 1]] * 50 + [["Khong Phai", 2], ["Cung Khong", 3]]
        found = tabular.place_columns(["A", "Value"], rows,
                                      self.PROVINCES, self.COMMUNES)
        self.assertIsNone(found["tỉnh"])

    def test_blank_cells_are_not_counted_against_a_column(self):
        rows = [["Ha Noi", 1], [None, 2], ["", 3], ["Hai Phong", 4]]
        found = tabular.place_columns(["A", "Value"], rows,
                                      self.PROVINCES, self.COMMUNES)
        self.assertEqual(found["tỉnh"], "A")

if __name__ == "__main__":
    unittest.main()


class TestTheCommuneBarIsOneNumber(unittest.TestCase):
    """Survey and profile must not disagree about the same sheet.

    They did: the survey called a PEPFAR export commune-level because its
    district column cleared a 0.6 bar, while the admin-level detector — using
    its own 0.85 — correctly called it province-level.
    """

    def test_the_detector_reads_the_threshold_from_here(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "emap_cli",
            Path(__file__).resolve().parent.parent
            / "skills/easy-map/scripts/easy_map.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        self.assertIs(cli.COMMUNE_NAME_COVERAGE, tabular.COMMUNE_SHARE)

    def test_a_district_column_does_not_clear_the_commune_bar(self):
        """Two thirds of districts share a commune name; that is not enough."""
        communes = {f"xa {i}" for i in range(10)} | {"binh chanh", "cu chi"}
        rows = [["Binh Chanh"], ["Cu Chi"], ["District 5"], ["District 10"]]
        found = tabular.place_columns(["SNU2"], rows, set(), communes)
        self.assertIsNone(found["xã"])

    def test_a_real_commune_column_still_clears_it(self):
        communes = {"cam giang", "an duong", "vinh bao", "tan hoa"}
        rows = [["Cam Giang"], ["An Duong"], ["Vinh Bao"], ["Tan Hoa"]]
        found = tabular.place_columns(["Xã/phường"], rows, set(), communes)
        self.assertEqual(found["xã"], "Xã/phường")


class TestASheetHoldingTwoTables(unittest.TestCase):
    """The warning has to travel with the sheet the person chose.

    ``survey`` has always reported a sheet with two tables in it. ``profile``
    did not, so naming the sheet you wanted lost the warning — and read straight
    through, the second table's heading row becomes a data row. On the fixture
    written for this, the literal string "Tỉnh/thành phố" was fuzzy-matched onto
    Thanh Hóa at 88.9%.
    """

    def setUp(self):
        self.cli = context.cli()
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def workbook(self, sheets):
        from openpyxl import Workbook

        wb = Workbook()
        wb.remove(wb.active)
        for title, rows in sheets.items():
            ws = wb.create_sheet(title)
            for row in rows:
                ws.append(row)
        path = self.folder / "two-tables.xlsx"
        wb.save(path)
        return path

    TWO = [["Bảng 1"], ["Tỉnh", "Số ca"], ["Hà Nội", 10], ["Huế", 20],
           [], [], ["Bảng 2"], ["Tỉnh", "Chỉ tiêu"], ["Hà Nội", 99]]
    ONE = [["Tỉnh", "Số ca"], ["Hà Nội", 10], ["Huế", 20]]

    def test_the_second_table_is_reported(self):
        path = self.workbook({"S": self.TWO})
        found = self.cli._tables_in_sheet(path, "S")
        self.assertEqual(found["số_bảng_trong_sheet"], 2)
        self.assertEqual(len(found["vị_trí_các_bảng"]), 2)

    def test_one_table_says_nothing(self):
        path = self.workbook({"S": self.ONE})
        self.assertEqual(self.cli._tables_in_sheet(path, "S"), {})

    def test_it_looks_at_the_sheet_it_was_given(self):
        """Two sheets, one tidy and one not; the answer must follow the name."""
        path = self.workbook({"gọn": self.ONE, "lộn xộn": self.TWO})
        self.assertEqual(self.cli._tables_in_sheet(path, "gọn"), {})
        self.assertEqual(
            self.cli._tables_in_sheet(path, "lộn xộn")["số_bảng_trong_sheet"], 2)

    def test_a_delimited_file_has_no_second_table_to_find(self):
        csv = self.folder / "flat.csv"
        csv.write_text("Tỉnh,Số ca\nHà Nội,10\n", encoding="utf-8")
        self.assertEqual(self.cli._tables_in_sheet(csv, None), {})

    def test_an_unreadable_workbook_does_not_stop_the_profile(self):
        """A file the reader cannot open is reported by the reader, not here."""
        broken = self.folder / "broken.xlsx"
        broken.write_bytes(b"not a workbook")
        self.assertEqual(self.cli._tables_in_sheet(broken, "S"), {})

    def test_the_profile_itself_carries_the_warning(self):
        """The one that matters.

        Everything above tests the helper. The defect was never in a helper —
        it was that ``profile`` did not call one, while ``survey`` did. A test
        that only exercises ``_tables_in_sheet`` would stay green through
        exactly that regression, which is how the gap lasted this long.
        """
        try:
            import geopandas  # noqa: F401
        except ImportError:                    # pragma: no cover - env-dependent
            self.skipTest("geopandas is needed to run a profile")
        repo = Path(__file__).resolve().parents[1]
        if not sorted((repo / "shapefiles" / "viet-nam" / "province").glob("*.shp")):
            self.skipTest("the province shapefile is not present")

        import contextlib
        import io as _io
        import json
        import shutil

        path = self.workbook({"S": self.TWO})
        folder = "khong-bao-gio-duoc-giu"
        argv = ["profile", "--project-root", str(repo), "--country", "viet-nam",
                "--run-folder", folder, "--excel", str(path), "--sheet", "S"]
        args = self.cli.build_parser().parse_args(argv)
        out = _io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.cli.command_profile(args)
            report = json.loads(out.getvalue())
        finally:
            shutil.rmtree(repo / "output" / folder, ignore_errors=True)

        self.assertIn("nhiều_bảng_trong_sheet", report)
        self.assertEqual(report["nhiều_bảng_trong_sheet"]["số_bảng_trong_sheet"], 2)
        self.assertTrue(any(n.get("việc") == "nhiều_bảng"
                            for n in report.get("cách_đọc_sheet", [])))


if __name__ == "__main__":
    unittest.main()
