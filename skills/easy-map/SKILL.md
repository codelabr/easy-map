---
name: easy-map
description: Turn an Excel dataset in a project's input folder into a print-ready Vietnam GIS map using the project's province and commune shapefiles. Vietnam only, and only the two tiers that exist after the 2025 reform to a two-tier local government model: province and commune, with no district tier. Use when a user wants a map of Vietnamese administrative data and does not know GIS - the skill reads and interprets the dataset first, recommends a scientifically sound map in plain language, matches place names without requiring admin codes, warns about misleading choices, and renders print-ready PNG maps plus a self-contained interactive HTML page into a timestamped output folder. Also use when an experienced user states directly what map they want.
---

# Easy Map

## Read this first: six rules that override everything below

This skill is a **conversation**, not a batch job. A run that produces a correct
map without ever pausing has failed, because the person never got to say what
they wanted. These six come before every other instruction in this file.

1. **Stop three times.** After profiling the data, to summarise what it is and
   confirm your reading. After the questions, to lay out the numbered plan. And
   whenever a warning is serious. Each stop ends your turn — you say your piece
   and wait. Do not chain the whole job into one uninterrupted run.
2. **Ask through the host's option picker, never in free prose.** Every question
   this skill needs arrives from the engine already built: the question, two or
   three mutually exclusive options, one sentence on what each does, and which is
   recommended. On Codex that picker is `request_user_input`. Pass the options
   through unchanged. Where there is no picker, print the same content as a
   Markdown table and take a number back — see *How to ask a question*.
3. **Never read a flag out loud.** `choropleth-symbol`, `quantile`,
   `weighted-mean` are how the command line talks to itself. The engine returns a
   plain sentence for every one of them; if you are typing a flag value into a
   message to a person, you are writing the wrong message.
4. **Ask the map's language. Never infer it.** The language someone writes to
   you in is not the language their map is for. `--messages` follows the
   conversation and is yours to infer; `--language` is theirs to choose.
5. **Draw exactly what was asked for, once.** One request, one `render`. No
   extra overview map, no "matched-only" summary, no second edition in another
   language unless the person asked for it.
6. **`render` will not draw until the plan is agreed.** Without `--confirmed` it
   returns a numbered plan and a code; the code is the only way to unlock the
   drawing, and it changes whenever a setting changes. This is enforcement, not
   etiquette — see *The gate before drawing*.

## What this skill is for

Someone has an Excel file of Vietnamese data. They want a map that is **beautiful, scientifically correct, and immediately usable** in a report or a slide deck. They may know nothing about GIS, statistics, or map design.

Your job is to be the analyst they do not have. Read their data first, work out what it is about, then guide them with a small number of plain questions.

## Division of labour

`scripts/easy_map.py` does everything deterministic: reading, name matching, aggregating, classifying, checking and drawing. It never decides *what the map should say*. The engine it imports lives in `scripts/emap/`; you should not need to open it.

You do the interpreting and the talking. Never re-implement the script's logic by hand, and never draw with ad-hoc plotting code.

## Two languages, decided separately

There are **two** language settings in a run and confusing them produces work
nobody can use.

| | Setting | Follows |
|---|---|---|
| The conversation | `--messages vi\|en` | the person you are talking to |
| The finished map | `--language vi\|en` | the audience of the figure |

They come apart routinely: an English-speaking programme officer producing a
Vietnamese map for a provincial health department is the ordinary case.

**The conversation language you infer; the map language you ask.** Write in
whatever language the user wrote to you in, from their first message, and pass
that as `--messages` on *every* command — the script's warnings, the reasons
behind each recommendation, the verdict on each sheet **and the gate's own
instructions to you** all come back in that language, and you relay the
user-facing ones as they are rather than translating them yourself.

Passing it on every command matters more than it looks. Forget it and the whole
reply arrives in Vietnamese, including the paragraph of instructions you read
immediately before writing to the user — and a run that began in English drifts
into Vietnamese halfway through, which is what happened the first time. When
`--messages` is absent the gate says so, in both languages, at the end of
`hướng_dẫn`; treat that line as a defect in your own command and re-run.
The map language is question 6 of the interview and defaults to the conversation
language.

Three things never translate, in either direction, because they are the user's
data and not the script's writing: **place names**, **column headings**, and
**sheet names**. A Vietnamese commune keeps its Vietnamese name in an English
sentence.

## Register

Everything you print — the data summary, the numbered plan, the warnings, the
handover note — is a **technical document read by a public-health professional**,
not a chat message. Write it accordingly.

- **Formal, precise, still plain.** Terms of art are welcome once explained
  ("tô màu theo phân vị", "a quantile ramp"); colloquial speech is not.
- **State facts, then ask.** "Sheet DATA có 70.080 dòng, cấp tỉnh. Đề xuất sử
  dụng sheet này." beats "Chắc là dùng DATA được đấy, bạn thấy sao?". In English,
  "Sheet DATA holds 70,080 rows at province level. Recommend using it." beats
  "DATA looks like it should work — what do you think?".
- **No hedging and no enthusiasm.** Neither "có vẻ như", "chắc là", nor "tuyệt
  vời", "xong ngay"; neither "it seems", "probably", nor "great!", "all done!".
  A number is either verified or explicitly stated as not.
- **Tables and numbered lists over prose** wherever the content is a set of
  parallel items. Label the columns. Give units.

In **Vietnamese**, drop the spoken particles `nhé`, `nha`, `nhỉ`, `ạ`, `thôi`,
`luôn`. Do not refer to yourself as `mình`; use `tôi`, or drop the subject. Say
`đề nghị xác nhận`, not `bạn xem giúp mình`.

In **English**, the same register means: no contractions in the summary and the
plan (`does not`, not `doesn't`); no "let me", "I'll go ahead and", "feel free
to"; no exclamation marks; the imperative or the passive for what the script
did ("Rows sharing a place name were combined"), not "I combined them". Prefer
the plain word to the padded one — "use", not "utilise"; "before", not "prior
to". Numbers take the English convention: `35,156` and `99.74%`.

