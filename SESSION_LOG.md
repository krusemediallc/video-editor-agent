# SESSION LOG — Video Editor Agent

## 2026-09-17 — Fifth round on the 3:00 organic edit: a censor bleep is placed from the waveform, not from any transcript

The bleep lesson written earlier today (place it from an isolated slice) failed the reviewer the
same way again: whisper large-v3 put the swear 100–150 ms early on the full file and on three
isolated slices alike, and the leading /f/ was almost silent, so a tone timed from a transcript
ended on the vowel. A 5 ms band-energy map (total, <1 k, 1–3 k, 3–6 k, 6–8 k) reads the phonemes
directly — vowel = loud low band, stop closure = fall to the floor, /t/ release = high-band burst —
and the window runs from the end of the previous vowel to the next word's burst. reel-recut's
paragraph is rewritten to say so. Also: a shared element's exit tween from one window overran the
next window's entrance (the takeover backdrop was invisible under the brand wall for a whole round);
the "key off the next window's start" rule in video-edit-pipeline now names shared elements.

## 2026-09-17 — Fourth round on the 3:00 organic edit: two more generic lessons

A range replace between two section comments in a generated composition deleted a third block that
sat between them; `hyperframes check` passed and the render was clean, the overlay was simply
absent until the frame sheet was read against the storyboard. video-edit-pipeline Stage 6 now says:
patch by unique markers, then grep the generated page for every element id the storyboard names,
and read the sheet for what should be there, not only for defects. Same round: two overlay windows
150 ms apart let the first one's banner re-show land inside the second — key exits and re-shows
off the next window's start. reel-recut's long-take traps gained the censor-bleep twin of the
transcript-drift trap (bleep 350 ms early from the full-file pass; the slice emitted "fuck-ton" as
one token, so match by prefix).

## 2026-09-17 — "Glitchy" meant the seams: measure clicks, declick in one graph, cut both streams from one grid

A reviewer's "super glitchy, skips around" on a 116-cut organic reel was neither the render nor the
bitrate (both measured first). It was the butt-joins: 47 of 116 seams jumped >0.05 full-scale.
Whisper-based seam QA cannot hear a click. Fixed by building the audio in one filter graph with
per-span fades and cutting the video frame-exact against the source's real frame grid; the two
streams now agree to the sample. Two wrong turns are recorded in reel-recut's new section so they
are not repeated: per-segment encodes + stream-copy concat (AAC padding stalls every seam), and
cutting audio and video with different rounding (drift). video-review-canvas gained "cap the
review encode" (a 21 Mbps peak stutters on a phone even when the file is perfect).

## 2026-09-17 — Revision round on the 3:00 organic edit: two generic lessons

Working-repo project; details in that repo's log. Kept here as process:

- **Many concurrent `<video>` players break caption clip-gating in the renderer** — ~30 players
  stacked every past caption; 5 did not. Pre-composite walls into one video (ffmpeg `xstack`).
  Added to video-edit-pipeline's culture rules.
- **Never index a list you have sorted** — takeover blocks read `TK[2]`/`TK[3]` after the list
  was sorted by time; a grep of the generated timeline (exit scheduled before entrance) caught it
  before render. Look up by id.
- Public-profile listing via `yt-dlp --flat-playlist` (dates + view counts, no login) is a reliable
  source of a creator's own back catalogue when the platform's grid page refuses automation.

## 2026-09-17 — A 4:18 → 3:00 organic edit exercised reel-recut and broll-capture at length

Working-repo project (the retrospective reel); details and the canvas in that repo's log. Generic
lessons folded into the skills:

- **reel-recut**: `build_reel.py` cannot render past ~120 keep spans (ffmpeg expression parser
  limit) — recovered via the concat demuxer from the manifest's cut events. The manifest's
  remapped words drop edge words; the render's own fresh transcription is the word map. Manual-cut
  edges must come from isolated source slices, not the full-file pass; six of six edges were wrong
  from the full file and exact from slices. Each is now a gotcha in the skill.
- **broll-capture**: tsx's `__name` helper breaks `page.evaluate(fn)` (pass strings); TikTok's
  grid never renders for automation; Instagram's grid scroll is an inner container (static take);
  frame-tiling every take caught both.
