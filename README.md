# easy-map

Turns a public-health spreadsheet into a print-ready GIS map, through
conversation. The user needs to know nothing about GIS: describe what you want,
and the skill reads the data, recommends how to show it, warns about choices
that would mislead, and draws nothing until you have agreed to a numbered plan.

This is a **skill package for an AI coding assistant** (ChatGPT Codex or Claude
Code), not a library you call from your own code.

## Scope

**This version maps Vietnam only, at the two tiers that exist after the 2025
reform to a two-tier local government model: province and commune.** The
district tier was abolished by that reform and is not supported; district-level
figures can only be aggregated up to province. Boundaries, projection,
place-name matching and the crosswalk from the 63 pre-2025 province names to
the 34 current ones are all built for post-reform Vietnam and for nothing else.

## The division of labour

This boundary is the most important thing about the project:

| The language model | Deterministic Python |
|---|---|
| Interprets column headings and works out what they mean | Matches place names against the shapefile |
| Recommends the indicator to map, and says why | Tells a count from a rate, and so how repeated rows combine |
| Writes the title, the legend headings, the sentence underneath | Computes class breaks, projection and label placement |
| Asks the questions that are the user's to answer | Runs 21 cartographic checks before drawing |

**Not one figure on the map comes from the language model.** All of the
arithmetic lives in `skills/easy-map/scripts/emap/` and is covered by
**560 automated tests**.

## Installing the skill

The skill runs under **ChatGPT Codex** and **Claude Code**. Both read skills
from the same shape of folder, so one command serves both. Nothing needs to be
cloned.

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.ps1 | iex
```

**macOS**:

```bash
curl -fsSL https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.sh | bash
```

It reports which assistants it found, asks which to install for, copies the
whole package into `~/.codex/skills/easy-map/` and `~/.claude/skills/easy-map/`,
and rewrites the commands inside the installed copy to point at the engine
beside it. The skill then works from **any** working folder. The download is
deleted afterwards; only the installed copy remains.

Both commands run a script fetched over the network. If you would rather read
it first, open the URL in a browser — or clone the repository and run the
installer it contains directly:

```powershell
powershell -ExecutionPolicy Bypass -File install\install.ps1
```

```bash
./install/install.sh
```

Boundaries are not installed: they are ~135 MB and their terms of use are yours
to accept. The script asks where they are and records the answer in
`EASY_MAP_SHAPEFILES`, which the engine reads when the working folder has no
`shapefiles/` of its own.

Non-interactive, answering everything up front:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.ps1))) -Targets codex,claude -Shapefiles D:\gis\boundaries -Quiet
```

```bash
curl -fsSL https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.sh | bash -s -- --targets codex,claude --shapefiles ~/gis/boundaries --quiet
```

Both accept a branch or tag (`-Ref` / `--ref`) if you would rather pin a version
than take whatever `main` holds.

## Getting started

```bash
# 1. Administrative boundaries — required. See shapefiles/README.md for
#    what is needed and where to download it. Not shipped with the
#    repository: the commune file is over GitHub's 100 MB per-file limit.

# 2. Dependencies
uv run --with pandas --with openpyxl --with geopandas --with matplotlib \
       --with mapclassify --with rapidfuzz \
       python skills/easy-map/scripts/easy_map.py list --project-root .

# 3. Build the simulated sample data, then survey it
uv run --with pandas --with openpyxl --with geopandas --with rapidfuzz \
       python tools/generate_hiv_demo.py
python skills/easy-map/scripts/easy_map.py survey --project-root .
```

The ChatGPT Codex installation guide is distributed separately and is not part
of this repository.

## Layout

```text
skills/easy-map/     the skill: SKILL.md, the emap/ engine, fonts, references
tests/               560 tests in 23 files
tools/               scripts that regenerate the sample data in input/
input/               empty; build sample data with tools/generate_*.py
shapefiles/          empty; see the README inside
output/              one timestamped folder per request; not tracked in git
```

The internal handbook — design decisions with their reasons, the table of fixed
defects, and the work still outstanding — is not part of this repository.

## Running the tests

```bash
uv run --with pandas --with openpyxl --with geopandas --with matplotlib \
       --with mapclassify --with rapidfuzz \
       python -m unittest discover -s tests -t tests
```

Most tests need only the standard library; the file-reading layer, the
long-format slicing and the page capture need the packages above.

## Data in this repository

The repository **ships no data files at all**. `tools/generate_*.py` builds
**simulated** sample datasets to try the skill on. They are not for reporting or
programme decisions, and maps drawn from them carry that warning printed on the
plate itself.

## Licence

The source code is **MIT** (`LICENSE`). The bundled fonts are **not**: they are
under the **SIL Open Font License 1.1** and stay under it. See
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md), which also explains why the
serif is called *EasyMap Serif* rather than by its upstream name.

## Limitations

- **Post-reform Vietnam only**, province and commune tiers. See *Scope* above.
  There is no support for any other country, and none for the district tier the
  2025 reform abolished.
- **Not evaluated with users.** Everything above is what the tool does, not
  what it has been shown to change.
- A series that crosses the 2025 boundary needs the `sap_nhap` field in the
  shapefile; without it, older province names will not join.
