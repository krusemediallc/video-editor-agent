# Setup

Run the complete local example with one command:

```bash
bash scripts/setup.sh --demo
```

This creates missing `.env` and `MASTER_CONTEXT.md` files, installs the locked
`tools/video-qa` npm dependencies, checks prerequisites, then generates a tiny
synthetic edit, a versioned review page, a searchable footage catalog, project
state, and QA reports under a new `outputs/demo-*` directory. The demo makes no
paid calls, downloads no models, and uploads nothing. Package installation needs
network access on the first run; the demo itself works offline afterward.

Python 3.10+, ffmpeg/ffprobe and Node.js 20+ with npm must already be installed.
On macOS use Homebrew (`brew install python ffmpeg node`); on Linux use your
package manager and a supported Node.js release. Linux distribution packages
sometimes provide older Node versions; the doctor reports this explicitly.
The shell entry points support macOS and Linux (or WSL on Windows).

## Choose the workflow you need

```bash
bash scripts/setup.sh --lane demo --dry-run
bash scripts/setup.sh --lane demo --no-install
bash scripts/check-setup.sh --lane demo
```

`--dry-run` prints the plan without writing files or installing anything.
`--no-install` creates only missing local config and requested skill links, then
reports missing prerequisites. Doctor checks are read-only and offline: no `npx`
downloads, API requests, model downloads, or secret values in output.

| Lane | Required tools beyond Python and ffmpeg/ffprobe |
| --- | --- |
| `local` (default) | None; raw cuts, recap assembly and catalog ingestion |
| `demo` | Node.js 20+, npm, locked video QA dependencies |
| `qa` | Node.js 20+, npm, locked video QA dependencies |
| `hyperframes` | Node.js 20+, npm, installed HyperFrames CLI |
| `sound-design` | Node.js 20+, npm, ElevenLabs API key |
| `all` | Everything above; choose only if using all those workflows |

ElevenLabs is required only for generated sound. Gemini, transcription backends,
publishing credentials, and other generation services remain optional for the
local/demo/QA workflows. Offline checks confirm configuration, not API access.
No MCP server is required for the local pipeline.

Setup never changes global packages or git configuration by default. Explicit
`--install-system` allows Homebrew or Debian/Ubuntu apt installation of missing
ffmpeg/Node prerequisites (Python must be installed first). It cannot be combined
with `--no-install`. System installation may prompt through the package manager.

Local npm dependencies are installed with `npm ci` when missing or when the lock
file changes. Existing matching installs are preserved. HyperFrames is optional;
its lane installs under `tools/hyperframes/node_modules` if no installed CLI is
found. Invoke that local binary directly, or add its `.bin` directory to PATH.
Setup does not download transcription models or update personal agent skills.

## Link skills into another working repo

```bash
bash scripts/setup.sh --no-install --link-skills /path/to/working-repo
```

Links are computed relative to the destination `.claude/skills/` directory.
Existing files, directories and symlinks (including dangling links) are preserved.
Rerunning setup is safe; it never replaces personal `.env` or `MASTER_CONTEXT.md`
content. New `.env` files are created with owner-only permissions. Fill in your
projects directory and editing preferences in `MASTER_CONTEXT.md` before a real
edit; set `VIDEO_PROJECTS_DIR` in `.env` if scripts should use that location.
Generated demo media always stays in its requested output directory, independent
of your personal projects directory.

## Run and inspect the demo

```bash
bash scripts/demo.sh
# Optional: choose a new directory. Existing output paths are never overwritten.
bash scripts/demo.sh --output outputs/demo-first-run
```

Serve the printed review directory locally. It contains two real 4-second
renders, a version picker, before/after comparison and a resolved sample note
with frame evidence. Notes are stored in this browser; export revisions JSON to
share them. The page uses JavaScript modules, and video seeking requires HTTP
byte ranges. Use the printed local-server command:

```bash
python3 scripts/serve-review.py --directory outputs/demo-first-run/review --port 8765
```

Open `http://127.0.0.1:8765`. The server serves only the chosen directory, binds to
the local machine, and supports seeking in both comparison videos. Use `--port 0`
to choose a free port and print its URL. Stop the server with Ctrl-C. Publishing
remains separate.

The demo's source is a six-second ffmpeg test pattern and tone. The recap
assembler places the ending before the opening, and a green card appears from
1 to 3 seconds in v2. It verifies 120 output frames, exact pre-encode audio sample
counts, decode, storyboard coverage and the card's actual pixels. It also writes
`project.json`, `catalog.json`, `_qa/`, and a machine-readable `demo-result.json`.
The transcript is empty because the fixture contains no speech; transcript QA is
reported as degraded and semantic QA is skipped. The HTML file records intended overlay
timing for the ffmpeg fixture; it is not a HyperFrames-rendered composition.

## Run regression checks

```bash
bash scripts/test.sh
bash scripts/test.sh --integration
```