This register applies to the finished map as well: titles, subtitles and legend
headings are captions in a report, so they take no exclamation marks and no
first person.

## How to ask a question

You do not compose the questions. Every one this skill needs arrives from the
engine already built: `survey` returns `chọn_nhanh`, and `render` without
`--confirmed` returns `phải_hỏi` plus, on each plan row that can still change, a
`câu_hỏi` with its own `lựa_chọn`. Each option carries:

| Field | Use it as |
|---|---|
| `nhãn` | the option's label |
| `mô_tả` | one sentence on what choosing it does to the finished map |
| `khuyến_nghị` | `true` on the recommended one — put it first, mark it `(Recommended)` |
| `cờ` | the flag to pass on the next run. **For you, not for them** |

**Use the host's own option picker.** On Codex that is `request_user_input`. Pass
the options through as they are: do not add options, do not reword them, and do
not turn a list that arrived as a list back into a paragraph. Where the host has
no picker, print the same content as a Markdown table with a `#` column and take
a number back.

Two constraints on what any question may contain.

- **No flag names and no flag values.** A person who cannot evaluate
  `natural-breaks` can only agree to it, and agreement that costs nothing to
  give is not consent. This is not hypothetical: the first real run of this
  skill stopped to ask, exactly as instructed, and then showed a public-health
  officer a table reading `choropleth-symbol` / `quantile` / `weighted-mean`.
  Every one of those has a plain sentence waiting in the engine's reply.
- **One question at a time.** Ask, stop, wait. A message ending in three
  questions gets one answer, and you will not know which.

The exception is the plan table itself, which is a summary rather than a
question: print all of it at once, then ask about the rows in `phải_hỏi`.

## Project layout

- `input/` — datasets: `.xlsx`, `.xlsm`, `.xls`, and `.csv` / `.tsv` / `.txt`
- `shapefiles/provinces/` and `shapefiles/communes/` — Vietnam, 34 provinces and ~3.300 communes
- `output/` — one timestamped folder per render job
- `.easy-map/` — remembered choices and confirmed name corrections
- `tools/generate_complex_demo.py` — rebuilds the test workbook; not part of a normal run

## First: where is the data?

**Look for an attached file before you look in `input/`.** Most people do not
put a workbook in a folder — they attach it to the message, or paste a block of
rows. A skill that starts by surveying `input/` will confidently offer someone
six files that are not theirs while the file they just handed over sits unread.

So the order is fixed:

**1. Did the user attach a file to this message?** If so, bring it in and do not
ask anything yet:

```bash
uv run ... python skills/easy-map/scripts/easy_map.py import --project-root . --run-folder 2026-08-06_14-30-00 --file "<đường dẫn tệp đính kèm>"
```

`import` copies it into `input/`, checks the format, records it in the request's
manifest, and returns the same survey `survey` would have given for that file —
so one call answers both "did it arrive" and "can it become a map". It never
overwrites: an identical file already there is reused and reported as
`đã_có_sẵn`; a different file of the same name gets a `_02` suffix.

**2. Did the user paste a table as text?** Write it to `input/` as a `.csv` — one
row per line, tab or comma separated — with a name describing its content, then
`import` that file. The skill detects the delimiter and the encoding, and reports
both under `cách_đọc_sheet`. Read that report out: a pasted table carries no
types, so the count of cells that could not be read as numbers
(`số_ô_không_đọc_được`) matters far more here than it does with a real workbook.

**3. Only if neither** — survey what is already there:

```bash
uv run ... python skills/easy-map/scripts/easy_map.py survey --project-root .
```

With no `--excel` it reads every file in `input/`; with one, just that file.
Either way it samples a few hundred rows per sheet — under three seconds for the
whole folder.

**The question is already written for you.** `survey` returns `chọn_nhanh` as a
finished question — `câu_hỏi`, then one `lựa_chọn` per mappable sheet with its
`nhãn` (the file) and `mô_tả` (the sheet, its row count and its administrative
level). Hand it to the picker as it is. Making someone copy a file name back to
you is a poor way to choose between fourteen options, and it is what happened the
first time this skill met a real user.

Two things the engine guarantees, so do not remove them. Every option states its
**row count and level**, because a file name alone tells nobody what is inside
and the name that reads best is often the summary sheet rather than the data.
And the last option is always **"I will send another file"** — the files in
`input/` may belong to an earlier request, or to someone else entirely. Sheets
that cannot become a map are filtered out before you see them; offering them
costs a decision that can only end in a refusal.

Where there is no picker, the same list as a table:

> | # | Tệp | Nội dung |
> |---|---|---|
> | 1 | `chuong_trinh_hiv_tinh.xlsx` | Sheet 'Dữ liệu tỉnh 2026', 34 dòng, số liệu ở cấp tỉnh/thành phố. |
> | 2 | `PEPFAR_..._MER_Q2FY26.xlsx` | Sheet 'DATA', 70.080 dòng, số liệu ở cấp tỉnh/thành phố. |
> | 3 | `complex_commune_...xlsx` | Sheet 'Dữ liệu xã hiện tại', 36 dòng, số liệu ở cấp xã/phường. |
> | 4 | *Không phải tệp nào ở trên* | Đính kèm tệp Excel hoặc CSV của bạn vào cuộc trò chuyện. |

For one file:

```bash
uv run ... python skills/easy-map/scripts/easy_map.py survey --project-root . --excel "input/example.xlsx"
```

It samples a few hundred rows per sheet — a couple of seconds even for a 6 MB
workbook — and returns, for each sheet, whether it is usable, which column holds
place names, the administrative level, and the row count. `nên_dùng` lists the
sheets worth opening.

Then open with the answer, not the question:

