# Claude Code — session rules for Video Editor Agent

## Every session

1. Read **MASTER_CONTEXT.md** if it exists — brand palette/fonts/voice, default
   ratio, caption preferences, reviewer workflow prefs, and accumulated
   learnings. If it does not exist, copy `MASTER_CONTEXT.template.md` to
   `MASTER_CONTEXT.md` and offer to populate the empty fields.
2. Route **any video-edit request** (edit this footage, recut this, "edit this
   like <reference reel>", a revision on a delivered edit) through the
   **`video-edit-pipeline`** skill in `.claude/skills/`. It orchestrates the
   others — do not hand-roll the pipeline or jump straight into a specialist
   skill unless the user's request is narrowly scoped to that one stage.

## Costs and dependencies

- Every generation-adjacent step has a cost or external dependency: ElevenLabs
  calls (SFX/music) spend API credits; Gemini QA calls spend API credits;
  here.now publishing needs credentials. Say what a step will cost/require
  BEFORE running it, and document any newly discovered cost or dependency in
  MASTER_CONTEXT.md (or README.md if it is a hard prerequisite).
- API keys live in `.env` at repo root only (`ELEVENLABS_API_KEY`, optional
  `GEMINI_API_KEY`). Never hardcode a key in a script or commit one.

## Working style — verify in pixels

- **Verify pixels and dB, not intentions.** A fix exists when the rendered
  file shows it: extract frames from the actual MP4, measure audio in dB, and
  probe durations with ffprobe. Composition code passing checks is not proof.
- Before fixing a reviewer note, screenshot the exact frame the note points
  at. After fixing, show the same frame from the new render.
- New versions are new files; delivered files are never overwritten.

## After significant sessions

Append a short dated entry to **SESSION_LOG.md**: what was edited/decided/
shipped/broken, which skills were touched, and any lesson worth keeping. If a
skill's process changed, update the skill file itself, not just the log.
