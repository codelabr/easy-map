"""easy-map internals.

The CLI in ``easy_map.py`` stays thin; everything reusable lives here so the
same deterministic logic runs identically under Claude Code and ChatGPT/Codex.
"""

__all__ = [
    "fonts",
    "semantics",
    "classify",
    "guardrails",
    "layout",
    "labels",
    "furniture",
    "prefs",
]
