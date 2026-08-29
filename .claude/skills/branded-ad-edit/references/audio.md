# Audio: ElevenLabs SFX + music, auditing, mixing

Needs `ELEVENLABS_API_KEY` (export it or put it in a `.env` at the repo root). The VO
stays dominant; SFX punctuate; the bed is felt, not heard.

## 1. SFX kit (~12 effects, reused across ~40 hits)

`POST https://api.elevenlabs.io/v1/sound-generation`
body `{"text": prompt, "duration_seconds": d, "prompt_influence": 0.35}` —
**`duration_seconds` minimum is 0.5** (0.4 → HTTP 400).

The kit (tune prompts to taste):

| Effect | Prompt sketch | d | Used on |
|---|---|---|---|
| whoosh-soft | "short soft airy whoosh, UI card sliding in, clean swipe" | 0.7 | card enters |
| swoosh-in | "fast whip swoosh transition, energetic, short" | 0.6 | reframes, slide-ins |
| pop-click | "a single loud clean UI pop click, bubble pop, punchy" | 0.5 | chips, tiles, rows |
| stamp-slam | "loud heavy thud slam impact, stamp hitting a desk, punchy bass" | 0.8 | stamps |
| cash-count | "fast cash register counter rapidly ticking up, ends with a ding" | 1.2 | count-ups |
| impact-boom | "deep cinematic bass impact hit, punchy sub drop, very short" | 0.9 | big reveals, takeovers |
| fire-ignite | "quick fire ignition whoosh, flame bursting to life" | 0.9 | fire beats |
| pen-scratch | "loud fast marker strokes crossing out text on paper, close-mic" | 0.9 | strikethroughs |
| cha-ching | "classic cash register cha-ching, money win sound, single" | 1.0 | money wins |
| clock-tick | "fast stopwatch ticking, urgent, dry, no music" | 1.8 | timers |
| shimmer-reveal | "soft glassy shimmer sweep, elegant logo reveal, bright" | 1.1 | brand reveal |
| star-ding | "loud bright single bell ding, achievement chime, crisp" | 0.6 | ratings, checkmarks |
| power-down | "video game power down, energy draining away, descending falling pitch whine, deflating, ends in a low thud, sharp attack" | 1.8 | counters draining to zero, "losing" beats |
| sub-drop | "cinematic movie trailer sub bass drop, deep braam impact with falling pitch, punchy sharp attack, powerful" | 1.4 | cold open (t≈0), biggest reveal |

⚠ **Whooshes are a taste risk.** A client killed every whoosh/swoosh as "cheesy."
Default transitions to silence or a soft pop; add whooshes only if the reference ads
use them. Match the SOUND to the on-screen motion semantics — a rising tick on a
counter that's counting DOWN got flagged; use power-down for losses.

### Audit — non-optional

**~1/3 of generations come back near-silent.** For every file:

```bash
ffmpeg -i x.mp3 -af volumedetect -f null /dev/null   # regenerate if peak < ~-12dB
ffmpeg -i x.mp3 -af silencedetect=n=-30dB:d=0.08 -f null /dev/null  # onset must be ~t=0
```

Regenerate duds with "loud"/"punchy" added and `prompt_influence: 0.6`. Then
**peak-normalize the whole kit to −3dB** (measure peak, apply `volume=<gain>dB`,
re-encode 192k) so `data-volume` values behave predictably.

## 2. Placement & mixing

Each hit is its own audio element — the framework mixes; no timeline JS:

```html
<audio id="sfx-07" src="sfx/stamp-slam.mp3" data-start="2.4" data-duration="0.8"
       data-track-index="18" data-volume="0.5"></audio>
```

- Unique `id` and a unique `data-track-index` per hit (11, 12, 13, …).
- `data-duration = min(fileDuration, compositionEnd − start)`.
- **Land on the exact word** ("fire" SFX on the word *fire*), not the sentence start.
- Volumes that sat right against VO peaking ≈ −7dB: pops 0.32 · whooshes 0.28–0.35 ·
  stamps/impacts 0.5 · count-ups 0.4–0.45 · cha-ching 0.4 · ticks 0.32. A hit whose
  post-mix window peak matches the VO's is *audible-subtle*; +3–5dB over is *punchy*.
  Don't slot-machine every hit — reference ads keep SFX tasteful.

## 3. Music bed

`POST https://api.elevenlabs.io/v1/music` body
`{"prompt": "...", "music_length_ms": <durationMs + 2000>}`.

> ⚠ **Artist names violate ToS** ("in the style of Hans Zimmer" → HTTP 400; the error
> body includes a usable `prompt_suggestion`). Describe the sound instead:
> *"suspenseful cinematic instrumental underscore: dark pulsing low strings, deep
> sub-bass hits, quiet ticking percussion building tension, sparse piano, minimal and
> atmospheric, a tension bed designed to sit under a voiceover, instrumental only,
> no vocals."* Match genre to the brand's reference ads (upbeat/percussive for DTC,
> tension for finance/perf-marketing, warm for wellness…).

**Trim to the beat onset.** Generated tracks open with a 2–4s warm-up intro that
reads as low energy ("the music takes too long to get started"). Scan per-second
`volumedetect` means over the first ~10s, find where energy plateaus, and cut the
bed with `-ss <onset>` (+ a 0.25s fade-in) so the beat is present from frame one —
pairs with a sub-drop open.

Trim to composition length with `afade=t=out:st=<end−2.2>:d=2.2`. Measure its peak,
then set `data-volume` so the bed peaks **~18–20dB under the VO peaks** (a 0dB-peak
track with VO peaking −7dB → `data-volume ≈ 0.10`; a client asked for the bed at
0.13 ≈ 15dB under — offer louder as an option). Mount as one audio element on its
own track. Verify post-render in a word-gap window: the bed should raise a gap's mean
by ~2–4dB vs the no-music render — present, not competing.
