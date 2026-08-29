# The method — commands, prompts, templates, heuristics

Verbatim-tested pipeline from a successful style-clone delivery. Work in a
scratch dir per job, e.g. `analysis/<job>/`. All paths below are relative to
that dir; the reference video is `ref.mp4`.

---

## 1. Obtain the reference locally

The user provides the file. If they only have a URL:

- Platform downloads (Instagram / TikTok / YouTube) usually need the **user's
  own authenticated session** — an anonymous fetch gets a login wall or a
  watermarked low-res proxy. Ask the user to download it with their own
  logged-in browser (or a downloader they run themselves) and hand you the
  file.
- Worst case, a full-quality screen recording of the reel is acceptable
  evidence — cut timing and layout survive; exact colors may shift slightly
  (note that in the guide if so).
- Do not build the analysis on a re-compressed preview thumbnail; caption
  stroke widths and grain read wrong.

Normalize the name to `ref.mp4` so every command below is copy-paste.

## 2. Probe & cut detection

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,duration \
  -show_entries format=duration -of json ref.mp4
```

Record duration, resolution, fps in the guide header (the clone should render
at the same fps — a 24fps ref cloned at 30fps loses the film cadence).

Detect hard cuts, dumping the first frame AFTER each cut as a PNG:

```bash
mkdir -p evidence/cuts
ffmpeg -i ref.mp4 \
  -vf "select='gt(scene,0.25)',showinfo" \
  -vsync vfr evidence/cuts/cut_%03d.png 2> evidence/cuts/showinfo.log
```

- Cut timestamps are the `pts_time:` values in `showinfo.log` (stderr). Pull
  them with: `grep -o 'pts_time:[0-9.]*' evidence/cuts/showinfo.log`
- `0.25` is the proven threshold for talking-head reels with graphics. If it
  fires on every caption pop (over-detection), raise toward `0.35`; if it
  misses cuts between two similar shots of the same person, drop toward
  `0.15` and eyeball the extra frames.
- `-vsync vfr` matters — without it ffmpeg duplicates frames to fill the
  timeline and the PNG numbering no longer maps 1:1 to cuts.

Compute from the timestamp list:

- **cuts/sec overall** = count / duration. Typical fast-style reels land
  0.4–0.8; the number is the pacing contract the clone must hit.
- **Per-section shot lengths**: split the timeline at the narrative seams
  (hook / body / CTA — you'll have the transcript by §4) and average the
  deltas per section. Hooks usually cut ~2× faster than the body; if you
  flatten that, the clone feels wrong even at the same average.
- **Shot-length histogram**: note the min and max. A style with 0.4s minimum
  shots AND a single 4s hold is telling you the hold is deliberate emphasis
  — the directives should reproduce that, not average it away.

## 3. Frame evidence — contact sheets

```bash
mkdir -p evidence/sheets
ffmpeg -i ref.mp4 \
  -vf "fps=2,scale=360:-2,tile=5x4" \
  evidence/sheets/sheet_%02d.png
```

2 fps × 5×4 tile = 20 frames = **10 seconds of video per sheet**, so
sheet N covers `[(N-1)*10, N*10)` seconds — a frame at row r, col c of sheet
N sits at `t ≈ (N-1)*10 + (r*5 + c)/2` (0-indexed). Put that formula in the
subagent prompt so reports come back with real timestamps.

360w is deliberate: big enough to read caption case/weight/color and overlay
structure, small enough that a whole sheet fits in one vision read. If a
detail is genuinely illegible (thin serif captions, small UI in a
screenshot), extract that single frame full-res on demand:

```bash
ffmpeg -ss 23.5 -i ref.mp4 -frames:v 1 evidence/full_23.5.png
```

## 4. Audio evidence

```bash
ffmpeg -i ref.mp4 -vn -ac 1 -ar 16000 evidence/audio.wav
```

Transcribe — base model is fine, you need narration BEATS not perfect words:

```bash
whisper-cli -m /path/to/ggml-base.en.bin -f evidence/audio.wav \
  -oj -of evidence/transcript        # JSON with word timings
```

(or `npx hyperframes transcribe evidence/audio.wav -d evidence --json --model
base.en` if the repo's HyperFrames toolchain is set up.)

Render the two pictures the audio agent will read:

```bash
ffmpeg -i evidence/audio.wav \
  -lavfi "showspectrumpic=s=1920x720:legend=1" evidence/spectrogram.png
