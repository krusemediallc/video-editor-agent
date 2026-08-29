# SETUP — connect every tool this pack needs

This file is written for the AI agent (and works fine for humans). Work through it
top to bottom on a fresh machine **before the first edit**. Every item has a CHECK
command and a FIX. Run all checks at once with:

```bash
bash scripts/check-setup.sh
```

**MCP servers: none required.** Everything runs through the CLI (ffmpeg, node,
python) and plain REST APIs (ElevenLabs, optional Gemini, optional here.now).
Two optional MCP-powered skills exist: `broll-capture` can use a **browser MCP**
(Playwright or a browser extension) for no-code website captures — the bundled
Puppeteer script covers the same ground without one — and `openart-broll` uses the
**OpenArt MCP** for AI-generated footage/overlays. Everything else is MCP-free.

---

## Required — the pipeline does not run without these

### 1. Node.js ≥ 20 (+ npx)

Runs HyperFrames, the caption generator, and the sound-design scripts.

- CHECK: `node -v` → v20 or newer; `npx --version` prints a version.
- FIX: install from https://nodejs.org or `brew install node`.

### 2. ffmpeg + ffprobe

Every crop, EDL cut, audio measurement, frame extraction, and QA check.

- CHECK: `ffmpeg -version | head -1` and `ffprobe -version | head -1`.
- FIX: `brew install ffmpeg` (macOS) / your package manager. Any recent build works;
  the skills avoid libass/drawtext on purpose, so no special build flags are needed.

### 3. HyperFrames (HTML→video renderer)

The composition/render engine for `branded-ad-edit` and everything downstream.
Installed on demand by npx — no global install.

- CHECK: `npx hyperframes --version` (first run downloads the package).
- THEN: `npx hyperframes skills update talking-head-recut` — pulls the fonts +
  `gsap.min.js` the composition templates expect.
- Optional speedup: render with `PRODUCER_BROWSER_GPU_MODE=hardware`.

### 4. ELEVENLABS_API_KEY (`.env`)

Sound design: SFX generation (`/v1/sound-generation`) and music beds (`/v1/music`).

- CHECK: `grep -c "^ELEVENLABS_API_KEY=.\+" .env` → 1.
- FIX: `cp .env.example .env`, paste your key from https://elevenlabs.io
  (Profile → API Keys). The scripts read it from `.env` / the environment; it is
  never hardcoded. Generation spends ElevenLabs credits — the agent announces
  before spending.

### 5. Transcription (bundled — verify once)

Word-level transcripts drive captions, storyboards, and EDL cuts.
`npx hyperframes transcribe <audio> --json --model small.en` manages its own
whisper models — no separate install.

- CHECK: `npx hyperframes transcribe --help` exits 0.
- Optional: a standalone `whisper-cli` (`brew install whisper-cpp`) + a ggml model
  makes `video-qa` L2 seam re-probes faster, but is not required.

### 6. python3

EDL transcript remaps, QA envelope scans, reel-recut rendering.

- CHECK: `python3 --version` → 3.10+.
- Optional: PIL (`python3 -c "import PIL"`) for vignette/overlay PNG generation —
  skills degrade gracefully without it.

---

## Optional — unlock specific stages

### 7. here.now (review-canvas delivery)

`video-review-canvas` publishes the frame.io-style review page and reads timeline
notes back. Without it, deliver cuts as files and collect notes as text.

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

### 11. pyJianYingDraft venv — capcut-export (work-in-progress)

Only for exporting a finished edit into a CapCut desktop draft.

- CHECK: `~/.venvs/capcut/bin/python -c "import pyJianYingDraft" && echo ok`.
- FIX: `python3 -m venv ~/.venvs/capcut && ~/.venvs/capcut/bin/pip install pyJianYingDraft`.
  Read the `capcut-export` SKILL.md before relying on it — the current-CapCut schema
  patch is documented but not yet field-verified.

---

## First-session smoke test

After the checks pass, prove the render path end to end (~1 minute):

```bash
npx hyperframes --version
bash scripts/check-setup.sh
```

Then drop a video into `footage/` and say **"edit this video"**. The
`video-edit-pipeline` skill takes over. If any stage fails on a missing tool, come
back to this file — and record machine-specific quirks you discover in
MASTER_CONTEXT.md so the next session doesn't rediscover them.
