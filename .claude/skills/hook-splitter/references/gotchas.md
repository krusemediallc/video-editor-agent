# hook-splitter — measured facts and traps

Every number here was measured on `Rough Cut - Composite.mov` (16:26, 21 hooks,
1080x1920 screen recording + camera bubble). Re-measure on a new source; do not assume.

## Transcription is the main hazard

| # | Trap | What happens | What to do |
|---|---|---|---|
| 1 | **A full-file whisper pass SMOOTHS a repeated take into one line** | Real doubles are invisible in every source-side transcript. Four flubs the client caught in review were this: two doubled "a fast", a leftover "let's see it", a doubled "let's see how" | **Transcribe the RENDER** (`qa.py`). It is the only pass that reliably shows them |
| 2 | **…and it HALLUCINATES repeats that are not there** | The cloud pass reported a doubled "And I'm going to show it to you right now" at 9:28, and three "let's see how it did" that are the played video's own VO | Slice the window to its own wav and transcribe it in ISOLATION (`isolate.py`). Resolved all 10 candidates on the reference project |
| 3 | **An isolated pass can still be wrong** | It read 733.4-736.0 as a single "Let's see how good it did." The render clearly had two | Slice each candidate burst separately (0.8-1.0s), and **believe the energy envelope** — it showed the 0.36s gap all along |
| 4 | **Whisper stretches the odd word across a pause** | A 2.56s "that" at 8.10, a 2.52s at 46.28. As a don't-cut-inside-a-word guard these act as protected regions and block the gaps you are removing | Drop any "word" longer than `max_word` (0.6s) from the guard |
| 5 | **A 4-word n-gram floor is too coarse** | It missed the three-word "let's see how" and that shipped | Scan at 3+ words (`qa.py` does) |

## Feedback rounds

| # | Trap | Fix |
|---|---|---|
| 5b | **A note's timestamp only means something against the cut the reviewer watched** | `build_canvas.py` snapshots `work/cuts-<version>.json`; `map_notes.py` maps through it. Mapping v2 notes against a v3 `cuts.json` moved every source time by seconds — enough to land on the wrong word entirely |

## Tooling

| # | Trap | Fix |
|---|---|---|
| 6 | **`whisper-vad-speech-segments` prints CENTISECONDS** | Dividing by 1000 silently discards everything past ~98s — the plan came out with zero joins on hooks 5-21 and output that was just the video. Divide by **100** |
| 7 | **VAD clips word ONSETS** | It started "Alright" at 3.52s where energy and whisper both put it at 2.48s. Never build the speech map from VAD alone |
| 8 | **`ffmpeg -ss` before `-i` IS frame-exact here** | Verified byte-identical against a direct extract, so per-hook input seek + relative filter times is safe. Don't pay for a full decode per hook |
| 9 | `amix` default halves the level | `normalize=0` |
| 10 | mjpeg thumbnails fail on this source | add `format=yuvj420p` to the scale filter |

## Audio levels (reference project)

| | |
|---|---|
| gap floor (mic) | **-71.9 dB** |
| speech (mic) | **-33.5 dB** mean, -27.6 p90 |
| played video, system track | **-35.1 dB** |
| played video, bleeding into the mic | **-57.6 dB** (~22.6 dB down) |
| system track digital silence | **75.6%** of the file |

Two consequences:

- **An energy gate IS reliable here** (36 dB separation) — unlike the -36 dB car take in
  `reel-recut/references/workflow.md` step 2b that forced a VAD-driven route. Match the
  method to the measured floor, not to habit.
- **The bleed sits right on the speech threshold.** So a loop tail gets re-detected as
  "speech" and kept, undoing the truncation; and any flat dB test for "is that the speaker or
  the ad?" fails on a speech-heavy ad (it left loop remnants on hooks 9, 17, 19).
  Predict the bleed from the system track and require the mic to rise above it.

## Loop detection

The player loops each video, so most regions end with 0.3-2.1s of it playing again.

- Raw-waveform correlation **fails** (peaked at 0.06 — phase differences). Use log-band
  spectral self-similarity.
- The search **must** be windowed near the known render length. Unwindowed it peaks at
  ~8.5s on a repeated musical stinger, with correlations up to 0.9 that look convincing.
- **Reject peaks pinned to either edge of the window** — boundary artifact, not a loop.
- Regions whose tail is shorter than the reference cannot be confirmed; fall back to the
  measured consensus. Seven confirmable regions all resolved to 10.12-10.19s, two at
  corr 1.00 — hence 10.15.
- **Where the speaker reacts OVER the loop, no cut can remove the ad audio.** Muting the system
  track from the loop point can, because the ad is isolated there. This is the single
  reason the two-stream source matters beyond the mask.

## Two defects a code review caught that no amount of listening did

Both shipped in v1-v3 of the reference project and were invisible on playback. `plan.py`
now asserts against the first; `render.py`'s tolerance is one frame, which surfaces the
second. **Do not loosen either.**

**1. Gap collapse can hand a `kill` back.** After kills are subtracted, the collapse step
extends the two neighbouring segments toward each other to leave the target residual —
straight back into the killed interval. 24 of 24 kills were partly restored; hook 12's
0.37s loop-tail kill was undone *in full*. The word guard can walk a boundary back in
too, and head/tail padding can re-enter a kill at a hook edge.
Fix: the retained residual must never overlap a kill (`_residual_avoids_kills`), kills are
re-subtracted after snapping, and an assert fails the run if any survives.

**2. ffmpeg `concat` injects digital silence at every join.** `trim` is frame-quantised
but `atrim` is sample-accurate, so for each non-final segment concat pads the shorter
stream — up to one frame (33 ms at 30 fps) of silence per join. Measured 26-130 ms added
per hook across 13 of 21, *unevenly*, which is precisely what the fixed-residual design
exists to prevent. A 150 ms mismatch tolerance hid all of it.
Fix: snap every boundary to the frame grid in `plan.py` (and the kills outward with it,
or rounding lands a boundary back inside one), re-snap the relative times in `render.py`,
and flag any hook off by more than 1.5 frames. Drift went from a 55 ms mean to 0.2 ms.

## Pacing

`join_gap` controls the whole feel. From `reel-recut`:

| target | reads as |
|---|---|
| 90 ms | tightened, still breathes |
| 45 ms | normal recut pace |
| 30 ms | run-on, "talking over myself" |
| <25 ms | starts to sound spliced |

- Join only BETWEEN speech segments, never inside one. Energy cannot tell a beat
  between words from a stop closure; word-gap cutting is proven to destroy words here.
- `tail_pad` 0.25s reads as loose — the reviewer flagged five endings. **0.08** is right.
- Leftover quiet spans under ~0.5s in `qa.py` are usually word-guard protected and
  correct. Do not chase them to zero.

## Editorial

- **Never trim copy for pacing.** Dead air, stumbles, aborted takes, repeats — yes.
  Shortening what the speaker said to hit a runtime — no, that is the user's call. Say the
  runtime out loud instead.
- A short (3-5s) play before the main one is usually the **reference video** the creator is
  matching, not a mistake. They often narrate it ("and that's an explainer from another
  brand"). Keep it. A 1.4s play is a false start — drop it.
- Two hooks with identical prompts are two separate takes with different results. Keep
  both and say so.
- Repeated phrasing across a reference video and its generated result is the content
  working as intended, not a double.
