# Design: brand research, B-roll, storyboard

## 1. Brand tokens from the live site (15 min, no design docs needed)

```bash
curl -sL -A "Mozilla/5.0" https://BRAND.com -o site.html
grep -oE "#[0-9a-fA-F]{6}\b" site.html | tr 'A-F' 'a-f' | sort | uniq -c | sort -rn | head -20
grep -oE '(src|href)="[^"]*(logo|icon|favicon)[^"]*"' site.html | sort -u
# fetch the linked .css files and repeat the histogram — often richer than inline
```

Download logo SVG/PNGs (prefer a white/knockout variant for dark canvases). Screenshot
the homepage with Playwright and LOOK at it: background family, primary accent,
semantic green/red, font. Emit the token block every card will use:

```css
:root {
  --brand-accent: #…; --brand-accent-deep: #…; --brand-accent-soft: #…;
  --bg-dark: #…; --panel: #…; --panel-2: #…;
  --green: #…; --red: #…; --gold: #…; --muted: #…;
}
```

If the site is light-themed, you can still run a dark canvas (ads live in dark feeds)
with the brand accent carrying identity — or mirror their light theme; decide from
their reference ads.

## 2. Real assets beat recreations

From any brand asset folder (Drive/Dropbox/etc.), pull: product/dashboard screenshots,
metric screenshots (before/after numbers are gold), logo variants, icon assets. A
genuine screenshot in a white rounded card reads as *proof*; a mockup reads as an ad.
If a winning-ads/swipe board exists: screenshot the grid, study it, and write down the
recurring visual MOVES (split layouts, floating metric cards, banner headlines, color
semantics, caption style). Clone the moves, not the pixels.

## 3. Website B-roll

Goal: 4–6 clips (3–6s) of the brand's real site/product scrolling smoothly, captured
clean. Recipe:

```js
const browser = await puppeteer.launch({
  headless: false, defaultViewport: null,
  // SYSTEM Chrome, not Chrome-for-Testing (see keychain gotcha below).
  // macOS default shown; set CHROME_PATH for Linux/Windows installs.
  executablePath: process.env.CHROME_PATH ||
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  userDataDir: "/tmp/broll-profile",              // fresh throwaway profile
  ignoreDefaultArgs: ["--enable-automation"],     // kills the automation infobar
  args: ["--kiosk", "--window-position=0,0", "--window-size=1920,1028",
         "--use-mock-keychain", "--password-store=basic", "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check"],
});
```

- Sweep junk on an interval (widgets re-mount): `display:none!important` on
  `[id*="cookie" i]`, `[class*="chat" i]`, `[class*="intercom" i]`, `[class*="crisp" i]`…
- Scroll with an eased rAF loop (~1.4s/move), hold 3–4s per section; log per-section
  timestamps for cutting.
- Record the display (any recorder; 60fps nice) or use Puppeteer screencast. Cut
  per-section clips including the scroll-in, `-crf 17 -g 30 -keyint_min 30 -an`.
- **Frame-extract-review every take.** Past captures contained: a macOS keychain
  dialog dead-center (Chrome-for-Testing pops one even with `--use-mock-keychain`,
  and an orphaned dialog survives `pkill` — hence system Chrome), personal app
  windows, and a scroll that never moved.
- **Scroll-target by the SMALLEST matching text node** — an ancestor div also
  "contains" the text and its `top` is 0, silently scrolling nowhere.

In-composition, B-roll plays inside a browser-chrome card (dark rounded frame,
traffic-light dots, URL pill) — instant "their real site" credibility.

## 4. Storyboard: card archetypes

One card per sentence. For each: mode (split/solo/fullhim/full), archetype, and the
word timestamps of every internal beat. Proven archetypes — map ANY industry's script
onto these:

| Script beat | Card |
|---|---|
| "the status quo / tool / data is wrong" | real screenshot in a white card + red rotated STAMP popping on the key word |
| a cost or scary number | giant red count-up (`$0→$500`), sub-label lands after |
| "from this to this" | two real screenshots slide in on the exact words — BEFORE (red outline) / AFTER (green outline), arrow between |
| checklist claim ("same X, same Y, fixed Z") | chips pop word-synced; the payoff chip filled in brand accent |
| causes/mechanism (2–4 items) | icon tiles pop per item → big stat count-up (red) + label |
| "everyone says X/Y/Z, but…" | rows pop per item → animated strikethroughs → answer row glows in accent |
| the one-word emotional beat | FULL takeover: one giant word (green if it's the win word), 200–260px |
| speed/time claim | SVG ring timer drawing + the number center |
| brand reveal | wordmark pops + hero B-roll in browser frame (split square) |
| social proof | count-up ("9,000+"), gold ★ rating, reviews-page B-roll |
| guarantee / risk-reversal | outlined shield card in green, pulse on the number |
| CTA (final 2–3s) | FULL: logo, offer line, pulsing button ("Tap 'Learn More'"), bounce arrow |

Rules of thumb: every number counts up; every list pops word-synced; split-square
content lives in the top ~880px (captions own the bottom strip); ≤3 full takeovers;
hard-cut into fullhim, tween between split/solo; a card that would sit empty >1s
before its beat should bring SOMETHING in early (frame, kicker) — dead squares read
as broken. An overlay card must never enter while a fullhim segment still runs — it
lands on the speaker's face; delay it to the framing cut.

**Screengrab presentation (client-tested):** a screenshot with a floating highlight
box + blurred backdrop + slow zoom was flagged as "looks bad" — twice. What reads
clean: the sharp screenshot inside a dark rounded **browser-chrome card** (traffic
dots), static (no zoom), sized to FILL the canvas — dead space around a small frame
got flagged too. For emphasis, draw a translucent highlighter band (scaleX 0→1) or
underline on the key line instead of a box. Measure crop offsets from the actual
image with a gridded contact print, not by eye from thumbnails.

**A strike sound needs a strike visual** — a pen-scratch SFX with nothing visibly
crossed out confuses the viewer. GSAP can't tween pseudo-elements: put a real `<i>`
bar element in the line and scaleX it on the sound.

**Mascots/logos from reference footage:** when cloning a style, extract the actual
mascot from a reference frame (find a flat-bg frame, saturation-bbox the sprite,
color-key the bg to alpha, NEAREST-upscale). A hand-drawn approximation WILL get
flagged against the real one.

**The last frames:** extract the final ~1.5s frame-by-frame and check when the
speaker breaks eye contact (glancing at the stop button) — the fade must be fully
black BEFORE that; audio finishing over black is fine.

Mode variety pattern that worked (72s): open split ×3 → fullhim (drama) → solo
(banners) → split ×5 → fullhim (drama) → full (takeover ×2) → split (brand) → solo →
split ×3 → full (CTA).
