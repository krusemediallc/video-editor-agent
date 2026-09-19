# Project state and footage catalog

Python 3.10+; no Python packages or cloud services required. Media indexing also uses
ffmpeg/ffprobe. Run `python3 tools/editor/editor.py --help` for the complete command tree.
Keep project JSON, catalogs, thumbnails, transcripts and media in the working media
directory (normally outside this repo, or under ignored `outputs/`).

## Resume an edit

```bash
python3 tools/editor/editor.py project init outputs/example \
  --name "Product reel" --lane reel-recut --source footage/source.mp4
python3 tools/editor/editor.py project checkpoint outputs/example ingest \
  --artifact outputs/example/transcript.json
python3 tools/editor/editor.py project status outputs/example
python3 tools/editor/editor.py project resume outputs/example
```

`init` records source fingerprints and the chosen lane. Use `--style STYLE-GUIDE.md`
to track an existing style reference and `--sound` to enable the sound-design stage.
The ordered stages are `ingest`, `style`, `edit`, `sound`, `qa`, `review`; style and
sound start skipped unless enabled. Other explicitly omitted stages can be recorded
with `checkpoint ... STAGE --skip "reason"`.

Checkpoints require existing artifact files. They record SHA-256 hashes, validate
upstream dependencies and invalidate downstream work when repeated. `status` and
`resume` verify files and report missing or changed inputs; they never silently accept
a modified source or change project state. Re-run ingest and checkpoint it to accept
an intentionally changed source. Paths are relative to `project.json`, so moving a
whole project and its source tree preserves references.

`resume` prints the next stage, owning skill, sources, style, renders, approvals and
open notes. It does not invoke an LLM or run arbitrary commands. To make a deterministic
stage executable, store an explicit argument vector and expected outputs:

```bash
python3 tools/editor/editor.py project configure outputs/example edit \
  --command '["python3", "build.py", "spec.json"]' --artifact output-v1.mp4
python3 tools/editor/editor.py project resume outputs/example --run
```

Commands run in the project directory without a shell. `--run` executes only the next
stage, saves a log in `_runs/`, and checkpoints it only after successful exit and
artifact verification. There is no implicit retry loop. A failed run remains retryable.
For a process interrupted outside the CLI, verify the process has stopped, then use
`project recover DIR STAGE --reason "interrupted run stopped"`. A leftover write lock
names the writer PID; remove it only after verifying that process is gone.

Configured commands are code supplied by the project's editor. Inspect imported project
files before executing them. Credentials belong in the environment, never in saved argv.

## Renders, approvals and review notes

```bash
python3 tools/editor/editor.py project render outputs/example \
  outputs/example/output-v1.mp4 --version v1
python3 tools/editor/editor.py project approve outputs/example v1 \
  --reason "Reviewer signed off on this version"
python3 tools/editor/editor.py project import-review outputs/example \
  outputs/example/review-revisions.json
python3 tools/editor/editor.py project note outputs/example \
  --text "Caption overlaps the face" --version v1
```

Registering a render resets QA/review checkpoints; register before checkpointing their
reports. A version cannot be repointed at new bytes or reused under another filename.
Approvals record the actual rendered file hash and become invalid if that file changes.
Use `approve` only to record real user sign-off; completing a script is not approval.

Notes use stable IDs. Update one with `--id ID --status resolved --evidence PATH_OR_URL`.
Resolution needs evidence, and the append-only project history records changes. Canvas
v2 JSON exports import idempotently; unresolved notes from earlier versions remain in
resume context. The canvas remains the shared review store; project imports are snapshots
and are refreshed after new reviewer feedback. See the canvas skill for export/readback.

## Index reusable footage

```bash
python3 tools/editor/editor.py catalog ingest outputs/library.json footage/ --recursive
python3 tools/editor/editor.py catalog search outputs/library.json "product launch"
python3 tools/editor/editor.py catalog search outputs/library.json --tag event --unused --json
python3 tools/editor/editor.py catalog annotate outputs/library.json ASSET_ID \
  --label "Stage demonstration" --tag event --interval 2.0 5.0 "Clean product shot" \
  --restriction "Slide permission pending"
python3 tools/editor/editor.py catalog use outputs/library.json ASSET_ID \
  --project outputs/example --version v2 --start 2 --end 5
```

The catalog records content-addressed asset IDs, source paths, codecs, dimensions,
duration, audio metadata, poster frames, 12-frame contact sheets, transcripts, chosen
intervals, restrictions and previous uses. Identical footage shares one asset even after
a rename or copy. Missing thumbnails regenerate. Derivatives live beside the catalog in
`<catalog-name>.assets/`; the original media is never copied or modified.

For each source, `filename.words.json` or `filename.transcript.json` is indexed
automatically. `--transcript FILE` supplies a transcript for a single input. Accepted
formats are a word/segment array, OpenAI `words`/`segments`, or whisper.cpp `transcription`
with millisecond offsets. Timestamps must refer to the source, not an edited output.
Search returns matching phrases with start/end times, and updated transcripts reindex
without regenerating unchanged thumbnails.

To generate transcripts locally, opt in with `--transcribe --whisper-model MODEL.bin`
and optionally `--whisper-bin PATH`. This requires an already installed `whisper-cli`
and model, extracts a temporary 16kHz mono WAV, and makes no API call or download.
Assets without a transcript remain searchable by labels, filenames and tags; the tool
does not claim to understand unlabeled visual content. Useful intervals and restrictions
are editorial annotations, not automatic permissions or creative ratings.

## Verification

```bash
python3 -m unittest discover -s tools/editor/tests -v
bash scripts/test.sh --integration
bash scripts/setup.sh --demo
```

Tests exercise fresh-session resume, changed inputs, missing artifacts, moved project
trees, failure recovery, render immutability, review imports, real thumbnail generation,
transcript corrections, duplicate media, annotations and prior-use tracking. The demo
generates media locally and connects the project tools, catalog, QA and review canvas.
