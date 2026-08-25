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
