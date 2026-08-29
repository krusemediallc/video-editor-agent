# Video Editor Agent

A Claude Code skill pack that edits short-form videos **end to end**: raw
talking-head footage in, a finished branded motion-graphics edit out — style
cloned from a reference reel, sound-designed with ElevenLabs, QA'd frame by
frame, delivered on a live review page with timeline comments, and revised
round after round until sign-off.

This is not a rendering library. It is a set of skills that make a Claude Code
session behave like a working video editor with a proven pipeline and a
"verify pixels and dB, not intentions" culture.

## The pipeline

```
footage/ + (optional) reference reel + brand/site + ratio
        │
        ▼
[1] reel-style-clone ──────────→ STYLE-GUIDE.md (only if a reference exists)
        │
        ▼
[2] branded-ad-edit
      ingest → two crop candidates (zoom vs blur-pad — show both)
      whisper transcript → storyboard from the style guide
      hand-authored composition + karaoke captions + SFX markers
        │
        ▼
[3] sound-design ──────────────→ ElevenLabs SFX kit + music bed, mixed by math
        │
        ▼
[4] QA loop (video-qa)
      hyperframes check → ONE multi-timestamp snapshot → LOOK with vision
      → fix → render MP4 → verify the RENDERED file (frames + dB)
        │
        ▼
[5] video-review-canvas ───────→ live review URL (reply leads with the link)
        │
        ▼
[6] revision rounds
      read notes → screenshot the exact frame per note → fix
      edl-tighten for pacing → new file per version → republish same slug
      per-note QA table with evidence from the rendered file
        │
        ▼
[7] (optional) capcut-export ──→ CapCut draft for a human's final pass
```

## Quickstart

1. Clone this repo and open it in Claude Code.
2. Install the prerequisites below.
3. Copy `.env.example` to `.env` and paste your `ELEVENLABS_API_KEY`.
4. Drop your raw footage into `footage/` (and a reference reel if you have
   one).
5. Say: **"edit this like `<reference reel>`"** — or just "edit this video".
   The `video-edit-pipeline` skill takes it from there.

## Prerequisites

| Dependency | Why | Install / notes |
|---|---|---|
| Node.js >= 20 | HyperFrames + scripts | nodejs.org |
| ffmpeg / ffprobe | every probe, extract, crop, mux | `brew install ffmpeg` (or your package manager) |
| HyperFrames | composition + rendering engine | `npx hyperframes`; then `npx hyperframes skills update talking-head-recut` (pulls fonts + gsap) |
| whisper-cli + a ggml model | word-level transcription | whisper.cpp; download a ggml model (e.g. base.en or larger) |
| python3 | helper scripts | PIL (`pip install pillow`) optional, used by some frame tooling |
| ElevenLabs API key | SFX + music generation | `ELEVENLABS_API_KEY` in `.env` at repo root |
| here-now skill + credentials | canvas review delivery | agent docs at https://here.now/docs (fetch with `User-Agent: claude`); credentials live in `~/.herenow/credentials` |
| `GEMINI_API_KEY` (optional) | video-qa's deeper vision layer (L3) | skip if unset; QA still runs its other layers |
| pyJianYingDraft in a venv (optional) | CapCut draft export | only needed for the capcut-export handoff |

External dependencies are documented, not vendored — nothing in this repo
ships a copy of HyperFrames, whisper models, or ffmpeg.

## Skills catalog

| Skill | What it does |
|---|---|
| `video-edit-pipeline` | **Master orchestrator.** Routes any edit request through the full pipeline. Start here. |
| `branded-ad-edit` | Raw talking head → finished branded motion-graphics ad: framing grammar, card-per-line, karaoke captions, ~40 SFX + bed, QA → render → verify. |
| `reel-style-clone` | Reverse-engineer a reference reel frame by frame into a STYLE-GUIDE.md + build directives. |
| `sound-design` | ElevenLabs SFX/music generation, audit pass, style-matching a reference track, mixing math. |
| `video-qa` | 4-layer QA procedures for compositions and rendered MP4s. |
| `video-review-canvas` | here.now review page with frame-accurate scrubber + timeline comments; reads notes back per version. |
| `edl-tighten` | Surgical silence/pacing cuts with a full timeline remap (captions/cards/SFX stay synced). |
| `reel-recut` | Spec-driven short-form recut style. |
| `capcut-export` | Layered export into a CapCut draft via pyJianYingDraft. |

## Limitations (honest)

- **CapCut export is work-in-progress.** The layered export works but the
  schema patch is still being hardened — always verify the draft opens in
  CapCut before relying on it.
- **Canvas delivery requires here.now.** Without the here-now skill and
  credentials you still get the rendered MP4, just no live review page or
  timeline-comment loop.
- Transcription quality tracks your whisper model choice; tiny models miss
  words that then miss captions.
- The pipeline assumes single-subject talking-head source footage; multi-cam
  or multi-shot sources need manual splitting first.
