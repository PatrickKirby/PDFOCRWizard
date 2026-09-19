"""Inspect a converted Word document before anyone relies on it.

Prints the document's shape, every table with its header row, and any gap in an
identifier sequence. A gap in a requirement or clause sequence means OCR lost a
row, which is the one failure that looks like success.

    python check_output.py out.docx
    python check_output.py out.docx --outline outline.txt
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

ID = re.compile(r"^([A-Z]{1,3})-(\d{1,3})$")


def walk(doc):
    """Paragraphs and tables in the order they appear in the document."""
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def id_gaps(table):
    """Missing numbers in each identifier prefix found in the first column."""
    seen = defaultdict(list)
    for row in table.rows:
        m = ID.match(row.cells[0].text.strip())
        if m:
            seen[m.group(1)].append(int(m.group(2)))
    report = []
    for prefix, nums in seen.items():
        missing = [n for n in range(1, max(nums) + 1) if n not in nums]
        report.append((prefix, min(nums), max(nums), missing))
    return report


def inspect_docx(docx_path, outline_path=None):
    """Re-inspect a finished document's shape. Returns a summary dict."""
    doc = Document(docx_path)
    outline, paras, chars, empties = [], 0, 0, 0
    tables = []

    for item in walk(doc):
        if isinstance(item, Paragraph):
            if item.text.strip():
                paras += 1
                chars += len(item.text)
                outline.append(f"[{item.style.name}] {item.text}")
        else:
            tables.append(item)
            header = " | ".join(c.text.strip() for c in item.rows[0].cells)
            outline.append(f"<<TABLE {len(item.rows)}x{len(item.columns)}>> {header}")
            for row in item.rows[1:]:
                chars += sum(len(c.text) for c in row.cells)
                if not any(c.text.strip() for c in row.cells):
                    empties += 1

    headings = sum(1 for line in outline if line.startswith("[Heading"))
    print(
        f"{Path(docx_path).name}: {paras} paragraphs ({headings} headings), "
        f"{len(tables)} tables, {chars} characters"
    )
    if empties:
        print(f"WARNING: {empties} wholly empty table row(s)")

    gaps = []
    print("\nTables")
    for i, t in enumerate(tables):
        header = " | ".join(c.text.strip()[:20] for c in t.rows[0].cells)
        print(f"  {i}: {len(t.rows)}x{len(t.columns)}  {header}")
        for prefix, lo, hi, missing in id_gaps(t):
            flag = f"MISSING {missing}" if missing else "no gaps"
            print(f"       ids {prefix}-{lo:02d}..{prefix}-{hi:02d}: {flag}")
            if missing:
                gaps.append((prefix, missing))

    if outline_path:
        Path(outline_path).write_text("\n".join(outline), encoding="utf8")
        print(f"\noutline written to {outline_path}")

    print(
        "\nThis checks shape, not accuracy. Figures, dates and clause numbers "
        "still need reading against the source PDF."
    )

    return {
        "paragraphs": paras,
        "headings": headings,
        "tables": len(tables),
        "characters": chars,
        "empty_rows": empties,
        "gaps": gaps,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("docx", type=Path)
    ap.add_argument(
        "--outline",
        type=Path,
        help="write the full heading/paragraph/table outline here",
    )
    args = ap.parse_args()
    inspect_docx(args.docx, args.outline)


if __name__ == "__main__":
    main()
