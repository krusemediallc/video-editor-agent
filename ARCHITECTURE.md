# ARCHITECTURE — Video Editor Agent

## What this is

A Claude Code skill pack that turns raw footage into finished, reviewed short-form video.
Editing workflows live in `.claude/skills/`; QA, storyboard checks, durable project state
and the footage catalog live in `tools/`; media and renders live in a **projects directory** that is
usually outside this repo. The pack is generic on purpose: a user's brand, machine, reviewer
habits and clients live in the gitignored `MASTER_CONTEXT.md`, and the pack gets better from
every real edit without ever carrying the edit's private details.

## Repo layout

```
.claude/skills/            # the skills (each: SKILL.md + references/ scripts/ assets/)
  video-edit-pipeline/     # MASTER orchestrator — start here; routes to everything below
  branded-ad-edit/         # raw talking head → branded motion-graphics ad (HyperFrames)
  reel-recut/              # spec-driven creator reel: banner, karaoke captions, callouts, silence cuts
  reel-style-clone/        # reference reel → STYLE-GUIDE.md + build directives
  arcads-video-edit/       # multi-take screen+camera+mic demo → EDL base cut → motion-graphics pass
  recap-video/            # event recap: per-line takes, supplied B-roll, split/full layouts, exact assembly
  hook-splitter/           # one long composite of many hooks → N tightened standalone videos
  hook-variations/         # one body × N hooks → N standalone variants (lossless + AVFoundation-verified)
  naming-convention/       # descriptive filenames for a batch of deliverables
  edl-tighten/             # silence/pacing cuts with a full timeline remap
  sound-design/            # ElevenLabs SFX kit + music bed, audit, mixing math
  ai-audio-sound-design/   # AI-actor footage → location ambience, room reverb, bleeps, watermark removal
  talking-head-image-overlays/  # uncut take + hard-cut overlays on nouns: title plate, inserts
                           #   above the eyeline, skeleton-UI cards, early CTA banner. No SFX.
  broll-capture/           # real-website screenshots and scroll recordings
  openart-broll/           # generated b-roll / overlays via the OpenArt MCP
  arcads-broll/            # generated b-roll / overlays via the Arcads REST API
  video-qa/                # the 4-layer QA procedure (what tools/video-qa automates)
  video-review-canvas/     # here.now review page + timeline-comment readback
  capcut-export/           # layered export to a CapCut draft (WIP)
tools/video-qa/            # the QA ENGINE: a standalone node package (tsx/zod), own package.json
  cli/qa-video.ts          #   4-layer run: --manifest | --lane hyperframes --edl … | --video
  cli/inspect-video.ts     #   Layer-4 inspection packet for one window
  cli/qa-storyboard.ts     #   planned IDs/timing checks + actual-render evidence
  src/                     #   layer1-technical, layer2-transcript, layer3-semantic, inspect, report,
                           #   manifest/{schema,adapter-hyperframes}, transcribe, gemini, cache, env
  src/__tests__/           #   offline deterministic + real-media regressions; live ASR opt-in
tools/editor/              # Python stdlib project state, stage resume and footage library
  editor.py               #   project init/status/resume/checkpoint/render/approve/note/import-review
                          #   catalog ingest/search/annotate/use
  project.py              #   hashed receipts, stale-state detection, locks, immutable render versions
  catalog.py              #   probe, thumbnails, sidecar/local transcription and content IDs
  tests/                  #   state, failure, cache, media and review-import regressions
scripts/
  setup.sh                # idempotent local setup + optional relative skill symlinks
  check-setup.sh           # offline lane-aware doctor; never downloads through npx
  demo.sh                 # synthetic footage → edit → QA → canvas/catalog/state
  serve-review.py         # localhost preview with byte ranges for accurate video seeking
  test.sh                 # offline suites; --integration adds demo and recap regression
  scrub-check.sh           # public-repo hygiene gate (secrets, paths, names, media)
  scrub-denylist.example.txt   # copy → scrub-denylist.local.txt (gitignored) with your own names
.githooks/                 # pre-commit (staged) + pre-push (all) → scrub-check.sh
.github/workflows/        # Linux offline regression and synthetic integration CI
footage/  outputs/         # gitignored conveniences for a standalone setup
CLAUDE.md                  # session rules
MASTER_CONTEXT.template.md # → MASTER_CONTEXT.md (gitignored): brand, defaults, projects dir, learnings
SESSION_LOG.md             # dated session history
SETUP.md                   # every tool + API with a CHECK and a FIX
.env                       # keys (gitignored; .env.example lists them)
```

