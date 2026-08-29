# Step-by-step: recut a reel

## 1. Probe + understand both clips
```
ffprobe -v error -show_entries format=duration -show_entries stream=codec_name,width,height <clip>
```
If the `claude-video-vision` plugin is available:
- `video_analyze` with `{scene_changes, silence, loudness, transcription}` on the
  reference reel — dense scene-change bursts = montage; no silence intervals + ~-14 LUFS
  = music bed throughout.
- `video_watch` with `view_sample` frames (images, ~340px) on both — read the reference's
  banner/caption/callout look, and the target's content + which segments are talking-head
  vs B-roll.

Without the plugin: extract frames (`ffmpeg -ss <t> -i clip.mp4 -frames:v 1 f.png`) and
read them, and transcribe with whisper-cli. If matching a NEW reference style, capture its
banner/caption/callout styling into the spec's `style` block (colors, font, positions).

## 2. Is there a music bed? (decides whether silence-cutting is safe)
Run `silencedetect` at a few thresholds:
```
ffmpeg -i <clip> -af silencedetect=noise=-30dB:d=0.15 -f null -
```
If the inter-phrase gaps DROP BELOW -30 dB, there's no loud bed — silence-cutting is clean.
If they don't (a loud continuous bed), cutting will glitch the music: lower `noise_db`,
rely on `manual_cuts`, or disable `silence_cut`.

## 2b. Noisy room? Cut from VAD, not from an energy gate

`silencedetect` is a flat energy gate, so a noisy source (car, cafe, fan, handheld
outdoors) defeats it *quietly*: it returns a few short spans and you ship a cut that
removed nothing. One in-car take had a -36 dB floor and `silencedetect` found 12 spans
in 118s and **none at all past 70s**.

The reliable map is voice activity, not level:

```
whisper-vad-speech-segments -f audio.wav -vm <path-to>/ggml-silero-v5.1.2.bin -vt 0.5
```
(if the GPU path aborts on your build, drop any `-ug` flag). That prints real speech
segments. Then, for each gap between them, walk each boundary outward against a 10 ms
RMS envelope while the level stays ~8-10 dB above the measured floor, so consonant tails
and breaths survive, and emit the remainder as a `manual_cuts` entry.
`scripts/plan_cuts.py` implements exactly that — feed it the wav and the VAD segments
as JSON, take its `cuts.json` into the spec's `manual_cuts`.

### Target a fixed RESIDUAL GAP, not a fixed pad

A fixed pad leaves whatever is left over, so joins end up 70–270 ms apart depending on how
much breath was in each gap — and it is that *unevenness*, not the average, that stops it
reading as one run-on take. Instead compute how much of each gap is genuinely inaudible,
then keep exactly `TARGET_GAP` of it split either side and cut the rest (what
`plan_cuts.py --gap` does). Now one number controls the whole feel:

| target | reads as |
|---|---|
| 90 ms | tightened, still breathes |
| 45 ms | the typical recut pace |
| **30 ms** | run-on, "talking over myself" (~1.8 frames at 60fps) |
| <25 ms | starts to sound spliced |

### Do NOT tighten the word gaps inside a segment

VAD merges over 120–330 ms beats *between words*, and tightening those looks like free
extra run-on feel. It is a trap. Energy cannot distinguish a beat between words from a
word-initial stop closure, a word-final fricative, or a reduced function word. On one paid
deliverable, a guard that rejected any quiet run sitting inside a word in **either** of two
transcripts still let through cuts that destroyed **"of"** in "the importance *of* quality"
(leaving "importance" audible on both sides of the join) and both ends of **"teams"** plus
the head of **"driving"**. Seam QA went PASS → FAIL with 6 HIGH findings, every one a
word-gap cut, while the flat-30 ms segment joins in the same render were clean. It was
worth 1.35s of runtime; not worth it. To go tighter, refilm at pace. (`plan_cuts.py`
keeps this pass in the code, disabled, as the record.)

**Phone raws carry STOP-TAPS at recording boundaries.** A line-by-line phone raw is many
stitched recordings — every digital-zero run ≥30ms in the audio is a stop/start boundary,
and a tap-to-stop transient often sits just before one. VAD counts the hand-reach + tap as
speech, so gap-based joins anchor AFTER the tap and it ships. Hunt three modes per
boundary: (1) stop-taps — a dip-below-floor followed by a kept spike in the 0.3s BEFORE
the zero run (do NOT search from `word_end + pad`; a tap inside the pad gets skipped —
that mistake cost a review round); (2) **kept digital-zero runs** — a boundary inside a
keep span puts literal silence in the render, and 90 ms of digital zeros reads dead in a
way room tone does not; (3) surviving start-noise after the boundary — but isolate before
cutting: one such candidate turned out to be the word "And" spoken softly. Fix: pin the
join edge to the measured word boundary, not VAD's. The same over-inclusion shows up as
"dead space" before a restarted word.