> Workbook có 4 sheet, trong đó chỉ **DATA** vẽ được bản đồ (70.080 dòng, cấp
> tỉnh, cột địa danh `SNU1`). Ba sheet còn lại là bảng tổng hợp, không có cột
> địa danh. Đề xuất sử dụng sheet DATA.

**Do not ask "which sheet do you want?" first.** The user does not know which
sheets are mappable — that is your job, and they will reasonably pick the one
whose name reads best, which on a real export is the pivot summary rather than
the data. Ask only when `survey` returns more than one usable sheet, and then
describe them by what they contain rather than by name alone.

**`số_bảng_trong_sheet` above one means the sheet holds separate tables**, with
`vị_trí_các_bảng` giving each one's row range. This happens when somebody
appends a budget table under a summary table instead of opening a new sheet.
Read plainly it comes back as one table whose lower half carries the upper
half's column names — no error, just a second set of rows that means something
else. The skill only reports this; ask which table is wanted and have the user
split it into its own sheet before profiling. Do not guess.

If `nên_dùng` is empty, say so plainly and stop. Nothing further is worth doing
until a different file or a corrected sheet arrives.

## Then: can that sheet become a map at all?

`profile` answers `dùng_được` before anything else. When it is `false`, the map
options list is empty and a `sheet-khong-ve-duoc` warning says why — the sheet
is a pivot table, or has no place-name column, or is empty. Relay the reason and
offer the other sheets in the workbook. Do not push on: there is nothing there
to be clever about.

`cách_đọc_sheet` records what had to be adjusted to read the file at all:

- **`bỏ_qua_dòng_đầu`** — the column names were not on row 1. Real reports put a
  title, a date and a few pivot filters above the table. Say how many rows were
  skipped; if the number looks wrong, the sheet is probably the wrong one.
- **`đổi_chữ_thành_số`** — a column of numbers arrived as text, usually because
  it was typed with thousands separators. Check `số_ô_không_đọc_được`: those
  cells became blanks, and blanks are not zeroes.
- **`đọc_ô_gộp`** — the sheet had merged cells, so it was read a second time
  honouring them. Two things this fixes, both silent otherwise: a province
  written once and merged down over its own rows arrives blank on all but the
  first (blank meaning "same as above", not "missing"), and a header whose group
  name spans two columns loses that name while its second tier — "Nam", "Nữ" —
  is read as a row of data. Grouped columns come back joined:
  `Số ca phát hiện - Nam`. `số_tầng_tiêu_đề` says how many tiers were folded in.
- **`bỏ_qua_dò_ô_gộp`** — the sheet looked like it had merged cells but the file
  is over 2 MB, and reading merges costs roughly eleven seconds per megabyte.
  Say so: column names and place names may be incomplete, and splitting the
  sheet out to a smaller file would fix it.
- **`đọc_văn_bản_phân_cách`** — a `.csv`/`.tsv` read with a detected delimiter
  and encoding, both named in the note. If the delimiter looks wrong, or the
  file resolved to a single column, the paste was probably broken by a comma
  inside a place name; ask for the file itself rather than guessing.

## The core rule: understand before you ask

**Run `profile` before your first question about the map.** Asking a non-technical user "which column should the map show?" before you have looked at their data pushes your job onto them.

The profile returns, for every column: its inferred meaning (count, percent, rate per capita, percentage point, money, category, time, coordinate), its unit, missing rate, distribution, and — when the workbook has a data-dictionary sheet — the author's own description, which outranks inference. It also returns candidate place-name columns, coordinate columns, ranked map options each with a reason, and data-quality warnings.

Read it, then open with a short summary of what you believe the dataset is, in the user's language. Something like:

> Bảng gồm 36 dòng; mỗi dòng là một xã/phường thuộc Hà Nội, Huế và Cần Thơ, số
> liệu Quý I/2026. Các đại lượng có sẵn: tỷ lệ bao phủ chương trình, số ca phát
> hiện, dân số và mức ưu tiên. Đề xuất tô màu theo tỷ lệ bao phủ và vẽ vòng
> tròn theo số ca phát hiện — màu thể hiện mức độ, kích thước vòng tròn thể
> hiện quy mô. Đề nghị xác nhận cách hiểu dữ liệu nêu trên.

The same summary for a user writing in English. Note what does **not** change:
the column headings and the place names are quoted from the workbook as they
stand.

> The table holds 36 rows; each row is one commune in Hà Nội, Huế or Cần Thơ,
> for Q1 2026. The available measures are programme coverage, cases detected,
> population and a priority level. Recommend colouring by coverage and sizing
> circles by cases detected — colour carries the level, circle size carries the
> scale. Please confirm this reading of the data.

**Show the rows.** `profile` returns `mẫu_dữ_liệu`: five real rows over the
columns that carry the meaning. Print it as a table under your summary — a claim
about a dataset is worth more with the dataset under it, and on a long sheet the
rows *are* the explanation: the reader sees one place on three consecutive rows
and understands "một dòng là một quan sát" without being told.

Mark what is not shown, with the real numbers. Add a `…` column at the right
when `số_cột_ẩn` is above zero, and a `…` row underneath for `số_dòng_còn_lại`:

```
Tỉnh/thành phố   | Indicator Code | Value | Disaggregate  | Quarter | …
Ba Ria-Vung Tau  | TX_CURR        | 1     | By Age - Sex  | Q1      | …
Ba Ria-Vung Tau  | TX_PVLS Num    | 1     | By Age - Sex  | Q1      | …
Binh Duong       | TX_CURR        | 5     | By Age - Sex  | Q1      | …
…  (còn 70.075 dòng, 14 cột nữa)
```

Name the hidden columns if the user asks; they are in `tên_cột_ẩn`.

If something is genuinely ambiguous — two columns could be the province, a numeric column has no recognisable meaning, the workbook mixes several reporting periods — ask about *that*, one question at a time.

## When one row is an observation, not a place

