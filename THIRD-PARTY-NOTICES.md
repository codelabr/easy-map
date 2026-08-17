# Third-party notices

The source code in this repository is under the **MIT License** (see `LICENSE`).
Two kinds of file shipped with it are **not**: the fonts, and the boundary data.

## Administrative boundary data

`shapefiles/provinces.zip` and `shapefiles/communes.zip` hold Vietnam's
post-2025 province and commune boundaries, downloaded from
<https://gis.vn/ban-do-hanh-chinh-viet-nam>.

**The source page states no licence.** These files are therefore redistributed
here on the judgement of this repository's owner rather than under any grant
from the provider, and the MIT licence above does not extend to them. Anyone
redistributing them again, or publishing maps drawn from them, should settle
the terms with the provider directly.

## Fonts

The font files are under the **SIL Open Font License 1.1** and remain under it,
modified or not. OFL 1.1 clause 5 requires that.

Everything below was read out of the `name` table inside the `.ttf` files
themselves (IDs 0, 7, 13 and 14) rather than written from memory.

## Fonts bundled with the skill

`skills/easy-map/assets/fonts/`

| File | Upstream | Modified | Licence text |
|---|---|---|---|
| `OpenSans-Regular.ttf`, `-SemiBold.ttf`, `-Bold.ttf` | Open Sans | yes, subset | `OFL-OpenSans.txt` |
| `EasyMapSerif-Regular.ttf`, `-Bold.ttf` | Merriweather | yes, subset **and renamed** | `OFL-EasyMapSerif.txt` |

**Open Sans** — Copyright 2020 The Open Sans Project Authors,
<https://github.com/googlefonts/opensans>. No Reserved Font Name, so the subset
keeps the name "Open Sans".

**Merriweather** — Copyright 2024 The Merriweather Project Authors,
<https://github.com/EbenSorkin/Merriweather4>, **with Reserved Font Name
"Merriweather"**. Merriweather is a trademark of Sorkin Type Co.

## Why the serif is called "EasyMap Serif"

OFL 1.1 defines a *Modified Version* as one "made by adding to, **deleting**, or
substituting -- in part or in whole -- any of the components of the Original
Version". The two files here were subset to Latin and Vietnamese, which deletes
glyphs, so they are a Modified Version.

Clause 3 of the licence:

> No Modified Version of the Font Software may use the Reserved Font Name(s)
> unless explicit written permission is granted by the corresponding Copyright
> Holder. This restriction only applies to the primary font name as presented
> to the users.

So the subset may not carry the name "Merriweather". The primary name fields
were changed to **EasyMap Serif**:

| Field | Before | After |
|---|---|---|
| nameID 1 (Font Family) | `Merriweather 18pt` | `EasyMap Serif` |
| nameID 4 (Full name) | `Merriweather 18pt` | `EasyMap Serif` |
| nameID 6 (PostScript) | `Merriweather-18pt` | `EasyMapSerif-Regular` |
| nameID 16 (Typographic Family) | `Merriweather` | `EasyMap Serif` |

**nameID 0 (copyright)** and **nameID 13, 14 (licence)** were kept, as clause 2
requires, so the origin is still readable inside the font file. Not one pixel of
the lettering changed; only the name did.

## Unmodified upstream fonts

`tools/font-sources/` holds two **unmodified** variable fonts, used to rebuild
the subsets above. Redistributing them verbatim does not engage clause 3, so
they keep their original names.

| File | Licence text |
|---|---|
| `Merriweather-VF.ttf` | `OFL-Merriweather.txt` |
| `OpenSans-VF.ttf` | `OFL-OpenSans.txt` |

## Notes

`OFL-EasyMapSerif.txt` and `OFL-Merriweather.txt` are the same text, downloaded
from the Merriweather source repository. Its copyright line reads 2020 while the
font file in use reads 2024; the copyright inside the font file is the
authoritative one for the version distributed here.

None of these licence files was rewritten or summarised. Each was downloaded
verbatim from the upstream repository of the font it covers.
