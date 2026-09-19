"""Interactive menu for PDF OCR Extractor.

Launched automatically when scan_to_docx.py is run with no arguments. Every
action here calls the same functions the command-line flags call; this file
adds no conversion logic of its own, only prompts.
"""

import datetime as dt
import shlex
import sys
from pathlib import Path

import pymupdf
import pytesseract

import check_output
import pageworker as W
import scan_to_docx as S


def ask(prompt, default=""):
    """Prompt with a bracketed default; Enter accepts it."""
    shown = f"{prompt} [{default}]: " if default else f"{prompt}: "
    reply = input(shown).strip()
    return reply or default


def ask_yes_no(prompt, default=False):
    shown = "Y/n" if default else "y/N"
    reply = input(f"{prompt} [{shown}]: ").strip().lower()
    if not reply:
        return default
    return reply.startswith("y")


def inspect_source(pdf):
    """Show pages, text-layer size and rough page size for one PDF."""
    doc = pymupdf.open(pdf)
    try:
        text_chars = sum(len(p.get_text().strip()) for p in doc)
        page_size = doc[0].rect if doc.page_count else None
    finally:
        doc.close()
    print(
        f"  {pdf.name}: {S.P.page_count(pdf)} page(s)"
        + (f", page size {page_size}" if page_size else "")
    )
    if text_chars > 200:
        print(
            f"    WARNING: {text_chars} characters of text layer already "
            "present — OCR is probably the wrong tool for this file."
        )
    return text_chars


def gather_pdfs():
    raw = ask("PDF file(s) or folder (space-separated, quote paths with spaces)")
    if not raw:
        print("No input given.")
        return []
    try:
        paths = [Path(p) for p in shlex.split(raw)]
    except ValueError as exc:
        print(f"Could not parse that: {exc}")
        return []
    try:
        return S.expand_inputs(paths)
    except SystemExit as exc:
        print(exc)
        return []


def build_args(overrides):
    """A scan_to_docx argparse.Namespace filled with defaults, then overridden."""
    ns = S.build_arguments().parse_args(["placeholder"])
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


def run_batch(pdfs, args):
    tess = S.locate_tesseract(args.tesseract)
    pytesseract.pytesseract.tesseract_cmd = tess
    run_stamp = dt.date.today().isoformat()
    n = len(pdfs)
    results, failed = [], []
    for i, pdf in enumerate(pdfs, 1):
        out_path = S.resolve_output_path(pdf, args, run_stamp)
        print(f"\n[{i}/{n}] {pdf.name}")
        try:
            results.append(S.convert_one(pdf, out_path, args, tess))
        except Exception as exc:
            print(f"FAILED: {pdf.name}: {exc}")
            failed.append((pdf, exc))

    print()
    if n > 1:
        print(
            f"batch done: {len(results)}/{n} converted"
            + (f", {len(failed)} failed" if failed else "")
        )
    if results:
        print(
            f"  {sum(r['pages'] for r in results)} pages, "
            f"{sum(r['paragraphs'] for r in results)} paragraphs, "
            f"{sum(r['tables'] for r in results)} tables, "
            f"{sum(r['highlighted'] for r in results)} word(s) highlighted, "
            f"{sum(r['elapsed'] for r in results):.0f}s total"
        )
        folders = sorted({str(r["out"].parent) for r in results})
        print("  output in: " + ", ".join(folders))
    print("Check figures, dates and clause numbers against the PDF before use.")


