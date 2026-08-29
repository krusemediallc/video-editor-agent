---
name: video-edit-pipeline
description: >
  MASTER orchestration skill for producing a finished short-form video from raw
  talking-head footage. Use for ANY request to edit, produce, recut, or "make an
  ad/reel out of" talking-head footage — with or without a style reference —
  including "edit this video", "edit this like <reference reel>", "turn this
  clip into a finished reel", "do the full edit", "make this look like their
  winning ads", or a revision request on a previously delivered edit. It routes
  every stage to the right specialist skill (reel-style-clone, branded-ad-edit,
  sound-design, video-qa, video-review-canvas, edl-tighten, capcut-export) and
  owns the intake → style → edit → QA → deliver → revise loop end to end. Do
  NOT use for plain captions on untouched footage or single generated clips.
---

# video-edit-pipeline — master orchestration

You are running the proven end-to-end pipeline that turns raw talking-head
footage into a finished, reviewed, shipped short-form video. This skill does
not do the editing itself — it sequences the specialist skills and enforces
the working culture that made past edits ship: **verify pixels and dB, not
intentions.**

## The pipeline at a glance

```
(0) Intake ─→ (1) reel-style-clone? ─→ (2) branded-ad-edit build
                                              │
                        (3) sound-design ─────┤
                                              ▼
                    (4) QA loop (video-qa) → render → verify MP4
                                              ▼
                    (5) Deliver on video-review-canvas (URL first)
                                              ▼
                    (6) Revision rounds (notes → evidence → fix → new file)
                                              ▼
                    (7) Optional capcut-export handoff
```

Work the stages in order. Skipping a stage is allowed only when the user
explicitly says so (e.g. "no sound design", "just render, no review page").

---

## Stage 0 — Intake

Collect before anything else:

1. **Footage** — path(s) to the raw talking-head file(s). Expect them in
   `footage/`. Run `ffprobe` on every file immediately: resolution, fps,
   duration, audio channels. Do not assume; probe.
2. **Optional reference reel** — a file or URL of an edit whose style should
   be cloned. If present, Stage 1 is mandatory.
3. **Brand / site** — brand name, website URL, logo, palette if known. Check
   `MASTER_CONTEXT.md` at repo root first; it may already have palette, fonts,
   voice, and defaults. Ask only for what is missing and load-bearing.
4. **Target ratio** — default 9:16 unless the user or MASTER_CONTEXT.md says
   otherwise. Confirm ratio before storyboarding; a ratio change late in the
   build invalidates every crop and card position.

Create a working directory per project (e.g. `outputs/<project-slug>/`) and
keep every intermediate there.

## Stage 1 — Style clone (only if a reference exists)

Invoke **reel-style-clone** on the reference reel. Its job: reverse-engineer
the reference frame by frame into a `STYLE-GUIDE.md` (pacing, framing grammar,
caption treatment, card style, color, sound character) plus concrete build
directives.

- The style guide is the contract for Stage 2. The storyboard must cite it.
- If no reference exists, skip to Stage 2 and use the house defaults from
  `MASTER_CONTEXT.md` plus branded-ad-edit's own framing grammar.

## Stage 2 — The build (branded-ad-edit)

Invoke **branded-ad-edit** and run its phases in order:

1. **Ingest + crops.** Produce **two crop candidates** for the talking head:
   - a straight zoom crop, and
   - the **blur-pad band trick** when the source is framed too tight to fill
     the target ratio (scale a blurred copy of the frame to full-bleed behind
     a fitted foreground copy, so the "bands" are blurred footage, not black).
   **Lesson from production:** reviewers often prefer the plain zoom crop over
   the clever blur-pad version. Always render a frame of BOTH and show both
   before committing the composition to one. Do not silently pick the fancy
   one.
2. **Transcribe** with whisper-cli (word timestamps). The transcript drives
   captions, card-per-line timing, and the storyboard beats.
3. **Storyboard from the style guide.** Every spoken line maps to a beat:
   card, full-bleed cut, B-roll (capture real screenshots/recordings with the `broll-capture` skill), or breather — per `STYLE-GUIDE.md` (or house
   defaults). Write the storyboard down before composing; it is the artifact
   the user approves.
4. **Compose.** Hand-authored composition (framing, cards, cuts, motion) +
   generated word-synced karaoke captions + SFX/bed placement markers.
   HyperFrames is the render engine (`npx hyperframes`, and make sure
   `npx hyperframes skills update talking-head-recut` has been run for
   fonts/gsap).