ffmpeg -i evidence/audio.wav \
  -lavfi "showwavespic=s=1920x480" evidence/waveform.png
```

What to read off them (this is the whole point — you can *see* sound design):

- **Music present?** A music bed shows as continuous broadband texture under
  the speech formants; VO-only shows silence-black gaps between phrases.
- **BPM from kick spacing.** Kicks are the evenly-spaced low-frequency
  (bottom-of-image) energy columns. Measure the spacing in seconds
  (`spacing = duration * px_gap / image_width`), then `BPM = 60 / spacing`.
  Sanity-check: reels bed at 80–140 BPM; if you compute 40 or 240, you
  measured half- or double-time.
- **SFX placement.** One-off vertical full-spectrum spikes that don't repeat
  on the beat grid = whoosh/impact hits. Cross-reference their timestamps
  against the cut list — most styles hit SFX ON cuts; some hit on caption
  pops instead. Which one is a style fact worth recording.
- **Energy arc.** Squint at the waveform: where the envelope steps up
  (drop / section change) and where it thins out (music duck under a key
  line). The clone's mix should copy the arc, not just the track.

## 5. Parallel forensic analysis

Fan out subagents when the Task tool is available (they can each study images
with vision). Solo fallback: run the same passes yourself sequentially —
slower but identical output contract. Every agent must return **timestamped,
countable observations** — no vibes.

**Agent type A — one per contact sheet** (so a 60s reel = ~6 agents):

> You are doing forensic frame analysis of sheet N of a reference reel
> (frames at 2fps; frame at row r, col c ≈ t = (N-1)*10 + (r*5+c)/2 s).
> For your 10-second window report, with timestamps:
> 1. CAPTIONS: font class (sans/serif/slab), weight, case, color(s),
>    stroke/shadow, screen position, words-at-a-time, and — critically — any
>    CONDITION under which the treatment changes (see register systems).
> 2. GRAPHIC OVERLAYS: every non-caption graphic — what it IS (screenshot,
>    stat, list, arrow, frame, badge) and what it appears to be FOR
>    (proof, emphasis, navigation, humor).
> 3. B-ROLL: what replaces the talking head, how it's framed (full-bleed,
>    device frame, floated over blur), and what word it lands on.
> 4. FRAMING: talking-head crop modes (tight/medium, centered/offset,
>    zoom-punch levels) and when they switch.
> 5. GRADE: contrast/saturation character, any color cast, vignette, grain.
> Count INTERNAL BUILDS: every element that pops on within a shot
> (caption word-groups, list items, zoom steps). Report builds-per-shot.

**Agent type B — one agent on the whole `evidence/cuts/` folder:**

> These PNGs are the first frame AFTER every hard cut, in order, with this
> timestamp list: [...]. Report the SHOT-ALTERNATION GRAMMAR: what category
> each cut lands on (face / B-roll / graphic takeover / text card), the
> transition pattern as a sequence (e.g. face→face→graphic→face...), any
> flash frames, luma dips, whip/zoom transitions between specific pairs,
> and any once-only trick — a frame unlike every other (light leak, invert,
> glitch). State what each cut CHANGES: framing? subject? register?

**Agent type C — one agent on the audio evidence** (spectrogram + waveform +
transcript + the cut list): everything in §4, plus: do cuts land on beats?
Do caption pops land on beats or on words? Where does the music duck?

## 6. Synthesis — the style guide

One synthesizer agent (or you) merges all reports + your computed pacing
numbers into `style-guide.md` with EXACTLY these sections. The section names
are a contract — the build skill navigates by them.

```markdown
# Style guide — [reference name]

Source: [duration] @ [resolution] [fps]. Analyzed [date].

## PACING
- cuts/sec overall; per-section (hook/body/CTA) avg shot lengths
- builds/sec (internal pops) — the PERCEIVED pace target
- min/max shot length + where the long hold is and why
- what cuts land on (beat grid? word starts?)

## CAPTIONS
- the register system: each register's full spec (font/weight/case/color/
  stroke/position/words-at-a-time) AND the condition that selects it
- timing: word-synced? phrase-chunked? lead the VO or trail it?

## GRAPHIC LANGUAGE
- every recurring device, named, with: what it looks like, what it is FOR,
  and its trigger condition
- the once-per-video trick — described, and marked "use exactly once"

## B-ROLL GRAMMAR
- what qualifies as B-roll in this style, framing treatment, entry/exit
  animation, dwell time, and what kinds of lines trigger it