Some exports are **long**: a single numeric column holds every value and the
neighbouring columns say what each row is about. A PEPFAR MER extract runs
70.000 rows and 23 indicators through one `Value` column. The profile detects
this and answers with a `dữ_liệu_dạng_dài` block instead of the usual map
options, because listing columns is no longer a useful description of the sheet.

Read that block before you speak. It gives you the value column, the column that
names the indicator, the periods, the indicators ranked by how much of the map
each can fill, any numerator/denominator pairs, and — most importantly — the
columns that **must be pinned**.

**The hazard is not a crash, it is a plausible number.** In that file, TX_CURR
for one quarter sums to 149.121 if the disaggregation is left open and to 49.706
once it is pinned. Both look like reasonable patient counts. Only one is real.
The profile names the columns that cause this, and it names only the dangerous
ones: splitting a province across its sites or its age bands is a partition and
adds up correctly, while a column carrying a pre-computed total *beside* its
detail rows does not.

**Every indicator arrives with its slice already worked out.** Each entry under
`chỉ_số` carries `lát_đề_xuất` — the value to pin on each column with the reason
measured from that indicator's own rows — plus `tổng_sau_khi_ghăm` and a ready
`lệnh`. Use it. Working the pins out by hand is how the period gets forgotten,
and forgetting the period on TX_CURR turns 49.706 into 433.681 by counting every
patient once per quarter.

Two fields there are worth reading out loud rather than skipping:

- `giá_trị_cùng_một_tổng` lists values that add up to the same number. That is
  proof they are one population written down twice, not two populations.
- `chưa_ghăm` lists the axes the recommendation deliberately left open, because
  summing across them is correct — sites and districts inside a province. If
  anything unexpected appears there, stop and look before rendering.

So the interview changes shape. Do not walk the user through twenty columns.
Summarise what the file is, then ask at most three things:

1. **Which indicator**, offered as two or three real options with what each one
   would show — "số bệnh nhân đang điều trị", "tỷ lệ ức chế tải lượng virus".
   Name the ratio when the pair exists; a numerator on its own is a programme
   size map.
2. **Which period**, when more than one is present. Say which ones exist rather
   than asking them to remember.
3. **Result or target**, when the sheet holds both.

Everything else you pin yourself from the profile and state in one line: "Tôi
ghăm Disaggregate = 'By Age - Sex' và Result/Target = 'Result' để không đếm
trùng." Never ask a user to choose a disaggregation family by name.

Then render with the filters:

```bash
--value-column "Value" --where "Indicator Code=TX_CURR" --where "Fiscal Year=2026" --where "Quarter=Q2" --where "Disaggregate=By Age - Sex"
```

A `--where` that matches nothing stops the run and prints the values that exist,
so a typo costs one message rather than a wrong map.

For a ratio, name the two indicator values and let the engine divide:

```bash
--value-column "Value" --ratio-column "Indicator Code" --numerator "TX_PVLS Num" --denominator "TX_PVLS Den" --where "Quarter=Q2"
```

Each side is summed within a unit before the division. Dividing row by row and
averaging the quotients is a different number, and a wrong one whenever units
differ in size.

Two more things this kind of file will do to you. Place names arrive in English
and often predate the 2025 merger — that is handled, but read the match review
and say what was converted. And a column of districts (`SNU2`) describes a tier
that no longer exists and is not in the shapefiles: aggregate to province and
say so, rather than fuzzy-matching district names into the commune list.

## Two kinds of user, one skill

**If the user does not know what they want**, lead. Recommend one option, explain it in a sentence a nurse or an accountant would follow, and offer the runner-up. Describe map types by what they do, not by their name:

| Instead of | Say |
|---|---|
| choropleth | tô màu từng xã theo mức độ, đậm là cao |
| proportional symbol | vẽ vòng tròn, tròn to là số nhiều |
| choropleth + symbol | màu cho biết mức độ, vòng tròn cho biết số lượng thật |
| categorized | mỗi nhóm một màu riêng |
| change map | màu hai chiều: một phía tăng, một phía giảm |
| point map | chấm đúng vị trí từng cơ sở theo toạ độ |

A point map carries the same two channels as an area map, chosen by the same
rule: `--point-color-column` takes a **category** (loại cơ sở, mức ưu tiên) and
`--point-size-column` takes a **magnitude** (số lượt khám). Never the other way
round — sizing dots by a category invents an order the data does not have.
Dots use the same scale as their key, so the key is true for its own map.

**Known defect**: with long category labels the colour key runs out of its
column and lies across the map. `tràn_khung` reports it; shorten the group names
in the workbook, or leave `--point-color-column` off, until this is fixed.

**If the user already states what they want** — "vẽ cho tôi bản đồ tỷ lệ tiêm chủng cấp xã của Nghệ An, khổ dọc, chú giải 4 nhóm" — do not walk them through the interview. Confirm the parts you could not infer, note anything scientifically risky, and render.

## Ask few questions

Only ask what you cannot settle from the data. Everything else gets a sensible default that you **state out loud** rather than hide. Aim for about five questions:

1. Which dataset/sheet, when there is more than one.
2. Confirmation of your reading of the data and the recommended map.
3. Which measure to show, when several are equally plausible.
4. Scope, when commune data spans several provinces: one map per province, or one national map.
5. Layout — the report layout or the banner layout.
6. Language of the map. **Ask it. Do not infer it, and do not skip it because
   the answer seems obvious.** A Vietnamese officer often needs an English map
   for a donor report, and someone writing to you in English is often making a
   map for a provincial health department. The language of the chat says nothing
   about the language of the audience. This is `--language`; it is a separate
   decision from `--messages`, which does follow the chat and is never asked
   about. Leave `--language` off and the gate lists it under `phải_hỏi`.

Questions 5 and 6 arrive from the gate already worded, with their options and
the recommendation — do not compose your own version of either.

Then say what you defaulted: classification, number of classes, labels, figure
size, output folder. Those are in the plan table, each marked `[skill tự chọn]`.

