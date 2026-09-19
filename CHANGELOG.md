# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-19

Initial public release.

### Added
- PDF to Word conversion via PyMuPDF rendering and Tesseract OCR, with per-page caching.
- Table detection by hairline rule erosion, rebuilt as native Word tables at original column proportions, stitched across page breaks when column count, header, and widths agree.
- Parallel spreadsheet output, one sheet per table.
- Bold detection from stroke width; italic detection (opt-in) from slant.
- Multi-column reading order, with a guard against misreading a page-number gutter as a column.
- Deskew, despeckle, letterhead/footer/stamp removal, and template-based region exclusion.
- Low-confidence word highlighting, with a second higher-zoom OCR pass on weak lines.
- Lost-space repair and reference-ID repair (e.g. `M-O1` to `M-01`), both logged in the quality report.
- Quality report naming what was repaired and what needs human review.
- Interactive no-argument menu, and `pdfocr.bat` / `pdfocr.sh` convenience launchers for Windows, macOS, and Linux.
- `check_output.py` for re-inspecting a finished document after hand edits.
- `traceback.print_exc()` on a per-file conversion failure, so a bug report can include the actual stack trace instead of just the exception message.
- Black and Ruff configuration in `pyproject.toml`; `CONTRIBUTING.md` documents the pre-commit check.
- `CONTRIBUTING.md`, `CHANGELOG.md`.

[1.0.0]: https://github.com/OWNER/REPO/releases/tag/v1.0.0
