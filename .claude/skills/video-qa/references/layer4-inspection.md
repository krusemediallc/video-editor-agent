# Layer 4 — targeted inspection packets

One packet gives you everything about a time window, so you reason across modalities
instead of inferring everything from pixels. Build one for every CRITICAL/HIGH issue
**before** changing any edit, and for anything the user asks you to look at.

**Padding rule:** deterministic-layer (L1/L2) timestamps are exact → pad ±0.5s.
Gemini-sourced windows → pad ±1.5s. Below: `S` = padded start, `T` = padded span,
`DIR = $QA/inspect/<issue-id>/` (mkdir -p).

## Packet contents

### events.json
Manifest events whose output window intersects [S, S+T] — the cut/caption/SFX context
for everything else in the packet.

### contact_sheet.png — frames from the ORIGINAL render (never the proxy)

Adaptive density — flash-hunting needs dense sampling, framing checks don't:
span ≤ 2s → fps 10 · ≤ 5s → 6 · else 3. `COLS = min(6, ceil(span*fps))`,
`ROWS = ceil(total/COLS)`.

```bash
"$FF" -nostdin -y -ss $S -t $T -i "$VIDEO" \
  -vf "fps=$FPS,scale=320:-2,tile=${COLS}x${ROWS}" -frames:v 1 "$DIR/contact_sheet.png"
```

Read left→right, top→bottom; first tile = S; one tile per 1/fps seconds. State that
mapping in the packet index so timestamps can be recovered from tile position.

### waveform.png — window waveform with edit-event markers

```bash
"$FF" -nostdin -y -ss $S -t $T -i "$VIDEO" \
  -filter_complex "aformat=channel_layouts=mono,showwavespic=s=1600x400:colors=0x9be070" \
  -frames:v 1 "$DIR/waveform.png"
```

Then overlay labeled tick marks for every event in the window (cuts red, captions blue,
SFX yellow, …) — many ffmpeg builds lack drawtext, so PIL draws them:

```bash
# markers.json: {"start": S, "end": S+T,
#   "markers": [{"t": <event out.start>, "label": "<event id>", "kind": "cut"}, ...]}
python3 .claude/skills/video-qa/scripts/draw_markers.py \
  "$DIR/waveform.png" "$DIR/markers.json" "$DIR/waveform.png"
```

A marked waveform answers "is there really a gap/click AT the seam" in one glance.

### audio_stats.json — the meter for the window

```bash
"$FF" -nostdin -hide_banner -ss $S -t $T -i "$VIDEO" \
  -af "silencedetect=noise=-40dB:d=0.2,astats=metadata=0" -vn -f null - 2> stats.log
```

Record: last `Peak level dB`, last `RMS level dB`, last `Max difference` (click
indicator), and every silence span (offset by S back to absolute time). Add an RMS-lull
scan of the window (`scripts/rms_scan.py <video> --start $S --duration $T`) when the
issue is dead-air-shaped — silencedetect alone misses breathy lulls.

### transcript.md — words in the window with inline cut markers

From the output-time word timings (±0.2s slop on the window edges), render one line with
each cut inserted where it lands, e.g.

```
so the whole funnel |[cut:src48.8]| runs on autopilot and
```

plus a `| word | start | end |` table. The inline form makes clipped words and
duplicates jump out.

### packet.md — the index

Window, video path, one line per artifact, EDITS line listing event ids @ times, AUDIO
line with peak/RMS/silences, first ~160 chars of the transcript line. This is what you
(or the user) read first.

## Reviewing a packet

- Watch/listen when in doubt: cut a 2–3s subclip
  (`"$FF" -ss $S -t $T -i "$VIDEO" -c copy "$DIR/clip.mp4"`) — subclips beat scrubbing
  when escalating to the user.
- Confirm the issue in ≥2 modalities before acting (e.g. waveform gap + transcript gap;
  contact-sheet stray frame + scene-spike pair).
- If the packet contradicts the flag (word visible in transcript, meter shows speech),
  downgrade to LOW with the evidence noted — do not "fix" ghosts.