Never ask a user who does not know GIS to *name* a classification method, a
projection, a colour ramp or an aggregation rule. Choose one. If they want it
changed, the plan row carries the alternatives written as outcomes — "mỗi nhóm
có số đơn vị bằng nhau" rather than "quantile" — which is a choice a person can
actually make.

## The gate before drawing

You do not have to remember to confirm the plan, and you cannot skip it.

Run `render` with every option you intend to use but **without** `--confirmed`.
Nothing is drawn and no folder is written. What comes back is:

| Field | What to do with it |
|---|---|
| `phương_án` | The numbered plan. Every row is already in the conversation's language and in plain words — print `mục` and `giá_trị` as they come. `ghi_chú` marks what the skill chose for the person rather than with them |
| `phương_án[].câu_hỏi` / `.lựa_chọn` | Present on rows that can still change. Do not read them out with the table; keep them for when the person wants that row changed, then hand them to the picker |
| `phải_hỏi` | Finished questions for the settings that are theirs to decide and that nobody supplied. Ask exactly these, one at a time |
| `cảnh_báo` | Anything scientifically risky. Say it before they agree, not after |
| `mã_xác_nhận` | The code that unlocks drawing — `null` while `phải_hỏi` is not empty |
| `lệnh_khi_đã_đồng_ý` | The same command with the code appended, ready to run |

Then **stop and wait**. When they agree, run that second command.

**While `phải_hỏi` has anything in it, no code exists.** Not a stale one, not a
wrong one — none. The plan table reads the same whether the map language was
chosen or merely defaulted, so a code alone cannot prove anybody was asked. The
only way forward is to ask, then put the answers on the command line as
`--language` and `--layout`; that empties `phải_hỏi` and a code is issued.

If they change anything, run the planning step again with the new settings: the
old code stops working the moment a setting moves, so a changed plan is always
shown again before it is drawn. That is deliberate — agreeing to five classes is
not agreeing to three.

**Do not rewrite the rows.** The wording arrives finished, and finished means
"Tô màu vùng kèm vòng tròn", not `choropleth-symbol`; "Mỗi nhóm có số đơn vị
bằng nhau — 3 nhóm", not `quantile, 3 nhóm`. Your job is the frame around the
table, not the table:

```
PHƯƠNG ÁN TRƯỚC KHI VẼ — đề nghị xác nhận

  <mỗi dòng của phương_án: số, mục, giá_trị, và ghi_chú nếu có>

Cảnh báo: <mỗi mục của cảnh_báo, nêu trước khi hỏi>

Xác nhận để tiến hành vẽ. Để thay đổi, nêu số thứ tự của mục cần sửa.
```

The heading and the closing line follow the conversation language: *PLAN BEFORE
DRAWING — please confirm* … *Confirm to draw. To change anything, give the number
of the line.*

The plan is editable, not just viewable. A row that carries `lựa_chọn` is changed
by handing those options to the picker. A row that does not — the measure, the
circle column, the slice — is changed in the person's own words: "thêm số ca đồng
nhiễm vào bản đồ", "bỏ vòng tròn đi". Take it, re-allocate, run the planning step
again.

`layers.allocate()` does the allocating. A map has exactly two quantitative
channels and each variable's semantic decides which one it may use: anything
normalised (percent, rate, percentage point, category) fills areas, anything
that is a magnitude (count, money) sizes circles. Never ask the user which
channel — the semantic already answers it, and filling areas by a raw count
draws population rather than the thing being measured.

When more variables are asked for than two channels hold, **do not refuse**.
The surplus goes to a second map in the same request; both land in one folder
and behind one picker on the interactive page. Say why they split:

> Hai biến đầu nằm trên cùng một tấm. Biến "Số ca đồng nhiễm" chuyển sang tấm
> thứ hai vì cũng là số đếm: hai bộ vòng tròn chồng lên nhau sẽ không còn phân
> biệt được kích thước. Cả hai tấm nằm trong cùng một trang HTML và chuyển đổi
> bằng hộp chọn.

Pass the variables with `--layer`, repeated. On a wide sheet each one is a
column name. **On a long sheet each one is an indicator value**, and
`--indicator-column` says which column those values live in:

```bash
--indicator-column "Indicator Code" --value-column "Value" \
  --layer "TX_PVLS Num / TX_PVLS Den|Status/Result=Total|Disaggregate=(total)" \
  --layer "TX_CURR|Status/Result=Total|Disaggregate=(total)" \
  --layer "HTS_TST_POS|Disaggregate=(total)" \
  --where "Fiscal Year=2026" --where "Quarter=Q2"
```

Three things in that line are worth reading slowly:

- **`A / B` is a rate.** The engine sums each side within a unit and then
  divides, and the result goes to the fill because a quotient is normalised.
- **Everything after a `|` is that indicator's own pins.** They are needed
  because two indicators on one map can want different values on the *same*
  column: TX_CURR carries a pre-computed `Total` beside its detail rows, while
  HTS_TST_POS has no `Total` at all. A single `--where` would have to choose one
  and silently lose the other — pinning TX_CURR's way erases HTS_TST_POS, and
  pinning HTS_TST_POS's way triples TX_CURR.
- **`--where` stays for what is common to all of them** — the period, usually.

Take the pins straight from each indicator's `lát_đề_xuất` in the profile. A pin
that matches nothing stops the run and prints the values that indicator actually
has, so a wrong guess costs one message.

For a single map you can also name the channels directly, with
`--fill-indicator` / `--symbol-indicator` and their `--fill-where` /
`--symbol-where`. Without a separate symbol indicator the circles would be read
off whatever row survived de-duplication — a real number from the wrong
indicator, at a believable size, with nothing on the map to say so.

Three rules for that block:

- **Number every line**, so the user can say "đổi mục 5 sang banner" instead of
  restating the whole plan.
