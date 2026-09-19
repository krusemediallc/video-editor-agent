#!/usr/bin/env bash
# Portable entry point; setup.py uses Python's standard library only.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.10+ is required. Install python3, then rerun this command.' >&2
  echo 'macOS: brew install python; Debian/Ubuntu: sudo apt-get install python3' >&2
  exit 1
fi
exec python3 "$SCRIPT_DIR/setup.py" "$@"
