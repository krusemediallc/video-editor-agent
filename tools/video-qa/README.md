# video-qa — automated 4-layer QA for rendered videos

A finished .mp4 is an **audio + video artifact** — roughly half of real editing
mistakes are audible, not visible (a shipped branded edit's post-mortem found 6 audible
seam flubs that stills-only QA had missed). This engine lets an agent QA its own
edits without screenshot sweeps, spending compute cheap → expensive:

```
CHEAP    L1  ffprobe/ffmpeg technical (blackdetect, freezedetect, flash frames,
             decode errors, duration-vs-manifest, silencedetect, LUFS, clipping)
         L2  transcript edit-boundary checks on EVERY dialogue cut
             (clipped words, duplicate phrases, seam dead-air, caption coverage,
             butt-splice clicks) + isolated seam re-probes
         L3  Gemini watches AND listens to a 480p proxy (audio intact @128k),
             5fps sampling, enforced JSON schema — tells Claude WHERE to look
EXPENSIVE L4 inspection packets: contact sheet + marked waveform + word-level
             transcript + audio stats for a specific window — Claude verifies
             before changing any edit
```

## Invocation

This is a self-contained package (`tools/video-qa/`, node >= 20). Install once:

```bash
npm --prefix tools/video-qa install
```

Then from the pack root `npm --prefix tools/video-qa run qa:video -- <args>`, or from
inside the directory just `npm run qa:video -- <args>`. A working repo elsewhere can
alias it (`"qa:video": "npm --prefix \"<path to pack>/tools/video-qa\" run qa:video --"`);
relative path arguments resolve against the directory you ran the command from
(`INIT_CWD`), and `.env` is read from there first, then from the pack root.

## Commands

```bash
# reel-recut lane (manifest is dumped by build_reel.py during every build):
python3 .claude/skills/reel-recut/scripts/build_reel.py spec.json --qa-manifest-only
npm run qa:video -- --manifest <project>/spec.qa-manifest.json --words <project>/transcript.json

# hyperframes lane (EDL + output-time words, e.g. a branded-ad-edit project):
npm run qa:video -- --lane hyperframes --video out.mp4 --edl edl.json \
    --words words-master.json --words-are-output [--placement preview/manifest.json]

# any mp4, no manifest (L1 + Gemini only):
npm run qa:video -- --video out.mp4

# targeted inspection packet:
npm run qa:inspect -- --manifest spec.qa-manifest.json --start 31.5 --end 33.0

# tests (fixtures generate on first run; clean.mp4 is the false-positive canary):
npm run qa:test
```

Flags: `--skip-semantic` (no Gemini), `--fps N` (Gemini sampling), `--no-cache`,
`--instructions file.txt` (original request → given to Gemini), `--json`,
`--out dir`. Exit codes: **0** PASS · **1** PASS_WITH_WARNINGS · **2** FAIL.
Reports land in `<video dir>/_qa/<video stem>/qa-report.{json,md}` with inspection
packets under `inspect/<issue-id>/`. If an agent sandbox kills Node, run with it disabled.

## The three iron rules (learned the hard way)

1. **Never re-whisper the whole render and diff it.** Whisper hallucinates
   connective phrases at jump cuts and fuses differently every run. L2 maps
   SOURCE-side word times through the EDL; suspect seams get an **isolated 5.5s
   window re-probe** of the render, arbitrated by word *presence* (never by
   whisper's duration numbers — word ends are padded into pauses).
2. **The manifest comes from edit INTENT, never from analyzing the output.**
   `build_reel.py` dumps it from its own computed timeline; the hyperframes lane
   feeds the EDL/placement files the build already produces. A manifest derived
   from the render would inherit the exact bugs QA exists to catch.
3. **Measure the FILE, never the log.** Duration, streams, loudness all come from
   ffprobe/ffmpeg on the actual MP4.

## Issue anchoring

Issues anchor to **stable manifest event ids** (`cut:src48.8`, `caption:12` —
lane-native keys), not timestamps. A fix that shifts the timeline moves every
timestamp but keeps the anchors, so comparing anchored issues across re-renders
tells you reliably whether something was fixed.

## Fix loop + auto-fix whitelist

`run QA → FAIL? → read packet → fix → re-render → re-run` (cache makes unchanged
layers free). Claude may apply these repairs **without asking**:

| action | limit |
|---|---|
| nudge a cut point | ≤ 500ms (`suggestedFix.params.ms` says how far) |
| retime a caption | to its spoken window |
| gain/level adjustment | ≤ 3dB |
| extend/trim a clip | ≤ 500ms |
| remove an accidental duplicate segment | exact duplicate only |
| add an edge fade at a splice click | 25–30ms |

Anything else — restructuring the edit, dropping content, creative changes — goes
to the user with the inspection packet (2–3s subclips beat scrubbing). **Max 3
fix→re-render rounds** (`VIDEO_QA_MAX_REPAIR_ITERATIONS`), then stop and
escalate. Never loop on LOW or subjective issues.

## Severity meanings

- **CRITICAL** — corrupt/unreadable render, missing expected audio stream, hard
  clipping at 0 dBFS, >1s duration mismatch. Never ship.
- **HIGH** — probe-confirmed clipped word, duplicate dialogue, unexpected black
  or frozen frames, flash frames at a seam. FAIL until fixed or overridden.
- **MEDIUM** — dead air, splice click, loudness off target, caption mismatch
  (non-reel-recut), SFX masking VO. Warn — reviewable, not blocking.
- **LOW** — informational (hot-but-unclipped master, paraphrased reel captions,
  unconfirmed suspicions). Never blocks; never auto-"fix".

## Calibration notes (from live runs)

- A shipped-clean reel (49 silence cuts): PASS, zero HIGH — keep one as your
  false-positive canary.
- A repaired branded edit: PASS_WITH_WARNINGS (quiet −21 LUFS master + one splice
  click — both real observations).
- The same edit pre-fix (known-dirty): Gemini heard BOTH documented seam flubs
  (a "Because…" false-start, a re-take clip).
- Silence-derived cuts (reel-recut `silence_cut`) cannot clip audible speech —
  word "overlap" there is whisper end-padding; only probe-confirmed misses flag.
- Gemini 503s are retried ×3 with backoff, then the layer degrades to `skipped`
  with the reason in the report — never a crash.

## Env (`.env`)

`GEMINI_API_KEY` (Layer 3; everything else runs without it) ·
`GEMINI_QA_MODEL` (default `gemini-flash-latest`) · `VIDEO_QA_GEMINI_FPS` ·
`VIDEO_QA_INSPECT_PADDING_S` (default 1.5) · `VIDEO_QA_MAX_REPAIR_ITERATIONS`
(default 3) · `VIDEO_QA_TRANSCRIBER` (`auto`→whisper.cpp via
`npx hyperframes transcribe`, falls back to OpenAI word-granularity whisper —
`OPENAI_API_KEY`) · `VIDEO_QA_CACHE_DIR` (default `tools/video-qa/.qa-cache/`) ·
`FFMPEG_PATH` / `FFPROBE_PATH` (default: PATH, then /opt/homebrew/bin, /usr/local/bin).