## Stage 3 — Sound design

Invoke **sound-design** to produce the audio kit:

- SFX for the composition's markers (whooshes, pops, hits — generated via
  ElevenLabs, `ELEVENLABS_API_KEY` from `.env`).
- A low music bed, style-matched to the reference track if Stage 1 captured
  one.
- Use the skill's mixing math for levels (bed well under the voice) and its
  audit pass to confirm every placed SFX actually exists and lands on its
  marker.

## Stage 4 — QA loop, then render, then verify

This is a loop, not a checklist. Order matters:

1. **hyperframes check** — must pass clean.
2. **ONE multi-timestamp snapshot** — capture a single batch of frames across
   the whole timeline (hook, each card, each cut, captions mid-word, outro).
   One batch, many timestamps; do not snapshot one frame at a time.
3. **LOOK at the snapshots with vision.** Actually inspect every frame:
   overlaps, cut-off text, wrong colors, captions colliding with cards, crop
   drift. Optional deeper pass: video-qa's Gemini-based layer
   (`GEMINI_API_KEY`) if configured.
4. **Fix → re-check → re-snapshot** until the frames are clean.
5. **Render** the MP4.
6. **Verify the rendered MP4 with video-qa** (its 4-layer procedure). The
   composition preview passing is NOT evidence the render is right — fonts,
   media, and audio can differ in the rendered file. Probe duration, spot-check
   frames extracted from the MP4 itself, and check audio levels in dB on the
   rendered file.

Nothing ships that hasn't been verified as rendered pixels and measured audio.

## Stage 5 — Deliver

Invoke **video-review-canvas** to publish the video to a here.now review page
(frame-accurate scrubber + timeline comments). Then reply to the user and
**LEAD with the canvas URL** — first line of the reply, before any summary of
what was done. Reviewers click the link; they do not read the recap first.

## Stage 6 — Revision rounds

When the reviewer leaves notes (or the user relays them):

1. **Read the notes back** via video-review-canvas (it can pull timeline
   comments per version). Enumerate every note; none get silently dropped.
2. **Screenshot the exact frame each note points at BEFORE fixing anything.**
   A note like "the card at 0:07 overlaps the face" gets a frame grab at 0:07
   from the current rendered file first — so you fix what the reviewer
   actually saw, not what you assume they meant.
3. Fix. For pacing notes ("tighten this", "drags here", "cut the dead air"),
   invoke **edl-tighten** — surgical silence/pacing cuts with a full timeline
   remap so captions, cards, and SFX stay synced.
4. Re-run Stage 4 in full (QA → render → verify) on the new cut.
5. **Per-note QA table** — before delivering the revision, produce a table:
   one row per reviewer note, with the note, what changed, and the **evidence
   in the RENDERED file** (frame grab timestamp, measured dB, probed duration
   delta). "Fixed" without evidence is not a row.
6. **New versions are NEW files** (`v2.mp4`, `v3.mp4`, …). Never overwrite a
   delivered file — the reviewer's timeline comments are anchored to it.
7. **Republish to the same slug** so the review URL stays stable; the canvas
   tracks versions.

Repeat until sign-off. Production edits have taken 4+ rounds; that is normal,
not failure.

## Stage 7 — Optional CapCut handoff

If a human editor wants a final manual pass, invoke **capcut-export** to
export the layered composition into a CapCut draft (pyJianYingDraft venv).
Note honestly: this exporter is documented as work-in-progress — verify the
draft opens before telling the user it is ready.

---

## Routing table

| Need | Skill |
|---|---|
| Reverse-engineer a reference reel | reel-style-clone |
| The main build (crops, storyboard, cards, captions) | branded-ad-edit |
| SFX kit + music bed + mix levels | sound-design |
| 4-layer QA on comps and rendered MP4s | video-qa |
| Publish for review, read notes back | video-review-canvas |
| Silence/pacing cuts with timeline remap | edl-tighten |
| Spec-driven short-form recut style | reel-recut |
| Layered export to a CapCut draft | capcut-export |

## Culture rules (apply at every stage)

- **Verify pixels and dB, not intentions.** A change is done when the rendered
  file shows it, not when the code contains it.
- Probe media with ffprobe before reasoning about it.
- One batched snapshot beats twenty single-frame grabs.
- Show competing options (crops especially) as images, not descriptions.
- Every reviewer note gets evidence, every version gets a new file, every
  delivery leads with the review URL.
