# Composition: crops, contract, captions, QA

## 1. Ingest & crops

```bash
mkdir -p project/{assets,broll,public}
ffprobe -v error -show_entries format=duration -show_entries stream=codec_type,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 source.mp4
```

Record duration — it becomes `data-duration` everywhere. Two crops from a 16:9 source
(tune crop x-offsets by extracting a frame and looking at the face position):

```bash
# band crop (split/solo modes) — 1080×840, keeps the source audio
ffmpeg -y -i source.mp4 -vf "crop=<h*1080/840>:<h>:<x>:0,scale=1080:840" \
  -c:v libx264 -crf 18 -g 30 -keyint_min 30 -pix_fmt yuv420p \
  -movflags +faststart -c:a aac -b:a 192k public/input-video.mp4

# full-bleed crop (fullhim mode) — true 9:16, no upscale, no audio
ffmpeg -y -i source.mp4 -vf "crop=<h*1080/1920>:<h>:<x>:0,scale=1080:1920" \
  -c:v libx264 -crf 19 -g 30 -keyint_min 30 -pix_fmt yuv420p \
  -movflags +faststart -an public/input-video-vert.mp4
```

`-g 30 -keyint_min 30` (a keyframe every frame-second at 30fps) is mandatory on EVERY
media file entering the composition — the renderer seeks per frame and sparse GOPs
freeze under overlays.

## 2. Project layout

```
public/
  index.html          # GENERATED — never hand-edit; regenerate from the template
  input-video.mp4  input-video-vert.mp4
  fonts/Inter-{400,700,800,900}-latin.woff2   # local woff2 (fontsource CDN, downloaded once)
  vendor/gsap.min.js                          # from the talking-head-recut skill assets
  assets/  broll/  sfx/  music-*.mp3
index-template.html   # the file you author (cards + timeline + placeholders)
build.mjs             # injects captions/SFX into the template → public/index.html
storyboard.json  transcript.json
```

## 3. The composition contract

```html
<div id="stage" data-composition-id="<name>" data-start="0" data-duration="<DUR>"
     data-fps="30" data-width="1080" data-height="1920">
  <div id="backdrop"></div>                <!-- brand-dark gradient + faint 90px grid -->
  <div class="video-wrapper" id="video-wrap">   <!-- CSS base top:1080px; moved with y transforms -->
    <video id="bg-video" src="input-video.mp4" muted playsinline
           data-start="0" data-duration="<DUR>" data-track-index="1"></video>
  </div>
  <audio id="source-audio" src="input-video.mp4" data-start="0" data-duration="<DUR>"
         data-track-index="10" data-volume="1"></audio>
  <div class="video-full" id="video-full">      <!-- CSS: visibility:hidden; opacity:0 -->
    <video id="full-video" src="input-video-vert.mp4" muted playsinline
           data-start="0" data-duration="<DUR>" data-track-index="4"></video>
  </div>
  <div id="vignette-full"></div>   <!-- opacity 0; gradient darkening top/bottom for fullhim captions -->
  <div id="progress"></div>        <!-- 8px brand-gradient bar, transform-origin left, scaleX(0) -->
  {{SFX_ELEMENTS}}
  <!-- one card-host per card: -->
  <div class="card-host clip" data-card-id="card-01" data-start="0" data-duration="3.06"
       data-track-index="2" style="left:0;top:0;width:1080px;height:1080px;visibility:hidden;opacity:0;">
    <div class="card" data-card-id="card-01"> …scoped <style> + markup… </div>
  </div>
  <div id="captions" data-track-index="5">
{{CAPTION_SPANS}}
  </div>
  <script src="vendor/gsap.min.js"></script>
  <script>
    (function () {
      var tl = window.gsap.timeline({ paused: true });
      var Q = function (t) { return Math.round(t * 30) / 30; };
      // helpers: enter/exit (host fades), pop (back.out scale), rise (y+fade), countUp
      …cards, framing, retention devices…
{{CAPTION_TWEENS}}
      window.__timelines = window.__timelines || {};
      window.__timelines["<name>"] = tl;
    })();
  </script>
</div>
```

Non-negotiables (the linter catches most; the rest cost renders):

- ONE paused timeline, built synchronously. No `setTimeout`/promises/`Math.random()`/
  `Date.now()`/`repeat:-1`.
- Every timed element carries `class="clip"`; **every `<video>`/`<audio>` has a unique
  `id`** (missing id ⇒ FROZEN media in renders).