The default runner tests setup safety, project/catalog behavior, review model and
builder behavior, and the installed QA engine. Missing optional media/Node
prerequisites are reported as skips. `--integration` requires the demo dependencies
and additionally runs the full demo and recap assembler fixtures. Both commands
are offline; live transcription/model checks are disabled. Individual suites can
also be invoked directly, for example:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
npm --prefix tools/video-qa test
npm --prefix tools/video-qa run typecheck
```

## Optional — unlock specific stages

### 7. here.now (review-canvas delivery)

`video-review-canvas` publishes the frame.io-style review page and reads timeline
notes back. Without here.now, use a local canvas and export its review JSON, or
deliver cuts as files and collect notes as text.

- CHECK: `test -f ~/.herenow/credentials && echo ok`; publish script present at
  `~/.agents/skills/here-now/scripts/publish.sh` (or set `HERENOW_PUBLISH` to yours).
- FIX: install the here-now skill and sign in once. Its agent docs are UA-gated:
  fetch https://here.now/docs with header `User-Agent: claude`.

### 8. GEMINI_API_KEY (`.env`) — video-qa Layer 3

A multimodal model watches+listens to a 480p proxy of the render and flags
candidate issues. Skipped gracefully when unset; QA layers 1/2/4 still run.

- CHECK: `grep -c "^GEMINI_API_KEY=.\+" .env` → 1 (or accept the skip).
- FIX: key from https://aistudio.google.com. Model override: `GEMINI_QA_MODEL`
  (default `gemini-flash-latest`).

### 9. Website capture (broll-capture)

- **Puppeteer** for the bundled screenshot script: CHECK
  `node -e "require.resolve('puppeteer')"` from the repo root; FIX `npm i puppeteer`.
  (Or skip it and use a connected browser MCP.)
- **Screen Studio** (macOS, optional): highest-fidelity B-roll of your real browser.
  CHECK `ls /Applications/Screen\ Studio.app` and `command -v screenstudio` for its
  CLI. Any screen recorder substitutes — the skill's sync-marker + crop recipe is
  recorder-agnostic.

### 10. OpenArt MCP (openart-broll) — generated footage & overlays

- CHECK (in-session, not shell-checkable): the `openart_*` tools are present and
  `openart_account_get` returns your plan + credit balance.
- FIX: connect the OpenArt MCP in your client (claude.ai → Connectors, or Claude
  Code MCP settings). No API key — auth rides on the connection. Generation spends
  OpenArt credits; the skill quotes with `openart_model_cost` and asks before firing.

### 10b. Arcads API (arcads-broll) — generated B-roll & motion graphics

- CHECK: `grep -c "^ARCADS_API_KEY=.\+" .env` → 1, and the companion pack cloned:
  `git clone https://github.com/krusemediallc/arcads-claude-code` (its
  `arcads-external-api` skill carries the routes + per-model prompt library).
- FIX: key from your Arcads account (sign up: https://arcads.ai/?via=claude-code).
  Generation spends Arcads credits — the skill estimates and asks before firing.

### 10c. OPENAI_API_KEY (`.env`) — cloud whisper fallback

Used only when whisper.cpp is unavailable: the QA engine's transcriber, `hook-splitter`'s
`transcribe.py`, and `arcads-video-edit`'s per-shot transcripts.

- CHECK: `grep -c "^OPENAI_API_KEY=.\+" .env` → 1 (or accept local whisper only).
- FIX: key from https://platform.openai.com. Transcription spends API credits.

### 11. pyJianYingDraft venv — capcut-export (work-in-progress)

Only for exporting a finished edit into a CapCut desktop draft.

- CHECK: `~/.venvs/capcut/bin/python -c "import pyJianYingDraft" && echo ok`.
- FIX: `python3 -m venv ~/.venvs/capcut && ~/.venvs/capcut/bin/pip install pyJianYingDraft`.
  Read the `capcut-export` SKILL.md before relying on it — the current-CapCut schema
  patch is documented but not yet field-verified.

### 12. Swift toolchain — hook-variations (optional)

`hook-variations` verifies joined files with an AVFoundation probe (`scripts/avtest.swift`)
because ffmpeg cannot see the parameter-set mismatch that freezes QuickTime.

- CHECK: `command -v swiftc`.
- FIX: `xcode-select --install`. The skill builds `avtest` on first use
  (`swiftc -O avtest.swift -o avtest`, gitignored).

### 13. The scrub hook — before your first commit

This is a public-style repo: `scripts/scrub-check.sh` refuses secrets, private hosts,
personal paths, e-mails, review-canvas slugs, fee amounts, media files and anything in your
deny-list.

- CHECK: `git config core.hooksPath` → `.githooks`.
- FIX: `git config core.hooksPath .githooks`, then
  `cp scripts/scrub-denylist.example.txt scripts/scrub-denylist.local.txt` and add your
  clients, people and private repo names (the local file is gitignored). Dry run:
  `bash scripts/scrub-check.sh --all`.

---

## First-session smoke test

```bash
bash scripts/setup.sh --demo
```

After the synthetic example passes, put real source footage in your configured
projects directory and ask the agent to edit it. Record machine-specific setup
notes in the gitignored `MASTER_CONTEXT.md`. Keep real media and credentials out
of commits; see the scrub-hook instructions above.
