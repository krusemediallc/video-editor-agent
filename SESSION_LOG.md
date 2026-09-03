# SESSION LOG — Video Editor Agent

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
