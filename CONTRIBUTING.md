# Contributing

## Before you start

Open an issue first for anything beyond a small fix, so the approach is agreed before you spend time on it.

## Bug reports

Include:
- OS and Python version (`python --version`)
- Tesseract version (`tesseract --version`)
- The exact command you ran
- The full traceback (failures print one to stderr per file, in addition to the summary line)

## Code style

[Black](https://black.readthedocs.io/) formats, [Ruff](https://docs.astral.sh/ruff/) lints, both configured in `pyproject.toml`. Run both before opening a PR (step 2 above). `E741` (single-letter variable names) is deliberately off, `l` is used throughout for a text line and renaming it risks a typo in code with no test suite.

## Scope

English body text, ruled tables, single OCR engine (Tesseract). A change that adds another script or OCR engine is a larger discussion, open an issue before writing code.

## License

By contributing, you agree your contribution is licensed under this project's MIT license.
