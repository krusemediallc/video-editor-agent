#!/usr/bin/env bash
# check-setup.sh — verify every tool/API this pack needs. Mirrors SETUP.md.
# Exit 0 = all required present. Optional items report but never fail the run.
set -u
pass=0; fail=0; warn=0
ok()   { printf "  PASS  %s\n" "$1"; pass=$((pass+1)); }
bad()  { printf "  FAIL  %s\n" "$1"; fail=$((fail+1)); }
opt()  { printf "  SKIP  %s (optional)\n" "$1"; warn=$((warn+1)); }

echo "== required =="
command -v node >/dev/null && [ "$(node -e 'console.log(process.versions.node.split(".")[0])')" -ge 20 ] \
  && ok "node $(node -v)" || bad "node >= 20 (SETUP.md #1)"
command -v ffmpeg >/dev/null && ok "ffmpeg" || bad "ffmpeg (SETUP.md #2)"
command -v ffprobe >/dev/null && ok "ffprobe" || bad "ffprobe (SETUP.md #2)"
npx --yes hyperframes --version >/dev/null 2>&1 \
  && ok "hyperframes ($(npx --yes hyperframes --version 2>/dev/null | head -1))" \
  || bad "npx hyperframes (SETUP.md #3)"
if [ -f .env ] && grep -q "^ELEVENLABS_API_KEY=.\+" .env; then ok "ELEVENLABS_API_KEY in .env"
else bad "ELEVENLABS_API_KEY in .env (SETUP.md #4)"; fi
command -v python3 >/dev/null && ok "python3 $(python3 --version 2>&1 | cut -d' ' -f2)" || bad "python3 (SETUP.md #6)"

echo "== optional =="
python3 -c "import PIL" 2>/dev/null && ok "PIL" || opt "PIL — vignette/overlay PNGs"
[ -f "$HOME/.herenow/credentials" ] && ok "here.now credentials" || opt "here.now — review canvas delivery (SETUP.md #7)"
PUB="${HERENOW_PUBLISH:-$HOME/.agents/skills/here-now/scripts/publish.sh}"
[ -f "$PUB" ] && ok "here-now publish.sh" || opt "here-now skill publish script (SETUP.md #7)"
if [ -f .env ] && grep -q "^GEMINI_API_KEY=.\+" .env; then ok "GEMINI_API_KEY in .env"
else opt "GEMINI_API_KEY — video-qa L3 (SETUP.md #8)"; fi
"$HOME/.venvs/capcut/bin/python" -c "import pyJianYingDraft" 2>/dev/null \
  && ok "pyJianYingDraft venv" || opt "pyJianYingDraft — capcut-export (SETUP.md #9)"
command -v whisper-cli >/dev/null && ok "whisper-cli" || opt "whisper-cli — faster QA seam probes"
node -e "require.resolve('puppeteer')" 2>/dev/null && ok "puppeteer" || opt "puppeteer — broll-capture screenshots (SETUP.md #9)"
[ -d "/Applications/Screen Studio.app" ] && ok "Screen Studio" || opt "Screen Studio — Lane C B-roll (SETUP.md #9)"

echo
echo "$pass passed, $fail required missing, $warn optional skipped"
[ "$fail" -eq 0 ] && echo "READY — required setup complete." || echo "NOT READY — fix the FAIL lines via SETUP.md."
exit "$fail"
