#!/usr/bin/env bash
# Read-only, offline dependency checks. No npx, installation, or credential output.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'FAIL  Python 3.10+ is required. Install python3, then rerun this command.' >&2
  exit 1
fi
exec python3 "$SCRIPT_DIR/setup.py" --check "$@"
