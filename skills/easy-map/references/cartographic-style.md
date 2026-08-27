# Static Map Style

> **The organisation whose published guidance this is drawn from is named below for provenance only. It must never appear in anything the skill produces — not in a plate, a legend, a footnote, a file name, a message to the user, or a slide. The visual system is this project's own house style.**

Use this reference whenever rendering a final map. It translates official CDC web visualization and public-health cartography guidance into deterministic defaults for this skill.

## Layout

- Use a short title that states what, where, and when when those details are known.
- Do not include the word "Map" in the title.
- Put location, administrative level, population, or period context in a short supertitle/subtitle.
- Give the map the dominant visual area. Put legends outside the mapped geography.
- Put the data source and concise classification/method note in a footer.
- Use balanced white space and a fine outer boundary where it clarifies the mapped extent.
- Do not add a CDC logo or imply CDC authorship unless the user supplies an authorized brand asset and explicitly requests its use.

## Typography

- The house style pairs a serif for headlines with **Open Sans** for everything
  else. Both are bundled in `assets/fonts` (Open Sans Regular/SemiBold/Bold, and
  the serif as `EasyMapSerif-Regular/Bold`), instantiated from the upstream
  variable fonts with full Vietnamese coverage. **Ask for the family by the name
  the file carries — `EasyMap Serif`, not the upstream name.** The subset may not
  use the upstream name; see `THIRD-PARTY-NOTICES.md`.
- There is **no fallback chain**. If the packaged fonts cannot be registered the run
  raises instead of substituting Arial — silently shipping the wrong typeface is what
  made earlier output look generic.
- Use bold only for the title, supertitle, and legend headings.
- Keep political/administrative labels horizontal. Split or offset labels and use leader lines where needed.
- Use a white text halo when labels cross thematic fills or boundaries.

## Color And Hierarchy

- Use CDC Blue `#005eaa` for the title band and primary identity.
- Use one CDC sequential family for ordered numeric data, with darker shades indicating greater magnitude unless the indicator meaning requires reversal.
- Use CDC qualitative colors only for unordered categories.
- Use neutral gray for missing/suppressed data and explain it in the legend or subtext.
- Use light internal boundaries for small administrative units and a stronger outer boundary for geographic orientation.
- Avoid rainbow/spectral schemes for choropleth maps and avoid red-green combinations.

CDC theme families and approved shades:

Sequential ramps must keep lightness monotone. The ramp actually used for ordered
numeric data is anchored on CDC Blue and defined in `scripts/emap/classify.py`; for
five classes it is `#dceefb #a9d2ec #6ba9d5 #2f7cb8 #005eaa`. Do not build a ramp by
walking across the theme families below — mixing blue into teal and back reads as a
hue change, not as more or less.

- Blue: `#005eaa`, `#88c3ea`, `#c0e9ff`, `#edf9ff`
- Teal: `#00695c`, `#4ebaaa`, `#ceece7`, `#ebf7f5`
- Green: `#497d0c`, `#84bc49`, `#dcedc8`, `#f1f8e9`
- Slate: `#29434e`, `#7e9ba5`, `#b6c6d2`, `#e2e8ed`
- Amber: `#fbab18`, `#ffd54f`, `#ffecb3`, `#fff7e1`
- Pink: `#af4448`, `#e57373`, `#ffc2c2`, `#ffe7e7`
- Purple: `#712177`, `#b890bb`, `#e3d3e4`, `#f7f2f7`

## Thematic Mapping

- Prefer an equal-area projection for statistical area maps.
- Use choropleth color primarily for normalized values such as rates and percentages.
- Use proportional symbols for counts or burden; symbol area, not diameter, must scale with value.
- A rate choropleth plus count symbols is valid when both risk and burden matter. Keep the overlay to two thematic layers.
- Use four or five classes by default; normally stay within three to seven.
- Use whole-number class labels for counts, percent labels for percentages, and grouped digits for values over 999.
- Make legend symbols match map symbols, order ranges logically, and use intuitive headings.
- For related small multiples, keep map extent, scale, classification, and legend consistent.

## Official Sources

- CDC, [Cartographic Guidelines for Public Health](https://stacks.cdc.gov/view/cdc/136790/cdc_136790_DS1.pdf)
- CDC COVE, [General Map Guidance](https://www.cdc.gov/cove/data-visualization-types/general-map-guidance.html)
- CDC COVE, [Legend Panel - Maps](https://www.cdc.gov/cove/documentation/legend-panel-maps.html)
- CDC WCMS, [Preferred Color Pairings](https://www.cdc.gov/wcms/4.0/cdc-wp/page-and-site-options/preferred-color-pairings.html)
- CDC COVE, [Visual Panel - Charts and Maps](https://www.cdc.gov/cove/documentation/visual-panel-charts-maps.html)
