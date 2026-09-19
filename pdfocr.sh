#!/usr/bin/env bash
# Convenience launcher for macOS and Linux. Forwards all arguments and the exit code.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/scan_to_docx.py" "$@"
fi

if command -v python >/dev/null 2>&1; then
    exec python "$SCRIPT_DIR/scan_to_docx.py" "$@"
fi

echo "Python 3 not found on PATH. Install it and try again." >&2
exit 1
