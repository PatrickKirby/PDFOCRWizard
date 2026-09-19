# PDF OCR Extractor: operator's manual

## Contents

| Welcome | Installation | Usage and Output Files | Technical Details |
|---|---|---|---|
| [What this is](#what-this-is) | [Supported platforms](#supported-platforms) | [Quick start](#quick-start) | [Architecture at a glance](#architecture-at-a-glance) |
| [Who this is for](#who-this-is-for) | [Before you start](#before-you-start) | [Command-line reference](#command-line-reference) | [How it works](#how-it-works) |
| [What it does](#what-it-does) | | [Running it](#running-it) | [Troubleshooting](#troubleshooting) |
| [What this tool doesn't do](#what-this-tool-doesnt-do) | | [Excluding things you don't want](#excluding-things-you-dont-want) | [Version notes](#version-notes) |
| [Limits and known trade-offs](#limits-and-known-trade-offs) | | [Speed, caching and per-page overrides](#speed-caching-and-per-page-overrides) | [Glossary](#glossary) |
| [Emphasis, columns and figures](#emphasis-columns-and-figures) | | [Reading the run output](#reading-the-run-output) | [Before you rely on the output](#before-you-rely-on-the-output) |
| | | [Reading the check output](#reading-the-check-output) | |
| | | [The spreadsheet](#the-spreadsheet) | |
| | | [The quality report](#the-quality-report) | |

---
# Welcome

## What this is

The full reference for running PDF OCR Extractor: every flag, every output
file, what each troubleshooting message means, and the reasoning behind the
tool's limits. For the two-paragraph pitch and a quick install, see
`README.md`; this document assumes you already know what the tool is for
and want to operate it.

## Who this is for

Scanned business, legal, technical documents such as tenders,
contracts, reports, forms, and similar paperwork where tables, headings and
emphasis carry meaning and need to survive the conversion.

This is not a general-purpose OCR library, a handwriting reader, or a layout
digitiser for magazines, checkbox forms, or non-English body text. See
[What this tool doesn't do](#what-this-tool-doesnt-do) before running it
against something it wasn't built for.

## What it does

Every page is rendered as an image and OCR'd. That's the whole trick, and
it's why the tool doesn't care whether the PDF already has a text layer,
whether that layer is flagged to block copying, or whether it's missing
entirely. Nothing here reads the PDF's internal text; it reads the page
the way you would, as a picture, and works out what's on it.

It does what it says on the tin: it takes each page and extracts the
text. It doesn't stop there:

- Tables are rebuilt as native Word tables and saved a second time to
  their own spreadsheet, ready to filter and total.
- Bold is detected from ink, not guessed; italic is available if you ask
  for it.
- Multi-column pages are read in the right order, not straight across the
  gutter.
- Letterhead, footer bands and ink stamps are lifted automatically; a
  template image removes anything else, wherever it appears.
- Pages tilted during scanning are straightened, and stray specks are
  cleaned off before OCR runs.
- Weak words are highlighted in place, so you check them where they sit
  rather than against a separate list.
- A quality report flags exactly what needs a human: gaps in an
  identifier sequence, rejected page-order readings, low-confidence
  lines, all where human-in-the-loop review matters.
- It handles one file, several, or a whole folder in one run, and can be
  driven by a config file for jobs that need per-page treatment.

The full mechanics behind each of these: [How it works](#how-it-works).

## What this tool doesn't do

- Read handwriting.
- Reproduce exact page layout. Margins, line breaks and pagination are not
  recreated, but reading order is.
- Detect italics reliably.
- Recognise a table with no ruling lines.
- Repair a randomly shuffled scan.
- Open a password-encrypted PDF. Decrypt it first; a permission flag
  blocking copying is not the same thing, and that one the tool ignores
  by design.

## Limits and known trade-offs

- **English body text only**, is dropped by design rather than garbled:
  character mix and collapsed confidence flag another script before it
  reaches the page. 
- **Italic is opt-in because it's unreliable.** Ink slant is a far noisier
  signal than stroke width, and a wrong italic mark is worse than a missing
  one.
- **Deskew does nothing below one degree of tilt**, deliberately: resampling
  softens the hairline rules that table detection depends on.
- **Figure extraction is conservative.** Rejecting decorative bars means
  also rejecting a genuine figure that happens to be wide and thin.


## Emphasis, columns and figures

**Bold** is estimated because a scan carries no font metadata. The tool
measures stroke width against line height, decides per line, and overrides
for a word markedly heavier than its line.

**Italic** uses ink slant, far noisier than stroke width. `--italic` turns
it on; verify the result before trusting it.

**Columns** are detected from the gutter between blocks of words, then
guarded: both sides must hold a real share of the words across several
lines. Without that guard, a contents page, whose page numbers sit in
their own column, gets read in the wrong order. Pages read as columnar are
named in the report.

**Low-confidence words are highlighted yellow** in the document itself, so
checking happens in place rather than against a list of line numbers. Every
weak line is re-read at double size in single-line mode first, and the
better reading kept, so what remains highlighted has already survived two
attempts. `--no-highlight` and `--no-second-pass` turn these off.

**Tables keep their original column proportions**, measured from the rule
positions. A table is treated as continuing overleaf only when column
count, header and column widths all agree; when they don't, the report
names which test failed and on which page.

**Figures** are ink that is neither table nor text: diagrams, charts,
logos. Solid bars, rules, and anything overlapping a table are rejected as
decoration or duplication.

---

# Installation

## Supported platforms

The tool runs on Windows, macOS and Linux. It is developed and tested
primarily on Windows; the Python code carries no platform-specific
dependency, and the only difference across platforms is how Tesseract
gets installed and which convenience launcher you use. `pdfocr.bat`
wraps the tool on Windows; `pdfocr.sh` does the same on macOS and Linux.
Both forward your arguments to `scan_to_docx.py`, so calling the
script directly with `python` (or `python3`) works identically everywhere.

## Before you start

Two things need to be on your system before you run a conversion:
Python 3.12 or later (the floor `scipy` sets; tested on 3.14), and
Tesseract, the OCR engine the tool drives. Both are one-time installs.

**Windows**

```
winget install --id UB-Mannheim.TesseractOCR -e
```

Python 3 is required separately if not already installed; get it from
[python.org](https://www.python.org/downloads/) or the Microsoft Store,
and make sure "Add to PATH" is checked during setup.

**macOS**

```
brew install tesseract
```

Python 3 ships with recent macOS versions; if `python3 --version` fails,
install it with `brew install python3`.

**Linux**

```
sudo apt install tesseract-ocr    # Debian, Ubuntu
sudo dnf install tesseract        # Fedora
```

Python 3 is preinstalled on almost every current distribution.

**All platforms**, once Python and Tesseract are in place, install the
Python dependencies from this folder:

```
pip install -r requirements.txt
```

Run that once per machine. It installs eight packages, each doing one
job in the pipeline:

| Package | Does what |
|---|---|
| `pymupdf` | Renders PDF pages to images and reads page metadata |
| `pytesseract` | Drives the Tesseract OCR engine from Python |
| `pillow` | Image handling: resizing, template matching |
| `numpy` | Pixel-array math behind ink masks, kernels and measurements |
| `scipy` | Image processing: deskew, despeckle, region analysis |
| `python-docx` | Writes the output `.docx` |
| `openpyxl` | Writes the output `.xlsx` spreadsheet |
| `pyspellchecker` | Dictionary lookup behind spelling repair and the quality report |

Tesseract itself is not a Python package; it's a separate program that
`pytesseract` calls, which is why it gets its own install step above.
The full dependency picture, including which module uses what, is in
[Architecture at a glance](#architecture-at-a-glance).

After all of this, have a scanned PDF ready to test against, ideally one
with at least one ruled table, so you can see the table reconstruction
work on the first run.

---

# Usage

## Quick start

```
pip install -r requirements.txt
python scan_to_docx.py "path/to/scan.pdf"
```

Three files land beside the PDF, in a date-stamped folder by default:
`OCR_2026-09-18/scan_OCR.docx`, `scan_OCR_tables.xlsx`, `scan_OCR.quality.md`.
Open the `.quality.md` file first; it names what needs a human look before
you open the document itself.

Every flag, and how to read what the run prints: the rest of this manual.
Why the pipeline is built the way it is: `README.md`.

## Command-line reference

```
python scan_to_docx.py <pdf> [pdf ...] [options]
```

`<pdf>` accepts one file, several files, or a folder (every `*.pdf` inside
it, not recursive). No arguments at all launches the interactive menu
instead; see [Running it](#running-it).

| Flag | Default | Effect |
|---|---|---|
| `-o`, `--out` | date-stamped folder | output `.docx` for one file, or a folder for several |
| `--same-dir` | off | write output beside each source PDF instead of a date-stamped folder |
| `--config` | none | read any of these settings from a JSON job file |
| `--page-options` | none | per-page overrides, config file only |
| `--no-xlsx` | off | skip the parallel spreadsheet |
| `--dictionary` | none | text file of extra words the spell checker should accept |
| `--exclude-pages` | none | pages to drop entirely, e.g. `1,36-37` |
| `--exclude-template` | none | image of a region to remove wherever it appears; repeatable |
| `--keep-furniture` | off | keep coloured letterhead and footer bands |
| `--keep-stamp` | off | keep ink stamps instead of lifting them |
| `--no-reorder` | off | trust scan order instead of printed page numbers |
| `--no-emphasis` | off | skip bold/italic detection |
| `--italic` | off | also detect italics (noisy; verify before trusting) |
| `--no-figures` | off | do not embed diagrams and images |
| `--no-autofix` | off | report lost-space errors instead of repairing them |
| `--no-highlight` | off | do not highlight low-confidence words |
| `--no-second-pass` | off | do not re-read weak lines at higher zoom |
| `--no-deskew` | off | skip straightening |
| `--no-despeckle` | off | skip dust removal |
| `--jobs` | half the cores | worker process count |
| `--no-cache` | off | ignore cached page analysis for this run |
| `--clear-cache` | off | delete the cache before running |
| `--dpi` | 300 | render resolution |
| `--scale` | 1 | extra Lanczos upscale after rendering, for poor scans |
| `--tesseract` | auto-detected | explicit path to the Tesseract executable |

`python scan_to_docx.py --help` prints this same table grouped by category.

## Running it

### One file

```
python scan_to_docx.py "path/to/scan.pdf"
```

Nothing is written until the whole document has been assembled, so an
interrupted run leaves no half-file.

### Several files at once

```
python scan_to_docx.py scan1.pdf scan2.pdf
python scan_to_docx.py "path/to/folder/"
```

A folder argument expands to every `*.pdf` inside it. Each file gets its
own three outputs; one bad file prints `FAILED` and doesn't stop the rest
of the batch. A summary line totals pages, paragraphs, tables and
highlighted words across the run, and names every output folder used.

### No arguments: the interactive menu

```
python scan_to_docx.py
```

Prompts for file(s) or a folder, shows page count and text-layer status for
each before doing anything, confirms the plan (source, output location,
exclusions, estimated time), then converts. Also handles re-checking a
finished document, clearing the cache, and managing the `--dictionary` word
list.

## Excluding things you don't want

Three ways, strongest last.

**By page.** `--exclude-pages 1,36-37` drops those pages entirely: covers,
blank versos, signature sheets.

**By example.** `--exclude-template footer.png` removes any region matching
that image, wherever it appears. Crop the sample from any page, a
letterhead, a footer strip, a stamp, a watermark, and pass it. The flag
repeats, so several samples can be given at once. Matching is on ink shape,
not brightness, so it survives exposure drift between pages.

**By default.** Coloured letterhead and footer bands, and ink stamps, are
removed without being asked. `--keep-furniture` and `--keep-stamp` turn
that off.

## Speed, caching and per-page overrides

Pages are analysed in parallel, half the cores by default; `--jobs N`
changes that. Each page's analysis is cached against the PDF's content and
the run's settings: changing a setting that affects pages re-analyses them,
changing one that only affects assembly doesn't. `--no-cache` ignores the
cache for one run; `--clear-cache` empties it.

When one page needs different treatment from the rest, use the config
file, keyed by printed page number:

```json
{"page_options": {"12": {"single_column": true},
                  "19": {"no_tables": true},
                  "37": {"exclude": true}}}
```

`single_column` stops column detection on a page it gets wrong. `no_tables`
treats a page's ruled grid as prose. `keep_stamp` and `keep_furniture`
spare a page the usual cleaning. `exclude` drops it.

---

# Output Files

## Before you rely on the output

Remember, the output is an interpretted extract of the source, not a copy of it. The pipeline
checks structure: whether a table survived, whether a heading was
recognised, whether an identifier sequence has a gap. But errors can still arise and, ultimately, human inspection is the best quality gate. So please, before any number, date, deadline or clause reference is quoted, priced 
or committed to, read it against the original PDF and do a sanity check.

## Reading the run output

```
37 pages at 300 dpi, 37 to convert, 8 worker(s)
pages analysed in 22s
scan out of order; reading by printed number (scan page, printed page): [(12, 13), (13, 12)]
footer readings ignored as inconsistent: [(26, 36), (36, 2)]
11 page(s) without a trusted page number; their position is assumed correct
saved out/scan_OCR.docx
268 paragraphs, 11 tables, 0 figures, 789 bold and 0 italic runs, 54 word(s) highlighted
tables also in out/scan_OCR_tables.xlsx (11 sheet(s))
```

| Line | What it means | When to worry |
|---|---|---|
| `scan out of order` | The scan's physical order disagrees with the printed page numbers; output follows the printed numbers. | Always read the pairs. If they look wrong, rerun with `--no-reorder` and compare. |
| `footer readings ignored` | A page number was read but contradicted its own position, so it was discarded. Usually a stamp sitting across the footer. | Only if there are many; a handful is normal. |
| `without a trusted page number` | Full-bleed table pages often carry no readable number; their position is left as scanned. | If most pages fall here *and* the scan is genuinely shuffled, the tool can't fix it; reorder the PDF first. |
| `pages analysed in Ns` | A cold cache does the full analysis; a warm one returns in about a second. | Only if slower than the page count suggests; check the worker count. |
| `N word(s) highlighted` | Words still weak after the second pass, marked yellow in the document. | A large number means a poor scan; read them in place. |

## Reading the check output

`check_output.py` reports shape, not accuracy: whether the converter lost
anything structural, not whether the text is correct.

- **Identifier gaps** matter most. `ids M-01..M-15: no gaps` means every
  requirement between the first and last was captured; `MISSING [7]` means
  a row was dropped, and you must check the source page.
- **Empty table rows** flag a row that exists with nothing in it.
- **Header rows** are printed so you can eyeball the column structure. A
  header cell holding junk (`PRED 1`) means that column's rule was
  misplaced on that page.

`--outline out.txt` writes the whole document structure to a file, the
fastest way to confirm headings and section order survived.

## The spreadsheet

`<name>_OCR_tables.xlsx` holds every table, one per sheet, with the header
row frozen, an autofilter set, numbers cast to numbers, and a contents
sheet linking to each. It carries the same content as the Word tables, in a
form you can filter and total.

## The quality report

`scan_OCR.quality.md` opens with **Needs a human**, the section that
matters most:

- **Identifier gaps**: a requirement number missing from a sequence means
  a row was dropped; go to that page.
- **Rows with text but no identifier**: usually a continuation row,
  sometimes a split row whose identifier was stranded.
- **Rejected footer readings**: page numbers the reorder logic refused to
  act on.
- **Low-confidence lines**: listed in full, with page numbers.
- **Words no dictionary knows**: proper nouns and jargon mostly, OCR
  errors otherwise. Pass known jargon with `--dictionary words.txt` so it
  stops being flagged.

It then lists every lost-space repair applied, so no change is silent.

---

# Technical Details

## Architecture at a glance

```
scan_to_docx.py   CLI, orchestration, document assembly, spreadsheet trigger
   |
   +-- pageworker.py   one page's analysis: isolated, parallel, cached on disk
   |       |
   |       +-- pagelab.py   pixel-level work: render, deskew, despeckle,
   |                        exclusions, table geometry, stroke measurement,
   |                        columns, figures
   |
   +-- qualitycheck.py   spelling repair, identifier audits, quality report
   +-- tablebook.py      the parallel spreadsheet of every table

check_output.py    standalone: re-inspects a finished .docx
interactive.py     standalone: no-argument menu, calls the same functions
                    scan_to_docx.py's CLI calls, no separate logic
```

`scan_to_docx.py` is the only module invoked directly by the CLI; the
others are libraries it composes. `interactive.py` and `check_output.py`
sit alongside it as independent entry points that reuse its functions
rather than duplicating them.

That's the module graph, your code. Underneath it, this is what's
installed and doing the work:

```
Tesseract (external program, installed separately)
   ^
   | called by
pytesseract -------- OCR: text, word boxes, confidence

numpy, scipy -------- pixel math: ink masks, deskew, despeckle,
                      table-rule detection, stroke measurement
pillow -------------- image loading and template matching
pymupdf -------------- page rendering, page metadata

python-docx ---------- writes the .docx
openpyxl -------------- writes the .xlsx
pyspellchecker -------- dictionary lookup for spelling repair
                      and the quality report
```

Everything above the line is a program on your machine; everything below
it is a Python package `pip install -r requirements.txt` fetches.
Neither list is optional; the tool won't run without both.

## How it works

1. Renders each page with PyMuPDF, so pages holding several images, or a
   mix of image and vector content, still work. Pages are analysed in
   parallel, and the result cached against the file's content and the
   run's settings.
2. Drops excluded pages, then removes coloured letterhead and footer
   bands, ink stamps, and any region matching a supplied template image.
3. Finds table rules by eroding the ink mask with long kernels; only
   something rule-shaped survives, which is how faint hairlines are told
   apart from body text.
4. Inverts solid header bars so white-on-black headings can be read.
5. Straightens pages tilted by a degree or more and erases specks too
   small to be type.
6. OCRs each page, then re-reads any weak line at double size in
   single-line mode, keeping whichever reading scores better. What is
   still weak is highlighted in the finished document.
7. Measures each word's stroke width and slant, decides emphasis per
   line, and detects multi-column layout, guarded so a contents page's
   page-number gutter isn't read as a second column. Detail on this
   step: [Emphasis, columns and figures](#emphasis-columns-and-figures).
8. Reassembles in reading order: headings, paragraphs, bullets, tables at
   their original column proportions and stitched across page breaks
   only when column count, header and widths all agree, figures
   embedded.
9. Repairs lost spaces, audits identifier sequences, writes the
   spreadsheet and the quality report.

## Troubleshooting

### Setup

**Tesseract not found.**
Install it (`winget install --id UB-Mannheim.TesseractOCR -e` on Windows,
or your package manager elsewhere), or pass `--tesseract` with the full
path to the executable.

### Output quality

**The output is nearly empty.**
Little ink survived the cleaning. Rerun with `--keep-furniture
--keep-stamp` and no templates to see the page untouched. A template
matching too loosely, or a mostly-coloured page read as furniture, can
strip the body.

**A table came out as prose.**
No ruling lines survived erosion, or there weren't any. See
[Limits and known trade-offs](#limits-and-known-trade-offs) for why there's
no alignment-based fallback. Accept the prose, or rebuild that table by
hand.

**A table's columns are wrong or shifted.**
A column rule was missed on that page, usually because the scan is pale
down one edge. If several pages do this, the whole scan is likely
under-exposed, and a better scan will fix more than any setting.

**Rows are merged, or one row's text landed in the row above.**
A horizontal rule was too faint to detect. Same cause, same fix as above.

**The header row is doubled in a stitched table.**
The tool drops a repeated header only when it matches the first one
exactly; OCR noise in one copy defeats that. Delete the duplicate row in
Word.

**Everything came out bold, or nothing did.**
The baseline moved; see [Emphasis, columns and figures](#emphasis-columns-and-figures).
`--no-emphasis` turns the feature off.

**A page came out in the wrong order within itself.**
The column guard called it wrong either way. See
[Emphasis, columns and figures](#emphasis-columns-and-figures). Fix it with
`{"page_options": {"12": {"single_column": true}}}` in the config file.

**One table became several, or several became one.**
The quality report's **Needs a human** section names the page and the test
that failed: column count, header agreement, or column widths.

**A figure is missing, or a decorative bar was embedded as one.**
Rejecting bars costs the occasional genuine figure. See
[Limits and known trade-offs](#limits-and-known-trade-offs). Crop it from
the PDF by hand.

**Text is missing entirely.**
Three likely causes, in order: it's in a script other than English
(dropped by design); it sat under a stamp and the ink was lifted with the
glyphs; OCR confidence fell below threshold.

**Words are run together: `Alldocuments`, `Wherea`.**
Low resolution. Below roughly 200 DPI, Tesseract loses inter-word spaces.
Try `--scale 3`; a rescan at 300 DPI is the real fix.

**Digits look wrong: `M-O1`, `1` for `l`, `0` for `O`.**
Identifier-shaped first-column cells are repaired automatically; digits in
body text and other cells are not.

**Non-English text is gone.**
By design. See [Limits and known trade-offs](#limits-and-known-trade-offs).

**The letterhead, footer or stamp is still there.**
Furniture and stamps are found by colour heuristics tuned for common
cases; a black-and-white scan of a colour original can defeat both. Use
`--keep-furniture` to see the page untouched, then use
`--exclude-template` on the specific region.

### Performance

**The run is slower than it should be.**
Check the worker count in the first line of output; `--jobs` overrides it.
A cold cache costs the full analysis, a warm one costs seconds.

**It took much longer than expected.**
Time scales with page area as well as page count. A3 or high-DPI scans at
`--scale 2` produce large images; drop to `--scale 1` on anything
already above 300 DPI.

### Missing content

See "Text is missing entirely" and "Non-English text is gone" above.

## Version notes

No formal compatibility matrix is maintained. The code targets a current
Python 3 and Tesseract 5.x; if OCR quality seems unexpectedly poor, check
`tesseract --version` before assuming the tool is at fault.

## Glossary

| Term | Meaning here |
|---|---|
| Furniture | Coloured letterhead and footer bands, removed by default |
| Ink mask | The rendered page reduced to "ink present / not present" per pixel, the basis for table-rule and figure detection |
| Stroke width | Thickness of a glyph's ink, measured to infer bold |
| Reorder | Reading pages by their printed page number rather than their physical scan order |
| Second pass | Re-reading a low-confidence line at double size in single-line OCR mode |
| Schema | The detected column layout and header of a table, used to decide whether it continues on the next page |
| Deskew | Straightening a page that was scanned at a slight tilt |
| Despeckle | Removing specks of noise too small to be a printed character |
| Template match | A region removed from every page because it matches a supplied sample image (a stamp, a logo) |
| `page_options` | Config-file setting that overrides behaviour for one printed page number only |
