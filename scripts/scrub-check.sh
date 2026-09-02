#!/usr/bin/env bash
# scrub-check.sh — refuse to commit/push anything that looks like a secret, a personal path, a
# private host, media, or a name from the local deny-list. Runs as the pre-commit hook (staged
# files) and pre-push hook (all tracked files); run it by hand with --all or --staged.
#
#   bash scripts/scrub-check.sh --staged      # what is about to be committed
#   bash scripts/scrub-check.sh --all         # every tracked file
#   SCRUB_ALLOW=1 git commit …                # conscious bypass (say why in the commit message)
#
# Deny-list: scripts/scrub-denylist.local.txt (gitignored, one regex per line, `#` comments,
# matched case-insensitively) — put partner names, people, internal hostnames and repo names
# there. Copy the .example to start. --staged scans the STAGED blobs, not the working tree.
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
mode="${1:---staged}"
if [ "${SCRUB_ALLOW:-0}" = "1" ]; then echo "scrub-check: bypassed (SCRUB_ALLOW=1)"; exit 0; fi
SCANROOT="$ROOT"
case "$mode" in
  --staged)
    files="$(git diff --cached --name-only --diff-filter=ACMR)"
    # scan the STAGED blobs, not the working tree — a secret can sit in the index after the
    # working copy was cleaned, and a partial `git add -p` stages different content than the file
    SCANROOT="$(mktemp -d "${TMPDIR:-/tmp}/scrub.XXXXXX")"; trap 'rm -rf "$SCANROOT"' EXIT
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      mkdir -p "$SCANROOT/$(dirname "$f")"; git show ":$f" > "$SCANROOT/$f" 2>/dev/null || true
    done <<< "$files";;
  --all)    files="$(git ls-files)";;
  *) echo "usage: scrub-check.sh [--staged|--all]"; exit 2;;
esac
# the scanner and its example deny-list contain the patterns themselves
files="$(printf '%s\n' "$files" | grep -vE '^(scripts/scrub-check\.sh|scripts/scrub-denylist\.example\.txt)$' || true)"
[ -z "$files" ] && { echo "scrub-check: nothing to scan"; exit 0; }
hits=0
say() { hits=$((hits+1)); printf '  %s\n' "$1"; }

# 1. files that must never be committed at all
while IFS= read -r f; do
  case "$f" in
    .env.example) ;;
    .env|.env.*|MASTER_CONTEXT.md|scripts/scrub-denylist.local.txt) say "FORBIDDEN FILE  $f";;
    *.mp4|*.mov|*.MP4|*.MOV|*.wav|*.m4a|*.mp3|*.aac|*.webm|*.mkv)
      case "$f" in .claude/skills/*/assets/*) ;; *) say "MEDIA FILE      $f (media stays in the projects directory)";; esac;;
  esac
done <<< "$files"

# 2. content patterns (binary files skipped)
# placeholders that look like secrets but are documentation
PLACEHOLDER='(\.\.\.|…|<[^>]*>|your[-_ ]|xxx|example|placeholder|\$\{|\$[A-Z_]{3,}|=[[:space:]]*$)'
scan() { # $1 label, $2 regex (ERE), $3 optional grep flags (e.g. -i)
  local label="$1" re="$2" flags="${3:-}" out
  out="$(cd "$SCANROOT" && printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 grep -nIE $flags --binary-files=without-match -e "$re" -- 2>/dev/null | cut -c1-160)"
  [ "$label" = "SECRET        " ] && out="$(printf '%s\n' "$out" | grep -vE "$PLACEHOLDER" || true)"
  [ -n "$out" ] && { printf '%s\n' "$out" | while IFS= read -r line; do say "$label  $line"; done; hits=$((hits+1)); }
  return 0
}
scan "SECRET        " '(sk-[A-Za-z0-9_-]{16,}|sk_(live|test)_[A-Za-z0-9]{8,}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}|EAA[A-Za-z0-9]{40,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9._-]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|(api[_-]?key|secret|token|passw(or)?d|auth)[A-Za-z0-9_]*[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9._/+:-]{16,})' -i
scan "PRIVATE HOST  " '(\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}\b|\b192\.168\.[0-9]{1,3}\.[0-9]{1,3}\b|\b10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b|smb://)'
scan "PERSONAL PATH " '(/Volumes/[A-Za-z]|/Users/[A-Za-z._-]+/|Caleb Personal)'
scan "EMAIL         " '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,63}([^A-Za-z0-9_-]|$)'
scan "REVIEW SLUG   " '([A-Za-z0-9-]+\.here\.now|https?://[^[:space:]"'"'"'<>]*\.here\.now)'
scan "MONEY         " '\$[0-9]{1,3}(,[0-9]{3})*(\.[0-9]+)?[kK]?\b[^|]{0,40}(deal|fee|paid|brand|budget|per (video|reel|post))'
if [ -f scripts/scrub-denylist.local.txt ]; then
  while IFS= read -r re; do
    case "$re" in ''|'#'*) continue;; esac
    scan "DENY-LIST     " "$re" -i
  done < scripts/scrub-denylist.local.txt
fi
if [ "$hits" -gt 0 ]; then
  echo "scrub-check: $hits finding(s) above. Fix them, or SCRUB_ALLOW=1 to bypass on purpose."
  exit 1
fi
echo "scrub-check: clean ($(printf '%s\n' "$files" | wc -l | tr -d ' ') files)"
