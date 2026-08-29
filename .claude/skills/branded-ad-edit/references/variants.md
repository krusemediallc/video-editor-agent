# Hook A/B variants (EDL cutting)

Raw cuts often stack two hooks back-to-back ("X is broken…" + "you're burning money…").
Ad platforms want hook variants anyway. Ship one version per hook by cutting the
composition programmatically — **never hand-retime cards**.

## The EDL remap

1. **Choose cut ranges on the ORIGINAL timeline**, at sentence boundaries, inside
   word-gaps (check the transcript: cut between word N's `end` and word N+1's `start`).
   Example: variant A cuts hook 2 `[8.525, 12.98)`; variant B cuts hook 1 `[0, 8.529)`.
2. **`mapTime(t)`**: `null` if t falls inside a cut; else `t − (total width of cuts
   before t)`. New duration = old − total cut width.
3. Apply the map to EVERYTHING that carries a time:
   - every `Q(x)` position and helper time-arg in the timeline JS — **drop whole
     statements** whose time maps to null;
   - every `data-start`/`data-duration` attribute pair (elements spanning the full
     composition keep start 0 and get the new duration);
   - caption chunks and SFX hits (filter out the cut ones, shift the rest) — do this
     in the generator, before emission;
   - the stage's `data-duration` and the progress-bar tween duration — **patch these
     explicitly**: pretty-printed HTML puts the stage's attributes on separate lines,
     so a single-line attr regex silently misses it and the render comes out
     full-length with a frozen tail. Verify the RENDERED file's duration with ffprobe.
4. **Excise fully-cut card-host blocks from the HTML** — left in place with stale
   times they overlap the remapped cards on the same track and `check` fails.
5. **Pre-cut the media per variant** (trim/concat filter for interior cuts, `-ss` for
   a head cut; re-encode with `-g 30 -keyint_min 30` again; cut the music file to the
   variant length with its own end-fade) and point the srcs at variant filenames.
6. Hide each splice inside a framing change — a jump cut masked by the video moving
   to a new position reads as an edit, not an error.

## Variant that OPENS mid-grammar (e.g. on the full-bleed crop)

Two landmines when the cut moves a mid-video state to t=0:

- The wrapper must be visible from frame 0 → set it in **CSS** for that variant build
  (a `tl.set` at ~0 doesn't paint frame 0), and drop the now-redundant near-zero
  fade-in tweens (they'd flash dark).
- **GSAP `fromTo` defaults `immediateRender: true`** — a LATER segment's
  `fromTo(el, {opacity: 0}, …)` stamps inline `opacity:0` on the element at PAGE LOAD,
  overriding your CSS and blacking out the opening. Add `immediateRender: false` to
  any fromTo whose element must be visible before that tween's position.
  Diagnostic tell: the element's own background color doesn't paint (the page backdrop
  shows through it) → something stamped the element itself; it is NOT the media
  pipeline. Bisect with `snapshot` (30s), not renders (3min).

Also give an opening variant its own opening graphic (a banner/kicker chip over the
speaker for the first ~2.5s) — a cold open with nothing but captions reads as
unfinished, and the human WILL flag it.

## Revision cuts after client feedback

When review finds a surviving flub, the fix is a NEW master cut — and the whole
composition retimes. Same mapTime discipline, chained through EDL JSONs:

1. Keep an EDL per version (`edl-v1.json`, `edl-v2.json`, …: raw↔master windows).
   Map any old time via **old-master → raw → new-master** (raw positions are the
   stable coordinate system). Times below the first cut are identity; times inside
   removed material collapse to the cut point.
2. Apply the map to EVERY position pattern the template uses — `Q(x)` literals,
   bare-number time args at helper call-sites (`enter/exit/pop/rise/hide`), framing
   fns (`bandOn/fullOn/punch*`), `wordSwap` time arrays + endAt, `countUp`'s at-arg,
   card-host `data-start`/`data-duration` pairs (new dur = `map(start+dur)−map(start)`),
   stage/media durations, SFX hit lists, caption config ranges, the music trim + fade.
   **Split the file at the `<script>` boundary** so attribute passes and literal
   passes can't double-map each other.
3. **Count capture groups in every retime regex** — a nested group shifts the callback
   args and silently maps times to 0/NaN (gotcha #20).
4. Beats that collapse onto a cut point need hand-tuning to the NEW word times (from
   the per-clip transcript) — that's normally 1-2 values, not a hand-retime.
5. Regenerate captions from the per-clip EDL-anchored transcript (gotcha #19) — never
   re-run whisper on the new full cut and call it done.
6. Snapshot the cut boundaries + re-render; sweep the whole file at 2fps and LOOK.
