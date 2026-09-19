# Durable state and reusable footage

The executable entry point is `<pack>/tools/editor/editor.py`. Full flags and schemas are
documented in [tools/editor/README.md](../../../../tools/editor/README.md).

## Existing project

Run `project resume <project>` and read its packet before choosing the next editing action.
Changed inputs and missing artifacts invalidate progress. Rebuild affected stages; a saved
"complete" label does not override the fresh file checks. `resume --run` executes only a
previously configured argv command for the next stage, and never invokes the editing agent.

## New project

1. `project init <project> --source <source> --lane <skill>` stores references without moving
   media. Repeat `--source` for multiple inputs. Style and sound default to skipped; enable
   them with `--style <guide>` and `--sound` when relevant to the requested workflow.
2. Complete the lane's editing work as usual. Save ingest/edit/QA/review receipts with
   `project checkpoint <project> <stage> --artifact <file>` (repeat for multiple artifacts).
   Explicitly omitted work can use `--skip "reason"`; receipt bookkeeping is not a request
   for new user approvals.
3. Register each new render and its version with `project render`, then checkpoint QA and
   review against that version. New render registration resets those final checkpoints.
4. Read back canvas JSON with `read-notes.mjs <url> --json --out <file>` or use its Export
   button, then `project import-review <project> <file>`. Open notes from all versions stay
   available in the next session. Record approval only after actual sign-off.

Keep the state file in the media project's folder. Keep private context and credentials out
of this public pack; configured commands should refer to environment variables through
their programs, not embed credential values in argv. CLI input paths are relative to the
invoking directory; a configured command and its expected artifacts resolve in the project.

## Shared catalog

`catalog ingest <catalog.json> <media paths...> --recursive` probes sources and creates
poster/contact sheets. It imports matching `.words.json`/`.transcript.json` sidecars, or
`--transcript <file>` for one source. Optional `--transcribe --whisper-model <local model>`
uses installed whisper-cli without network calls or model downloads.

`catalog search <catalog.json> "phrase"` returns matching transcript intervals and asset
metadata. Use `catalog annotate` to save useful source intervals, descriptive tags and any
restrictions; use `catalog use` to record the project/version and source interval actually
used. Restrictions remain visible in search; a catalog entry never grants permission.
The same content hash reuses derivatives across copies/renames. Search does not infer visual
semantics from unlabeled footage; inspect the contact sheets before choosing a shot.

## Storyboard coverage

Write `{"version":1,"elements":[{"id":"title","start":0,"end":2}]}` alongside the
composition. Each ID must occur once and have a matching explicit static schedule, e.g.
`<div id="title" data-start="0" data-duration="2">…</div>`. Use absolute output times.

```bash
npm --prefix "<pack>/tools/video-qa" run qa:storyboard -- \
  --storyboard "<project>/storyboard.json" --html "<project>/index.html" \
  --video "<project>/output-v2.mp4" --out "<project>/_qa/storyboard-v2"
```

Static presence and timing checks are separate from actual-render contact sheets. Do not
claim JavaScript transitions, CSS visibility, occlusion or nested composition timing were
verified from HTML alone. Inspect frames against every expected visual, including what is
missing. Use full QA for seams/audio and `--require-layers` only for checks the project
actually requires; optional missing model access is explicit coverage, not a clean pass.
