# Hansard Extractor — V3

A Streamlit app that extracts structured, clean speaker-turn data from Malaysian
Dewan Rakyat Hansard PDFs and enriches it with MP and cabinet minister information.

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Select your repo, branch `main`, main file path `app.py`.
4. Click **Deploy**.
5. Upload roster files via the sidebar after the app loads.

---

## How to use

### 1 — Upload roster files (sidebar, optional but recommended)

| Slot | File | What it provides |
|------|------|------------------|
| MP Roster | `Ahli_Dewan_Rakyat_Parlimen_15_updated.xlsx` | Constituency for all 222 MPs |
| Original Cabinet | `rosters/Kabinet_Asal_19122022.xlsx` | Cabinet as of 19 Dec 2022 |
| After First Reshuffle | `rosters/Kabinet_Reshuffle_Pertama.xlsx` | Cabinet after first reshuffle |
| After Final Reshuffle | `rosters/Kabinet_Reshuffle_Akhir.xlsx` | Cabinet after final reshuffle |

All roster files are included in the `rosters/` folder — you can drag them straight
into the sidebar uploaders.

### 2 — Upload Hansard PDFs (main area)

Upload up to **5 PDFs** at once. The app shows the page count of each and processes
all pages automatically — no page range needed.

### 3 — Process and export

Click **Process All Documents**. After processing:

- Review results in the **Data Preview** table.
- Filter by speaker using the **Filter** expander.
- Download individual **XLSX files** (one per PDF, named after the source file).
- Download a combined **JSON** of all files together.

---

## Output columns

| Column | Description |
|--------|-------------|
| `Speaker` | Personal name as it appears in the PDF |
| `Normalized_Speaker` | Name with all honorific prefixes stripped |
| `Role` | Ministerial/official role (from PDF bracket or minister roster) |
| `Portfolio` | Full Jawatan from minister roster (blank for non-ministers) |
| `Is_Minister` | `Yes` if matched to any cabinet roster |
| `Is_Deputy` | `Yes` if matched as Timbalan Menteri |
| `Cabinet_Version` | Which cabinet(s) the speaker appeared in — see below |
| `Constituency` | Parliamentary constituency |
| `Roster_Match` | How the constituency was resolved — see below |
| `Speech` | Cleaned speech text |
| `Page` | PDF page number where the turn begins |
| `Document_Name` | Source PDF filename |

### `Cabinet_Version` values

| Value | Meaning |
|-------|---------|
| `original` | Only in the original cabinet (19 Dec 2022) |
| `first_reshuffle` | Only in the first reshuffle cabinet |
| `final_reshuffle` | Only in the final reshuffle cabinet |
| `original+first_reshuffle` | Present in both |
| `original+first_reshuffle+final_reshuffle` | Present in all three |
| *(combinations)* | Any subset of the three versions |

### `Roster_Match` values

| Value | Meaning |
|-------|---------|
| `exact` | Name matched directly after normalisation |
| `nobin` | Matched after stripping `bin`/`binti` (informal name lists) |
| `binti_normalised` | Women's name variant matched (e.g. `Azalina Othman Said` ↔ `Azalina Binti Othman`) |
| `last_token` | Matched on unambiguous family-name suffix |
| `first_token` | Matched on unambiguous given name |
| `backfill` | Constituency filled from another turn by the same speaker in the same document |
| `—` | No match — legitimate non-MP (e.g. Setiausaha, Tuan Yang di-Pertua) |

---

## Roster file format

All three cabinet roster files use the same standardised column format:

| Column | Description |
|--------|-------------|
| `Bil` | Row number |
| `Nama` | Clean name — no honorific prefixes, consistent across all three files |
| `Jawatan` | `Menteri` or `Timbalan Menteri` |
| `Kementerian` | Ministry / department name |
| `Kawasan Parlimen` | Constituency (blank for senators) |
| `Timbalan` | `Ya` if deputy minister, blank otherwise |
| `Senator` | `Ya` if senator, blank otherwise |
| `Kabinet` | Cabinet label for traceability |

The MP roster uses a different format: `BIL` \| `NAMA PENUH` \| `KAWASAN PARLIMEN`.
Any file with those columns will be accepted.

---

## What was fixed (V1 → V3)

| # | Issue | Fix |
|---|-------|-----|
| 1 | Ministerial role treated as Speaker; real name put in Constituency | Bracket with `bin`/`Dato`/etc. is the real name → outer text becomes `Role` column |
| 2 | Deputy PM entry silently dropped (missing `]` in PDF) | `UNCLOSED_RE` fallback regex |
| 3 | Unicode curly-quote `'` (U+2019) broke regex matching | `\u2018\u2019` added to character class |
| 4 | Speakers without a bracket got blank constituency | Two-pass extraction: PDF observation lookup + roster back-fill |
| 5 | `DR.19.12.2022` page headers bleeding into speech (47 entries) | `_is_header_only_block()` checks all lines in block, not just the start |
| 6 | Next speaker's line embedded in previous speaker's speech (39 entries) | `_split_block_by_speakers()` splits mid-block on speaker-line pattern |
| 7 | Indian patronymic names (`a/l`, `a/p`) not detected | Added `/` to `_CHAR` regex character class |
| 8 | `KeyError: 'Speaker'` crash on empty result | Guard with `st.stop()` + user warning |
| 9 | `use_container_width` deprecation warnings | Replaced with `width="stretch"` |
| 10 | Senator/special-title names stripping incorrectly | Added `SENATOR DATUK SERI`, `DATUK AMAR`, `HAJAH`, etc. to `_STRIP_TITLES` |

## What's new in V3

- **Up to 5 PDFs** processed simultaneously (was 3)
- **No page range input** — processes all pages, shows page count as info metric
- **Individual XLSX export per PDF** — filename matches source PDF (e.g. `DR-19122022.xlsx`)
- **MP roster lookup** — 222 MPs, 4-strategy matching (exact → binti_normalised → last_token → first_token)
- **Three-cabinet minister roster** — original + first reshuffle + final reshuffle, all in standardised format
- **New output columns** — `Portfolio`, `Is_Minister`, `Is_Deputy`, `Cabinet_Version`
- **`nobin` match strategy** — handles informal name lists that omit `bin`/`binti`
- **Light theme** with indigo/pink accent gradient
- **Speech column cleaned** — page headers, standalone page numbers, and embedded speaker lines removed

---

## Included roster files

```
rosters/
├── Ahli_Dewan_Rakyat_Parlimen_15_updated.xlsx   — 222 Dewan Rakyat MPs
├── Kabinet_Asal_19122022.xlsx                   — 49 ministers (original, 19 Dec 2022)
├── Kabinet_Reshuffle_Pertama.xlsx               — 57 ministers (after first reshuffle)
└── Kabinet_Reshuffle_Akhir.xlsx                 — 62 ministers (after final reshuffle)
```

---

## Requirements

- Python 3.11+
- Dependencies: `streamlit`, `PyMuPDF`, `pandas`, `openpyxl` — see `requirements.txt`