- **Composition**: a keep-callouts-apart rule must sort callouts by their word time first — the
  script order is not the list order ("superpower" precedes "focused"), and an unsorted rule
  scheduled a callout's exit before its entrance so it never left. Measure chin position through
  every callout window with face landmarks on the RENDER; v1 clipped the chin on 8 of 14.
- Follow-up: make `build_reel.py` render via the concat demuxer itself (task chip filed).

## 2026-09-16 — Recap Video skill from a completed event edit

**Goal:** Turn the complete production and revision workflow of an event recap
into a reusable skill in this pack.

**Done:** Added `recap-video` with reference forensics, B-roll cataloging,
per-line multi-take selection, disfluency-aware editing, split/full composition,
source-anchored revisions, SDR/HLG handling, measured sound finishing and QA
adjudication. Added a portable Python assembler with versioned EDLs/word maps,
explicit veto/raw ranges, exact frame/sample trims and protected outputs. Wired
the lane into `video-edit-pipeline`, ARCHITECTURE and the README catalog.

**Decisions:** Use final implementation and reviewer corrections ahead of
superseded reference directives. Treat crop coordinates, colors, music gain and
montage counts as adaptable settings. Preserve approved substantive copy and
require actual clearance for restricted slide content. Keep source media,
private session history and client details outside this public pack.

**Validation:** Skill frontmatter, UI metadata and reference links pass. An
independent scenario review checked multi-take selection, restricted slides,
quiet tails, partial repeats and revisions; its approved-ending clarification
was applied. Assembler synthetic tests pass at 30 fps / 44.1 and 48 kHz, including
cross-rate resampling, exact frames/PCM samples, rendered reorder pixels, repeated
source word occurrences, overlap/veto/raw behavior and overwrite refusal. The
original edit's inputs also pass planning in an isolated temporary project;
no source media was modified. Independent code review found the existing QA
adapter's forward-source-order and fixed-geometry assumptions; the skill now
requires an occurrence-based seam audit for reordered/reused takes and avoids
the generic chronological pacing helper on recap revisions.

**Failed / why:** The system Python lacked PyYAML for the skill validator; used
an isolated temporary validation environment. No runtime dependency was added
to the assembler.

**Current state at a glance:** Recap Video is implemented, validated and linked
into the pipeline. Repository changes are scoped to this skill and its catalog,
route and documentation. Remote publication is separate from this local addition.
**Next:** Use `recap-video` on the next event recap; retain the documented QA
adapter limitation until per-occurrence boundary support is implemented.

## 2026-09-16 — New skill: `talking-head-image-overlays`, deconstructed from a reference reel and proven on unrelated footage

A creator-supplied reference reel (82 s, 720x1280) was taken apart by measurement, the style was
rebuilt on a completely different talking-head video, and the result became a new skill. Five
forensic passes ran in parallel over ffmpeg evidence (2 fps contact sheets, full-res before/after
pairs at every detected change, spectrogram + waveform + word-level transcript), then three
adversarial checks.

**The headline: the reference has ZERO camera cuts.** One continuous 82 s take; every visual
change is a composite. Scene detection returning nothing was the finding, not a failure — the
lesson is now in `method.md` §1, along with the fact that the events list built that way missed
6 of 34 container transitions.

**What the measurement overturned.** The naive read (a persistent serif title, overlays that
never touch the face) was wrong on both counts. The serif appears exactly twice — an opening
plate 0.000–2.533 s and a CTA banner from 75.400 s to the final frame — with a bare top band for
the 73 s between. The designed cards are opaque 80%x80% takeovers that bury the speaker for ~35%
of the runtime, and two image rects cut straight through his eyebrows: **the reference has no
face-avoidance logic at all.**

**Two measured rules worth keeping.** Captions are not centred per line — each *sentence* is a
block centred on its widest line with every line left-aligned to that edge (verified on 11
sentences, predicted-vs-measured left edge within 1 px). And the CTA banner leads its own keyword
by 3.34 s: it lands on the first CTA verb of the outro and never leaves.

**The audio finding was the most surprising: there is no sound design at all.** No music bed (gap
floor varies 20.5 dB across 35 pauses; a bed pins it to 2–3 dB) and zero SFX on any of the 28
overlay events — seven overlays pop into near-digital silence. −14.8 LUFS, −0.6 dBTP, and 15.3%
of runtime retained as pauses with breaths left in.