## COLOR & GRADE
- overall grade character; per-mode differences (face vs graphic beats);
  ffmpeg/CSS-filter approximation if identifiable

## SOUND DESIGN
- music: written AS AN ELEVENLABS MUSIC PROMPT (genre, BPM from §4, energy
  arc, instrumentation, "no vocals" if bed) — directly generatable
- SFX: the hit vocabulary (whoosh/impact/click/riser), what each lands on,
  approximate level vs VO
- mix arc: duck points, the drop, ending

## BUILD DIRECTIVES
(see §7)
```

## 7. Build directives — applying the style to YOUR script

The directives are a **per-line table over the user's script** (not the
reference's). One row per spoken line / narrative beat:

```markdown
| # | Line (yours) | Cuts within | Visual | Caption register | Builds | SFX |
|---|--------------|-------------|--------|------------------|--------|-----|
| 1 | "hook line…" | 2 (at word X, Y) | tight face → punch-in | sans-lower (face on) | 4 word-pops | whoosh on cut 1 |
```

Rules that make directives buildable:

- **Match the reference's cuts/sec density**, per-section. Total cuts in
  your plan ≈ ref cuts/sec × your runtime, distributed hook-heavy the way
  the reference distributes them. Same for builds/sec (lesson 2).
- Every visual entry uses a **named device from GRAPHIC LANGUAGE** — never
  invent a new overlay in the directives; if the script needs one the
  reference lacks, flag it as a deliberate departure.
- Assign the **once-per-video trick to exactly one row** — the row with the
  same narrative function it served in the reference (usually the reveal or
  the biggest claim).
- Caption register per row follows the SYSTEM's condition, computed from
  that row's visual (face visible → register A, replaced → register B…).
- SFX entries name the hit type and the exact word/cut it lands on.
- End with a handoff note: which build skill (branded-ad-edit for full
  motion graphics; reel-recut for banner+captions+pacing styles) and any
  assets the build needs collected (brand colors, screenshots, music gen).

## 8. Analysis heuristics — the lessons, in depth

**Register systems (the signature).** When two caption treatments appear,
do NOT record "uses two fonts". Find the switching condition. The proven
case: *sans-serif lowercase whenever the speaker's face is on screen; serif
ALL-CAPS whenever a graphic replaces the speaker*. The condition is the
style; the fonts are just its clothes. Test every candidate condition
(face-visible?, section?, sentiment?, music-section?) against all sheets
until one predicts every frame. If no condition predicts it, say so — random
alternation is itself a (rare) finding.

**Builds vs cuts (perceived pace ≈ 2× cut rate).** Viewers experience
"something changed", not "the shot changed". A reference at 0.5 cuts/sec
with 2 caption pops per shot *feels* like 1.5 events/sec. Count builds per
shot on the contact sheets (elements present in frame k+1 but not k within
one shot). Clones that match cuts but not builds are the #1 "why does mine
feel slow?" cause.

**The once-per-video trick.** Scan agent-B output for the frame unlike all
others. The proven case was a light-leak flash at the product reveal —
once. In the clone, spend it once, at the equivalent narrative moment.
Twice = template energy; the original creator knew this.

**Named devices worth looking for** (recur across many creators):

- *screenshot-over-own-blur* — evidence screenshot floated (rounded corners,
  shadow) over a blurred, scaled-up copy of itself as the background. FOR:
  showing any-aspect proof in 9:16 without letterboxing.
- *blue reading-highlight* — translucent highlight sweeping text word-by-word
  as the VO reads it. FOR: eye control on dense text (screenshots, articles)
  so the viewer reads exactly what's spoken.

**Function over appearance.** For every overlay the agents describe, the
synthesizer must answer "what is this FOR?" — proof / emphasis / navigation /
pacing / humor / authority. Directives deploy overlays by function onto new
lines; appearance-only descriptions can only redecorate the original lines.

## 9. Verify before handoff

- Re-read the guide against 2–3 contact sheets you haven't cited: does every
  visible element trace to a guide entry? Unexplained recurring elements =
  the analysis missed a device.
- Sum the directive table's cuts: within ~15% of ref cuts/sec × your runtime?
- Does exactly one row carry the signature trick?
- Is the SOUND DESIGN music prompt generatable as written (genre + BPM +
  arc + instrumentation, no artist names — ElevenLabs rejects them per ToS)?

Then hand `style-guide.md` to the build skill and stay available: review
rounds will send you back to `evidence/` to settle "is that really what the
reference does?" questions — that's why evidence is kept.
