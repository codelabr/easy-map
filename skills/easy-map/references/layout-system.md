# Layout System

Two approved page layouts. Both put the map first: there is no side rail of
commentary and no four-part statistics strip. Everything on the page either
encodes data, decodes the encoding, or credits the source.

## Shared skeleton

1. **Kicker** — administrative level, period, province. Uppercase, primary blue, small.
2. **Title** — what, where, when. Never contains the word "Bản đồ".
3. **One-line insight** — a descriptive fact taken from the mapped values only.
4. **Map** — dominant, sized from the geometry.
5. **Legend block** — colour classes, then symbol key, then locator.
6. **Footer** — source line, then method line.

## `report`

Print-first. Thin primary-blue rule across the top, Merriweather headline, legend
column on the left, map right-aligned beside it.

Use for documents that will be printed or pasted into a report.

## `banner`

Solid primary-blue title band with the headline reversed out in white Open Sans,
map on the left, legend rail on the right carrying the insight sentence above
the legends, separated by a hairline.

Use when the product should read as a public-health communication piece, or for
slides.

## Sizing

The figure is derived from the mapped geometry, never from a fixed 16:9 canvas:

- long side of the map area starts at 8.6 in and is clamped to 4.2–10.5 in
- the map axes is then shrunk to the geometry's own aspect ratio, so no dead
  space is left beside the drawn area
- chrome heights (header, footer, band) are fixed, so the page grows only in the
  direction the geography needs

A near-square province produces a near-square page; Vietnam as a whole produces
a tall one.

## Legend block

Stacked with a running cursor — each element returns the vertical position it
finished at, and the next one starts below it. Nothing is placed by hand-tuned
offset, because that is what previously made the symbol key, the colour legend
and the locator overlap.

- Colour classes run **low at the top, high at the bottom**, one column.
- "Chưa có số liệu" is always the last row when any area is unfilled.
- Symbol keys are drawn with `scatter`, not circle patches, so they stay circular
  on a non-square axes.
- The locator is sized to Vietnam's 1:2.2 bounding box and clamped above the
  footer rule; if there is no room it is dropped rather than drawn over text.

## Labels

- Default to labelling only units that carry data, with the value under the name.
- Eight candidate positions per label, measured against the real rendered text
  box, then three distance rings.
- A leader line is drawn only when the label could not stay adjacent to its
  feature, and it ends on the edge of the text box nearest the feature.
- Beyond ~45 labels the lowest-ranked ones are dropped and reported rather than
  overplotted.

## Suppression

When a map has no colour classes and no symbol key — a plain point map or a
boundary map — the side panel is removed and the map takes the full width.

## Quality gate

Before delivery, open the PNG and confirm:

- no text is clipped at any page edge, especially the second footer line
- no label overlaps another label or a symbol
- every leader line terminates on a label
- legend classes ascend
- the locator highlights the right province and touches nothing
- counts are not shown with decimals and rates are not shown as counts
- grey is explained
