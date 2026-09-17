# The method — building this style on new footage

Verbatim-tested pipeline. Work in a per-project folder in the projects directory
(see MASTER_CONTEXT.md); nothing here writes into this repo.

Read [style-system.md](style-system.md) for the measured spec. This file is how
you execute it.

---

## 1. Deconstruct the reference (only if one was given)

The general version of this lives in the **reel-style-clone** skill — use it.
Three things that pass is prone to getting wrong on *this* style specifically:

- **Scene detection returns zero cuts, and that is the finding, not a failure.**
  If `select='gt(scene,0.25)'` yields nothing, do not lower the threshold hunting
  for cuts. Dump raw scores instead and treat the high ones as overlay events:
  ```bash
  ffmpeg -nostdin -v error -i ref.mp4 \
    -vf "select='gte(scene,0)',metadata=print:file=scores.txt" -f null -
  ```
  Then re-verify with a frame-difference pass masked around the overlay events —
  a locked-off talking head can hide a jump cut from the scene detector.
- **An events list built this way is incomplete.** One measured run missed 6 of
  34 container transitions and every intra-rect clip swap. Never hand it
  downstream as the authoritative overlay list without a full-res pass.
- **A blue-mask scan for "is the title up?" gets false positives** from blue
  content inside a found-footage insert. Gate on the mask's pixel *area*.

## 2. The base cut — the step that inverts normal practice

This style keeps its pauses. Target **~15 % retained silence, median gap
~0.32 s, breaths audible**. A conventional silence-cut base with zero air will
not carry the style no matter how good the overlays are.

Most raw talking-head footage sits at 40–45 % silence, so you do need to cut —
just **cap** each pause instead of removing it. Remove the middle of every gap
longer than `KEEP`, leaving `KEEP/2` either side so no word onset is clipped:

```python
KEEP = 0.25; HALF = KEEP / 2
removals = [(s + HALF, e - HALF) for s, e in gaps if (e - s) > KEEP]
```

Sweep `KEEP` and pick the value that lands nearest 15 % on the *output*
duration, then render with a `select`/`aselect` pair on the same expression so
picture and sound stay locked:

```bash
ffmpeg -i source.mp4 \
  -vf "select='$SEL',setpts=N/FRAME_RATE/TB" \
  -af "aselect='$SEL',asetpts=N/SR/TB" \
  -c:v libx264 -crf 17 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k base.mp4
```

Verify the result: re-run `silencedetect` on the OUTPUT and confirm the gap count
and total. Do not trust the plan.

**Speech rate is a casting spec, not a post spec.** The reference runs 252 WPM,
flat. Footage at ~190 WPM will feel slower however it is cut; say so rather than
trying to fix it with tighter overlays.

## 3. Derive the overlay band FROM THIS FOOTAGE

Run `scripts/measure-face-band.py <base.mp4> <outdir>`. It samples a frame per
second, segments the head against the background, and reports the cap-top and
eye-line distributions plus the two floors.

```
EYE_FLOOR  = min eye line − 24   # the reference's own (sloppy) behaviour
HEAD_FLOOR = min cap top  −  8   # clears the head entirely
```

Then fit each source at **native aspect**:

- width ≥ 70 % of frame → may sit against `EYE_FLOOR`
- width < 70 % of frame → must clear `HEAD_FLOOR`

**Why the second rule exists:** a narrow portrait insert centred above a head,
bottom-anchored to the eye floor, lands on the crown and reads as a hat. The
reference never hit this because its inserts were landscape. Phone-recorded
b-roll is portrait, so you will.

**Never copy the reference's y-values.** On one real build the difference
between a guessed floor and the measured one was 278 px, which was the
difference between a 163 px sliver and a usable insert.

## 4. Storyboard against measured word onsets

Pull the exact onset of every candidate trigger word from the word-level
transcript and build the storyboard from those numbers, not from listening.

- **One card per concept noun.** The card's title is `THE <NOUN>` where the noun
  is a word the speaker actually says.
- **Inserts on concrete nouns** in Act 2 — the object being named.
- **The CTA banner on the first verb of the outro**, not on the keyword. Match
  the reference's ~3.3 s lead, and hold to the final frame.
