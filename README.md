# easy-map

Turn a spreadsheet of Vietnamese health data into a print-ready map, by
describing what you want. No GIS knowledge needed: the skill reads the data,
recommends how to show it, warns about choices that would mislead, and draws
nothing until you have agreed to a numbered plan.

<p align="center">
  <!-- Served from github.com rather than raw.githubusercontent.com. A
       same-repo image resolves to that host however the path is written, and
       it rate-limits anonymous traffic per IP, so a reader behind a busy
       address gets a 429 instead of the picture. The copy under assets/ is
       the one a clone gets. -->
  <img src="https://github.com/user-attachments/assets/4f8ee320-5fb6-4326-bb8d-59ee6fd37e24" width="430"
       alt="Province-level map of Vietnam, provinces shaded by positivity rate with proportional circles for new diagnoses, an inset for Hoang Sa and Truong Sa, scale bar and legend.">
  <br>
  <sub>One request, drawn from <b>simulated</b> data.</sub>
</p>

**Vietnam only**, at the two tiers left by the 2025 reform to a two-tier local
government model: **province** and **commune**. The district tier the reform
abolished is not supported; district figures can only be aggregated up to
province.

## What you get

One timestamped folder per request, holding:

| | |
|---|---|
| `.png` | Print-quality maps, ready for a report or a slide |
| `.html` | One interactive page — zoom, search by name, click a unit for its figures. Self-contained, so a single file can be emailed on its own |
| `.csv` | The numbers actually drawn, after name matching and aggregation, for checking a figure without repeating the work |

Time series render as video and as a page with a slider.

## Install

It runs under **ChatGPT Codex** and **Claude Code**. Both read skills from the
same shape of folder, so one command serves both.

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.ps1 | iex
```

**macOS**:

```bash
curl -fsSL https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.sh | bash
```

It reports which assistants it found, installs Python if there is none, and
unpacks Vietnam's administrative boundaries — which ship with the package, so
there is nothing else to download. Then **start a new assistant session**; one
already open will not see it.

The boundaries take about 135 MB unpacked. Pass `-SkipShapefiles` /
`--skip-shapefiles` to leave them alone. They are third-party data and are
**not** under this repository's licence — see
[`shapefiles/README.md`](shapefiles/README.md).

## Using it

Paste a table into the conversation, attach a spreadsheet, or leave one in
`input/`. Then say what you want — in Vietnamese or English.

The skill stops and asks you three times: after reading the data, to confirm
what it thinks the table is; before drawing, with a numbered plan that includes
the defaults it picked for you; and whenever a choice would mislead. A run that
produces a correct map without ever pausing has failed, because you never got
to say what you wanted.

The conversation and the map are two separate languages. Somebody writing in
English often needs a Vietnamese map for a provincial health department.

## How it works

This boundary is the point of the project:

| The language model | Deterministic Python |
|---|---|
| Interprets column headings and works out what they mean | Matches place names against the shapefile |
| Recommends the indicator to map, and says why | Tells a count from a rate, and so how repeated rows combine |
| Writes the title, the legend headings, the sentence underneath | Computes class breaks, projection and label placement |
| Asks the questions that are the user's to answer | Runs 17 cartographic checks before drawing |

**Not one figure on the map comes from the language model.** All of the
arithmetic lives in `skills/easy-map/scripts/emap/`, under more than 550
automated tests.

## Limitations

- **Post-reform Vietnam only.** No other country, and no district tier.
- **Not evaluated with users.** Everything above is what the tool does, not
  what it has been shown to change.
- A series crossing the 2025 boundary needs the `sap_nhap` field in the
  shapefile; without it, older province names will not join.
- Your spreadsheet is read by an AI assistant, so its contents leave your
  machine. The drawing itself runs locally.

## Data

The repository ships **no data**. `tools/generate_*.py` builds simulated
datasets to try the skill on; they are not for reporting or programme
decisions.

## Licence

Source code is **MIT** (`LICENSE`). The bundled fonts are not: they are under
the **SIL Open Font License 1.1** and stay under it. See
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md), which also explains why the
serif is called *EasyMap Serif* rather than by its upstream name.
