# Layer 1 — deterministic technical QA (ffprobe/ffmpeg)

Three passes over the rendered file. Every detection is cross-checked against the
manifest's `intentional` spec before flagging. Timestamps here are EXACT.

`FF=${FFMPEG_PATH:-ffmpeg}` · `FP=${FFPROBE_PATH:-ffprobe}` · `VIDEO=<the render>`
· `QA=<video dir>/_qa/<stem>` (mkdir -p it).

## Pass 0 — ffprobe (streams, duration, geometry)

```bash
"$FP" -v error -print_format json -show_format -show_streams "$VIDEO" > "$QA/probe.json"
```

Checks (severities in parentheses):

- ffprobe errors out → `corrupt_file` (CRITICAL). Stop.
- no video stream → `missing_video_stream` (CRITICAL). Stop.
- no audio stream and `intentional.noAudio` is not set → `missing_audio_stream` (CRITICAL).
- **duration**: `format.duration` vs the manifest's `expectedDuration`.
  Δ > 0.15s → `duration_mismatch` (HIGH; > 1s → CRITICAL). Always phrase it as measured
  from the file — render logs lie about duration.
- resolution vs `expected.width/height` → `resolution_mismatch` (HIGH).
- fps (`avg_frame_rate` as a fraction, n/d) vs `expected.fps`, tolerance 0.5 →
  `fps_mismatch` (MEDIUM).

## Pass 1 — video filters (one decode, three detectors)

```bash
"$FF" -nostdin -hide_banner -i "$VIDEO" \
  -vf "blackdetect=d=0.1:pix_th=0.10,freezedetect=n=-60dB:d=1.5,select='gt(scene,0.45)',showinfo" \
  -an -f null - 2> "$QA/l1-video.log"
```

Parse the log (all of this prints to stderr):

- **decode**: nonzero exit → `decode_error` (CRITICAL). Exit 0 but lines matching
  `error|corrupt|invalid data` (excluding `Parsed_` filter banner lines) →
  `decode_warnings` (HIGH).
- **black frames**: pair up `black_start:`/`black_end:` values. Skip pairs inside
  `intentional.blackRegions` (±0.2s slack). Length ≥ 0.5s → CRITICAL, else HIGH
  (`black_frames`).
- **frozen frames**: `freeze_start:`/`freeze_end:` pairs. Skip `intentional.stillRegions`
  (±0.5s slack — freeze detection is fuzzy at region edges). Otherwise `frozen_frames`
  (HIGH) — the classic un-synced b-roll / dead-canvas signature.
- **flash frames**: every frame that passed `select='gt(scene,0.45)'` prints a `showinfo`
  line — collect its `pts_time:` values (these are hard visual discontinuities). Two
  spikes ≤ 100ms apart = a single-frame glitch / stray frames (`flash_frame`). If the
  first spike is within 2 frame-durations of a manifest cut, it is HIGH and anchors to
  that cut; otherwise MEDIUM. (Isolated single spikes are just cuts — expected.)

## Pass 2 — audio filters (one decode: silence + stats + loudness)

```bash
"$FF" -nostdin -hide_banner -i "$VIDEO" \
  -af "silencedetect=noise=-40dB:d=0.6,astats=metadata=0,ebur128=peak=true" \
  -vn -f null - 2> "$QA/l1-audio.log"
```

- **dead air**: `silence_start:`/`silence_end:` pairs ≥ 0.6s. Skip
  `intentional.silentRegions`; skip spans entirely inside the first/last 1.0s (intro
  fades, outro cards). A span ≥ 1.2s, or one starting within 150ms of a manifest cut
  (over-trim suspicion — anchor to that cut), → HIGH; else MEDIUM (`dead_air`).
- **loudness**: in the `Integrated loudness:` summary block, grab `I: <n> LUFS`. Target
  is `intentional.loudnessTarget` or the platform default (−14 LUFS for social, ±2) →
  `loudness_off_target` (MEDIUM).
- **true peak**: in the `True peak:` block, grab `Peak: <n> dBFS`. Above −1.0 dBTP:
  ≥ 0 → CRITICAL (hard clipping) · ≥ −0.1 → HIGH · else LOW (`clipping_risk` — social
  masters routinely peak between −1 and −0.2 dBTP; a merely hot master is informational).
- **flatline**: last `Flat factor:` from astats > 10 → `waveform_flatline` (HIGH) —
  sustained clipped/flat samples.

## Pass 2b — RMS-envelope lull scan (MANDATORY alongside silencedetect)

**The lesson:** silence QA needs BOTH silencedetect AND an RMS-envelope pass. Breathy
−28..−36dB lulls **read as dead air to human ears but pass −38/−40dB silencedetect**
untouched. On a shipped edit, two real gaps flagged by the reviewer were invisible to
silencedetect at −38dB; a 10ms-window RMS envelope found them immediately.

```bash
python3 .claude/skills/video-qa/scripts/rms_scan.py "$VIDEO" \
  --threshold-db -27 --min-dur 0.35 > "$QA/rms-lulls.json"
```

The script windows RMS at 50ms (astats `reset` mode), merges consecutive
below-threshold windows into runs, and reports each run's span + min/mean RMS. Triage:

- a lull that silencedetect ALSO caught → already handled above, ignore here.
- a lull silencedetect missed, longer than ~0.5s, in a dialogue section, not covered by
  b-roll/graphics per the manifest → treat as `dead_air` (MEDIUM; HIGH if it starts at a
  cut). These are the breathy gaps humans complain about.
- When trimming such a lull, walk each boundary outward against the envelope while the
  level stays ~8dB above the measured noise floor, so consonant tails and breaths survive
  the cut.

## Output

Collect all issues with: id (`L1-<category>-NNN`), severity, category, time window,
message, evidence (raw numbers), and event anchor when linked to a cut. Layer status:
any CRITICAL/HIGH → `fail` · any issue → `warn` · else `pass`.