**Proving it on other footage surfaced what the deconstruction could not.** The test video's base
cut had been silence-cut to *zero* air, the exact inverse of the style, so a new base was built by
capping each pause at 0.25 s rather than removing it (44.8% silence → 12.5%, 88.6 s → 57.4 s).
Four renders to solid:

1. **v1** — a guessed face floor of 402 px squeezed portrait inserts to a 163 px sliver.
   Measuring the real thing over 57 frames gave min eye line 704 → floor 680, a 278 px error.
   That measurement is now `scripts/measure-face-band.py`.
2. **v2** — the pill overflowed its fixed box and the CTA ran off frame; both auto-size now.
3. **v3** — a narrow insert bottom-anchored to the eye floor landed on the subject's cap and read
   as a hat. Hence two floors: wide sources may reach `EYE_FLOOR`, narrow ones must clear
   `HEAD_FLOOR`. The reference never hit this because its inserts were all landscape.
4. **v4** — captions still ran off frame because widths were measured before the webfonts
   loaded. Gating on `document.fonts.ready` fixed it. This bug survived two full renders and is
   now a named trap.

Mastering to −14.5 LUFS took the QA engine from PASS_WITH_WARNINGS to PASS, and hit the repo's
own logged zsh trap (`$M:linear` → `Invalid chars 'inear=true'`) on the way.

**Skills touched.** New `talking-head-image-overlays/` (SKILL.md, `references/style-system.md`,
`references/method.md`, `scripts/measure-face-band.py`). `video-edit-pipeline` gained the lane in
its routing table, its Stage-0 lane list and its description. ARCHITECTURE.md updated.

**Follow-up the same session — the measurement script was wrong and got replaced.** An
independent pass using Apple's Vision framework on all 1722 frames (not a 1 fps sample)
validated the eye floor (708.7 vs my 704) but broke the head floor: true min cap top was 452,
not the 528 a 1 fps luminance grid reported. The delivered render is unaffected — its two narrow
inserts run 10.0-15.6 s where the cap floors at 560 and 548, so a bottom edge of 520 clears by
28-40 px, verified per-window — but the RULE as first coded was unsafe on any take whose
highest-head transient falls inside an insert.

Two attempts to patch the heuristic both failed loudly, which is the useful part: taking the
first dark row from the top grabbed a framed print on the wall (124 px too high), and anchoring
on "densest dark row" grabbed a black t-shirt. `scripts/face-landmarks.swift` (Vision, compiled
on demand) is now the primary measurer, with the luminance path kept only as a gated fallback.
The gate is a rigid-head invariant: `(eye-cap)/(chin-cap)` must be near-constant for one person,
so a high CV proves the segmenter measured something that is not a head. Vision scores 3.4 % on
this footage; the two heuristics scored 9.3 % and 50.5 % and are correctly refused.

**Lessons kept (generic):** (1) a validation invariant that is independent of the thing being
measured catches silent failure that eyeballing three frames does not; (2) the binding constraint
in a talking-head take is almost always a sub-second transient at record start or stop, so a 1 fps
grid is not a measurement; (3) flooring each insert over its own window rather than the whole take
buys back real height, here ~100 px.

**Lesson kept (generic):** *a style's geometry is two different things.* Card geometry was rigid
to the pixel across seven instances and transfers verbatim; the image band was never fixed and
must be re-derived from each subject's own eye line. Copying the second kind is how a clone ends
up with a 163 px sliver, or a graphic hat.

## 2026-09-02 — This pack becomes the only home for video editing; the working repo symlinks in

