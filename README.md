<img src="ocr%20wizard%20logo.png" alt="OCR Wizard" align="right" width="180">

# PDF OCR Extractor

![License](https://img.shields.io/github/license/PatrickKirby/PDFOCRWizard)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![CI](https://github.com/PatrickKirby/PDFOCRWizard/actions/workflows/ci.yml/badge.svg)

<br clear="right">

Turns a scanned, image-only PDF into an editable Word document: OCR'd prose
with headings, bullets and inline bold, ruled tables rebuilt as real Word
tables at their original column proportions, multi-column pages read in
reading order, figures embedded, and low-confidence words highlighted in
place. Every table is also written to a parallel spreadsheet. Every run
writes a quality report naming what it repaired and what a human still has
to check.

Pages are analysed in parallel and cached, so a 40-page scan takes roughly
twenty seconds cold and a few seconds warm.

Built and tuned against real-world scanned tenders and reports: mixed
letterheads and stamps, ruled tables, multi-column layouts, and pages
transposed during scanning. It is not a general document-layout engine; see
[MANUAL.md](MANUAL.md) for what it deliberately does and does not handle.


## Why it's built this way

Most OCR tools stop at recognised text. This one also rebuilds structure:
table geometry, reading order, emphasis, and it tells you exactly what to
check rather than presenting a wall of text as fact. The reasoning behind
each design choice, its architecture, and its limits: [MANUAL.md](MANUAL.md).

## Install

Requires Python 3.12 or later (set by `scipy`'s own floor). Tested on 3.14.

Once per machine, install Tesseract, then the Python dependencies.

| Platform | Install Tesseract with |
|---|---|
| Windows | `winget install --id UB-Mannheim.TesseractOCR -e` |
| macOS | `brew install tesseract` |
| Linux | `apt install tesseract-ocr` (Debian, Ubuntu) or `dnf install tesseract` (Fedora) |

```
pip install -r requirements.txt
```

The Python code is identical across platforms. Tesseract is found on
`PATH`, at the default install location, or via `--tesseract`. Full
setup detail, including what each dependency does: [MANUAL.md](MANUAL.md).

## Use

```
python scan_to_docx.py "path/to/scan.pdf"
```

No arguments launches an interactive menu instead. `pdfocr.bat` (Windows)
and `pdfocr.sh` (macOS, Linux) are thin wrappers that forward all arguments
and the exit code, so `pdfocr scan.pdf --exclude-pages 1` works the same as
calling the script directly.

Every flag, day-to-day usage, reading the run output, and troubleshooting:
[MANUAL.md](MANUAL.md).


## License

MIT. See [LICENSE](LICENSE).

## Support

If this saved you time, [buy me a coffee](https://buymeacoffee.com/preceperi).