## How the skills relate (the pipeline)

`video-edit-pipeline` is the only entry point users need. It decides the lane at intake:

- **Talking head + brand** → `reel-style-clone` (if a reference exists) → `branded-ad-edit`
  (crops/transcribe/storyboard/compose) → `sound-design` (SFX + bed) → QA loop with
  `video-qa` (snapshot → look → fix → render → verify the MP4 with the engine) → deliver via
  `video-review-canvas` → revision rounds (notes readback, frame-evidence per note,
  `edl-tighten` for pacing, new file per version, same slug) → optional `capcut-export`.
- **The creator's own signature reel look** → `reel-recut` (one JSON spec, deterministic).
- **Multi-take screen + camera + mic recordings** → `arcads-video-edit` (EDL base cut the
  reviewer locks, then a motion-graphics pass).
- **Event/conference/travel recap with spoken takes + supplied B-roll** → `recap-video`
  (reference forensics, line selection, B-roll catalog, exact base assembly, source-anchored
  captions/graphics, render/QA and review revisions). Its portable Python assembler writes
  versioned EDL/word maps; it needs Python and ffmpeg/ffprobe, with no new cloud dependency.
- **One long recording of many hooks** → `hook-splitter`; an approved body plus many hooks →
  `hook-variations`; any batch of more than two files → `naming-convention` before delivery.
- **AI-actor footage that sounds sterile** → `ai-audio-sound-design` (audio-only pass).
- **An uncut take carrying stacked image overlays** → `talking-head-image-overlays`. This lane
  inverts the usual base cut (keeps ~15% of runtime as pauses) and ships no audio assets.
- B-roll comes from `broll-capture` (real screens) or `openart-broll` / `arcads-broll`
  (generated).

The specialist skills are also independently invocable for narrowly scoped requests.

## The QA engine (`tools/video-qa`)

