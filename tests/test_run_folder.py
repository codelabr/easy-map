"""One request, one folder.

The contract used to rest entirely on the agent remembering `--run-folder`.
It forgot, and five folders holding nothing but a profile and a match review
piled up in `output/`. So the rule now lives in the code: `start-run` is the
only command that opens a folder, and a command that names nothing joins the
run already open — until that run has been quiet long enough that a nameless
command is more likely to belong to a new request.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import context  # noqa: F401  (path bootstrap)
from emap import dataio, prefs


def age(folder: Path, hours: float) -> None:
    """Backdate every write in a folder, the way a long pause would."""
    when = time.time() - hours * 3600
    for child in list(folder.iterdir()) + [folder]:
        os.utime(child, (when, when))


class TestRunFolder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # --- the defect that started this -----------------------------------

    def test_a_command_that_forgets_the_flag_joins_the_open_run(self):
        opened = dataio.create_run_dir(self.root, fresh=True)
        forgot = dataio.create_run_dir(self.root)          # no --run-folder
        self.assertEqual(forgot, opened)
        self.assertEqual(len(list((self.root / "output").iterdir())), 1)

    def test_five_forgetful_commands_still_leave_one_folder(self):
        opened = dataio.create_run_dir(self.root, fresh=True)
        for _ in range(5):
            dataio.create_run_dir(self.root)
        self.assertEqual([p.name for p in (self.root / "output").iterdir()],
                         [opened.name])

    # --- and the guard against the opposite mistake ----------------------

    def test_start_run_always_opens_a_new_folder(self):
        first = dataio.create_run_dir(self.root, fresh=True)
        (first / "dataset_profile.json").write_text("{}", encoding="utf-8")
        second = dataio.create_run_dir(self.root, "2026-08-05_09-00-00", fresh=True)
        self.assertNotEqual(first, second)

    def test_a_quiet_run_stops_collecting_new_work(self):
        """Otherwise tomorrow's request lands in yesterday's folder."""
        stale = dataio.create_run_dir(self.root, fresh=True)
        (stale / "dataset_profile.json").write_text("{}", encoding="utf-8")
        age(stale, dataio.OPEN_RUN_HOURS + 0.5)
        self.assertIsNone(dataio.open_run(self.root))
        self.assertNotEqual(dataio.create_run_dir(self.root), stale)

    def test_a_run_worked_on_recently_is_still_open(self):
        fresh = dataio.create_run_dir(self.root, fresh=True)
        (fresh / "map.png").write_text("x", encoding="utf-8")
        age(fresh, dataio.OPEN_RUN_HOURS - 0.5)
        self.assertEqual(dataio.open_run(self.root), fresh.name)

    def test_work_inside_the_folder_keeps_it_open(self):
        """The pointer's own age is not the measure — the work is."""
        run = dataio.create_run_dir(self.root, fresh=True)
        age(run, dataio.OPEN_RUN_HOURS + 1)
        self.assertIsNone(dataio.open_run(self.root))
        (run / "map.png").write_text("x", encoding="utf-8")   # a render lands
        self.assertEqual(dataio.open_run(self.root), run.name)

    # --- naming a folder explicitly still wins ---------------------------

    def test_a_named_folder_is_reused_not_duplicated(self):
        first = dataio.create_run_dir(self.root, "2026-08-05_10-00-00")
        second = dataio.create_run_dir(self.root, "2026-08-05_10-00-00")
        self.assertEqual(first, second)

    def test_naming_a_folder_reopens_it_for_later_commands(self):
        dataio.create_run_dir(self.root, fresh=True)
        named = dataio.create_run_dir(self.root, "2026-08-05_10-00-00")
        self.assertEqual(dataio.create_run_dir(self.root), named)

    # --- nothing here may take a run down --------------------------------

    def test_a_pointer_to_a_deleted_folder_is_ignored(self):
        run = dataio.create_run_dir(self.root, fresh=True)
        run.rmdir()
        self.assertIsNone(dataio.open_run(self.root))
        self.assertTrue(dataio.create_run_dir(self.root).is_dir())

    def test_a_damaged_pointer_is_ignored(self):
        dataio.create_run_dir(self.root, fresh=True)
        (self.root / prefs.FOLDER / dataio.OPEN_RUN).write_text("{not json",
                                                                encoding="utf-8")
        self.assertIsNone(dataio.open_run(self.root))
        self.assertTrue(dataio.create_run_dir(self.root).is_dir())

    def test_two_auto_named_runs_in_the_same_second_do_not_collide(self):
        name = dataio.new_run_name()
        first = dataio.create_run_dir(self.root, fresh=True)
        (self.root / "output" / name).rename(self.root / "output" / f"{name}_keep")
        (self.root / "output" / name).mkdir()
        second = dataio.create_run_dir(self.root, fresh=True)
        self.assertNotEqual(first.name, second.name)

    def test_the_pointer_records_which_folder_is_open(self):
        run = dataio.create_run_dir(self.root, fresh=True)
        stored = json.loads((self.root / prefs.FOLDER / dataio.OPEN_RUN)
                            .read_text(encoding="utf-8"))
        self.assertEqual(stored["run_folder"], run.name)
        self.assertLess(
            abs(datetime.fromisoformat(stored["mở_lúc"]) - datetime.now()),
            timedelta(minutes=5))