def convert_flow(with_exclusions):
    pdfs = gather_pdfs()
    if not pdfs:
        return
    print("\nInspecting source file(s):")
    for pdf in pdfs:
        inspect_source(pdf)

    overrides = {"pdf": pdfs}
    if with_exclusions:
        exclude_pages = ask("Pages to exclude entirely, e.g. 1,36-37", "")
        keep_furniture = ask_yes_no("Keep letterhead/footer bands?", False)
        keep_stamp = ask_yes_no("Keep ink stamps?", False)
        overrides.update(
            exclude_pages=exclude_pages,
            keep_furniture=keep_furniture,
            keep_stamp=keep_stamp,
        )

    same_dir = ask_yes_no(
        "Write output beside each source file instead of a date-stamped folder?", False
    )
    overrides["same_dir"] = same_dir
    args = build_args(overrides)

    run_stamp = dt.date.today().isoformat()
    dest_note = (
        "beside each source file"
        if same_dir
        else f"a date-stamped folder ('OCR_{run_stamp}') next to each source file"
    )

    print("\nReady to convert")
    print("-" * 40)
    for pdf in pdfs:
        print(f"  source   {pdf}")
    print(f"  output   {dest_note}")
    if with_exclusions:
        print(
            f"  exclude  pages: {overrides['exclude_pages'] or 'none'}, "
            f"furniture kept: {overrides['keep_furniture']}, "
            f"stamps kept: {overrides['keep_stamp']}"
        )
    est = len(pdfs) * 20
    print(f"  est time ~{est}s ({len(pdfs)} file(s), ~20s each on a typical scan)")

    if not ask_yes_no("Proceed?", True):
        print("Cancelled.")
        return
    run_batch(pdfs, args)


def recheck_flow():
    raw = ask("Path to an existing .docx")
    if not raw:
        return
    path = Path(raw)
    if not path.exists():
        print(f"No such file: {path}")
        return
    check_output.inspect_docx(path)


def cache_flow():
    root = W.cache_root()
    files = list(root.rglob("*")) if root.exists() else []
    size = sum(f.stat().st_size for f in files if f.is_file())
    print(f"Cache: {root}")
    print(f"  {len(files)} file(s), {size / 1_048_576:.1f} MB")
    if files and ask_yes_no("Clear it now?", False):
        W.clear_cache()
        print("Cache cleared.")


def dictionary_flow():
    raw = ask("Dictionary file path", "dictionary.txt")
    path = Path(raw)
    words = []
    if path.exists():
        words = [
            w.strip()
            for w in path.read_text(encoding="utf-8").splitlines()
            if w.strip()
        ]
        print(f"{len(words)} word(s) currently in {path}:")
        print("  " + ", ".join(words) if words else "  (empty)")
    else:
        print(f"{path} does not exist yet.")

    added = ask("Add word(s), comma-separated (blank to skip)", "")
    if added:
        new_words = sorted(
            set(words) | {w.strip() for w in added.split(",") if w.strip()}
        )
        path.write_text("\n".join(new_words) + "\n", encoding="utf-8")
        print(f"Saved {len(new_words)} word(s) to {path}")
        print(f"Use it with --dictionary {path} or the config file.")


def help_flow():
    print(__doc__ or "")
    print("Full flag reference:\n")
    S.build_arguments().print_help()
    print("\nSee README.md and MANUAL.md beside this script for full detail.")


MENU = [
    ("Convert file(s)", lambda: convert_flow(with_exclusions=False)),
    ("Convert file(s) with exclusions", lambda: convert_flow(with_exclusions=True)),
    ("Re-check an existing .docx", recheck_flow),
    ("Clear / inspect cache", cache_flow),
    ("Manage dictionary (custom words)", dictionary_flow),
    ("Help / About", help_flow),
]


def run():
    while True:
        print("\nPDF OCR Extractor")
        print("-" * 40)
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  {i}) {label}")
        print("  0) Quit")
        choice = ask("\nSelect", "1")
        if choice in ("0", "q", "Q"):
            return
        try:
            index = int(choice) - 1
            label, action = MENU[index]
        except (ValueError, IndexError):
            print("Not a valid choice.")
            continue
        try:
            action()
        except KeyboardInterrupt:
            print("\nCancelled.")
        except SystemExit as exc:
            print(exc)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)
