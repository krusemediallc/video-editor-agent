# Phase 3 — rebuilding N hooks onto one locked body

When a client asks for hook-level changes after the body is signed off, the body must not move: it is
stream-copied bit-identical into every deliverable, and only the hooks are re-cut and re-rendered. This is
the lane where a fan-out pays: on the proving run, twenty subagents each rebuilt one hook overnight.

## The material problem

Hooks split out of a long screen recording are **burnt-in composites**: one video stream with the speaker's
webcam already baked in as a circle near the bottom-centre. There is no separate camera file, so the usual
match-move has nothing to move. Treat the composite itself as a camera subject:

- **One `#cam` wrapper**, `transform-origin: 0 0`, driven by named crops `{x, y, w}` in source pixels;
  height is `w*16/9`; `scale = 1080/w`, `x = -x*scale`, `y = -y*scale`. Eased tweens between crops are the
  "smooth zoom" a client means when they say "zoom in so we can read it".
- **The bubble is the composite's own circle**, cut with `clip-path: circle(mask_r at cx cy)` on a second
  copy of the same video and translated to the new position. `mask_r = r - 8` so no rim of the original
  circle survives.
- **Every crop is asserted to end above the burnt-in circle** (`y + w*16/9 <= circle.cy - circle.r + 2`).
  That ceiling, not taste, caps how tight the framing can go — typically ~730px of a 1080 source, so a
  full-bleed 9:16 ad inside the recording gets cropped ~8% per side. Say so rather than pretending it fits.
- Measure the circle **per hook** from motion (the webcam moves, the UI does not), even when every hook comes
  from one session. Twenty independent measurements agreed within 1px, and the one that did not would have
  been the one that shipped a rim.

## Per-hook config, one generator

One `hook.json` per hook (circle, crops, beats, the trim, the product) and one generator for all of them.
Every hook differs: some open the app's own full-size reference preview (a synthetic product card would then
show the product twice — omit it), some hover reference *images* whose preview jumps position per thumbnail
(a fixed popup crop misframes it — omit the zoom). On the proving run 15 of 21 carried a product card and
11 of 21 a popup zoom. Make both optional in the generator rather than forcing every hook into one shape.

## Trimming the example without cutting speech

The client's note is usually "the example is too long". The rule that survives review:

- Trim **only** inside the ad-playback region; never the speaker's own words. Re-transcribe the cut file and
  diff the word list against the source — that is the proof, not a waveform glance.
- Land the out-point on the **generated ad's own shot change** where one exists; the join then reads as the
  ad's cut rather than an edit.
- Keep the beat where the product is worn, held or poured. A shorter example that loses that beat fails the
  note it was meant to satisfy.
- Some ads have wall-to-wall voiceover with no window big enough. Land at 9–9.6s and say why, rather than
  clipping a word to hit a number.

## Four traps that each shipped once before being asserted

| Trap | Symptom | Assertion |
|---|---|---|
| Pull-back overruns the cut | the whole example plays as a slow zoom-out from the popup crop | `popupOut <= cut - (pullback duration + 0.006)` |
| Duration at/above `frames/fps` | the render comes back exactly one frame long | truncate `duration` to a frame boundary before rendering |
| Card placement | the product card lands under the title or over the face bubble | assert against the pill band, the bubble box and the bottom safe line |
| A tag left in the platform's bottom zone | invisible on the platform, and it was in the *approved* hook | assert every text node inside the safe band |

The last one matters most: it shipped in the hook the client approved, and only surfaced because six agents
looked at the same layout independently. **A fan-out is a review panel, not just a throughput trick** —
collect the cross-cutting complaints and fix them centrally, then rebuild every comp.

## Orchestration

- Give each agent a written brief on disk, not a prompt: paths, the measurement recipe, the exact re-encode
  command, the config schema, the constraints, and "do not render". Correct the brief for later waves when
  early ones report a path or an assumption wrong.
- Waves of five, paced against machine load. Agents run ffmpeg and headless-browser snapshots; render time
  per hook tracks the load average almost linearly.
- **The orchestrator renders**, with bounded concurrency, so twenty browsers never compete. Agents stop at
  snapshot-and-look.
- Expect one agent to stall. Budget for finishing one by hand.
- Joining: hook loudness lift is commonly +13 to +17 dB, and the hooks needing the most lift overshoot true
  peak at the default limiter ceiling even though every other check passes. Verify true peak per file and
  rebuild the hot ones a couple of dB lower; do not lower it globally and squash the rest.
- Never let a positional index name a deliverable. Parse the hook number from its source filename, or one
  missing hook silently renumbers the whole set.