The `video-qa` skill documents the four layers as a procedure; `tools/video-qa` implements
them. It is a self-contained node package: `npm --prefix tools/video-qa install` once, then
`npm --prefix tools/video-qa run qa:video -- …` from anywhere (relative paths resolve
against the directory you ran it from via `INIT_CWD`, and `.env` is read from there first,
then from this repo's root). Reports land next to the video in `_qa/<stem>/`; exit codes
0 / 1 / 2 = PASS / PASS_WITH_WARNINGS / FAIL. Coverage is explicit; incomplete optional
checks warn, required missing layers fail. Layer 3 (Gemini) skips cleanly without
`GEMINI_API_KEY`; transcription uses whisper.cpp via `npx hyperframes transcribe`, falling
back to OpenAI whisper-1 when `OPENAI_API_KEY` is set. `npm --prefix tools/video-qa test`
runs offline fixtures, source-order/occurrence checks, cache/coverage tests and real media
regressions. Live transcription tests require explicit opt-in. Each layer is isolated so an
optional backend failure does not discard the technical report; incomplete results are not cached.

`qa:storyboard` takes a storyboard JSON, composition HTML and optional render. It checks
stable IDs and absolute `data-start`/`data-duration`/`data-end` schedules, then samples the
actual video into per-element contact sheets. Static coverage never implies verified rendered
visibility; CSS, JavaScript, occlusion and nested composition offsets still need inspection.

## Durable state, footage and revisions

`tools/editor/editor.py` keeps `project.json` in each media project. It records source/style
fingerprints, stage receipts, versioned render hashes, approvals and review notes. Read-only
`status`/`resume` recompute stale state from files. Explicit `resume --run` executes one
configured argv command (no shell), requires output artifacts and records failures/logs.
Writers are serialized; a running stage cannot be replaced by another stage mutation.
See `tools/editor/README.md` for the CLI and lifecycle.

The catalog is separate from an individual edit so projects can share one library. Media
content hashes identify assets; metadata, contact sheets and local transcripts are cached.
Editorial intervals, restrictions and previous uses are retained across copies/renames.
Transcription uses supplied sidecars or an explicitly requested installed whisper-cli/model;
there is no automatic cloud fallback or model download in the catalog.

Canvas v2 embeds a version manifest and loads public `comments` plus append-only
`reviewEvents` from the existing here.now store. Events record replies, status and paired
frame evidence. A local demo mode uses browser storage and explicitly labels that scope.
Exported revision JSON includes raw records and replayed notes; `project import-review`
updates the project's snapshot. Publishing remains a separate existing here.now operation.

The recut renderer's `cut_timeline.py` replaces long select/aselect expressions with bounded
16-span lossless FFV1/PCM batches, reconstitutes the frame grid after concatenation, and
encodes AAC once. The same grid drives keep windows and cumulative sample counts, including
fractional FPS. Rendered frame counts, PCM samples, audio duration and full decode are verified.

## Setup and regression entry points

`bash scripts/setup.sh --demo` is the first-run path. It creates missing local config,
installs project dependencies and builds an API-free synthetic demo. `--link-skills DIR`
adds relative links without overwriting existing paths. The offline doctor requires only
the selected workflow's dependencies. Global package installation requires `--install-system`;
git configuration is never changed implicitly.

`bash scripts/test.sh --integration` runs setup safety, project/catalog, canvas, TypeScript,
technical/storyboard/seam/long-cut QA and recap assembler regressions. GitHub Actions uses
the same Linux workflow. Test sources are generated locally; media and private state remain
outside version control.

## Working-folder mode and the projects directory

A user's videos usually live in their own working repo, not here. The pattern:

1. Run `bash "<pack>/scripts/setup.sh" --no-install --link-skills "<working-repo>"` to
   create relative skill links for the actual directory layout, preserving existing paths.
   A Claude Code session started there loads the skills while their files stay in this repo.
2. `MASTER_CONTEXT.md` (here, gitignored) names the **projects directory**; every skill
   creates `<projects dir>/<project-slug>/` for its working files and never moves media into
   this repo. `VIDEO_PROJECTS_DIR` in `.env` says the same for scripts.
3. The working repo aliases the QA engine (`"qa:video": "npm --prefix \"<pack>/tools/video-qa\" run qa:video --"`).
4. Personal/process split: generic lessons go into the skill; the client, the fee, the
   reviewer's name, machine paths and review URLs go into MASTER_CONTEXT.md or the working
   repo's own logs. `scripts/scrub-check.sh` enforces it at commit and push time.

## External dependencies (documented, not vendored)

- **HyperFrames** — composition + render engine: `npx hyperframes`, plus
  `npx hyperframes skills update talking-head-recut` for fonts/gsap; `npx hyperframes
  transcribe` is the default whisper.cpp route.
- **ffmpeg / ffprobe** — all probing, extraction, cropping, muxing. Python project tools
  accept `FFMPEG` / `FFPROBE` or `FFMPEG_PATH` / `FFPROBE_PATH`, then search PATH and
  Homebrew locations. The QA
  engine uses `FFMPEG_PATH` / `FFPROBE_PATH`, then Homebrew locations, then PATH.
  No libass/drawtext needed anywhere — text goes through PIL PNGs or HTML.
- **whisper-cli + ggml models** — word-level transcription and VAD for the cut planners
  (`WHISPER_CLI`, `WHISPER_MODEL`, `VAD_BIN`, `VAD_MODEL`).
- **node >= 20**, **python3** (+ PIL; numpy/scipy for `ai-audio-sound-design`).
- **ElevenLabs API** — `ELEVENLABS_API_KEY`; **OpenAI** (optional) — `OPENAI_API_KEY`;
  **Gemini** (optional) — `GEMINI_API_KEY`; **Arcads** (optional) — `ARCADS_BASIC_AUTH` /
  `ARCADS_API_KEY` + workspace ids; **OpenArt MCP** (optional).
- **here-now skill** — canvas publishing; docs at https://here.now/docs (fetch with
  `User-Agent: claude`), credentials in `~/.herenow/credentials`.
- **pyJianYingDraft** in a venv — CapCut export only. **Swift toolchain** — builds
  `hook-variations`' `avtest` probe on first use.

## Provenance

Distilled from a production editing stack and real shipped edits: a 4-round paid brand ad,
a style-clone reel, a product-news explainer built from a generated likeness, an eight-version
multi-take product demo, a 21-hook composite split and re-joined into 42 variants, and a
10-scene AI-actor audio pass. The hard-won lessons (two crop candidates shown as images, one
batched snapshot, per-note evidence tables, new file per version, verify-in-pixels, verify with
a different decoder than you built with) are baked into the skills rather than left as tribal
knowledge.
