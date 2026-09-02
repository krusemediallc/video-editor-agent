# Claude Code — session rules for Video Editor Agent

This repo is the **only home for video-editing skills, scripts and process**. Everything
generic about how a finished short-form video gets made lives in `.claude/skills/` and
`tools/`; everything personal (brand, machine paths, reviewer habits, clients) lives in the
gitignored `MASTER_CONTEXT.md`. The two never mix.

## First session on a new machine

0. Run `bash scripts/check-setup.sh`. Any FAIL: walk **SETUP.md** with the user before
   starting an edit — every stage's tools and APIs are listed there with check + fix
   commands. (No MCP servers are required by this pack.)

## Every session

1. Read **MASTER_CONTEXT.md** if it exists — brand palette/fonts/voice, default ratio,
   caption preferences, reviewer workflow prefs, hard rules, the **projects directory**, and
   accumulated learnings. If it does not exist, copy `MASTER_CONTEXT.template.md` to
   `MASTER_CONTEXT.md` and offer to populate the empty fields.
2. Route **any video-edit request** (edit this footage, recut this, "edit this like
   <reference reel>", split these hooks, add hooks to this body, a revision on a delivered
   edit) through the **`video-edit-pipeline`** skill in `.claude/skills/`. It orchestrates
   the others — do not hand-roll the pipeline or jump straight into a specialist skill
   unless the user's request is narrowly scoped to that one stage.
3. **Media never lives in this repo.** Per-project working folders (`<slug>/` with the
   source, transcripts, comp, renders, `review/`, `_qa/`) go in the projects directory named
   in MASTER_CONTEXT.md — default `outputs/` here, but often a media folder in the user's own
   working repo. `footage/` and `outputs/` are gitignored conveniences, not a rule.

## Working-folder mode (a session started in another repo)

Users commonly run Claude Code inside their own working repo and expose this pack's skills
there as **relative symlinks** (`<repo>/.claude/skills/<name> → ../../../../Video Editor
Agent/.claude/skills/<name>`; a `link-video-editor-skills.sh` helper in that repo keeps them
current). In that mode:

- The skill files you are reading and editing are **this repo's files** — the symlink
  target. Edit them here, commit them here. Never copy a skill into the working repo; a
  copy is a fork that silently stops improving.
- The QA engine is invoked as `npm --prefix "<this repo>/tools/video-qa" run qa:video --
  …` (the working repo usually aliases it as `npm run qa:video`). Relative paths resolve
  against the directory the command was run from; `.env` is read from there first.
- **Every skill improvement is generic.** A lesson from a real edit goes into the skill as
  process ("verify in the medium the reviewer consumes"), never as the client's name, the
  fee, the reviewer's name, a machine path, or a review URL. Those go in MASTER_CONTEXT.md
  (or the working repo's own logs).

## Public-repo hygiene

- `scripts/scrub-check.sh` runs as the pre-commit (staged files) and pre-push (all files)
  hook once `git config core.hooksPath .githooks` is set (SETUP.md § 13). It refuses
  secrets, private hosts, personal paths, e-mails, review-canvas slugs, fee amounts, media
  files, and anything in `scripts/scrub-denylist.local.txt` (gitignored: clients, people,
  private repo names). Fix the finding; `SCRUB_ALLOW=1` is a conscious, explained bypass.
- Never commit `.env`, `MASTER_CONTEXT.md`, the deny-list, or media. Skill `assets/` may
  carry small example files only.
- Worked examples in skills anonymise the client ("a server-side tracking SaaS", "a paid
  brand-deal edit") and never state what a deal paid.

## Costs and dependencies

- Every generation-adjacent step has a cost or external dependency: ElevenLabs calls
  (SFX/music/ambience) spend API credits; Gemini QA calls spend API credits; OpenArt /
  Arcads generation spends their credits; here.now publishing needs credentials. Say what a
  step will cost/require BEFORE running it, and document any newly discovered cost or
  dependency in MASTER_CONTEXT.md (or README.md if it is a hard prerequisite).
- API keys live in `.env` at the repo root (or the invoking working repo's `.env`):
  `ELEVENLABS_API_KEY`, optional `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ARCADS_*`. Never
  hardcode a key in a script or commit one.

## Working style — verify in pixels

- **Verify pixels and dB, not intentions.** A fix exists when the rendered file shows it:
  extract frames from the actual MP4, measure audio in dB, and probe durations with ffprobe.
  Composition code passing checks is not proof.
- **Verify in the medium the reviewer consumes, with a different tool than you built
  with.** A check that shares a blind spot with the thing it checks proves nothing
  (hook-variations' AVFoundation probe exists because ffmpeg passed files QuickTime froze on).
- Before fixing a reviewer note, screenshot the exact frame the note points at. After
  fixing, show the same frame from the new render.
- New versions are new files; delivered files are never overwritten.
- Every cut is delivered on the review canvas and the reply LEADS with the URL.

## After significant sessions

Append a short dated entry to **SESSION_LOG.md**: what was edited/decided/shipped/broken,
which skills were touched, and any lesson worth keeping. If a skill's process changed,
update the skill file itself, not just the log. When the reviewer signs off a final after
giving significant feedback, fold the process change into the skill that produced the work.
Update **ARCHITECTURE.md** when the repo's shape changes (a new skill, tool, or convention).