**Decision (the user):** every video-editing skill, script and process lives here, and only
here. The private working repo keeps the videos (its `Videos/<project>/` folders, organised as
before) and exposes this pack's skills through relative symlinks (`.claude/skills/<name> →
../../../../Video Editor Agent/.claude/skills/<name>`, a `link-video-editor-skills.sh` helper
there re-links new skills). Improvements from real edits are written here as generic process;
the personal layer (brand, machine paths, reviewer habits, clients, fees) lives in the gitignored
`MASTER_CONTEXT.md`. **Flipped public later the same day** (see below).

**Done**
- **Merged** the working repo's newer `branded-ad-edit` content into this copy: the automated
  4-layer QA step (with mastering + the SFX-only audit), canvas delivery via
  `video-review-canvas`, and gotchas 21–30 (empty card hosts, SFX-only render, kit scaling,
  narrow-viewport captures, PNG scroll b-roll, true-peak mastering…). `reel-recut` and
  `video-review-canvas` here were already generic supersets; the user-specific values they
  had dropped (accent colour, fonts, canvas eyebrow/author) now live in MASTER_CONTEXT.
- **Moved in three skills**, genericized: `hook-splitter` (one long composite → N hooks),
  `arcads-video-edit` (multi-take demo → EDL base cut → graphics pass; absolute paths →
  `GEN`/`OUT`/`PROJECT_DIR` env, workspace ids → `ARCADS_PRODUCT_ID`/`ARCADS_PROJECT_ID`, the
  reviewer's name and pronouns → "the creator / the reviewer", the internal copy-review bot →
  "a copy review"), `ai-audio-sound-design` (AI-actor ambience/reverb/bleeps).
- **Ported the QA engine** as `tools/video-qa` — a standalone node package (tsx, zod, dotenv)
  with its own `package.json`, `cli/qa-video.ts` + `cli/inspect-video.ts`, and `src/env.ts`
  (reads `.env` from the invoking directory up to root, then this pack; resolves CLI paths
  against `INIT_CWD` so `npm --prefix … run qa:video` works from any working repo).
  `openai-transcribe.ts` replaces the working repo's shared OpenAI service; the layer cache
  moved under the engine dir. **Verified:** typecheck clean, 14/14 tests, and a parity run on a
  real 100.7 s reel (33 dialogue cuts) reproduced the previous engine's report exactly
  (PASS — 0 critical / 0 high / 0 medium / 24 low).
- **Projects directory** concept: MASTER_CONTEXT § Projects directory + `VIDEO_PROJECTS_DIR`;
  `video-edit-pipeline` Stage 0 now picks the lane (branded / reel-recut / arcads-video-edit /
  hook-splitter / ai-audio-sound-design) and creates `<projects dir>/<slug>/`.
- **Public hygiene:** `scripts/scrub-check.sh` (secrets, private hosts, personal paths,
  e-mails, review slugs, fee amounts, media, gitignored deny-list) wired as `.githooks/`
  pre-commit + pre-push; `MASTER_CONTEXT.md` is now gitignored (it was designed as the
  personal layer but was never ignored — a public flip would have shipped it).
- Homebrew ffmpeg/ffprobe fallbacks in `reel-recut`, `video-review-canvas`, `hook-splitter`
  (non-login shells on a Mac often lack `/opt/homebrew/bin`).
- README, CLAUDE.md, ARCHITECTURE.md, SETUP.md (§0, §6b, §10c, §12, §13), `check-setup.sh`,
  `.env.example`, `MASTER_CONTEXT.template.md` (projects dir, hard rules, machine/keys) rewritten
  for working-folder mode. The earlier uncommitted `hook-variations` + `naming-convention` work
  is included in this commit.

- **GPT review (Codex) of the commit:** 11 findings, 9 applied — the scrub check now scans the
  STAGED blobs (not the working tree), the secret / e-mail / review-slug patterns are broader and
  the deny-list matches case-insensitively; `arcads_gen.py` resolves `ARCADS_PRODUCT_ID` /
  `ARCADS_PROJECT_ID` after the `.env` is loaded (they were read at import time and the legacy
  `PRODUCT_ID` name was the only one honoured); `transcode-clips.sh` is bash + nullglob;
  `inspect-video --out` resolves from the invoker; three all-caps brand eyebrows and one internal
  project path genericized. Declined: renaming the `palmier` QA lane (a third-party editing tool,
  not a client) — kept.

**Lessons kept**
- BSD `sed` has no `\b`: a rename silently did nothing; only the typecheck caught it. Always
  typecheck a ported package before trusting a green install.
- A scrub script must exclude itself from the scan, and a deny-list must not contain the
  public org's own name.
- "Verify in the medium the reviewer consumes, with a different tool than you built with" is
  now a CLAUDE.md rule, not just a hook-variations note.

**Public flip (same day).** Before flipping, every unique blob in the repo's history (180 blobs, 9
commits) was scanned for secrets, private hosts, personal paths, e-mails, review slugs, fee amounts
and deny-list names: no hits beyond the scrub script's own regex text and brand eyebrows in old
versions of files already genericized; `.env`, `MASTER_CONTEXT.md`, the deny-list and media were
never committed. `gh repo edit --visibility public`, verified anonymously. From here on **every push
publishes** — the pre-commit/pre-push scrub is the gate; `SCRUB_ALLOW=1` only with a stated reason.

**Next**
- The working repo is writing a user-specific wrapper skill for its organic-reel takeover lane;
  once that session finishes, distil the generic lane (base cut first, one comp, speaker in a
  circle PIP, "pointing at the screen" sections untouched) into `reel-recut/references/`.
- Run the pipeline end-to-end from the working repo on the next real edit and log what breaks.

Append a short dated entry after every significant session: what was
edited/decided/shipped/broken, skills touched, lessons kept.

---

## 2026-09-02 — two new skills: hook-variations + naming-convention

Both distilled from a real batch job in the private working repo: 21 hooks × 2 body cuts = 42
ad variants, built, verified, renamed and delivered on two review canvases.

**`hook-variations`** — one body + N hooks → one standalone video per hook. The join is four
lines of ffmpeg; the skill exists because those four lines produce files that are broken on
the user's disk while looking correct in every tool you would naturally reach for. Four
traps, three of them silent:
1. the concat demuxer does not rescale the second file's timebase (a 121s file reported 236s)
2. AAC audio overruns its video, and the offset comes from the container, so the body lands
   off the frame grid and stays lip-sync drifted
3. **different SPS/PPS between the halves** — one `avcC` cannot describe both, so the file
   plays in ffmpeg and FREEZES after the hook in QuickTime. This one shipped
4. hooks off a raw mix sit 10–20 LU under a loudnormed body

**The QA lesson is the reason the skill is worth having.** The broken batch had passed a
thorough check: every frame decoded, pixel-identical to source, constant 30fps, zero audio
lag. Build and check both used libavcodec, which honours in-band parameter sets that
AVFoundation ignores. *A check that shares a blind spot with the thing it checks proves
nothing.* `verify_variants.py` now shells out to `avtest`, a small Swift
`AVAssetImageGenerator` probe, and decodes 12 points per file with QuickTime's own decoder.
This is the repo's "verify pixels, not intentions" rule sharpened: **verify in the medium the
user consumes, with a different tool than you built with.**

Also captured: `ProcessPoolExecutor` workers do not inherit module globals under `spawn`, so
a verifier reading its paths from globals checked the wrong folder while printing the right
labels — 21 confident "ALL PASS" lines about files nothing had opened.

**`naming-convention`** — the filename carries every axis that varies, plus a stable sort
key. `hook-07-lookalike-cinematic-body-unedited.mp4`. The load-bearing half is
*verify the facts before baking them into 40 files*: two products in that batch were
mislabelled upstream (a "sparkling water" hook was really a cap — the upstream title had
named the reference **video**, i.e. the style reference, not the product; a "Gut Check" hook
was really the Thumb-Stopper bar). The reliable source was the generation tool's own prompt
panel, not the ad frames, which are close-ups that crop wordmarks.

**Scripts are tested, not just written.** `probe_join.py` ran against the real 21-hook set and
reproduced the manual findings exactly; `build_variants.py` + `verify_variants.py` built and
passed a variant end to end (12/12 AVFoundation, body pixel-identical, PSNR 54.7 dB);
`rename_batch.py` renamed and then reported "already named" on a second run. Two bugs were
caught in that testing and fixed: ffprobe returns fields in its own order, so positional csv
unpacking mis-assigns them (use key=value or json), and a leftover dead call.

Improvement over the original session code: the builder now **stream-copies hooks whose
`avcC` already matches the body** and only re-encodes the ones that differ — the session
version always re-encoded.

Registered both in `video-edit-pipeline` (routing table + a new Stage 6b) and ARCHITECTURE.md.
Upstream for producing the hooks themselves is `hook-splitter` (now in this pack).

Append a short dated entry after every significant session: what was
edited/decided/shipped/broken, skills touched, lessons kept.

---

## 2026-08-29 — Repo created

Skill pack distilled from a real production edit: a 4-round talking-head ad
edit that was style-cloned from a reference reel, sound-designed with
ElevenLabs (SFX kit + music bed), tightened with 5 surgical EDL cuts, and
shipped through a here.now canvas review loop (timeline comments read back
per round, new file per version, same review slug) to sign-off.

Skills written (9):

1. `video-edit-pipeline` — master orchestrator for the end-to-end pipeline
2. `branded-ad-edit` — raw talking head → finished branded motion-graphics ad
3. `reel-style-clone` — reference reel → STYLE-GUIDE.md + build directives
4. `sound-design` — ElevenLabs SFX/music, audit, style-matching, mixing math
5. `video-qa` — 4-layer QA on compositions and rendered MP4s
6. `video-review-canvas` — here.now review page + notes readback
7. `edl-tighten` — silence/pacing cuts with full timeline remap
8. `reel-recut` — spec-driven short-form recut style
9. `capcut-export` — layered CapCut draft export (schema patch WIP)

Also created: README.md, CLAUDE.md, ARCHITECTURE.md,
MASTER_CONTEXT.template.md, .env.example, .gitignore, footage/ and outputs/
placeholders.

## 2026-09-02 — organic reel from a generated likeness, two looks, one generator; reel-recut gains `map-words.py`

Two organic reels built from the SAME 30 s script, each a Seedance 2.5 talking head generated from
a different reference clip (a locked-off studio shot and a handheld selfie), so the only variable
between the two edits was the footage. Lane: `reel-recut` raw cut (silence cut to a ~50 ms residual
gap, 22 cuts per look) → one HyperFrames generator shared by both projects (`build.mjs <project>`,
per-look geometry in a `look.json`: PIP scale/anchor, split anchor, clip names) → both QA lanes →
review canvas. Six beats: face-only hook, PIP reveal with the real reference clip and voice card
wired into a model node, full-face breath, a split with 30 s vs 15 s bars + a strip of output
frames, a PIP terminal receipt, the comment callout with a DM mock. 44 SFX hits, no music bed.

**Skill change — `reel-recut/scripts/map-words.py` + workflow.md § 3b.** The manifest-lane seam QA
reported 4 HIGH "clipped word" issues on the studio cut; isolated re-probes heard every word
intact. Root cause was the word map, not the cut: a full-file whisper.cpp large-v3 pass smeared
onsets INTO the silences (a phrase-initial word placed 0.7 s inside a silencedetect span), and
transcribing each 1–2 s keep span in isolation was worse (token offsets collapse to the segment
start on short clips; it hallucinated words). Cloud whisper-1 word times ran a consistent ~0.15 s
late and never smeared; the silencedetect edges are the true onset of every phrase-initial word.
The script combines the two (shift, assign to keep spans, snap span heads, drop words that only
exist past the media end) and writes the cut-time word map a comp anchors on plus the QA-lane
shapes. Same cuts, regenerated manifest: 0 issues on 22 cuts, both looks.

**Lessons kept (generic):**
1. **A caption whose window straddles a mode change lands in the wrong mode.** A full-mode caption
   that starts before a PIPIN stays at the bottom through the takeover and crosses the circle (the
   face). Split the phrase at the boundary or null it when the graphic already carries the words.
2. **Full-mode chips must sit above the video layer.** Anything below the `#vclip` z-index is
   invisible whenever the video is full frame; it only shows inside takeovers.
3. **Two CSS classes with the same name in one generator** (a reveal chip wrapper and the terminal
   rail chips both called `.rchip`) silently override each other; the flex centring vanished.
4. **A hit anchored on the last word before a silence cut never plays.** The studio cut left 0.09 s
   between "voice" and the next phrase; everything anchored there fired after the PIPOUT. Anchor on
   the word two or three back and let it hold.
5. **zsh eats `$var:l`** (`offset=$off:linear=true` reached ffmpeg as `0.37inear=true`). Brace every
   variable that is followed by a colon.
6. **The hyperframes QA lane over-flags silence-derived cuts** (it treated a 30 ms "came out" word
   pair as a repeated word); the manifest lane with accurate source words is the authority there.
   Verify any flag with an isolated re-probe of the RENDER before touching a cut.
7. AI-actor audio arrived at −27 LUFS on one look and −16 on the other; normalise the base to
   −14 LUFS before the comp so one SFX gain table serves both, then limiter-master the render
   (`-c:v copy`) and re-measure — the SFX sum pushed the raw render to −0.1 dBTP.
