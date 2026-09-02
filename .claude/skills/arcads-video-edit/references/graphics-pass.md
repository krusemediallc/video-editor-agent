# Phase 2 — the graphics pass

The locked cut is the background *and* a character. V6 treated it as a background (cards, chips,
lists over a static video) and was rejected: "really disappointed… no full-screen takeovers or
anything like that… approach this as if you were a senior video editor… go crazy." V7 rebuilt it
as match-moves grounded in the cut and got "overall much better!!". Everything below is the V7/V8
recipe; `scripts/build-comp.mjs` is the generator that shipped.

## 0. Decide the regime at intake

Ask who runs the ad. On the creator's organic feed, motion graphics never take the full frame. On a
brand-run ad (Arcads' own ad account) full-screen takeovers are *expected* and their absence
reads as under-delivery. Never cover the creator's face in either regime. The palette question matters too:
the creator chose monochrome editorial (near-black `#0E0E10`, cream `#F4F2EE`, Inter 100–900, no colour
accent) — "over the top" then has to come from motion, scale and real footage, not colour.

## 1. Transcript, per shot

```bash
# per-shot dry mic audio, exactly the EDL's keep ranges, transcribed in isolation, mapped to output time
npx tsx mg/transcribe-shots.ts        # -> mg/words.json  [{text,start,end,seg}]
```

- Never caption from Whisper on the finished cut: it drifts up to +1s by the back half.
- A 1-second shot will hallucinate ("And that's the end of this video" on the cap punch-in) —
  transcribe it together with its contiguous neighbour and map.
- A clipped first syllable makes three passes disagree ("to what" / "What" / "That's what"); a
  loudness-normalised re-pass settles it. Caption only what is unambiguously there.
- Fix names in place: `arcads.ai`, `Seedance 2.5`, `GPT Image 2`, `99%`.
- Even then expect a few onsets to be wrong. Two words sharing a timestamp is the tell. When the creator
  says a beat is out of sync, measure the syllable bursts on the RMS envelope and hard-set the
  times (V8: "wearing" was 0.3s early, "holding" 0.4s late).

## 2. Research, in parallel

Four readers before any design (run them as a Workflow): (a) every past motion-graphics edit
and the creator's exact praise/kills; (b) the technique palette with copy-paste mechanics from the
`hyperframes-*` skills and `branded-ad-edit/references`; (c) a catalogue of the real assets — the
generated-clip library (see `arcads-broll`; on the proving run 51 unique Seedance clips, all 720×1280 10s),
the storyboard PNGs, the screen captures that can be mined for a reference video; (d) extraction
of anything that must come from the base footage (the YETI reference video lived only in take 06's
screen capture, 456×800 native, 2.36× upscale is "soft but acceptable" for 2s with grain).

What the creator rewards, distilled from 27 edits: full-screen takeovers on brand ads; the base video
moving ("center-stage"); real UI, real recordings, real generated work over recreations; designed
motion over AI text-to-video b-roll; every frame carrying something; the creator's house style exactly; extreme
pacing; the creator on screen by default with talking-head windows between takeovers; purposeful
punch-ins; sub-drop cold opens; a bed ~13 dB under VO, not 18.

What the creator kills: whooshes and risers ("cheesy", "remove the random sfx"); anything over the creator's face;
off-brand looks; timid overlays on a paid ad; static layouts passed off as motion; footage cuts
when the creator asked for graphics; soft AI b-roll; guessed geometry; captions that lag or are hard to
read; "not X, it's Y" as a designed visual.

## 3. Design panel, then synthesis

Three independent storyboards from different angles (broadcast-kinetic / product-cinematic /
editorial-maximal), each covering every note and naming the mechanic, asset and SFX per beat.
Three judges (a motion director, a brand-safety reviewer, the render engineer) score on coverage,
ambition, feasibility, brand safety, pacing, real-asset use. One lead-editor synthesis with a
build order and open risks. The winner (kinetic, 66.4 vs 64.3 vs 63.3) still borrowed the
three-wrapper camera and the preview-thumb portal from product, and the card flip and four-word
stack from editorial.

## 4. Placement is measured

```bash
python3 mg/freespace.py     # -> mg/freespace.json : per-shot importance map + subject box
```

Importance = temporal-max Sobel over the rendered cut; the subject box = temporal std (the creator moves,
the room does not — warm-pixel skin detection failed because the creator's amber key light reads as skin).
Then a per-layout policy, not one rule: `cam` → above the creator's head; `split` → on the creator's chest under the creator's
chin (the top half is the product, off limits however quiet it measures); `screen` → top band,
captions moved above the circle (y1296). Face anchors, measured on full-res frames:
hook (550,700) · split (518–550,1260–1296) · elevating (440,670). Scales come from V5's own crops:
cam→split 0.50, split→circle 0.40, the creator's eyes ~50px above the circle centre (250,1608).

## 5. The generator — `mg/build-comp.mjs`

One file emits `mg/comp/index.html`: hand-authored beats + generated captions + generated SFX.
Every revision is edit-regenerate-check-snapshot-render.

**Camera.** `#vclip` (clip-path only, z35) > `#vwrap` (x/y/scale only, `transform-origin:50% 50%`)
> `#base` (punch scale, `transform-origin` set per shot at each seam). Clip and transform never
share an element. Reframe `x = qx−540−S·(fx−540)`, `y = qy−960−S·(fy−960)`, shared ease on
x/y/scale. The resting clip is `circle(2200px at 250px 1608px)` — 1400px clipped the far corner.

**Two kinds of takeover.** Ones that cover the creator at z46 above `#vclip` (switchboard, reference
video, b-roll). Ones that keep the creator in the circle PIP at z30 *below* it (MCP field, montage):
`#vclip` → `circle(190px at 250px 1608px)`, `#vwrap` reframed at 0.40. The MCP field hands off
to the cut's own `screen` layout under a two-frame 60% ring flash, so the hardest graphic ends on
a real Arcads screen with no visible cut. Seam-set rule: any `tl.set` that must coincide with a
base cut goes at `cut − 0.006`; a cover that must outlast the cut ends `+0.05` past it.

**The beats that shipped** (the creator's 13 notes, all landed):
- Hook: the creator drops to 72% into a ringed card; six real Seedance ads fly in from depth; WITH · AI on
  ink pills in the gutter; the cards snap into a 3×2 mosaic tiling the top half while the creator slides
  to the split's face position; full-frame blinds (0.14s strips, 0.015s stagger, starting 6.02
  for a 6.267 cut) hide the base cut.
- Speech bubble on the seam, tail into the creator's cap.
- Switchboard: frame slices in, NEW MODELS slams with extrusion, eight rows waterfall, toggles
  press/spring/invert/ring on the creator's cadence, counter 0/8→8/8, all-on flash, push off, hand back
  punched 1.08. Model names need receipts (see brand-safety).
- Reference video: preview card pops on the seam already playing; rushes the lens; full-bleed
  with L-brackets and a mono tag; on "like this" collapses into the exact 457×801 rectangle where
  the real UI plays it (clip on the outer wrapper, transform on the inner); a bracket draws around
  the real popup.
- Nodes on the seam with a wire drawing between them → MCP field: radar rings, wire draw, packets
  along the path (`getPointAtLength` on a proxy), a terminal typing the real server and handshake,
  the real prompt streaming, a quote band slam, whip out.
- Starting frames: the real GPT Image 2 boards waterfall in and flip into their clips.
- Credits like film credits (hairline, mono role, 76px name, sheen). Checklist: press, fill,
  drawn tick, ring ping, 12-particle burst, counter, conic ring, EVERYTHING, then the card flips
  to its back face with the quote. Seam strip between the video and the creator's head quoting the creator's gripes.
- Three type slams (WEARING / HOLDING / INTERACTING) on measured onsets. Styles rail with a
  number wheel and a translate roll inside an overflow-hidden slot (a clip-wipe roll overlapped
  both names for four frames and Gemini caught it).
- Frame draws in (no text) → closes to a wall → opens on generated b-roll inside the frame →
  snaps open on "create" with the creator punched full-frame.
- Montage: wall builds with the creator in the centre cell, WITHOUT slams, three hard cuts on the creator's words
  (the creator moves centre→corner circle under the first cut), INSANE / CREATIVE / BUDGETS in a fixed
  right-aligned column, blinds out. V7's five whips in three seconds were "too much movement";
  V8's three cuts were accepted.
- End box on the seam: seam halves draw in and dock, ink border draws around the mark, `arcads.ai`
  rises, a mono chip types the keyword and lifts off on "send".

**Captions.** Chunks of ≤3 words broken on pauses >0.22s and shot boundaries; each a timed clip
with an entrance tween only (the window ends it — an exit tween straddling another clip's start
fails lint); opaque ink pills fused with a 4px box-shadow, inactive 0.9, active pops 0.92→1;
cream-inverted on ink takeovers; y1690 default, y1296 on screen shots and while the PIP is live,
y1150 inside the MCP field; muted when a card carries the same significant word.

**Sound.** `branded-ad-edit/scripts/generate-sfx.py` on `assets/sfx-kit.json` (9 effects, audit,
retry duds, normalise −3 dB). "pop" came back as 0.48s of silence three times — pitch the click
up instead. Hits only on words and motion: thud on stamps, pop on chips, click on rows/cells,
ding on ticks, sub on slams, shimmer on the brand reveal; zero whooshes/risers. Music: two
ElevenLabs beds (ask for "energy stays constant, never fades out" — a bed generated at 68s faded
out at 58s), crossfaded at the drop so the arrangement changes; a gain envelope for the arc;
`data-volume` 0.24 (~13 dB under VO) plus, after the creator's note, the opening 28s at +11 dB limited.

## 6. Check → snapshot → render → master

```bash
node mg/build-comp.mjs && npx hyperframes check --dir mg/comp
npx hyperframes snapshot --at 2,4.6,6.23,14,18.6,21.4,31.3,35.03,39.9,49.5,53.4,55.6,62.5,66.5,79.6,84.2,86.85,89.35,90.7 --no-end --describe false -o "$(pwd)/mg/snapN"
```

Look at every sheet. Four snapshot rounds preceded the first full render and each found real
bugs (see gotchas). Then, as a **tracked background job**:

```bash
PRODUCER_BROWSER_GPU_MODE=hardware npx hyperframes render --video-frame-format png --quality high -o renders/vN-raw.mp4 --quiet
```

Master with two-pass `loudnorm` (I −14, TP −2.0 when the bed is hot) + `alimiter=limit=0.79..0.84`,
`-t <DUR>` so both streams match, check LUFS/TP/frames/decode, verify the bed lifts the quietest
windows ~+2 dB and the slams land +6–9 dB over the base, then `npm run qa:video --lane hyperframes`
and a copy review on every typeset word.
