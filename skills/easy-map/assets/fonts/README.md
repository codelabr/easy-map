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
| `EasyMapSerif-Regular.ttf` | ships, but nothing selects it — both users of the display face ask for bold |
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

The five files come to **746 KB** together, measured. TrueType hinting is
dropped: output is rendered at 220 DPI, where it has no effect.

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
aborts.

**Then rename the serif, before it goes anywhere.** Subsetting deletes glyphs,
which makes the files a Modified Version, and OFL 1.1 clause 3 forbids a
Modified Version from carrying the Reserved Font Name. Rewrite nameIDs 1, 4, 6
and 16 to *EasyMap Serif* — the exact values are tabulated in
`../../../../THIRD-PARTY-NOTICES.md`. Leave nameID 0 and nameIDs 13–14 alone;
clause 2 requires the copyright and licence to stay inside the file.

Open Sans carries no Reserved Font Name and keeps its own.

After rebuilding, confirm the family names matplotlib actually reads. These are
the names `emap/fonts.py` asks for, so a mismatch is not cosmetic — the run
aborts rather than substituting a typeface:

```python
from matplotlib import font_manager as fm
for filename, family in (("OpenSans-Regular.ttf", "Open Sans"),
                         ("EasyMapSerif-Bold.ttf", "EasyMap Serif")):
    assert fm.ttfFontProperty(fm.get_font(filename)).name == family, filename
```

After any change, verify Vietnamese coverage before committing:

```python
from emap import fonts
assert fonts.verify_vietnamese() == []
```

Do not replace these with system fonts. `emap/fonts.py` raises rather than
falling back to a substitute typeface — shipping a plate set in Arial
is exactly the defect this bundle exists to prevent.