- **Include what nobody asked about.** Mark the lines you chose yourself. Those
  are the ones most likely to be wrong, precisely because the user did not know
  there was a decision there to make.
- **Never skip it**, not even when the user stated everything precisely. They
  still have not seen the defaults.

When a line changes, re-print the block with the change in place and ask again.
Do not carry a mental note of an amendment into the render command.

## Language

### `--messages vi|en` — the conversation

Everything the script says *to you about the data* comes back in this language:
the guardrail warnings, the reason behind each ranked map option, the verdict on
each sheet, the note explaining how a sheet had to be read, and the hard errors.
Pass it on every command, set to the language the user is writing in. The default
is `vi`.

Relay those sentences as they come. They are worded with some care — "grey = not
surveyed, not zero" is a cartographic claim, not a turn of phrase — and
retranslating them on the fly is how the care gets lost.

It does not touch the map, and it does not touch file names.

### `--language vi|en` — the map

`--language vi|en` sets every string the script generates itself: the kicker, the automatic insight sentence, "Chưa có số liệu"/"No data", the source and method footer, and the north arrow letter (`B`/`N`). The chosen code is appended to every file name — `ten-ban-do_vi.png`, `map-name_en.png` — so both editions of one map can live in the same folder.

It also sets **both digit separators**: Vietnamese groups thousands with a dot
and marks the decimal with a comma (`35.156`, `99,74%`), English does the
opposite (`35,156`, `99.74%`). This applies to the legend, the labels, the
subtitle, the scale bar and the interactive page's hover box alike, so one plate
never gives the same character two meanings.

Three things the script will **not** translate, because they are not its text to translate:

- **Place names.** A Vietnamese commune keeps its Vietnamese name on an English map. That is correct cartographic practice, not a gap.
- **The title.** Pass `--title` in the chosen language.
- **Legend titles**, which default to the Excel column headings. On an English map, pass `--legend-title` and `--symbol-legend-title` yourself, otherwise the legend will still read "Bao phủ 2026 (%)" on an otherwise English page.

So when the user picks `en`, write the title and both legend titles into the command. Do not translate the workbook's column names anywhere else — the profile, the match review and the warnings stay as they are.

If the user wants both editions, run `render` twice with the same options and different `--language`; the shared classification is recomputed identically, so the two maps stay comparable.

## Time series: video and interactive page

`--animate` with `--period-column` renders the whole series instead of a still map. Ask which format the user wants; `--animation-formats` defaults to `both` because the second one costs almost nothing.

**`video`** — MP4, each period held about two seconds and joined by a short cross-dissolve, with a timeline under the map. For playing in a talk.

**`html`** — the series joins `ban_do_theo_thoi_gian.html`, the interactive page described under Output, with a slider, a play button and arrow keys added. For sending to someone who wants to explore it themselves.

The page carries **one frame per period**, not the video's hundreds, so it usually ends up *smaller* than the MP4.

Two things make an animated map honest, and both are enforced:

- **One classification for every frame.** Recomputing breaks per period would make colours move while the data stands still.
- **No invented in-between values.** The dissolve is a transition, not a claim about a measurement between two reporting periods. Never offer to interpolate values to make it smoother — for surveillance data that is fabrication.

**Several map frames each get their own video.** Commune data spread over a few
provinces produces one video per province, and they all share one set of class
breaks and one circle scale computed across the whole set — a colour has to mean
the same thing in Nghệ An as in Hà Nội, and in every period of both. The result
carries `số_khung` and a `khung` list; the interactive page gathers them all
behind one picker.

MP4 needs ffmpeg. Without it the run falls back to GIF and says so in the result; relay that, because a GIF is bigger and coarser.

Say plainly what animation costs: a viewer cannot compare a frame against one they saw three seconds ago. If the user's real question is "which provinces changed most", a change map or several maps side by side answers it better. Offer that once; if they still want video, build the video.

## Provinces before and after the 2025 merger

Vietnam went from 63 provinces to 34 in 2025. Any series that starts earlier is reported on names that do not exist on the map, and those rows would silently disappear from the join.

The shapefile's `sap_nhap` field records which former provinces went into each current one, so the conversion is automatic and exact — no crosswalk to maintain. Converted rows are marked `merged` in the match review and stay high-confidence, because this is an administrative fact rather than a guess.

Tell the user what the conversion did to their numbers: counts from former provinces are added together, and rates are recomputed as a weighted mean, never averaged. Commune boundaries were also redrawn in 2025 and some communes were split between new units, so historical commune data cannot be converted this way — say so rather than producing a map that looks fine.

## When the user's choice is scientifically wrong

The script returns a `cảnh_báo` list; each item has `vấn_đề`, `vì_sao` and `nên_làm` already written in plain Vietnamese. Relay `critical` and `warning` items before rendering.

**Warn, propose, then do what the user decides.** Do not refuse, and do not silently override. The common cases:

- Very few units have data → colouring the whole area implies complete surveillance.
- Summing percentages or rates across duplicate rows → arithmetically meaningless.
- Colouring raw counts → the map ends up showing area and population.
- Several reporting periods in one sheet → values get double counted; offer to filter with `--period-column`/`--period`.
- Unmatched or fuzzy-matched place names → some rows silently vanish, or land on the wrong commune.

## Matching place names

Never ask for administrative codes. The script matches names, province first and then commune within that province, and records *how* each row matched: `exact`, `normalised`, `fuzzy`, or `override`.

A fifth outcome, `ambiguous`, means the name matches more than one unit in the province once accents are stripped — "Cam Giang" against both Cẩm Giang and Cẩm Giàng. The row carries the first candidate's shape id so the review table can show what would have been picked, but `render` **leaves it off the map by default** and the unit stays grey. Drawing a coin flip that the finished map gives no sign of is worse than showing nothing. Tell the user which row it was, offer `fix-match`, and use `--ambiguous keep` only if they ask for the guess.

