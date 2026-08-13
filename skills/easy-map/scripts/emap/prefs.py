"""Remember what the user already approved.

Stored beside the project so a second run of a similar workbook does not ask the
same questions again, and so hand-corrected name matches survive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FOLDER = ".easy-map"
CHOICES = "choices.json"
OVERRIDES = "name-overrides.json"


def _path(project_root: Path, name: str) -> Path:
    return Path(project_root) / FOLDER / name


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dataset_key(excel: str | Path, sheet: str | None) -> str:
    return f"{Path(excel).name}::{sheet or ''}"


def remember_choices(project_root: Path, excel: str | Path, sheet: str | None,
                     choices: dict[str, Any]) -> Path:
    path = _path(project_root, CHOICES)
    store = _load(path)
    key = dataset_key(excel, sheet)
    entry = store.get(key, {})
    entry.update({k: v for k, v in choices.items() if v is not None})
    store[key] = entry
    _save(path, store)
    return path


def recall_choices(project_root: Path, excel: str | Path, sheet: str | None) -> dict[str, Any]:
    return _load(_path(project_root, CHOICES)).get(dataset_key(excel, sheet), {})


def remember_override(project_root: Path, admin_level: str, province: str | None,
                      raw_name: str, shape_id: int, shape_name: str) -> Path:
    path = _path(project_root, OVERRIDES)
    store = _load(path)
    bucket = store.setdefault(admin_level, {})
    bucket[_override_key(province, raw_name)] = {"shape_id": int(shape_id),
                                                 "matched_name": shape_name}
    _save(path, store)
    return path


def recall_overrides(project_root: Path, admin_level: str) -> dict[str, dict[str, Any]]:
    return _load(_path(project_root, OVERRIDES)).get(admin_level, {})


def _override_key(province: str | None, raw_name: str) -> str:
    return f"{(province or '').strip().lower()}|{str(raw_name).strip().lower()}"


def override_for(overrides: dict[str, dict[str, Any]], province: str | None,
                 raw_name: str) -> dict[str, Any] | None:
    return overrides.get(_override_key(province, raw_name))