- **Place the breathers deliberately.** Find the pivot lines in the script and
  leave 2.5–3.5 s of clean frame there.
- Keep Act 1 to ~2.5 s and hard-cut it off. Do not let the plate run into Act 2.

## 5. Build

A HyperFrames composition. Structure that worked:

```
comp/
  build.mjs          # storyboard + tokens -> emits index.html
  index.html         # generated; never hand-edit
  assets/{base.mp4, words.json, fonts/, img/, clips/}
```

`build.mjs` holds the design tokens as named constants traceable to
style-system.md, the storyboard arrays, and a per-card `body` (skeleton-kit HTML)
plus `beats` (interior build steps, each with a measured `at`). Emitting the HTML
from a script is what keeps every number reviewable in one place.

Conventions the runtime requires:

```html
<div id="root" data-composition-id="main" data-start="0"
     data-width="1080" data-height="1920" data-duration="..." data-fps="30">
  <video id="base" src="assets/base.mp4" data-start="0" data-duration="..." muted playsinline></video>
  <audio id="base-a" src="assets/base.mp4" data-start="0" data-duration="..." data-volume="1"></audio>
```
```js
window.__timelines = window.__timelines || {};
window.__timelines["main"] = tl;
```
Every media element needs `data-start` / `data-duration`, or preview and render
diverge.

**Containers use `tl.set(..., duration 0)`. Only interiors use `tl.to`/`fromTo`.**
That one discipline is most of the style.

### The caption engine
1. Group words into lines of ≤4 words, breaking on sentence-final punctuation.
2. Clean the copy — capitalise proper nouns, fix known ASR errors.
3. Emit one `<span>` per word so the highlight can be a background colour swap.
4. **Measure line widths only after `document.fonts.ready` resolves.** Measuring
   before the webfonts load returns fallback-font widths, the over-wide guard
   never fires, and captions run off frame. This bug survived two renders.
5. Scale any line wider than ~990 px down in place.
6. Apply the sentence-block rule: per sentence, `left = 540 − widest/2`.
7. Give the caption text a stroke. The reference's lack of one is a defect.

## 6. QA on the rendered file, then master

```bash
npx hyperframes check                       # before every render
npm --prefix <repo>/tools/video-qa run qa:video -- --video output.mp4
```

Extract frames from the **rendered MP4** at every act boundary and look at them.
The defects that survived `check` on a real build were all visual: a pill
overflowing its box, a CTA running off frame, an insert sitting on the subject's
head. None of those are detectable without looking at pixels.

Master to the reference's loudness — most phone-recorded talking-head footage
lands 4–6 dB quiet:

```bash
# two-pass loudnorm; ${M} MUST be braced - zsh eats $M:linear as a modifier
ffmpeg -i in.mp4 -af "loudnorm=I=-14.5:TP=-1.0:LRA=7:${M}:linear=true,alimiter=limit=0.891:level=false" \
  -c:v copy -c:a aac -b:a 192k out.mp4
```

Target **−14.5 to −15.0 LUFS, true peak ≤ −0.5 dBTP**. Re-measure with
`ebur128=peak=true` after; do not trust the filter's own report.

Then deliver on a review canvas (`video-review-canvas`) with the URL leading the
reply.

## 7. Known traps

| Trap | Symptom | Fix |
|---|---|---|
| Measuring text before fonts load | captions run off frame | gate on `document.fonts.ready` |
| Copying the reference's band | inserts tiny or on the face | derive from this footage (§3) |
| Narrow insert at the eye floor | reads as a hat | clear `HEAD_FLOOR` (§3) |
| `$VAR:linear` in zsh | `Invalid chars 'inear=true'` | brace it: `${VAR}:linear` |
| Silence-cutting to zero air | style does not land | cap gaps, don't remove (§2) |
| Adding SFX on overlay cuts | wrong style | the reference has none, measurably |
| Leaving the title up through the body | the giveaway mistake | hard-cut it at ~2.5 s |
| Fading a card in | wrong style | containers are 1-frame cuts, always |
