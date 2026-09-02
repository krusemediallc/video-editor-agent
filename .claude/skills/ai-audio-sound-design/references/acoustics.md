# Acoustics recipes — rooms, outdoors, levels, prompts

Everything here was tuned on real client rounds (a 10-scene AI-actor ad, v1–v5 approved). Numbers are
starting points, not law — but they're starting points a client already signed off on.

## 1. Room reverb table (synthetic IRs, `make_ir` in the engine)

The IR is exponentially-decaying noise, lowpassed for damping, highpassed at 150 Hz (keeps
reverb out of the mud), unit-energy normalized. `wet_db` is the wet mix under the dry voice.

| Location type | rt60 | damp_hz | wet_db | predelay | Why |
|---|---|---|---|---|---|
| Tiled bathroom | 0.70 | 6500 | −13 | 10 ms | Hard tile = long AND bright; the most audible room — clients love this one |
| Public interior (waiting area, lobby) | 0.55 | 3800 | −15 | 15 ms | Big + boxy, mid-heavy; long predelay = big room |
| Office / loft w/ brick | 0.45 | 4500 | −15 | 12 ms | Hard walls, medium size, slightly live |
| Kitchen | 0.35–0.40 | 4200–5000 | −16 | 12 ms | Hard surfaces, small |
| Living room / furnished | 0.30 | 3200 | −18 | 10 ms | Soft furnishings damp highs and decay |
| ...when client says "match her room size" | 0.42 | 3800 | −13 | 10 ms | Subtle-by-design reads as "no reverb" to clients; make it audible |
| Bedroom (bare walls) | 0.30 | 3600 | −17 | 10 ms | Live-ish but small |
| Bedroom (bed/soft, intimate) | 0.18 | 2800 | −20 | 8 ms | Driest interior — closeness IS the character |
| Outdoors | — | — | none | — | Outside has no room. See §3 |

Dialog EQ per scene: highpass 80–100 Hz (100 for bright exteriors/bathrooms, 80 for intimate
night scenes), then the 13 kHz anti-whine lowpass from the SKILL.

## 2. Ambience beds — prompts and levels

### Prompt cookbook (ElevenLabs sound-generation)

Pattern: `<space> + <2-3 concrete sources> + "steady" + "no voices"` (say "no close voices"
when distant crowd is wanted). Proven prompts:

- Night street/bar exterior: "late at night on a city street outside a bar, drunk people
  laughing loudly and talking in the distance, open-air outdoor chatter not muffled, distant
  traffic hum, a car passing by, night street ambience, no close voices"
- Kitchen: "quiet home kitchen interior room tone, steady refrigerator hum, faint electrical
  appliance buzz, domestic daytime ambience, subtle and steady, no voices"
- Morning kitchen: add "coffee maker gently brewing and dripping, faint birdsong through a window"
- Backyard/lawn: "sunny backyard lawn ambience, small songbirds chirping, soft summer breeze
  through grass, distant suburban neighborhood hum, calm daytime, steady, no voices"
- Bedroom night: "very quiet bedroom at night room tone, soft air conditioner hum, low rumble
  of a city muffled outside, calm still air, minimal and steady, no voices"
- Bathroom: "small tiled bathroom room tone, soft ventilation exhaust fan whir, faint
  fluorescent light buzz, close reflective room ambience, steady, no voices"
- Waiting area/office building: "air conditioning ventilation hum, distant indistinct crowd
  murmur, occasional muffled footsteps on hard floor, office building interior, steady"
- Office extras (layers): "an office laser printer printing pages, rhythmic mechanical
  whirring, paper feeding" · "fluorescent tube lights buzzing steadily overhead, electrical
  mains hum"
- Appliance close-ups (layers): "window air conditioner running, steady fan whir and low
  compressor hum" · "refrigerator compressor humming and buzzing steadily"
- One-shot car: "a single car driving by on a city street at night, approaching then passing
  with a smooth whoosh, tires rolling on asphalt, engine fading away, no horn, no voices"

### ElevenLabs gotchas

- ~1/3 of quiet room tones come back near-silent; the kit runner's audit+retry handles it, but
  set `min_peak_db: -35` or genuine room tones loop the retry forever.
- Generated "hum" beds often carry a **mosquito tone near 15.6 kHz** — the engine's bed
  lowpass + final brick-wall removes it; check the spectrogram anyway.
- A bed flagged "first sound at ~0.2 s" is fine as a bed (fade-in covers it) but must be
  head-trimmed (`ffmpeg -ss`) when used as a timed EVENT.
- **Peak-normalizing lies about beds.** A coffee-maker bed at peak −3 dB had RMS ~−60 —
  inaudible. Always measure ambience-under-dialog RMS from the stems after the first render.

### Level targets (ambience RMS under dialog RMS, per scene)

| Zone | amb-under | Use for |
|---|---|---|
| Whisper-quiet | −20 … −23 | Intimate bedrooms, "felt not heard" |
| Present (default) | −15 … −19 | Most interiors; a client's "perfect" landed ≈ −17 |
| Busy | −8 … −12 | Night street, public spaces, offices with machines — places that are loud in life |
| Too hot | > −6 | Back it off; it fights the voice |

The proving-run client liked ambience **louder than a mixer's default instinct** — they asked for a
global +4 dB after a −16…−23 mix. Start one notch hotter than feels safe. A timed event (car
pass) may peak as close as 4–5 dB under dialog for its loudest half-second.

## 3. Outdoors = distance, not reverb

When a client says "make it sound like it's outside," reaching for reverb is the trap. A busy
street sounds the way it does because of distance physics:

1. **Air absorption:** far sources go dark. Crowd across the street → lowpass ~3.2 kHz.
   Mid-distance moving source (passing car) → lowpass ~7.5 kHz, keeps its detail.
2. **Traffic rumble:** constant LF underneath. Lift the bed's own <160 Hz content (+~4 dB).
3. **Urban-canyon wash, not a room tail:** facades return a few sparse echoes and a thin dark
   diffuse decay. The engine's `outdoor_wash_ir`: 25 ms predelay, ~12 random taps at 5–90 ms,
   low-density noise tail RT ≈ 1.1 s, lowpassed 2.2 kHz. Wet ≈ −8 dB on far sources, −13 on mid.
4. **The phone-mic voice stays close and dry.** That contrast (dry voice / dark washed
   background) is what reads as "outside" — treat only the background.
5. **RMS-match the processed result to its input** so the character change doesn't move an
   approved level.

Quiet exteriors (backyard, park) need none of this beyond the bed itself — just skip reverb
on the voice and keep the highpass a bit higher (100 Hz).

## 4. Censor bleeps — the full spec

- Tone: 1 kHz sine, both channels, dry (no reverb — broadcast convention).
- Level: RMS of surrounding ±0.8 s of original dialog, +1 dB. Reads clearly, doesn't blast.
- Edges: 8 ms raised-cosine in/out; the dialog mute under it gets 5 ms linear ramps.
- Span: verified word times padded −0.10 s / +0.06 s (whisper starts run late).
- Mute the word **pre-reverb** (see SKILL §4). Post-bleep verification: target word absent
  from a fresh transcription of the final mix, zero collateral word loss, and dialog-stem RMS
  inside each bleep core below ≈ −60 dB *in dry scenes* (reverbed scenes legitimately show the
  previous word's tail there — that's correct, not leakage).
- Scope discipline: bleep exactly the user's list. Log near-misses ("swear to God"?) as an
  amber canvas note with a count, so it's a one-line flip, not a surprise.
