"""Quality checks over OCR output, and the report they produce.

Two jobs. First, repair the one OCR error that is safe to repair without
guessing: a lost space between two real words. Second, tell the reader
everything the run is unsure about, so the checking effort goes where it is
needed instead of across all 37 pages equally.
"""

import re
from collections import Counter

from spellchecker import SpellChecker

TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]+")
ID_LIKE = re.compile(r"^[A-Z]{1,3}-\d{1,3}$")
NUMERIC = re.compile(r"\d")

# Short words the scan most often runs into its neighbour.
FUNCTION_WORDS = {
    "a",
    "an",
    "the",
    "all",
    "and",
    "or",
    "of",
    "in",
    "on",
    "to",
    "for",
    "is",
    "as",
    "at",
    "by",
    "be",
    "no",
    "not",
    "any",
    "are",
    "was",
    "with",
    "from",
    "into",
    "each",
    "such",
    "this",
    "that",
    "where",
    "when",
    "which",
    "shall",
    "must",
    "may",
    "can",
    "will",
    "has",
    "have",
    "been",
    "per",
    "via",
    "if",
}

# Common IT/business/tender terms a general dictionary rejects. Anything
# domain- or client-specific belongs in a --dictionary file, not here.
DOMAIN_WORDS = {
    "searchable",
    "workflow",
    "workflows",
    "lifecycle",
    "versioning",
    "workaround",
    "workarounds",
    "datasheets",
    "ransomware",
    "pathfinding",
    "auditable",
    "scalable",
    "deduplication",
    "tiering",
    "toolset",
    "toolsets",
    "hypervisor",
    "middleware",
    "runbook",
    "changelog",
    "rollback",
    "failback",
    "rfp",
    "bidder",
    "bidders",
    "sla",
    "slas",
    "uat",
    "rbac",
    "mfa",
    "sso",
    "api",
    "apis",
    "graphql",
    "kubernetes",
    "cypher",
    "acid",
    "metadata",
    "scalability",
    "onboarding",
    "runbooks",
    "tenancy",
    "multi",
    "premises",
    "gapped",
    "hardening",
    "failover",
    "dashboards",
    "datasets",
    "connectors",
    "petabyte",
    "namespace",
    "namespaces",
    "cms",
    "s3",
    "etl",
    "json",
    "yaml",
}


class Checker:
    """Spell-aware repair and reporting over OCR'd text."""

    def __init__(self, autofix=True, extra_words=()):
        self.sp = SpellChecker()
        self.sp.word_frequency.load_words(DOMAIN_WORDS | set(extra_words))
        self.autofix = autofix
        self.fixes = Counter()
        self.suspect = Counter()

    def known(self, word):
        low = word.lower().strip("'-")
        if not low or NUMERIC.search(low) or len(low) < 3:
            return True
        return low in self.sp

    def split_repair(self, word):
        """'Alldocuments' -> 'All documents', where the scan lost a space.

        One half must be a short function word. Without that rule the check
        happily turns 'workflow' into 'work flow' and 'auditable' into 'audi
        table': both halves are real words, the compound is simply absent from
        a general dictionary. Lost spaces in practice cluster around the short
        words, which is the only case this will act on.
        """
        if len(word) < 7 or not word.isalpha():
            return None
        for i in range(2, len(word) - 2):
            left, right = word[:i], word[i:]
            if (
                left.lower() not in FUNCTION_WORDS
                and right.lower() not in FUNCTION_WORDS
            ):
                continue
            if self.known(left) and self.known(right):
                return f"{left} {right}"
        return None

    def clean(self, text, where):
        """Repair what is safe, record what is not, and return the text."""
        if not text:
            return text
        out = []
        for token in re.split(r"(\s+)", text):
            bare = token.strip(".,;:()\"'")
            if not bare or ID_LIKE.match(bare) or self.known(bare):
                out.append(token)
                continue
            repair = self.split_repair(bare) if self.autofix else None
            if repair:
                out.append(token.replace(bare, repair))
                self.fixes[f"{bare} -> {repair}"] += 1
            else:
                out.append(token)
                self.suspect[f"{bare} ({where})"] += 1
        return "".join(out)


def orphan_ids(rows):
    """Rows carrying text but no identifier, in a table that uses identifiers.

    Either the row continues the one above it, which is normal, or the row was
    split and its identifier is stranded, which is not. A gap check cannot see
    this: an identifier missing from the end of a sequence leaves no gap.
    """
    ided = sum(1 for r in rows if ID_LIKE.match(r[0].strip()))
    if ided < 3:
        return 0
    return sum(
        1 for r in rows[1:] if not r[0].strip() and any(c.strip() for c in r[1:])
    )


def id_gaps(rows):
    """Missing numbers per identifier prefix in a table's first column."""
    seen = {}
    for row in rows:
        cell = row[0].strip()
        if ID_LIKE.match(cell):
            prefix, num = cell.split("-")
            seen.setdefault(prefix, []).append(int(num))
    report = []
    for prefix, nums in seen.items():
        missing = [n for n in range(1, max(nums) + 1) if n not in nums]
        report.append((prefix, min(nums), max(nums), missing))
    return report


