# Security Policy

## Supported versions

Only the latest commit on `main` is supported. There are no maintained
older versions.

## Reporting a vulnerability

Do not open a public issue for a security problem.

Report privately via GitHub's [Security Advisories](../../security/advisories/new)
for this repository, or email pjpkirby@pm.me with a description, the
input that triggers it (or a redacted/synthetic reproduction if the PDF
is sensitive), and the impact you'd expect.

Expect an initial response within 7 days. This is a solo-maintained
utility, not a funded project — fixes ship as time allows, not on an SLA.

## Scope

This tool runs entirely locally: no network calls, no telemetry, no data
leaves the machine it runs on. The realistic risk surface is:

- A malicious PDF triggering unsafe behaviour in PyMuPDF, Pillow, or
  Tesseract (the parsing/rendering/OCR dependencies) — report upstream
  too if you can reproduce it there.
- Path handling that could write outside the intended output directory.

Report anything in that shape here even if you're unsure it's exploitable.
