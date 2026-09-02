# Phase 1 — the base cut

Goal: a locked picture the creator signs off ("consider this first edit done"). Everything in Phase 2
sits on top of this and never moves it. Proven path: V1 (2:18) → V2 ("talking over myself",
1:47) → V3 (three QA rounds, 22 defects) → V4 (21 timeline notes, 1:33) → V5 (two notes) →
signed off.

## 1. Ingest

- Source is a folder of takes; each take is three files: `Take NN - Screen.mov` (5120×2880
  ReplayKit, **variable frame rate**), `Take NN - Camera.mov` (1920×1080), `Take NN - Mic.wav`.
  Put them in `<project>/raw/`.
- **VFR screen captures break input seeking.** `-ss`/`-t` on the input returned the wrong window
  (take 01: 129 frames over 24.8s). Every window is cut *in the filter graph*:
  `fps=30,trim=start=A:end=B,setpts=PTS-STARTPTS`. `build.py` does this (`SWIN()`); do it in every
  ad-hoc probe too.
- Confirm A/V sync per take (clap or a plosive against the waveform). The camera and mic were
  in sync on every take here; the screen is aligned by `screenOffset` per segment, not globally.

## 2. Transcript → what to keep

- Transcribe each take (OpenAI Whisper, `granularity: ["word"]`; local `whisper-cli` with
  `base.en` is fine for locating stumbles).
- Find retakes: the same line read twice, false starts, "let me do that again". Keep the clean
  read. Whisper **dedupes back-to-back retakes** on continuous audio, so transcribe silence-split
  pieces in isolation when a take is one long roll.
