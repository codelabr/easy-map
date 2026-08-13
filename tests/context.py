"""Put the skill's engine on sys.path so tests can import ``emap``.

Tests live outside the skill because they are development-only; the skill folder
holds just what a run needs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "skills" / "easy-map" / "scripts"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))


def cli():
    """The command-line module itself, loaded by path.

    It is a script rather than a package member, so it cannot simply be
    imported by name; several tests need what lives in it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("emap_cli", ENGINE / "easy_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
