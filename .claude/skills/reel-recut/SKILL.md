---
name: reel-recut
description: >-
  Recut a raw vertical talking-head reel into a finished short-form edit: a
  persistent title banner, word-synced karaoke captions, callout boxes for
  asides and comment-keyword CTAs, and tight silence-cut "talking over myself"
  pacing — all described in ONE JSON spec and rendered deterministically.
  Use whenever the user hands over a talking-head video and wants it edited,
  styled, or "made to match my other videos / this reference reel" — including
  "add my captions", "put the banner on it", "tighten the cuts / make it
  punchier", "cut the dead air", "add a callout when I say X", or "fix the part
  where I trip over my words". Also use to tweak an existing reel-recut edit
  (change banner text, add/move a callout, remove a stumble, re-time captions),
  and for a graphics-free raw cut (pacing only) on brand-deal footage a
  client's editor will finish. Not for plain subtitles on untouched footage
  (embedded-captions), overlay graphic cards with the clip untouched
  (talking-head-recut), or a fully branded motion-graphics ad (branded-ad-edit).
---

# reel-recut — spec-driven short-form talking-head edit

Turns a raw (or lightly-edited) vertical talking-head reel into a finished
short-form look. The four signature elements:

1. **Persistent title banner** (top, rounded accent-color box, heavy weight, UPPERCASE, 1-2 lines)
2. **Karaoke captions** (bottom third, bold white + thick black stroke, short cleaned phrases, ~2s each)
3. **Callout boxes** for an aside or the comment-keyword CTA (mid-screen, same box style)
4. **Tight "talking over myself" pacing** — inter-phrase pauses silence-cut out so phrases butt together

The existing music/B-roll/audio are kept. The whole edit is described in ONE JSON
"spec" and rendered by `scripts/build_reel.py` in a single pass.

**The styling is spec-driven, not hardcoded.** The spec's `style` block sets the
accent color, font, weights, sizes, and positions (see `references/spec.md`). The
defaults — purple `#8030F8` boxes + Montserrat Black/ExtraBold — are **one example
creator's brand**, reverse-engineered from their reels and kept so the script runs out
of the box. Replace them with the user's brand, or capture the values off whatever
reference reel you're asked to match (sample the box color from a frame, identify the
font, note positions as fractions of frame height). `assets/spec.example.json` labels
the example values explicitly.

**Raw-cut mode (no graphics).** Omit `banner`, `captions` and `callouts` entirely and the
script skips the whole overlay pass — you get element 4 (the pacing) on its own. That is the
right shape for a first-round cut on a brand deal, where the brand's own editor finishes the
video and any overlay you add is wasted work. Pair it with `"fps": "source"` so a 60fps
master is not silently downsampled to 30 on the way to their editor.

## Environment constraints (read `references/environment.md`)

- All text is rendered with **PIL into transparent PNGs** and composited with ffmpeg
  `overlay`. This exists because some ffmpeg builds lack libass/libfreetype (`drawtext`
  and `subtitles` simply don't exist there), and it is kept because it is fully portable —
  don't rewrite it around `drawtext`.
- Graphics are pre-composed into **one overlay video** so the final render has 2 inputs.
  Do not hand-build a 30-input filtergraph — it can OOM a 16 GB machine. The script handles this.
- If an agent sandbox kills ffmpeg (SIGURG / odd exit codes), re-run with the sandbox disabled.
- ffmpeg/ffprobe come from PATH (override with `FFMPEG`/`FFPROBE` env vars). Local
  transcription uses whisper-cli + a ggml model; cloud Whisper needs `OPENAI_API_KEY`
  in a `.env` at the repo root.

## Workflow

**Source from a URL?** If the user gives a link instead of a local file (an IG reel,
TikTok, YouTube — their own or a reference to match), download it first (e.g. `yt-dlp
"<url>"`), then feed that local path in as the target/reference clip below.

The script does the deterministic rendering. Your job is the judgment: watch the
videos, write good captions, and choose the cuts. Follow `references/workflow.md`
step by step. In short:

1. **Probe + watch.** `ffprobe` both clips. Use the `claude-video-vision` plugin if
   available (`video_analyze` for scene/silence/loudness, `video_watch` for frames), or
   plain frame extraction. If matching a NEW reference, capture banner/caption/callout
   styling from it into the spec's `style` block.
2. **Transcribe.** Get the target's speech with timestamps (whisper-cli `-ojf` locally,
   or OpenAI Whisper `verbose_json` with `timestamp_granularities=["word"]` — word-level
   timing is needed for stumble removal and CTA placement).
