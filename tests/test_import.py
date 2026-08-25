"""Getting the user's file into the project, and reading it once it is there.

Most people never put a workbook in a folder — they attach it to the chat, or
paste a block of rows. Until now the skill assumed the file was already sitting
in ``input/``, so the very first step of a real request had no code behind it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import dataio


class TestAdoptFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.outside = self.root / "elsewhere"
        self.outside.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def attach(self, name: str, body: str = "a,b\n1,2\n") -> Path:
        path = self.outside / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_the_file_lands_in_input(self):
        result = dataio.adopt_file(self.root, self.attach("so-lieu.csv"))
        self.assertEqual(result["files"], "input/so-lieu.csv")
        self.assertEqual(result["status"], "copied")
        self.assertTrue((self.root / "input" / "so-lieu.csv").exists())

    def test_the_same_file_twice_is_not_copied_twice(self):
        """Re-attaching after a failed run must not leave two identical copies
        for the user to choose between."""
        dataio.adopt_file(self.root, self.attach("so-lieu.csv"))
        again = dataio.adopt_file(self.root, self.attach("so-lieu.csv"))
        self.assertEqual(again["status"], "already_present")
        self.assertEqual(len(list((self.root / "input").iterdir())), 1)

    def test_same_name_but_different_content_keeps_both(self):
        """The older file may be what an earlier map in this conversation used."""
        dataio.adopt_file(self.root, self.attach("so-lieu.csv"))
        changed = dataio.adopt_file(self.root, self.attach("so-lieu.csv", "a,b\n9,9\n"))
        self.assertEqual(changed["files"], "input/so-lieu_02.csv")
        self.assertEqual(len(list((self.root / "input").iterdir())), 2)

    def test_an_unsupported_format_names_what_is_accepted(self):
        with self.assertRaises(SystemExit) as caught:
            dataio.adopt_file(self.root, self.attach("bao-cao.pdf"))
        message = str(caught.exception)
        self.assertIn(".xlsx", message)
        self.assertIn(".csv", message)

    def test_a_missing_file_says_so_rather_than_failing_later(self):
        with self.assertRaises(SystemExit):
            dataio.adopt_file(self.root, self.outside / "khong-ton-tai.xlsx")

    def test_a_name_the_filesystem_refuses_is_cleaned_not_rejected(self):
        self.assertEqual(dataio.safe_name('so:lieu*2026?.csv'), "so_lieu_2026_.csv")
        self.assertEqual(dataio.safe_name("   "), "data")

    def test_vietnamese_names_and_spaces_survive(self):
        """The user has to recognise their own file in the list afterwards."""
        self.assertEqual(dataio.safe_name("Số liệu HIV 2026.xlsx"),
                         "Số liệu HIV 2026.xlsx")


class TestReadingPastedTables(unittest.TestCase):
    """A pasted block of rows, written to a file and read back.

    It arrives however the source wrote it — tabs from a spreadsheet,
    semicolons from a Vietnamese-locale export. Guessing the delimiter wrong
    does not raise: it produces one column holding the whole line, which then
    looks like a sheet with no place-name column.
    """

    def setUp(self):
        import pandas  # noqa: F401  - the reader needs it

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.deps = dataio.load(require_geo=False)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, body: str, name: str = "dan.csv", encoding: str = "utf-8") -> Path:
        path = self.root / name
        path.write_text(body, encoding=encoding)
        return path

    def test_a_tab_separated_paste_keeps_its_columns(self):
        path = self.write("Tỉnh\tSố ca\nHà Nội\t12\nHuế\t7\n")
        df = dataio.read_table(self.deps, path, None)
        self.assertEqual(list(df.columns), ["Tỉnh", "Số ca"])
        self.assertEqual(len(df), 2)

    def test_a_semicolon_export_keeps_its_columns(self):
        path = self.write("Tỉnh;Số ca\nHà Nội;12\nHuế;7\n")
        self.assertEqual(list(dataio.read_table(self.deps, path, None).columns),
                         ["Tỉnh", "Số ca"])

    def test_numbers_written_the_vietnamese_way_become_numbers(self):
        """dtype=str yields the 'str' dtype on current pandas, not 'object'.
        A `!= object` guard skipped every column, and a table of numbers was
        profiled as a table of categories."""
        path = self.write("Tỉnh\tSố ca\tTỷ lệ\nHà Nội\t1.284\t91,4\nHuế\t312\t93,7\n")
        df = dataio.read_table(self.deps, path, None)
        self.assertEqual(df["Số ca"].tolist(), [1284.0, 312.0])
        self.assertEqual(df["Tỷ lệ"].tolist(), [91.4, 93.7])

    def test_the_place_column_stays_text(self):
        path = self.write("Tỉnh\tSố ca\nHà Nội\t12\nHuế\t7\n")
        self.assertEqual(dataio.read_table(self.deps, path, None)["Tỉnh"].tolist(),
                         ["Hà Nội", "Huế"])

    def test_a_utf8_bom_does_not_corrupt_place_names(self):
        """Windows tools write the BOM; a mangled 'Hà Nội' matches no shape."""
        path = self.write("Tỉnh\tSố ca\nHà Nội\t12\n", encoding="utf-8-sig")
        self.assertEqual(dataio.read_table(self.deps, path, None)["Tỉnh"].tolist(),
                         ["Hà Nội"])

    def test_how_the_file_was_read_is_reported_not_assumed(self):
        notes: list = []
        dataio.read_table(self.deps, self.write("a;b\n1;2\n"), None, notes=notes)
        detail = " ".join(n.get("detail", "") for n in notes)
        self.assertIn("';'", detail)

    def test_a_csv_reports_one_sheet_so_the_survey_can_describe_it(self):
        self.assertEqual(dataio.read_sheets(self.deps, self.write("a,b\n1,2\n")),
                         [dataio.SINGLE_SHEET])

    def test_csv_files_in_input_are_offered_alongside_workbooks(self):
        (self.root / "input").mkdir()
        for name in ("a.csv", "b.xlsx", "c.txt", "notes.md"):
            (self.root / "input" / name).write_text("x", encoding="utf-8")
        found = {p.name for p in dataio.find_excel_files(self.root)}
        self.assertEqual(found, {"a.csv", "b.xlsx", "c.txt"})


if __name__ == "__main__":
    unittest.main()
