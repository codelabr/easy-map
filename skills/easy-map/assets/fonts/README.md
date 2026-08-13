# Bundled fonts

Licensing, and why the serif is called EasyMap Serif rather than Merriweather:
see `../../../../THIRD-PARTY-NOTICES.md` and the `OFL-*.txt` files here.

The house style pairs **Merriweather** (headlines) with **Open Sans** (everything else).
Both are open licence — Open Sans and Merriweather are released under the SIL
Open Font License 1.1 — so they ship inside the skill. That guarantees identical
output on any machine, including a sandbox with no system fonts installed.

| File | Role |
|---|---|
| `OpenSans-Regular.ttf` | body text, legends, footer |
| `OpenSans-SemiBold.ttf` | map labels |
| `OpenSans-Bold.ttf` | legend headings, `banner` title |
| `EasyMapSerif-Regular.ttf` | reserved |
| `EasyMapSerif-Bold.ttf` | `report` layout headline |

## Provenance

Instantiated from the upstream variable fonts in the `google/fonts` repository
(`ofl/opensans/OpenSans[wdth,wght].ttf`, `ofl/merriweather/Merriweather[opsz,wdth,wght].ttf`),
then subset to Latin + Vietnamese.

Static instances are pinned at `wdth=100`, `wght=400/600/700` for Open Sans and
`wdth=100, opsz=18, wght=400/700` for Merriweather.

Subset ranges — Latin, Latin-1, Latin Extended-A/B, combining marks, Latin
Extended Additional (Vietnamese lives at U+1EA0–U+1EF9), punctuation, currency
and the minus sign:

```
U+0000-00FF,U+0100-024F,U+0300-036F,U+1E00-1EFF,U+2000-206F,U+20A0-20CF,U+2122,U+2212
```

Subsetting takes the set from 2.482 KB to 741 KB. TrueType hinting is dropped —
output is rendered at 220 DPI where it has no effect.

## Rebuilding

The upstream variable fonts are kept at `tools/font-sources/` in the project root
so the set can be rebuilt without network access.

Instantiate the static weights with `fontTools.varLib.instancer` (pass
`updateFontNames=True`), then run `fontTools.subset` with the ranges above and
**`--name-IDs=*`**.

Keeping the name records matters: pinning `opsz=18` renames Merriweather's
nameID 1 to "Merriweather 18pt", and FreeType only reports the plain family name
because nameID 16 (Typographic Family) carries it. A default subset drops
nameID 16, matplotlib then sees a family called "Merriweather 18pt", and the run
aborts. After rebuilding, confirm the family name matplotlib actually reads:

```python
from matplotlib import font_manager
prop = font_manager.ttfFontProperty(font_manager.get_font("Merriweather-Bold.ttf"))
assert prop.name == "Merriweather"
```

After any change, verify Vietnamese coverage before committing:

```python
from emap import fonts
assert fonts.verify_vietnamese() == []
```

Do not replace these with system fonts. `emap/fonts.py` raises rather than
falling back to a substitute typeface — shipping a plate set in Arial
is exactly the defect this bundle exists to prevent.