3. **Write the spec** (copy `assets/spec.example.json`). This is where the craft is:
   - `banner`: 1-2 SHORT uppercase lines, parallel to the reference's hook.
   - `captions`: split the transcript into ~2s phrases of <= ~6 words. **Clean them**:
     drop filler ("like", "um"), fix transcription errors (whisper reliably mangles
     product/brand names — learn the user's recurring ones), and apply the user's house
     copy rules (the example brand bans em dashes in on-screen copy — use
     periods/commas). Captions are paraphrase-clean, not verbatim.
   - `callouts`: add one when the user flags an aside or a CTA ("add a callout when I
     say comment X"). Set `suppress_captions` to the caption indices that overlap, so
     the same words don't show twice.
   - `silence_cut.enabled: true` for the tight feel. FIRST confirm there's no loud
     music bed (see workflow.md) — if pauses don't drop below the noise floor, cutting
     glitches the music; lower `noise_db` or disable.
   - **Noisy source (car, cafe, fan, handheld outdoors)? `silence_cut` will silently do
     almost nothing.** It wraps ffmpeg `silencedetect`, a flat energy gate, so a source
     whose floor sits near the threshold reports a handful of pauses and misses the
     rest. Check first: if `silencedetect=noise=-30dB:d=0.15` returns only a few spans,
     or none in the back half, switch to VAD-driven `manual_cuts` planned with
     `scripts/plan_cuts.py` (see workflow.md step 2b — it targets a fixed residual gap
     per join, which is what makes the pacing read as one continuous take).
   - `manual_cuts`: `[[start,end]]` ranges (original timeline) to remove a stumble or
     a bad take. Get exact word times from the transcript.
4. **Render.** `python3 scripts/build_reel.py spec.json`. It prints the new duration +
   counts and dumps `<spec>.qa-manifest.json` next to the spec (regenerate anytime with
   `--qa-manifest-only`) — a machine-readable manifest of every cut, caption, and
   callout with source + output times.
5. **QA every seam** (workflow.md step 5b): run `scripts/verify_cuts.py` on the planned
   cuts (cut-vs-uncut transcription of the same window), spot-check seams from the
   manifest, re-transcribe the OUTPUT and read it end to end as prose, and scan for
   doubled words. Fix by editing the spec (nudge a cut ≤500ms, retime a caption),
   re-render, re-verify; stop after 3 rounds and surface what's left to the user.
6. **Deliver a phone-viewable link** (review page or file host — see environment.md),
   never just a bare path. Big masters want a 720p proxy for the player; keep the
   master on disk. Keep the original raw untouched.

Iterate by editing the spec and re-running — it's fast (a 60-75s reel renders in well
under a minute). Spec fields are documented in `references/spec.md`.

## On a PAID brand deliverable, the script is approved copy

Only remove what the script itself marks as an alternate (Hook 1 / Hook 2, alt takes) and
genuine stumbles. **Never trim approved lines to hit a runtime target** or to match a
reference ad's duration — propose the trim with timecodes and let the user decide, since
they own the client relationship. Verify every cut with a *different* transcription pass
than the one that made it, and read the surviving transcript end to end as prose.

## Style quick-reference

- The example brand (defaults): accent `#8030F8`, Montserrat (Black banner, ExtraBold
  captions/callouts, auto-downloaded from Google OFL on first run), vertical 1080x1920,
  30fps, no em dashes in on-screen copy. **Treat every one of these as replaceable** —
  set the user's own values in the spec's `style` block.
- Don't restyle the speaker or their footage; this skill edits pacing and adds graphics,
  nothing else.
