# Layer 2 — transcript edit-boundary QA

Runs on EVERY dialogue cut (near-free). The primary signal is SOURCE-side word timings
checked against each cut's provenance (`src.start`/`src.end` = the removed source range) —
**never a full re-whisper of the render** (whisper hallucinates connective phrases at jump
cuts and fuses differently every run). Marginal calls escalate to an isolated short-window
re-probe of the render — the formalized "join_check.wav" practice.

## Acquiring word timings (priority order)

1. **Output-time words the editor emitted** (source transcript mapped through the EDL at
   build time) — best.
2. **Source-time words + the cut list** — map them yourself (algorithm in
   [manifest-and-edl.md](manifest-and-edl.md)).
3. **Transcribe the SOURCE footage** (the only full transcription ever allowed):

```bash
"$FF" -nostdin -y -i "$SOURCE" -vn -ac 1 -ar 16000 "$QA/source.wav"
# preferred (whisper.cpp via HyperFrames CLI — prints {ok, transcriptPath}; the
# transcript file is a flat [{text,start,end}] word array, seconds):
npx hyperframes transcribe "$QA/source.wav" --json --model small.en
# raw whisper.cpp alternative (word-level via max-len=1 + split-on-word):
whisper-cli -m <path to ggml-small.en.bin> -f "$QA/source.wav" -ml 1 -sow -oj -of "$QA/source-words"
```

whisper.cpp `-oj` JSON nests words as
`{transcription:[{tokens:[{text, offsets:{from,to}}]}]}` — offsets are **milliseconds**;
skip tokens starting with `[_` (timestamp markers). Normalize everything to
`[{text, start, end}]` in seconds.

No words at all → **degraded mode**: run only the splice-click check (§5) and report the
layer as `degraded`, not failed.

## The checks

Notation: for each cut, `rs`/`re` = removed source range, `t` = output-time seam
(`out.start`). `norm(w)` = lowercase, strip everything but letters/digits/apostrophes.

### 1. Clipped words (source-side straddle)

A cut lands inside a spoken word when a source word straddles the removed region:

- word runs INTO it: `w.start < rs` and `w.end > rs + tol` → its **tail** may be cut off.
- word starts INSIDE and continues past: `rs ≤ w.start < re - tol` and `w.end > re` →
  its **head** may be cut off.

`tol` = 0.06s for manual/EDL cuts, **0.25s for silence-origin cuts** (see gates below).
Every suspect gets a seam re-probe (§ probes) before it can flag HIGH.
Suggested fix: nudge the cut later (tail) / earlier (head) by `overlap_ms + 60`.

### 2. Repeated words (duplicate stumble across a seam)

Take the last 2 words ending before `t` and the first 2 starting after it.

- `isDup`: last-before == first-after (normalized, ≥3 chars, < 1.5s apart).
- `isBigramDup`: both word pairs match in order (at least one token ≥3 chars).

Either → `repeated_word` (HIGH), suggested fix: remove the exact duplicate. A content
word recurring one position away from the seam is normal copy ("…fixes the tracking
issue. | Server-side tracking…") — do NOT flag that; only adjacency or a full bigram.

### 3. Seam dead air

Gap between last word before and first word after a cut > 0.7s, with no
graphic/b-roll/callout/SFX event covering the gap window → suspect. **Confirm against the
meter before flagging**: run silencedetect (−40dB, d=0.3) on just that window of the
render; only real if measured silence ≥ 50% of the word gap. A word-gap over
speech-level audio is whisper mistiming, not dead air (live false positive: a mistimed
brand-name word made a fake 1s "gap"). Real → `seam_dead_air` (MEDIUM).

### 4. Caption vs transcript

For each caption event with text: collect spoken words in its window (±0.15s). No words
at all → `caption_orphaned` (HIGH) — orphaned by a cut; retime it. Otherwise score
**asymmetric coverage**: fraction of the CAPTION's tokens found among spoken tokens
(extra spoken context must not dilute the score), with 4-char prefix-stem matching so
"info"/"information" count as spoken. Skip captions under 3 tokens (bag-of-words noise).
When the caption carries source provenance (`src` range), compare against SOURCE-side
words in that range instead — output-time mapping is lossy at silence-cut edges and
false-flagged 40+ correct captions before this. Coverage < 0.75 → `caption_mismatch`
(MEDIUM; LOW on lanes whose captions are paraphrase-by-design).

### 5. Butt-splice clicks (every dialogue cut)

```bash
"$FF" -nostdin -hide_banner -ss $(t - 0.04) -t 0.08 -i "$VIDEO" \
  -af astats=metadata=0 -vn -f null - 2>&1 | grep "Max difference"
```

Last `Max difference` > 0.35 in the ±40ms join window → `splice_click` (MEDIUM),
suggested fix: 25–30ms edge fade at the join.

## Isolated seam re-probes (the join_check practice)

Whisper the RENDER around one suspect seam only, and arbitrate by whether the flagged
word is **heard** there:

```bash
"$FF" -nostdin -y -ss $(t - 2.75) -t 5.5 -i "$VIDEO" -vn -ac 1 -ar 16000 "$QA/probe.wav"
# then transcribe probe.wav as above; add (t - 2.75) back onto the word times
```

- **5.5s window, seam centered.** Whisper drops words at the edges of short clips — a 3s
  window failed to hear an intact word in live testing. Give it a full phrase either side.
- Word present (normalized match) within ±1.5s of the seam → whisper source-timing
  overshoot, NOT a real clip → downgrade to LOW (or drop, see gates).
- Word absent → clip **confirmed** → HIGH, confidence 0.9.
- **Never trust whisper durations from a probe — only presence/absence.** Word ends are
  padded into pauses.
- Cap probes (~40) on cut-heavy edits; unprobed manual-cut suspects stay HIGH at lower
  confidence, unprobed silence-origin suspects stay LOW.

## Causal calibration gates (the false-positive killers)

- **Silence-origin cuts cannot clip audible speech.** A cut whose removed region was
  derived from measured silence removed only a pause; word "overlap" there is whisper
  end-padding (40/49 cuts false-flagged on a live reel before this gate). Suspects at
  such cuts start LOW/0.3-confidence and are **dropped entirely** unless the probe
  confirms the word missing.
- **Silence-origin cuts cannot manufacture duplicate dialogue** — single-word repeats
  across them are script style ("garbage in, | garbage out" false-flagged live). Only
  manual/EDL cuts (retake splices) arm the single-word duplicate check; bigram dups flag
  everywhere.
- Head trims (`t ≈ 0`) have no left side — skip the seam checks there.

## Output

Layer status: any CRITICAL/HIGH → `fail` · any issue → `warn` · none → `pass` ·
no words → `degraded` (with reason). Anchor every issue to its cut/caption event id.