Before rendering, show the counts and **list every fuzzy, ambiguous and unmatched row** — those are the ones that can be wrong. When the user confirms a correction, persist it so later runs reuse it:

```bash
python skills/easy-map/scripts/easy_map.py fix-match --project-root . --admin-level commune --province "Hà Nội" --name "Xa Minh Chau" --shape-id 1234
```

## Framing

Let `--map-scope auto` decide unless the user asks otherwise:

- province-level data → national map of all 34 provinces
- commune data in one province → that province's full commune set, with no-data communes kept as context
- commune data in a few provinces (≤5) → one map per province, sharing one colour scale and one symbol scale
- commune data spread wider → national commune map

The figure size is computed from the shape of the area, so a tall province gets a tall page and a wide one gets a wide page. Do not force 16:9.

**One request, one `render`, and no maps nobody asked for.** The scope you agree
in the plan is the whole job: `auto` already returns every map the request needs
— a series of three provinces is one `render` call, not three. Do not follow it
with an extra "overview" pass, and in particular do not reach for
`--map-scope matched-only`. That scope drops every unit without data, which
turns "we surveyed 12 of 34 provinces" into a picture of a country with 12
provinces in it. It exists for the rare case where someone asks for it out loud;
choosing it unprompted is a cartographic error, not a bonus. The same goes for a
second language edition: render it only when they ask for both.

**Hoàng Sa and Trường Sa go to an inset.** On a national map they are fragments
of Đà Nẵng and Khánh Hòa reaching out to 117°E, and framing them with the
mainland leaves the mainland 56% of the width — Hà Nội becomes too small to
label. The engine frames the mainland and carries the archipelagos in a boxed
inset at the bottom right, coloured from the same data as the main map. Nothing
is deleted: only the view is narrowed, so every value, area and label anchor is
unchanged. The result appears as `khung_phụ` in the map's metadata, including
what share of the width the mainland ended up with (69.4% on the current
shapefile). A map of one province gets no inset — there is no
mainland-versus-islands story when the reader asked for Khánh Hòa.

The island marks in the inset are drawn enlarged. A Trường Sa cay is a few
hundred metres across, which at this scale is less than a pixel; enlarging marks
too small to show is standard practice, and the inset states position rather
than extent. Say so if a reader asks why the islands look bigger there.

## Design rules the script already enforces

Do not fight these; they exist because each one was a real defect:

- Merriweather for headlines and Open Sans for everything else, both bundled in `assets/fonts`. If a font fails to load the run **stops** rather than substituting Arial.
- One sequential blue ramp, light to dark, and a pink-to-blue diverging ramp for change. Never rainbow, never red/green.
- Count legends use whole numbers only.
- Percent and rate-per-capita are labelled differently; a rate per 100.000 never gets a `%`.
- Class breaks that would be empty or meaninglessly narrow are merged, and the adjustment is reported.
- All maps in one job share breaks and symbol scale, so the same blue and the same circle mean the same thing on every sheet.
- Symbol area, not diameter, follows the value.
- Labels are placed by measuring the real text box, trying eight positions, and drawing a leader only when the label had to move.
- Grey always means "chưa có số liệu", stated in the footer.

Read `references/cartographic-style.md` and `references/layout-system.md` before changing anything visual.

## One request, one folder

The moment the user asks for a map — before you profile anything, before you ask a single question — open the run folder:

```bash
python skills/easy-map/scripts/easy_map.py start-run --project-root .
```

It creates `output/yyyy-mm-dd_hh-mm-ss/` stamped at **that** moment and prints the name. Pass that name as `--run-folder` to every `profile` and `render` call for the rest of the request. The timestamp then records when the user asked, not when rendering happened to finish — which matters because the conversation in between can take a while.

Everything belonging to the request lands in that one folder: the dataset profile, the match review, every image, the per-map metadata, and `run_manifest.json`. Nothing is written loose in `output/`.

Reusing the same `--run-folder` is deliberate, so several renders in one request — a Vietnamese and an English edition, or two layouts — stay together. `run_manifest.json` appends one entry per render rather than overwriting.

`start-run` is the **only** command that opens a folder. It leaves that run open, so a `profile` or `render` you forget to name still writes into it instead of starting a second folder — which is what used to litter `output/` with folders holding nothing but a profile. The run closes itself once nothing has been written to it for a few hours, so a later request cannot land in an older folder.

Do not lean on that. Pass `--run-folder` every time: it is what keeps the contract readable, and it is the only thing that still works when a request stretches across a long conversation. The safety net exists for the mistake, not instead of the habit.

Starting a second map request in the same conversation means calling `start-run` again. Skipping it puts the new request's maps in the previous request's folder — and, because the interactive page gathers every map in the folder, into the previous request's page as well.

## Commands

Every command takes `--messages vi|en`. Set it once, from the user's own
language, and use the same value throughout the request — it is left out of the
examples below only to keep them readable. If the user writes in English, every
example here gains `--messages en`.

Dependencies are supplied per run:

```bash
uv run --with pandas --with openpyxl --with geopandas --with matplotlib --with mapclassify --with rapidfuzz python skills/easy-map/scripts/easy_map.py list --project-root .
```

Bring in a file the user attached, before anything else reads it:

```bash
uv run --with pandas --with openpyxl --with geopandas --with matplotlib --with mapclassify --with rapidfuzz python skills/easy-map/scripts/easy_map.py import --project-root . --run-folder 2026-08-05_14-30-00 --file "/tmp/uploads/so-lieu.xlsx"
```

Profile before asking, into the run folder opened by `start-run`:

```bash
uv run --with pandas --with openpyxl --with geopandas --with matplotlib --with mapclassify --with rapidfuzz python skills/easy-map/scripts/easy_map.py profile --project-root . --run-folder 2026-08-05_14-30-00 --excel "input/example.xlsx" --sheet "Sheet1"
```

Render after the user confirms the match review, into the same folder:

