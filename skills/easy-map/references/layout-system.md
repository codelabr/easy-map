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

Print-first. Thin primary-blue rule across the top, serif headline, legend
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
- The locator box takes its shape from the country being drawn, measured from
  the frame and clamped to between 0.2 and 5.0 tall for its width. It used to be
  a fixed 2.2, called Vietnam's bounding box: Vietnam's own frame is 1.10, so the
  box was twice as tall as its contents even for the country it was measured for.
  It is clamped above the footer rule; if there is no room it is dropped rather
  than drawn over text.

## Labels

- Default to labelling only units that carry data, with the value under the name.
- **The name is tried on the unit's own anchor point first**, centred, the way an
  atlas sets it — a name sitting on its unit needs no explaining. Only if that
  collides does it step outward through five rings of eight candidate positions
  each, every one measured against the real rendered text box.
- **A leader line is drawn when nothing else says which unit the name belongs
  to** — that is, when the text box neither covers the anchor nor rests against a
  drawn symbol. Where a proportional circle is drawn, the circle marks the place
  and a name against it reads as its own. The line ends on the edge of the text
  box nearest the feature.
- Beyond 45 labels the lowest-ranked ones are dropped and reported rather than
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