- **Transforms only** for motion: `x/y/scale/opacity`. The video reframes tween `y`
  against the CSS base (`top:1080px` + `y:-540` = solo; `y:900` = off-screen). Never
  animate `top/left/width/height` on anything that moves.
- **Initial hidden states in CSS** — one rule listing every delayed element with
  `opacity: 0` — never `tl.set(..., 0)` (zero-duration sets at position 0 don't render
  on frame 0). Animate in with `fromTo`.
- Card `<style>` rules all scoped `.card[data-card-id="…"] …`; no `<script>` in cards;
  no external URLs anywhere (renderer has no network); body `font-family` lists
  concrete font names (the static analyzer doesn't expand CSS vars).
- Quantize every position: `Q(t)`.

## 4. Framing + retention devices

```js
// split → solo and back: tween the band
tl.to("#video-wrap", { y: -540, duration: 0.5, ease: "power2.inOut" }, Q(t));
// split → fullhim: fast crossfade + vignette (hard-cut feel)
tl.set("#video-full", { visibility: "visible" }, Q(t - 0.04));
tl.fromTo("#video-full", { opacity: 0 }, { opacity: 1, duration: 0.12 }, Q(t - 0.04));
tl.to("#video-wrap", { opacity: 0, duration: 0.12 }, Q(t));
tl.fromTo("#vignette-full", { opacity: 0 }, { opacity: 1, duration: 0.3 }, Q(t + 0.03));
// slow push-in during a fullhim hold (one per segment; don't overlap with punches)
tl.fromTo("#full-video", { scale: 1 }, { scale: 1.05, duration: <hold>, ease: "none" }, Q(t));
// full takeover: slide the band off  → tl.to("#video-wrap", { y: 900, … })

// progress bar (whole duration, linear)
tl.fromTo("#progress", { scaleX: 0 }, { scaleX: 1, duration: DUR - 0.13, ease: "none" }, 0.05);
// zoom-punch on a key word (on the <video>, not the wrapper)
tl.to("#bg-video", { scale: 1.07, duration: 0.15, ease: "power2.out" }, Q(w));
tl.to("#bg-video", { scale: 1.0,  duration: 0.35, ease: "power2.inOut" }, Q(w + 0.18));
```

## 5. Karaoke captions

Generate them — never hand-write 90 tweens. Use `scripts/generate-captions.mjs`
(bundled with this skill; see its header for the config format). The algorithm it
implements:

1. Chunk words: break at 3 words, a gap > 0.45s, or terminal/comma punctuation.
2. Display window: `start − 0.04` → **next chunk's raw start − 0.04, always** — holding
   a chunk past the next one's start renders a mashed double-caption.
3. Position class from the mode at the chunk midpoint: split → top ≈ 880 (bottom strip
   of the square), solo → ≈1440, fullhim → ≈1500 (vignette behind), full → ≈1560.
4. Style: heaviest available weight (Inter 800/900), ~78px, white, heavy soft shadow.
   `<em>` highlights on money/number/keyword tokens, colored by the beat's sentiment:
   red while agitating costs, green for wins, brand-accent for brand/CTA sections.
5. Per chunk: positioned span + three tweens (set visible / 0.12s pop scale .92→1 /
   set hidden at window end).

## 6. QA → render → verify

```bash
npx hyperframes check public                       # fix ALL errors; warnings judgment-call
PRODUCER_BROWSER_GPU_MODE=hardware npx hyperframes snapshot public \
  --at t1,t2,…,tN --no-end                         # ONE call — separate calls overwrite
PRODUCER_BROWSER_GPU_MODE=hardware npx hyperframes render public -o output.mp4 --fps 30
```

Snapshot every card's hero moment + every transition. LOOK at the contact sheet:
overflowing headlines, glyphs that don't render headless (Apple private-use chars —
use emoji/text), cards landing on the speaker's face, dead-air gaps, unreadable
overlaps (dim what's underneath to ~0.12 as a stamp lands).

Verify the rendered FILE: `ffprobe` duration (render logs lie when a stage attr was
missed), frame-extract previously-fixed beats, `volumedetect` 0.6–1.2s windows around
each SFX hit compared to the same window without SFX (a hit is real only if the peak
rises), and a word-gap window for the music bed. Renders are ~2–3 min for 70s on an
M-series — background them and keep working.
