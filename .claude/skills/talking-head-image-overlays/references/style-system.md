# The style system — measured spec

Every number here was measured from pixels across five independent forensic
passes on a reference reel in this style (82 s, 720x1280 @30fps), then proven by
rebuilding the style on unrelated footage. Where passes disagreed, the range is
given. Canvas below is **1080x1920**; the reference was 720x1280, so source x1.5.

Nothing in this file is specific to one creator or one video. Geometry that must
be derived per-video is marked **DERIVE**.

---

## 1. Layout

| Zone | norm | px @1080x1920 |
|---|---|---|
| Image-overlay envelope | y 0.022–0.452, x 0.000–1.000 | y 42–868 |
| Designed-card rect | x 0.100–0.899, y 0.100–0.899 | **x 108–972, y 192–1728 (864x1536)** |
| Caption highlight band | y 0.728–0.771 | **y 1398–1481** (h 81–84) |
| Caption baseline | y 0.7594 | y 1458 |

The **card** rect is rigid — identical in all seven card instances, an exact
10 % inset on all four sides, which is 9:16 inside a 9:16 frame.

The **image band is not rigid.** Across seven inserts the top edge ranged
y 28→168 and the bottom y 415→578 (at 720). The invariant is: *top-anchored in
the upper third, never below y≈0.45, horizontally free, sized to the source's
native aspect at whatever scale fits.* Two of seven bled to both frame edges.

**DERIVE the floor per video.** The reference has no face-avoidance logic: its
rects are absolutely positioned while the speaker moves, so the same rect clears
the brow in one shot and cuts through the eyebrows in another. Use
`scripts/measure-face-band.py` to get:

- `EYE_FLOOR` = minimum eye line across the take − 24 px
- `HEAD_FLOOR` = minimum cap/hair top − 8 px

Wide sources (≥70 % of frame width) may sit against `EYE_FLOOR`. Narrow sources
must clear `HEAD_FLOOR` — a narrow insert centred over a head reads as a hat.

**No camera moves.** A static background landmark holds constant scale for the
whole reference (max/min ≤ 1.09). Apparent punch-ins are the subject leaning in.
There is a slow handheld drift of a few px/s. Adding punch-ins will not match.

---

## 2. Colour and type

One saturated blue, used for exactly two things and nothing else.

| Token | Hex | Where |
|---|---|---|
| Brand blue | **`#2752E5`** | title plate box, CTA banner box, caption highlight |
| Card paper | `#FAF7F8` | designed-card background |
| Sub-card / panel | `#FEFEFE` | inner cards, shelves, panels |
| Sub-card border | `#E5E5E5` | 1 px |
| Skeleton pill | `#C0BFB4` | every fake text bar, h 21 |
| Hairline divider | `#D7D7D7` | 1 px |
| Connector curve | `#A2A09A` | 3–4 px |
| Pass check | `#107C59` | |
| Fail check | `#D12468` | |
| Dashed empty slot | `#DEDEDE` | dash 6 on / 1.5 off, ~2 px |
| Filled slot border | `#CCCCC5` | solid — a filled slot swaps dashed → solid |
| Muted label | `#8A8785` | mono lowercase, ~34 px |
| Card title ink | `#242220`–`#272423` | |
| Card footer ink | `#696765`–`#7E7C78` | |
| Prompt-card black | `#13160E` | a warm near-black, not `#000` |
| Scan rule | `#ADABA0` | 5–6 px |

Blue verification: title box median `#2752E5` over 76 k px, caption highlight
median `#2A52E3` over 8 k px on moving skin — a 3/255 delta, i.e. chroma bleed.
**One blue token.**

**Three type roles, strictly separated:**

1. **High-contrast display serif** (Playfair Display class) → the opening title
   and the closing CTA banner **only**. It appears exactly twice in the video.
2. **Monospace** (JetBrains / IBM Plex Mono class) → card titles (Bold, ALL
   CAPS), and every label, footer and prompt dump (Regular, lowercase).
   Monospace is *proven* by constant glyph advance across `l`/`I`/`O`/`X`.
3. **Heavy geometric grotesque sans** (Inter / Montserrat class) → karaoke
   captions only.

---

## 3. The persistent frame — there isn't one

| Element | Window | Geometry @1080 | Type |
|---|---|---|---|
| Title plate | 0.000 → ~2.5 s, hard off | box x 75–1005, y 219–495, r 21–24 | serif regular, cap 67–93 px, size ~95 px, 2 lines centred |
| Pill | same window, dies same frame | x 326–755, y 474–606, r 18 | bold sans, ~52–62 px, black on `#FEFEFE` |
| CTA banner | ~92 % → final frame | line 1 x 39–1040 y 237–431 r 24; line 2 x 129–950 y 432–530 r 27 | serif **heavier cut**, cap 75 px, size ~86–105 px, line-height 0.94 em |

- The plate is up at **frame 0**, before the subject is in frame. The first
  caption appears ~0.5 s later.
- The pill **overlaps** the plate's bottom edge by ~20 px. It is hook-only and
  never returns — the CTA banner has no pill.