def write_report(path, run):
    """Write the quality report beside the document.

    Structured so the first section is the one worth acting on: anything the
    run could not resolve by itself.
    """
    L = [f"# Quality report — {run['source'].name}", ""]
    L.append(
        f"Converted to `{run['output'].name}` on " f"{run['finished']:%Y-%m-%d %H:%M}."
    )
    L.append("")

    L.append("## Needs a human")
    problems = []
    for table, prefix, lo, hi, missing in run["gaps"]:
        problems.append(
            f"- Table {table}: identifiers `{prefix}-{lo:02d}` to "
            f"`{prefix}-{hi:02d}` are missing {missing}. A row was "
            "dropped; check that page against the PDF."
        )
    for table, count in run.get("orphans", []):
        problems.append(
            f"- Table {table}: {count} row(s) hold text but no "
            "identifier. Usually a row continuing from the one "
            "above; sometimes a split row whose identifier was "
            "stranded. Worth an eye."
        )
    for page, why in run.get("schema", []):
        problems.append(
            f"- Page {page}: {why}. If they are one table, the "
            "column rules were read differently on the two pages."
        )
    if run["empty_rows"]:
        problems.append(f"- {run['empty_rows']} table row(s) came out wholly " "empty.")
    if run["rejected_pages"]:
        problems.append(
            f"- Footer page numbers ignored as inconsistent: "
            f"{run['rejected_pages']}."
        )
    low = run["low_confidence"]
    if low:
        problems.append(
            f"- {len(low)} line(s) below the confidence floor. " "Listed in full below."
        )
    if run["suspect"]:
        problems.append(
            f"- {len(run['suspect'])} word(s) no dictionary "
            "recognises, after repairs. Listed in full below."
        )
    L += problems or ["- Nothing outstanding."]
    L.append("")

    L.append("## What the run did")
    L.append(
        f"- {run['pages']} pages in {run.get('elapsed', 0):.0f}s: "
        f"{run['paragraphs']} paragraphs, {len(run['tables'])} tables, "
        f"{run['figures']} figures embedded."
    )
    if run.get("workbook"):
        L.append(
            f"- Every table also written to `{run['workbook']}`, one "
            "sheet per table."
        )
    if run.get("highlighted"):
        L.append(
            f"- {run['highlighted']} word(s) highlighted in the document "
            "as low confidence. Check those in place; they are the ones "
            "the OCR was least sure of."
        )
    if run.get("rescued"):
        L.append(
            f"- {run['rescued']} weak line(s) re-read at higher "
            "magnification, and the better reading kept."
        )
    if run.get("skewed"):
        L.append(
            f"- Pages straightened before reading: {run['skewed']} " "(page, degrees)."
        )
    L.append(
        f"- Emphasis applied: {run['bold']} bold run(s), "
        f"{run['italic']} italic run(s)."
    )
    if run["columns"]:
        L.append(f"- Multi-column pages read column by column: " f"{run['columns']}.")
    if run["moved_pages"]:
        L.append(
            f"- Pages reordered to match printed numbers: " f"{run['moved_pages']}."
        )
    if run["excluded"]:
        L.append(f"- Excluded by request: {run['excluded']}.")
    if run["templates"]:
        L.append(f"- Template exclusions matched on {run['templates']} " "region(s).")
    if run["fixes"]:
        L.append(f"- {sum(run['fixes'].values())} lost-space repair(s) applied.")
    L.append("")

    if run["fixes"]:
        L.append("## Repairs applied")
        L.append(
            "Each of these joined two dictionary words that the scan ran "
            "together. Every one is listed so none is silent."
        )
        L.append("")
        for fix, n in run["fixes"].most_common():
            L.append(f"- `{fix}`" + (f" ×{n}" if n > 1 else ""))
        L.append("")

    if run["suspect"]:
        L.append("## Words to check")
        L.append(
            "Not in the dictionary and not repairable. Many will be "
            "proper nouns or product names; the rest are OCR errors."
        )
        L.append("")
        for word, n in run["suspect"].most_common(200):
            L.append(f"- `{word}`" + (f" ×{n}" if n > 1 else ""))
        L.append("")

    if low:
        L.append("## Low-confidence lines")
        L.append("")
        for page, conf, text in low[:200]:
            L.append(f"- p{page} ({conf:.0f}%): {text}")
        L.append("")

    L.append("## Tables")
    for i, (rows, cols, header) in enumerate(run["tables"]):
        L.append(f"- Table {i}: {rows}×{cols} — {header}")
    L.append("")

    L.append(
        "This report checks shape and spelling, not meaning. Figures, "
        "dates and clause numbers still need reading against the source "
        "PDF before anything binding depends on them."
    )
    path.write_text("\n".join(L), encoding="utf8")