- Take order: numeric, except what the creator says at intake (here: "take one comes after I bring up
  Claude Code, don't start with it").
- The creator's hard rule on paid deliverables: the approved copy is not yours to trim for pacing. Only
  marked alternates (Hook 1 / Hook 2) and flubs come out. A separate "remove this line" from the creator
  is a one-clip deletion (the character-drift line).

## 3. The EDL (`edl.json`) — single source of truth

```jsonc
{
  "canvas": { "w": 1080, "h": 1920, "fps": 30 },
  "cam":    { "full": {"crop":[608,1080,666,0]}, "half": {"crop":[1215,1080,363,0]},
              "circle": {"crop":[1080,1080,430,0], "size": 380, "x": 60, "y": 1418} },
  "screenRects": { "homepage": [2430,2160,1345,182], "modal": [2400,2133,1500,510], "panel": [1080,1920,3086,520], /* … */ },
  "segments": [
    { "id": "03-craziest", "take": "06", "in": 3.94, "out": 9.54, "layout": "split", "rect": "modal",
      "keep": [[3.94, 9.54]], "screenOffset": 10.28, "gain": 1.6 },
    { "id": "03b-prompt", "take": "06", "in": 9.54, "out": 13, "layout": "split", "rect": "prompt_zoom",
      "keep": [[9.54, 12.815]], "screenOffset": 21.96, "gain": 1.6, "veto": [[11.935, 12.075]], "joinPrev": true }
  ]
}
```

| Field | Meaning |
|---|---|
| `layout` | `cam` = the creator full frame (608 src px → 1080); `split` = screen crop on top 1080×960, the creator below from the 1215-wide crop; `screen` = screen crop full-bleed with the creator in a 380px circle at (60,1418) |
| `rect` | a named `[w,h,x,y]` crop of the 5120×2880 capture. Split rects are 1.125 aspect, screen rects 9:16. Name them by what they show; measure them against **several moments** of a clip that reframes, not one |
| `keep` | sub-ranges of the take that survive, in source time. Written by `tighten.py`; hand-edit only via the note workflow |
| `screenOffset` | shifts the screen capture so the example is actually *playing* during the shot (35s of frozen screens in V2 were fixed with this). `qa/screen_offsets.py` measures liveness inside the segment's own rect and proposes it |
| `screenTake` | borrow another take's screen when the take's own never moves (the CTA gallery) |
| `screenAudio` / `screenAudioOffset` / `duckUntil` | mix an example ad's audio in, ducked while the creator talks; picture and audio can come from different moments of the same recording |
| `veto` | gaps proven by `verify_cuts.ts` to damage a word. **Additive across runs** — a vetoed gap stops being a cut, so rewriting the list from a fresh run forgets the decision |
| `protect` | ranges that survive even in silence (an example ad playing). **Move `protect` whenever `in`/`out` moves** or the trim silently does nothing |
| `gain` | per-clip dB so every line sits at the same level (`qa/clip_gains.py`, voiced frames only, clamp 4 dB) |
| `camX` | camera crop x for shots where the creator leans out of the fixed crop. Measure the creator's cap centre; every unflagged shot sat ~+27px right of it |
| `flipScreen` | mirror a generated clip whose product text reads backwards |
| `joinPrev` | this segment's audio is sample-contiguous with the previous one — drop the anti-click fades at the seam. For picture-only splits mid-word (a punch-in). `build.py` asserts the keeps touch and the previous keep is a whole frame count |

## 4. Render — `build.py`

```bash
cd <project> && python3 build.py            # full render -> arcads-ad-vN.mp4
python3 build.py --stills --only 03b-prompt         # one JPEG per segment to validate a crop
```

What it does and why: renders each segment video-only, **measures its exact frame count**, then
builds the whole audio track in one filter graph padded to those measured lengths, then two-pass
`loudnorm` (single-pass landed at −17.3 against a −14 target) + `alimiter`, `-video_track_timescale
30000 -muxdelay 0 -muxpreload 0`. Per-segment audio + concat cannot work: AAC quantises to 21.3ms
and video to 33.3ms, so 29 joins produced 29 gaps and 0.23s of drift.

Layout mechanics worth knowing: `screen` layout draws the creator with `geq` circular alpha; `split`
stacks `vstack`; the punch-in shots (`05z-swapout`, `03b-prompt`) are separate segments with a
tighter rect, static — the creator approved static punch-ins twice; a synthetic push-in is an effect the creator
did not ask for.

## 5. Pacing — `tighten.py` and the QA harness

- `python3 tighten.py` rewrites every `keep` from the mic waveform. Threshold `max(noise+9 dB,
  p95−18 dB)`: peak-relative, because the noise floor moves ~20 dB between takes and an absolute
  threshold under-cuts the quiet ones. Guardrails `MIN_GAP_TO_CUT 0.14`, `MIN_PIECE 0.35`,
  `MERGE_SPAN 0.60`. It started at `p95−22`; the creator's own breath notes (−25 to −33 dB in the output)
  showed the creator's standard was 4 dB tighter. **Take a round of the creator's marks as the calibration.**
- `npx tsx qa/verify_cuts.ts` renders the neighbourhood of every cut with and without it,
  transcribes both, and compares word sequences. Whisper stretches a word's span into the pause
  after it, so removing pure silence reads as the word shortening — `qa/silent_gap.py` (a gap whose
  loudest frame is 24 dB under the take's p95 cannot contain a word) pre-clears those. Three of the
  first four "word damage" vetoes were false.
- `qa/clip_gains.py` — per-clip level over voiced frames only. Before trusting a large override,
  **check the spectrum**: a "quiet Pixar" was a 43 Hz desk thump being amplified +14 dB.
- Audits to run on every render: `blackdetect`, `freezedetect` on the screen half (35s of frozen
  screens shipped in V2), shot list for anything under 0.5s, dead stretches 14 dB under the take's
  speech level, both streams start at 0.000 and end together, clean decode, script intact end to
  end by transcription.
- Frame-by-frame QA is worth a multi-agent pass with skeptics told to refute each finding
  (V3: 22 confirmed defects, including a moderation-rejection card readable for 12s, a browser
  chrome tab, a MUTE icon on the split seam, decapitated characters on ads that reframe).

## 6. Applying the creator's base-cut notes

Every note is an output timestamp; convert it to source time by walking the segment's `keep`
ranges (a helper in the session log's V4 entry). Then:

- "cut the silence / breath here" → tighten the threshold globally, verify every new cut.
- "end this shot here / start here" → move `out`/`in` **and** any `protect` range with it.
- "don't have this ad playing with audio" → drop `screenAudio`, start the shot on the creator's first word.
- "zoom into X" → a new segment with a tighter rect, `joinPrev: true` if it splits mid-word.
- "center me" → measure the creator's cap centre and set `camX`; the house offset was ~+27px.
- "my voice cuts off on the last word" → the keep ends before the consonant decays; extend it
  (V8: 5.285 → 5.40 on take 21).

Re-render, regenerate the canvas with the new version and blurb, publish to the same slug, and
lead the reply with the URL.
