"""The packaged typography.

The house style pairs a Merriweather derivative (headlines) with Open Sans (everything
else). Both are
bundled in ``assets/fonts`` so output is identical on any machine, including
sandboxes with no system fonts.

The old renderer silently fell back to Arial when Open Sans was missing, which
is how plates shipped in the wrong typeface. Falling back silently is
now an error: either the packaged fonts load, or the run stops.
"""

from __future__ import annotations

from pathlib import Path

from . import messages as msg

BODY = "Open Sans"
DISPLAY = "EasyMap Serif"

REQUIRED = {
    BODY: ["OpenSans-Regular.ttf", "OpenSans-SemiBold.ttf", "OpenSans-Bold.ttf"],
    DISPLAY: ["EasyMapSerif-Regular.ttf", "EasyMapSerif-Bold.ttf"],
}



def font_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "fonts"


def missing_files() -> list[str]:
    folder = font_dir()
    return [n for names in REQUIRED.values() for n in names if not (folder / n).exists()]


#: Characters every font is allowed not to have, because nothing draws them:
#: the space family, and the control codes.
_IGNORE = set(range(0x00, 0x21)) | {0xA0, 0x200B, 0x2060, 0xFEFF}


def _coverage() -> set[int]:
    """Every code point *all* the packaged fonts can draw.

    The intersection, not the union: a headline in a character only the body
    font has is still a box on the plate, because the headline is set in the
    display face.
    """
    from fontTools.ttLib import TTFont

    folder = font_dir()
    shared: set[int] | None = None
    for names in REQUIRED.values():
        for name in names:
            path = folder / name
            if not path.exists():
                continue
            points: set[int] = set()
            for table in TTFont(path, lazy=True)["cmap"].tables:
                points |= set(table.cmap)
            shared = points if shared is None else (shared & points)
    return shared or set()


def undrawable(texts) -> list[str]:
    """The characters in ``texts`` that no packaged font can draw.

    Returned in the order first met, so the message names the ones a reader
    will look for first. An empty list means the plate can be lettered.
    """
    try:
        covered = _coverage()
    except Exception:            # pragma: no cover - fontTools is optional
        return []
    if not covered:              # pragma: no cover - no fonts is install's error
        return []
    out: list[str] = []
    for text in texts:
        for char in str(text or ""):
            point = ord(char)
            if point in _IGNORE or point in covered or char in out:
                continue
            out.append(char)
    return out


def install(matplotlib_module) -> dict[str, str]:
    """Register the packaged fonts and make them the default.

    Raises RuntimeError rather than degrading to a substitute typeface.
    """
    folder = font_dir()
    missing = missing_files()
    if missing:
        raise RuntimeError(msg.text("error.missing-font", folder=folder,
                                    missing=", ".join(missing)))

    from matplotlib import font_manager

    for path in sorted(folder.glob("*.ttf")):
        font_manager.fontManager.addfont(str(path))

    registered = {f.name for f in font_manager.fontManager.ttflist}
    for family in REQUIRED:
        if family not in registered:
            from_bundle = sorted({f.name for f in font_manager.fontManager.ttflist
                                  if str(folder) in str(f.fname)})
            raise RuntimeError(msg.text("error.wrong-font-family", family=family,
                                        folder=folder, found=from_bundle))

    rc = matplotlib_module.rcParams
    rc["font.family"] = BODY
    rc["axes.unicode_minus"] = False
    # keep SVG text as text by default; render.py switches to outlines on request
    rc["svg.fonttype"] = "none"
    return {"body": BODY, "display": DISPLAY}


def verify_vietnamese(sample: str = "ệỹẫợừửỗẳ") -> list[str]:
    """Return characters the packaged body font cannot draw."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return []
    path = font_dir() / "OpenSans-Regular.ttf"
    if not path.exists():
        return list(sample)
    cmap = set(TTFont(path).getBestCmap())
    return [c for c in sample if ord(c) not in cmap]
