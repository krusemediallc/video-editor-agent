# Gotchas — every entry cost a render, a snapshot round, or a review round

Skim before starting. Return whenever a frame or a number looks wrong.

## Base cut

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | First render 169s instead of 139s; five split segments overrun | ReplayKit screen captures are VFR; input `-ss`/`-t` seek the wrong window | window everything in-filter: `fps=30,trim=start:end,setpts=PTS-STARTPTS` |
| 2 | A cut "lands inside a word" per Whisper, but the audio is silence | Whisper stretches a word's span into the pause after it | `qa/silent_gap.py` pre-check (loudest frame 24 dB under p95 = no word); then A/B transcription |
| 3 | Bad cuts come back after a fix | `verify_cuts.ts` wrote a fresh (empty) veto list; a vetoed gap stops being a cut | the veto list is additive across runs |
| 4 | A 2.5s dead zone survives two rebuilds | `protect` ranges did not move when `in`/`out` moved | move `protect` whenever `in`/`out` moves |
| 5 | 29 silent gaps and 0.23s of drift by the CTA | per-segment AAC (21.3ms frames) vs video (33.3ms) quantisation | build the whole audio in one pass to measured frame counts |
| 6 | A 0.7s clip amplified +14 dB carries no word | 99.9% of its energy under 300 Hz — a desk thump, not a quiet "Pixar" | check the spectrum before trusting a large gain override |
| 7 | Single-pass loudnorm lands at −17.3 against −14 | linear mode needs the measured values | two-pass: measure, then apply with `measured_*` + `linear=true` |
| 8 | 35s of a frozen screen half | the example in the player was paused during the take | measure liveness inside the segment's rect (`qa/screen_offsets.py`) and set `screenOffset`/`screenTake` |
| 9 | Heads decapitated on example ads | the crop was measured at one moment of a clip that reframes | measure the rect against several moments |
| 10 | The last word's consonant is cut ("ove-") | the keep ended before the tail decayed | extend the keep by the decay (5.285 → 5.40); rebuild the base |
| 11 | A moderation-rejection card, a browser tab, a MUTE icon on the seam | crop rects that included UI chrome | re-crop; a frame-by-frame agent pass with skeptics finds these |
| 12 | The creator's breath marks at −25…−33 dB were being kept | threshold `p95−22` too loose | `p95−18`; the creator's marks are the calibration |
| 13 | Picture-only split mid-word notches the audio | the anti-click fades at every segment seam | `joinPrev` on the second half (build.py asserts contiguity and whole-frame length); the audio came out bit-identical |

## Graphics pass

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 14 | Every hanging chip, the credits, checklist, strip, rail and end card missing from the first render | `fromTo` with `opacity` only in the FROM vars tweens it back to the CSS value 0 | put `opacity:1` in the TO vars of every entrance |
| 15 | The top-right corner of every frame clipped by a curve | the resting `#vclip` circle (1400px at 250,1608) misses (1080,0) at 1810px | 2200px |
| 16 | The creator vanishes behind the hook's ink field | the field was z38, above `#vclip` z35 | fields below the video wrapper |
| 17 | "WIWITHOUT" — doubled glyphs on extruded type | absolute copies left-align while the block centres; padding on the block offsets them further | copies `width:100%`; size the block with `width`, never padding |
| 18 | The hero video layer blacks out the wall on the pull-back | `.tk` background is opaque ink | `background:transparent` on layers that must show what is under them |
| 19 | Black frames mid-whip | hero video windows ended exactly at the cut | `data-duration = slot + 0.3` |
| 20 | The base cut is visible for two frames under the mosaic | the cover started at the cut, not before it | blinds at 0.14s strips / 0.015s stagger starting 0.25s before the cut |
| 21 | EVERYTHING slams at 63.6; the CTA chip types at 69s | `W("everything",1)` and `W("ads",3)` resolved to other shots | scope word lookups to the shot: `WS(sid, word)` |
| 22 | A cream hero invisible; a border invisible | cream on a cream plate, cream stroke on a cream box | `.plate.cream .hero{color:ink}`; ink strokes on cream |
| 23 | Two style names overlap for four frames on every tick (Gemini: 3 medium) | a clip-wipe roll hides and reveals from the same edge | translate roll inside an overflow-hidden slot |
| 24 | `data-duration="NaN"` on every caption, then "601 samples" of overlap | chunk ends read the next chunk's start before it was assigned | two passes: all starts, then ends |
| 25 | `gsap_exit_missing_hard_kill` on 60 captions | an exit fade + hard kill straddling another clip's start | captions have no exit tween (the window ends them); cards snap `out` back off any boundary |
| 26 | A real card-on-card collision passed the audit | `data-layout-allow-overlap` on a container suppresses its children | put it only on tight-leading `.ln` children and extrusion copies |
| 27 | A blank white plate on screen for 1.6s | a list wiped in before its first row's word | start lists on the first row's time |
| 28 | The quote plate shows glyphs and no text | only the extrusion copies were animated | reveal the line itself (`RISEW`) |
| 29 | `pop.mp3` is 0.48s of silence, three generations in a row | ElevenLabs puts the transient at the end for that prompt | derive it from the good click (`asetrate` ×1.55, 0.3s) |
| 30 | A 10s hole in the music bed | a bed generated at 68s fades out at 58s | prompt "energy stays constant, never fades out"; verify the RMS arc per 2s |
| 31 | The bed is inaudible on a phone | the by-the-book −18 dB-under level | `data-volume` 0.24 (~13 dB under); opening +11 dB limited after the creator's note; +12 clipped the MP3 |
| 32 | The renderer's frames freeze on seek | sparse GOP on any media | re-encode everything `-g 30 -keyint_min 30`; 56 clip proxies + 9 half-res for the wall |
| 33 | Two renders die at 10 minutes; a third dies at 2237/2802 frames | the foreground shell's timeout and a wait loop's `pkill` | render as a tracked background job; `setopt +o nomatch` before any glob in zsh |
| 34 | True peak −0.7 dBTP after the hotter bed | AAC overshoot past the limiter | loudnorm TP −2.0 + limiter 0.79; QA flags anything above −1.0 |
| 35 | The prompt card shows "; the creator." and "unclutte." | the pipeline's template truncates shot lines | stream the clean head (5 lines) verbatim |
| 36 | "Omni 1.1" typeset in the brand's ad | the creator's phrase, no receipt | OmniHuman 1.5 per Arcads' help center — typeset what the product documents |

## Working style that made it work

- **Look at pixels, measure dB.** Every bug above was found in a snapshot, a frame grab, a
  waveform or a probe — none by re-reading code. Four snapshot rounds before the first render.
- **Generate the repetitive 90 %.** Captions, SFX elements, placement, the hit table all come
  from the transcript and the EDL; hand-author only the beats.
- **Verify pixels against measurements, not intentions:** face points, popup rectangles, crop
  scales, word onsets.
- **Ask once, then run.** The creator wants a reviewable draft, not a spec.
- **Deliver drafts as new files on the same canvas slug, lead with the URL, answer every note.**