- Highlight rects are drawn **per line, sized to the line**. The opening plate
  only looks like one merged box because its two lines set to equal width.
- The CTA's comment keyword is set **ALL CAPS** inside otherwise sentence-case
  copy.
- Nothing occupies the top band between these two. Measured: title-blue present
  for 10.6 s of 81.9 s; absent for 72.9 s.

---

## 4. Captions

- **Every word is boxed, in spoken order, one at a time.** Not keyword
  selection. Verified 89/89 words in one window, 67 runs in another.
- Box `#2752E5`, radius 7–15 px, h-padding 15–18 px, opaque.
- Text `#FFFFFF`, heavy grotesque sans, cap height 37.5–45 px, size **52–64 px**
  (passes disagree; 52 px reads correctly at 1080 with a stroke).
- **Fixed y slot for the whole video.** Measured drift ±2 px over 82 s.
- Box **snaps** word to word — no slide, no tween. It **blanks for 1–2 frames**
  in inter-word gaps and holds through the trailing pause on a line's last word.
- Lines of 1–6 words (median 4), ~0.8–1.2 s each. Line change is a 1-frame swap.
- A full blank of **5–6 frames marks a sentence boundary**.
- Copy is **cleaned, not verbatim**: proper nouns capitalised, mumbles
  substituted, punctuation kept.
- Sync accuracy: median offset −0.013 s against word onsets, i.e. within a frame.

### The sentence-block rule

For each **sentence**, take the pixel width of its widest line `W`. Every line of
that sentence is drawn **left-aligned at `x = 540 − W/2`**, in the same y slot,
one line at a time. Only the longest line of a sentence is dead-centred; shorter
lines sit left of centre, by up to 215 px for a one-word line.

Verified on 11 sentences across two independent passes (predicted vs measured
left edge matched to ±1 px every time). A third pass, measuring only the
aggregate left-edge spread, recorded it as "left-aligned at a fixed margin" —
that is the same data read coarsely; the per-sentence rule *predicts* each value,
so it is the one to implement.

### A defect to fix, not copy

The caption layer renders **above** the opaque cards. White text with no stroke
on `#FAF7F8` means that during every card hold **only the boxed word is legible**
— 44–66 % of the card acts are a lone floating blue chip with ghost words either
side. Fix with a stroke on the caption text, a backplate, or by suppressing
captions during card holds. A stroke is the cheapest and keeps the karaoke.

---

## 5. Overlay vocabulary

**Found-footage rectangle.** Hard-edged, **square corners, no border, no
shadow**, 100 % opaque, **native aspect preserved** (4:3, 16:9 and 1:1 all
observed). Durations 1.1–2.9 s, clustering 2.0–2.9 s. Placed by eye, not to a
template. Video clips play with **audio muted**; stills do not pan or zoom.
Sources are recycled TV, film, home video and memes.

**Designed skeleton-UI card.** The signature asset — see §6.

**Raw prompt card on black.** A frozen, full-bleed monospace text dump on
`#13160E`, square corners, ink ~`#D7DAD2`, line-height ratio **1.60**.
**Content-sized, not a fixed frame** (observed 984x1119 at ~25 px type and
864x1044 at ~23 px type). Holds **1.5–1.6 s for ~200 words** — unreadable by
design. It is a screenshot cue and a proof-of-depth beat, not a read. Zero
animation: no typewriter, no scroll, no fade. Frame-to-frame NCC = 1.000.

**CTA banner.** See §3.

---

## 6. Designed card anatomy

### Shell (identical on every card)

| Property | Value @1080 |
|---|---|
| Rect | x 108–972, y 192–1728 (864x1536) |
| Fill | `#FAF7F8`, opaque |
| Corners | **square** (~3 px, at the antialias floor) |
| Border / shadow | **none** — background → card fill in 1 px, no halo |
| Inner gutter | x 158–922 (~50 px padding) |

Corner ramps are flat (`72,72,72,…` for 22 rows) and the outside luminance never
dips below the far-field value. Radius and shadow are both definitively absent.
**Rectangles are raw and square; only type highlights are rounded.** That
asymmetry is the whole look.

### Title
`THE <NOUN>` — **monospace Bold, ALL CAPS**, centred, ink band y 324–374, cap
height 51 px, advance 41.4 px, size ~69 px, colour `#272423`. Two-line titles
pitch at 74–76 px.

### Footer
The card's job in **plain lowercase monospace**, regular, centred,
**bottom-anchored** — last line ink always y 1617–1653, 75 px above the card
bottom; extra lines stack upward at 51 px pitch. Size ~39 px.

It is **not a caption of the narration** — it is a standing one-liner the viewer
can screenshot.

### The skeleton kit (the whole vocabulary — nothing else exists)
White sub-card (`#FEFEFE`, r 14, 1 px `#E5E5E5`, soft ~9 px / 6 % shadow) ·
grey pill (`#C0BFB4`, h 21, fully rounded, **deliberately uneven widths**) ·
checkbox (rounded square 40x40 or 55x57) · dashed empty slot · hairline ·
connector curve · artifact card (220x158, icon + pill).

