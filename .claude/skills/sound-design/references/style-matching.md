# Style-matching a reference track

The user hands you a track — "make the music feel like this." You cannot ask
ElevenLabs for the song: naming the artist, the song, a film, or a brand in a
`/v1/music` prompt returns HTTP 400 (ToS filter), and describing its melody would
just be a slower way of asking for the same thing. The workflow that works:
**profile the track objectively, then re-prompt its STYLE in descriptors** — tempo,
sonics, energy. Match the style, never the song.

## 1. Profile with a spectrogram

```bash
ffmpeg -i ref.mp3 -lavfi "showspectrumpic=s=1600x800" ref-spec.png
```

Open the PNG and read it like an audio engineer:

- **A music bed reads as a continuous low-frequency pulse** — a solid bright band
  below ~200Hz with evenly spaced kick blobs riding on it. If the low band is
  patchy or absent, the reference is more of an ambient/pad piece — say so in the
  prompt ("no drums, sustained pads").
- **Estimate BPM from kick spacing.** Pick two kick blobs several beats apart, read
  their times off the x-axis: `bpm = 60 × beats-between / seconds-between`. Kicks
  ~0.48s apart ≈ 125 bpm.
- **Brightness lives above ~4kHz.** Dense energy up top = hats/shakers/air ("bright,
  ticking hi-hats"); a dark top half = muted, lo-fi, warm.
- **Vertical full-band columns** are impacts/transients (braams, hits, risers
  resolving). **Smooth horizontal bands** are sustained pads/strings.
- **A vocal shows as wavy harmonic stacks** in the 200Hz–4kHz mids. If present,
  ignore it — your bed prompt always ends in "no vocals".

## 2. Estimate BPM programmatically (onset-envelope autocorrelation)

The eyeball estimate drifts; cross-check it with this dependency-free estimator
(python3 stdlib + ffmpeg). It decodes to low-rate mono PCM, builds an RMS envelope
per 512-sample hop, half-wave-rectifies the envelope's first difference (energy
rises = onsets), and autocorrelates over lags corresponding to 60–190 bpm:

```python
#!/usr/bin/env python3
# bpm.py — onset-envelope autocorrelation BPM estimate. Usage: python3 bpm.py track.mp3
import subprocess, struct, sys

SR, HOP = 11025, 512
raw = subprocess.run(
    ["ffmpeg", "-v", "error", "-t", "60", "-i", sys.argv[1],
     "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
    capture_output=True).stdout
n = len(raw) // 2
samples = struct.unpack(f"<{n}h", raw[: n * 2])

# 1. RMS envelope per hop
env = []
for i in range(0, n - HOP, HOP):
    frame = samples[i:i + HOP]
    env.append((sum(s * s for s in frame) / HOP) ** 0.5)

# 2. Onset strength: half-wave-rectified first difference, mean-removed
onset = [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))]
mean = sum(onset) / len(onset)
onset = [o - mean for o in onset]

# 3. Autocorrelate over lags for 60-190 bpm; the strongest lag is the beat period
hop_s = HOP / SR
lo, hi = int(60 / (190 * hop_s)), int(60 / (60 * hop_s))
best_bpm, best_r = 0.0, float("-inf")
for lag in range(lo, hi + 1):
    r = sum(onset[i] * onset[i - lag] for i in range(lag, len(onset)))
    if r > best_r:
        best_r, best_bpm = r, 60 / (lag * hop_s)

print(f"{best_bpm:.1f} bpm  (sanity-check half {best_bpm / 2:.0f} / double {best_bpm * 2:.0f})")
```

**Always sanity-check half/double.** Autocorrelation happily locks onto the
half-note or the eighth-note grid. Cross-check against the spectrogram's kick
spacing; if the picture says ~0.48s between kicks (≈125) and the script says 62.5,
double it. Typical ad beds land 80–140 bpm — prefer the candidate in that range
unless the track is obviously a slow cinematic pulse or a fast breakbeat.

Pure-python autocorrelation is slow-ish, which is why the ffmpeg call caps the
analysis at 60s (`-t 60`) — plenty for a steady bed.

## 3. Translate the profile into a prompt — descriptors only

Hard rules:

- **Never** name the artist, the song, a film, a game, or a brand → 400 + ToS.
- **Never** describe the melody or the lyrics. You are matching the style, not
  recreating the song — melodic description is both a rights problem and useless
  (the model won't land it anyway).

Map each measured property to a plain-words descriptor:

| Measured | Prompt descriptor |
|---|---|
| BPM from step 2 | "around 124 bpm" |
| Kick blobs, low band | "tight punchy four-on-the-floor kick" / "sparse booming kick" |
| Sustained low band, no blobs | "deep sustained sub bass drone" |
| Bright top half | "crisp ticking hi-hats, airy shakers" |
| Dark top half | "dark, muted, lo-fi texture, no bright percussion" |
| Vertical columns | "occasional cinematic impact hits" |
| Energy grows over the track | "steady energy with a gradual build" |
| Melody prominent in the mids | **do not describe it** → "minimal melodic content, no lead melody" |

Then append the bed-standard closers, every time:

> mixed quiet and dry to sit under a spoken voiceover, instrumental only, no
> vocals, seamless loop feel

Worked example — profile says: continuous low pulse, kicks ≈0.48s apart (≈125 bpm),
dark top, sustained sub, energy flat, prominent synth melody (ignored):

> dark minimal electronic underscore around 125 bpm, tight punchy kick, deep
> sustained sub bass, muted lo-fi texture with no bright percussion, minimal
> melodic content, no lead melody, steady flat energy, mixed quiet and dry to sit
> under a spoken voiceover, instrumental only, no vocals, seamless loop feel

## 4. Verify the match

Generate the bed, then close the loop with the same instruments you profiled with:

```bash
ffmpeg -i bed.mp3 -lavfi "showspectrumpic=s=1600x800" bed-spec.png
python3 bpm.py bed.mp3
```

- BPM within ±5 of the reference (after half/double correction) = tempo match.
- The low band should show the same character: pulsed kicks vs sustained drone.
- Similar top-half density = similar brightness.

If it misses, adjust one descriptor at a time (usually tempo wording or drum
character) and regenerate — don't rewrite the whole prompt, or you can't tell what
fixed it.