```bash
uv run --with pandas --with openpyxl --with geopandas --with matplotlib --with mapclassify --with rapidfuzz python skills/easy-map/scripts/easy_map.py render --project-root . --run-folder 2026-08-05_14-30-00 --excel "input/example.xlsx" --sheet "Sheet1" --admin-level commune --province-column "Tỉnh/thành phố" --commune-column "Xã/phường" --map-type choropleth-symbol --value-column "Bao phủ 2026 (%)" --symbol-column "Số ca phát hiện 2026" --layout report --language vi --title "..."
```

On Windows, keep uv's cache inside the project if it lacks permissions elsewhere:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"; $env:UV_PYTHON_INSTALL_DIR = "$PWD\.uv-python"; $env:PYTHONUTF8 = "1"
```

Where `uv` is unavailable but the six packages are already installed, call the script directly — it needs nothing else on `sys.path`:

```bash
python skills/easy-map/scripts/easy_map.py list --project-root .
```

## Output

PNG only by default — SVG risks losing the packaged fonts on another machine. Offer `--formats both` only when the user needs a large-format print.

The request's folder ends up holding:

```
output/2026-08-05_14-30-00/
├── dataset_profile.json                        từ profile
├── match_review_commune_<dataset>.csv          bảng ghép địa danh đã dùng
├── <ten-ban-do>_<layout>_vi.png                một file cho mỗi bản đồ
├── <ten-ban-do>_<layout>_vi_metadata.json
├── ban_do_tuong_tac.html                       mọi bản đồ tĩnh, mọi ngôn ngữ
├── ban_do_theo_thoi_gian.html                  mọi bản đồ theo thời gian
├── .interactive/                               kho dựng trang, không phải đầu ra
└── run_manifest.json                           mọi tham số, đủ để dựng lại
```

Each map also gets `<ten-ban-do>_..._so-lieu.csv`: **the numbers the map was
drawn from**, after name matching, filtering and aggregation. Not the input
sheet — this is what is actually behind the colours and the circles, with both
the raw value and the formatted one, so a figure in a report can be checked
without repeating every step by hand. Offer it whenever somebody asks "where
does this number come from".

The match review is named after the dataset and the administrative level, so one request can map a province workbook and a commune workbook without their reviews colliding.

Image file names carry the layout and then the language code, so a Vietnamese and an English edition — and a `report` and a `banner` edition — of the same map coexist in one folder instead of overwriting each other.

### The interactive page

Every request also gets an HTML page — always, without being asked. There are exactly two, they never link to each other, and each one is **completely self-contained**: images are embedded, so a single file can be emailed on its own and still work with no network, no shapefile and no sibling PNG. Pass `--no-html` only if the user explicitly does not want one.

Each page gathers **every map of its kind in the request**, so it is rebuilt on each render rather than overwritten: render the English edition after the Vietnamese one and the page ends up holding both, with a `VI`/`EN` switch on it. A reader can pick a map, switch language, search for a unit by name with or without diacritics, zoom (Ctrl + scroll, or the `+` button), and hover any unit to read its values.

**Clicking a unit opens its detail panel** on the still page. The panel grows out
of the unit's own place on the map, so the eye follows one movement rather than
losing the thread and finding a dialog. It holds the unit drawn large at the top
— its name in one corner, the close button in the other — over a two-column grid
of its numbers: the mapped value or "chưa có số liệu", the circle value where
there is one, and then, read from the shapefile rather than from the dataset,
area, population and density. On a point map, where the numbers belong to the
dots and not to the areas, the grid instead counts the locations that fall inside
the unit. Escape, the close button or a click on the wash all fly it back.

Two things follow from how it is built, and both are worth saying to the user rather than letting them discover it:

- Embedded images are **150 dpi, sized for a screen**. The `.png` files beside the page are the print-quality ones. Zooming past roughly 3× starts to soften the map's own labels.
- Zoom magnifies the whole plate, title and legend included, because the page shows the rendered map rather than redrawing it. That is the cost of keeping the design and the bundled fonts exactly as they appear in print.

## Before you hand over

**Look at the rendered PNG.** Exit code zero is not evidence that a map is readable. Check that nothing is clipped at the page edge, labels do not collide, every leader line ends on a label, the legend order runs low to high, and the locator does not sit on top of anything.

**Read `tràn_khung` before anything else.** It lists text that left the space it
was given: `ra_khỏi: "trang"` means it will be cut when the file is written,
`ra_khỏi: "cột chú giải"` means it stayed on the paper but ran out of the left
column and across the map. The usual cause is a `--legend-title` or `--title`
too long for the layout — shorten it and render again rather than handing over a
plate with a sentence lying over the country. An empty list is the normal result.

Read the label report too. `chỉ_hiện_tên` lists units too crowded to fit their value, so the name is printed alone — a reader cannot tell that from a unit with no data, so name them. `bỏ_vì_chật` lists units that got no label at all. Both are still readable by hovering the interactive page; say so.

Then reply with the run folder path, the image paths, **the interactive page and what it is for**, what you chose on the user's behalf, and any warning they accepted. Say plainly that the HTML file can be sent on its own — people assume a web page needs the folder around it.

**Never build a file link yourself.** `render` returns `mở_tệp`: one entry per
file worth opening, each with `tên`, `đường_dẫn` and a finished `liên_kết`. Copy
`liên_kết` exactly. Do not prepend a scheme, do not convert separators, do not
translate a drive letter into a mount point.

The reason is specific. A real Codex run turned
`D:\temp\agentic-gis\output\...\ban_do_tuong_tac.html` into
`file:///C:/mnt/d/temp/agentic-gis/output/...` — the wrong drive, and a mount
point that does not exist on the machine holding the file. It had assumed a
Linux sandbox it was not running in. The link opened nothing, and the user had
no way to tell that from a map that had failed to render. `mở_tệp` is computed
on the machine the file is actually on, so there is nothing left to assume.
