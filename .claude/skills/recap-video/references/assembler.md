# Portable base-cut assembler

Use `scripts/assemble.py` after selecting lines and normalizing a mezzanine.
Dependencies: Python 3 standard library, ffmpeg and ffprobe. Binaries resolve
from `FFMPEG` / `FFPROBE`, then `FFMPEG_PATH` / `FFPROBE_PATH`, then PATH.
It makes no API calls and does not choose takes or establish word accuracy.

## Input contract

The project contains `source.mp4`, `edl-lines.json`, and `transcript.json`, or
explicit replacement paths. Relative input paths resolve against `--project`.
Source video and audio must start together on a normalized CFR timeline matching
`--fps`. Normalize unlike frame rates, rotation, dimensions and color before this
stage; preserve an original-take to mezzanine map. Check quiet audio before
choosing a silence threshold.

`edl-lines.json` is a nonempty array in **playback order**, not chronological
source order. Times are seconds on the mezzanine clock. Assign unique stable
IDs; use a different ID for each intentional occurrence of reused source.

```json
[
  {"id":"intro", "take":2, "in":8.0, "out":10.0,
   "text":"Complete opening sentence.", "reason":"Cleaner microphone"},
  {"id":"body", "take":1, "in":1.0, "out":4.0,
   "text":"The chosen explanation.", "veto":[[2.1,2.4]]},
  {"id":"tail", "in":10.0, "out":11.0, "raw":true,
   "text":"Intentional room-tone hold"}
]
```

- `in` / `out`: valid source bounds with out greater than in.
- `veto`: ranges forcibly removed, even if loud. The portion intersecting the
  line is used. It still applies to a `raw` line.
- `raw: true`: skip silence removal for this line; useful for an intentional tail.
- `text`, `take`, `reason`: editorial metadata; they do not synthesize audio or
  decide whether a word survives. Inspect the actual kept speech.

`transcript.json` accepts `{"words":[{"word":"Hello","start":8.1,"end":8.5}]}`
or a words array, with `text` also accepted in place of `word`. All timestamps
must be on the same source clock; retain a separate original transcript if you
rebase source pieces. Empty ASR token strings are omitted with an alignment
warning; inspect that receipt rather than treating them as spoken words. Line
IDs must be nonempty and unique. The helper checks packet cadence as well as
nominal FPS before accepting the CFR source.

## Commands

Define `PACK` as this repository path and `PROJECT` as the media project path.

```bash
python3 "$PACK/.claude/skills/recap-video/scripts/assemble.py" \
  --project "$PROJECT" --version v1 --fps 30 --sample-rate 48000
```

For a planning-only pass use a separate version such as `plan-v1` and
`--no-render`. It runs source validation and pause detection and writes the EDL
and word maps, but no video. That version is reserved; choose a new version for
the later render. Every run refuses to overwrite an existing work directory or
base master, including a failed run's artifacts.

Parameters: `--edge 0.03`, `--noise -30`, `--minpause 0.13`, `--crf 16`,
`--preset medium`, plus `--source`, `--lines`, `--transcript`. Tune silence
parameters to the recording. The helper requires positive integer FPS and a
sample rate divisible by FPS: 44100/30 gives 1470 samples/frame; 48000/30 gives
1600. Normalize fractional-rate sources first or use a suitable rational-clock
editor; do not silently label 29.97 footage as 30.

## Output and verification

The master is `base-cut-<version>.mp4`. Supporting artifacts live together in
`_cut_work/<version>/` so a later run cannot replace an earlier review's intent:

| Artifact | Purpose |
|---|---|
| `inputs.json`, `pauses.json`, `silencedetect.log` | Input/settings receipt with source fingerprint; no stale cross-source pause cache |
| `edl.json` | Ordered source/output spans and total frame/sample counts |
| `qa-edl.json` | `windows` form for the HyperFrames adapter; see its reorder/reuse and geometry limits in `qa-and-revisions.md` |
| `words-cut.json` | Words mapped per retained source occurrence, with provenance |
| `words-master.json`, `source-words.json` | Output/source words for composition and QA |
| `alignment-warnings.json` | Partial or unmapped word spans requiring listening review |
| `quantization-notes.json`, `cut-report.txt` | Frame rounding/clamps and resulting cut report |
| `dialogue.wav` | Exact PCM dialogue from the concat graph, before AAC padding |
| `filter.txt`, `render-command.json`, `render-verification.json` | Exact render graph/arguments and measured frame/sample/duration/decode receipt |

Ordinary keeps round outward to frame boundaries, merge within each line, and clamp the
specific duplicate frame caused by adjacent line boundaries. Deliberate source
reorder/reuse is preserved. Explicit vetoes remove every frame touching the
vetoed interval, so their adjoining keep edges round inward; inspect adjacent
speech and move the veto if that would remove a wanted consonant. Each span uses exact frame and sample counts with
timestamp reset and short edge fades. Seeked inputs feed a concat filter so the
decoder does not queue an entire reordered source across dozens of branches.

Word mapping is per retained occurrence, not a global `find` of the first
matching source interval. ASR spans overlapping retained audio are mapped and
uncertainty is reported; a timestamp does not prove the audible word exists.
Read `alignment-warnings.json`, repair genuine missing speech and check names,
repeated starts and caption anchors before trusting the map.

Verify expected video frames, PCM samples, stream durations, sync and full decode.
AAC may expose encoder padding to raw decoders; inspect presentation duration
and the exact pre-encode PCM rather than declaring drift from padding alone.
The MP4 movie timescale matches the sample rate to avoid millisecond duration
rounding. `render-verification.json` records the measured result.
Do not use a fixed number of audio samples per frame copied from another rate.

The old implementation used decimal-second end trims that added one frame per
span, and a single-input many-trim graph that stalled on reordered takes. Retain
the exact frame/sample trim and seeked-input approach when adapting this helper.
This script verifies timing and encoding; it does not replace speech listening,
visual QA, sound mastering, or editorial review.

Run the bundled regression smoke test after changing the helper:

```bash
python3 "$PACK/.claude/skills/recap-video/scripts/smoke-test.py"
```

It uses temporary synthetic media and makes no API calls. It checks reordered
pixels/word occurrences, deliberate overlap, veto/raw behavior, silence handling,
44.1/48 kHz conversion, exact frame/PCM counts, decode and overwrite refusal.