**A raw full of repeated takes is a take-SELECTION job.** When the speaker re-reads lines
to fix them, the edit is choosing the script-correct take per pair, then pause removal.
Isolate BOTH candidates to their own wavs and transcribe independently before choosing —
and beware two traps: (1) **whisper smooths repeated takes away** in a full-file pass (it
printed one clean word where the audio had a stranded attempt + restart; the double only
appeared when the RENDER was re-transcribed and scanned for doubled words — do that scan
even when the source transcript looks clean); (2) VAD can merge a discarded take's tail
into the next keep segment — split the segment at the measured energy valley.

**Isolate a VAD segment to identify a flub.** A one-word false start transcribes as
garbage in the full-file pass (whisper large-v3 once also *hallucinated a 3× repeat loop*
that did not exist in the audio). Slice each suspicious VAD segment to its own wav and
transcribe that: aborted first syllables come back as unmistakable near-words once
isolated. Record confirmed flubs as `plan_cuts.py --flubs` entries so the whole segment
is dropped.

## 3. Transcribe with timing
Use `video_watch` transcription (if available) for phrase-level, or whisper word
timestamps (see environment.md — local whisper-cli `-ojf` or the OpenAI API) when you
need exact word times — required to remove a stumble or to place a CTA callout precisely.
Save the word JSON and point the spec's `words` field at it so the QA manifest carries
remapped word timings.

## 4. Author the spec (the craft)
Copy `assets/spec.example.json`. Captions are the main work:
- ~2s per card, <= ~6 words, <= 2 lines.
- **Clean them**: drop filler ("like", "um"); fix transcription errors (whisper mangles
  product and brand names — learn the user's recurring ones and fix on sight). Captions
  are paraphrase-clean, not verbatim.
- Apply the user's house copy rules (the example brand bans em dashes in on-screen
  copy — use periods/commas; ask for or learn your user's equivalents).
- Banner: 1-2 SHORT uppercase lines, parallel to the reference reel's hook.
- Callouts: one for an aside or the comment-keyword CTA; set `suppress_captions` for the
  overlapping caption indices so the same words don't show twice.
- Set `manual_cuts` for stumbles/bad takes from the word timings.
- Set the `style` block to the user's brand (or the captured reference styling).

## 5. Render
```
python3 scripts/build_reel.py spec.json
```
(disable the agent sandbox if ffmpeg dies under it). It prints the new duration + counts
and dumps `<spec>.qa-manifest.json` next to the spec — regenerate anytime with
`--qa-manifest-only`.

## 5b. Validate every seam before you ship

Cheap checks that have each caught real defects:

```bash
# 1. per-cut: does applying this cut change the words at the seam?
WHISPER_MODEL=<ggml-model> python3 scripts/verify_cuts.py cuts.json --src raw-audio.wav
# 2. the whole render: re-transcribe the OUTPUT and read it end to end as prose;
#    scan for doubled words (the fingerprint of a surviving discarded take)
```
The manifest lists every cut with source + output times — use it to spot-check each seam
in the render (`ffmpeg -ss <out_t - 1> -t 2` slices, transcribed in isolation).

Interpreting a flagged seam:
- If the flagged word is heard intact when the seam is isolated and re-transcribed, the
  flag is a false positive from loose word timings (transcript-timing overshoot) —
  common for `silence`-origin cuts, which removed *measured* silence.
- "Word NOT heard at the seam" on an isolated slice is real — **with one exception**:
  when the flagged word is the first word of an INTENTIONALLY DISCARDED take whose loose
  cloud word-start overlaps the seam, "not heard" is exactly what you want. Before acting
  on a confirmed clip at a take boundary, check the energy envelope and isolate the KEPT
  side of the seam.
- **Never act on a full-file transcript alone.** whisper large-v3 has hallucinated a 3×
  repeat loop and 10 invented words in a stat line *and* dropped an "of" that was
  genuinely present — all on one project. Any suspicion, re-transcribe that region in
  isolation before you change a cut.

Fix by editing the spec (nudge a cut ≤500ms, retime a caption, remove a duplicate),
re-render, re-verify; stop after 3 rounds and surface what's left to the user.

## 6. QA without a video player
- Extract frames: `ffmpeg -ss <t> -i out.mp4 -frames:v 1 q.png`, then read them.
- Pixel-check a callout/banner: sample its band for the spec's `accent_color`.
- Stumble/CTA edits: re-transcribe that region of the OUTPUT and confirm the words.

## 7. Deliver
Send a phone-viewable link (review page or file host — see environment.md); keep the
original raw untouched.

## Common follow-up requests and how to handle them
- "remove the callout / the zooms" -> delete from spec (this build has no zooms by default).
- "tighter cuts / talking over myself" -> enable silence_cut, lower edge/min_pause (or
  re-plan VAD cuts at a smaller --gap).
- "fix where I trip over my words / repeat myself" -> whisper word times -> add a
  `manual_cut` over the duplicated take; keep the cleaner one.
- "add a callout when I say X" -> whisper word times for X -> callout window + suppress
  the duplicate caption.
- "change the banner / wording" -> edit `banner` and re-run.