class TestHandingOverSomethingToOpen(unittest.TestCase):
    """The agent must never have to build a file address itself.

    It has always been handed real Windows paths and left to make a link out of
    one. A real Codex run produced
    ``file:///C:/mnt/d/temp/...``: the wrong drive, plus a mount point that does
    not exist on the machine holding the file. It had guessed at a Linux sandbox
    it was not running in, and the link opened nothing.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, *names: str) -> None:
        for name in names:
            (self.folder / name).write_text("x", encoding="utf-8")

    def test_the_link_points_back_at_the_very_same_file(self):
        """The only check that cannot be fooled by a plausible-looking string."""
        from urllib.parse import unquote, urlparse
        from urllib.request import url2pathname

        target = self.folder / "bản đồ tỉnh.png"
        target.write_text("x", encoding="utf-8")
        uri = dataio.link(target)
        self.assertTrue(uri.startswith("file:///"), uri)
        back = Path(url2pathname(unquote(urlparse(uri).path)))
        self.assertTrue(back.exists(), uri)
        self.assertEqual(back.resolve(), target.resolve())

    def test_a_space_or_a_diacritic_is_escaped_rather_than_left_raw(self):
        uri = dataio.link(self.folder / "bản đồ tỉnh.png")
        self.assertNotIn(" ", uri)
        self.assertRegex(uri, r"^file:///[!-~]+$")     # printable ASCII only

    def test_only_what_a_person_opens_is_listed(self):
        self.make("a.png", "a_metadata.json", "run_manifest.json",
                  "a_so-lieu.csv", "trang.html", "phim.mp4")
        found = [f["tên"] for f in dataio.openable(self.folder)]
        self.assertEqual(found, ["a.png", "a_so-lieu.csv", "phim.mp4", "trang.html"])

    def test_every_entry_carries_a_name_a_path_and_a_link(self):
        self.make("a.png")
        entry = dataio.openable(self.folder)[0]
        self.assertEqual(set(entry), {"tên", "đường_dẫn", "liên_kết"})
        self.assertEqual(entry["tên"], "a.png")
        self.assertTrue(entry["liên_kết"].endswith("/a.png"))

    def test_a_folder_that_is_not_there_is_an_empty_list_not_a_crash(self):
        self.assertEqual(dataio.openable(self.folder / "chua-co"), [])

    def test_a_folder_of_only_side_cars_hands_over_nothing(self):
        self.make("run_manifest.json", "a_metadata.json")
        self.assertEqual(dataio.openable(self.folder), [])


if __name__ == "__main__":
    unittest.main()


class TestWhereTheBoundariesLive(unittest.TestCase):
    """The boundaries are one shared set; the project root is one job's folder.

    Tying them together is what stopped the skill working outside a clone of
    the repository, so the two are resolved separately now.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = Path(self.tmp) / "work"
        (self.project / "shapefiles" / "provinces").mkdir(parents=True)
        self._shapefile(self.project / "shapefiles" / "provinces" / "inside.shp")
        self.shared = Path(self.tmp) / "boundaries"
        (self.shared / "provinces").mkdir(parents=True)
        self._shapefile(self.shared / "provinces" / "outside.shp")
        os.environ.pop(dataio.SHAPEFILE_ENV, None)
        self.addCleanup(os.environ.pop, dataio.SHAPEFILE_ENV, None)

    @staticmethod
    def _shapefile(path: Path):
        """A shapefile is four files, not one.

        These tests are about *where* the search looks, so the contents are
        irrelevant — but the companions have to exist, because a lone ``.shp``
        is now refused by name instead of being handed on to a reader whose own
        message explains nothing.
        """
        path.write_text("x")
        for companion in (".shx", ".dbf"):
            path.with_suffix(companion).write_text("x")

    def test_without_a_setting_it_looks_inside_the_project(self):
        found = dataio.find_boundaries(self.project, "province")
        self.assertEqual(found.name, "inside.shp")

    def test_the_environment_variable_moves_the_search(self):
        os.environ[dataio.SHAPEFILE_ENV] = str(self.shared)
        found = dataio.find_boundaries(self.project, "province")
        self.assertEqual(found.name, "outside.shp")

    def test_an_explicit_override_beats_the_environment(self):
        os.environ[dataio.SHAPEFILE_ENV] = str(Path(self.tmp) / "nowhere")
        found = dataio.find_boundaries(self.project, "province", override=str(self.shared))
        self.assertEqual(found.name, "outside.shp")

    def test_a_missing_shared_folder_is_reported_by_its_own_path(self):
        missing = Path(self.tmp) / "gone"
        os.environ[dataio.SHAPEFILE_ENV] = str(missing)
        with self.assertRaises(SystemExit) as raised:
            dataio.find_boundaries(self.project, "province")
        self.assertIn(str(missing), str(raised.exception))

    def test_a_lone_shp_is_refused_by_name(self):
        """Without .shx there is no geometry and without .dbf no attributes.
        The reader's own error for this names neither file."""
        for companion in (".shx", ".dbf"):
            (self.shared / "provinces" / "outside").with_suffix(companion).unlink()
        os.environ[dataio.SHAPEFILE_ENV] = str(self.shared)
        with self.assertRaises(SystemExit) as raised:
            dataio.find_boundaries(self.project, "province")
        self.assertIn(".shx", str(raised.exception))
        self.assertIn(".dbf", str(raised.exception))

    def test_two_datasets_in_one_folder_is_refused_rather_than_sorted(self):
        """Picking the alphabetically first of two would draw a map from a file
        nobody chose, and nothing downstream would look wrong."""
        (self.shared / "provinces" / "another.geojson").write_text("{}")
        os.environ[dataio.SHAPEFILE_ENV] = str(self.shared)
        with self.assertRaises(SystemExit) as raised:
            dataio.find_boundaries(self.project, "province")
        self.assertIn("another.geojson", str(raised.exception))
        self.assertIn("outside.shp", str(raised.exception))

    def test_the_same_data_offered_in_two_formats_is_not_a_conflict(self):
        """``outside.shp`` beside ``outside.geojson`` is one dataset written
        twice, which is a reasonable thing for a folder to hold. The shapefile
        wins because it is the one that keeps its column types."""
        (self.shared / "provinces" / "outside.geojson").write_text("{}")
        os.environ[dataio.SHAPEFILE_ENV] = str(self.shared)
        self.assertEqual(dataio.find_boundaries(self.project, "province").name,
                         "outside.shp")