**Zero real text lives inside the UI.** Every string is a grey bar, so the card
never competes with the caption for reading. This is load-bearing: it is why a
6 s card does not feel like homework.

### The three motion verbs, and one metronome
1. **Pop** — scale 94 % → 100 % over 3 frames, for anything appearing.
2. **Travel** — ease-in-out ~0.53 s falling, ease-out ~0.30 s rising, for things
   moving between containers.
3. **Flip** — a 2-frame colour swap, for state changes.
4. **The scan rule** — a full-panel-width hairline sweeping **linearly at
   466 px/s**, with each checklist row resolving the instant the rule crosses it.
   One animated rect that makes a checklist appear to run itself. The single most
   copyable trick in the style.

Interior beats run at **~1 beat / 0.43 s**, pinned to content words — with two
deliberate exceptions: a card depicting a *loop* ran its interior on a fixed
1.100 s period, deliberately unsynced, to read as "this repeats forever"; and a
diagram card built on a flat ~0.30 s cadence whose node names deliberately did
**not** line up with the spoken words.

---

## 7. Cadence and sync

- 17 overlay instances in 82 s = **55.9 % coverage**; mean instance 2.69 s.
- Two length classes: designed cards **2.5–6.0 s**, reaction inserts
  **1.1–1.7 s**, prompt cards **1.5–1.6 s**.
- Gaps 0.0–1.9 s typical, with deliberate breathers of **2.8, 3.3, 3.7 s** —
  every long gap lands on a pivot line, handing the frame back exactly where the
  argument turns. That is a rule, not an accident.
- At least one **butt-cut with zero clean frames** between two overlays.

**Sync rule:** every in/out lands within **±0.20 s of a word boundary** (median
|Δ| = 0.07 s = 2 frames), and the content word being spoken **names** the
overlay. Never on a function word.

**The CTA exception:** the banner cuts on at the **first CTA verb of the outro**
and leads its own keyword by **3.34 s**, then holds to the final frame. The rule
is *put the comment-bait up on the first CTA verb and never take it down* — not
*reveal on the keyword*.

**The ending:** no end card, no logo, no handle, no fade, no freeze. It stops on
a live frame with the CTA still up. That is what makes the loop-back seamless.

---

## 8. Sound

**There is none, and that is the finding.**

| Spec | Value |
|---|---|
| Music bed | **none** — gap floor varies 20.5 dB across 35 pauses; a bed pins it to 2–3 dB. The p10-over-time spectrum reads −122.8 dB at 6–16 kHz, i.e. digital silence |
| SFX | **none on any overlay event**. Seven overlays pop into near-silence; the 12 loudest HF moments are all `/s/` consonants, none within 0.16 s of a cut |
| Integrated loudness | **−14.8 LUFS** |
| True peak | **−0.60 dBTP**, zero clipped samples |
| Loudness range | 4.30 LU |
| Mix | mono (Side/Mid −24.6 dB, L/R r = 0.993) |
| Voice chain | HPF ~80–90 Hz + gentle compression to a **12.87 dB** speech spread. **No gate, no de-reverb, no noise suppression** — gap floor is independent of voice level (slope +0.09 dB/dB) |
| Room | dry — −20 dB in 30–105 ms, no audible tail |
| Silence retained | **15.3 %** — 35 gaps, median **0.324 s**, max 0.743 s, breaths audible in 20 of 34 |
| Speech rate | **252 WPM**, flat (σ ~15 WPM across eight 10 s windows) |

The room tone is continuous across every gap (mean step 3.33 dB, **every step
negative** = natural decay, never a positive splice step). Neither stream is cut.

**Budget zero for audio assets.** Resist adding a bed "because short-form has
one" — this style measurably does not.

---

## 9. Why it works (falsifiable)

1. **The uncut take is the spine.** Zero camera cuts means the viewer never gets
   a new-shot reset; the only thing that changes is information.
2. **Pace lives in the overlay layer.** A quarter of every minute is silence, yet
   it reads relentless, because something changes on screen every ~2.5 s.
3. **Nouns are made physical.** A card cuts in on the exact word it depicts, so
   the graphic is the definition of the word just spoken, never decoration.
4. **Empty skeletons outrun real text.** Grey bars carry the shape of a system in
   3 seconds without asking anyone to read.
5. **The breathers are placed.** Each long clean stretch lands on a pivot line.

---

## 10. What the evidence could not settle

- Exact typefaces. The three classes are proven by glyph metrics; family
  identification is not reliable at 720p H.264.
- Nominal pre-codec colour of the black prompt card (measured `#13160E`; the
  green cast is almost certainly 4:2:0 chroma on an intended neutral).
- Whether the white-on-white caption over cards is intentional.
- Caption font size: two passes said ~52 px @1080, one said ~64 px.
- Whether a card's interior element "pops" in ≤4 frames or is codec refinement
  on fine light-grey line art. The *container* is unambiguously 1 frame.
