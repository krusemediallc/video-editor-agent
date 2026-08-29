# ARCHITECTURE — Video Editor Agent

## What this is

A Claude Code skill pack that turns raw talking-head footage into finished,
reviewed short-form video. All the intelligence lives in `.claude/skills/`;
media and renders live in gitignored working directories.

## Repo layout

```
.claude/skills/          # the 9 skills (each: SKILL.md + references/scripts/assets)
  video-edit-pipeline/   # MASTER orchestrator — start here
  branded-ad-edit/       # the main build (crops, storyboard, cards, captions, render)
  reel-style-clone/      # reference reel → STYLE-GUIDE.md
  sound-design/          # ElevenLabs SFX/music, mixing math
  video-qa/              # 4-layer QA on comps + rendered MP4s
  video-review-canvas/   # here.now review page + timeline-comment readback
  edl-tighten/           # silence/pacing cuts with full timeline remap
  reel-recut/            # spec-driven short-form recut style
  capcut-export/         # layered export to a CapCut draft (WIP)
footage/                 # drop raw footage here (gitignored)
outputs/                 # per-project working dirs + renders (gitignored)
CLAUDE.md                # session rules
MASTER_CONTEXT.md        # brand + defaults + learnings (from template)
SESSION_LOG.md           # dated session history
.env                     # ELEVENLABS_API_KEY (+ optional GEMINI_API_KEY)
```

## How the skills relate (the pipeline)

`video-edit-pipeline` is the only entry point users need. It sequences:
intake → `reel-style-clone` (if a reference exists) → `branded-ad-edit`
(crops/transcribe/storyboard/compose) → `sound-design` (SFX + bed) →
QA loop with `video-qa` (snapshot → look → fix → render → verify the MP4) →
deliver via `video-review-canvas` → revision rounds (notes readback,
frame-evidence per note, `edl-tighten` for pacing, new file per version,
same slug) → optional `capcut-export` for a human's final pass.

The specialist skills are also independently invocable for narrowly scoped
requests (e.g. "just tighten the silences").

## External dependencies (documented, not vendored)

- **HyperFrames** — composition + render engine: `npx hyperframes`, plus
  `npx hyperframes skills update talking-head-recut` for fonts/gsap.
- **ffmpeg / ffprobe** — all probing, extraction, cropping, muxing.
- **whisper-cli + a ggml model** — word-level transcription.
- **node >= 20**, **python3** (+ optional PIL).
- **ElevenLabs API** — `ELEVENLABS_API_KEY` env var from `.env`.
- **here-now skill** — canvas publishing; docs at https://here.now/docs
  (fetch with `User-Agent: claude`), credentials in `~/.herenow/credentials`.
- **pyJianYingDraft** in a venv — CapCut export only.
- Optional **GEMINI_API_KEY** — video-qa's vision layer.

## Provenance

Distilled from a production editing stack and one full shipped edit: a real
4-round client-style engagement — style cloned from a reference reel,
ElevenLabs sound design, surgical EDL pacing cuts, and a canvas review loop
through sign-off. The hard-won lessons (two crop candidates shown as images,
one batched snapshot, per-note evidence tables, new file per version,
verify-in-pixels) are baked into the skills rather than left as tribal
knowledge.
