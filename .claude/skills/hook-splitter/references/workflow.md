# hook-splitter — step by step

## Round 1: build the set

### 0. Get the file and read the docs
If the source lives in cloud storage, download it to local disk first (the scripts
read local files only). Read `MASTER_CONTEXT.md` for the user's defaults and any past
learnings on this lane.

Make a project dir under the projects directory: `hooks-<slug>-<MMDD>/` with `source/`, and copy
`assets/hooks.example.json` to `hooks.json` beside it.

### 1. Probe
```
python3 probe.py hooks.json
```
Confirm it finds a mic track and a system track. **Then verify alignment** — transcribe
the same 45s window from both, once near the start and once near the end:
```
python3 isolate.py hooks.json 60 45          # mic
python3 isolate.py hooks.json 60 45 --sys    # system
```
The played-video dialogue must appear at the same place in both. Repeat near the end of
the file. A drifting mask silently corrupts every output.

### 2. Mask + speech maps
```
python3 video_regions.py hooks.json
python3 transcribe.py hooks.json
```
`video_regions.py` prints the structure — the talk/video rhythm is usually the hook
boundaries, laid out for you.

### 3. Read the whole thing and write the hook table
Render the transcript against the video markers and actually read it. This is the part
that is not automatable: you are deciding where each hook starts and ends, and spotting
what the speaker says twice.

For each candidate flub, **confirm it in isolation before writing a kill**:
```
python3 isolate.py hooks.json 82 24 --env
```
Then fill in `hooks` in `hooks.json`: `start`, `end`, `kills`, `title`, `note`.

### 4. Loops, mix, plan, render
```
python3 detect_loops.py hooks.json
python3 build_mix.py    hooks.json
python3 plan.py         hooks.json
python3 render.py       hooks.json
```

### 5. QA — never skip

`plan.py` asserts that no kill survives inside a kept segment and that segments never
overlap; `render.py` flags any hook whose rendered length is more than 1.5 frames off the
plan. If either fires, stop — something is being handed back or padded.

```
python3 qa.py hooks.json
```
Read every flag. A repeat is often genuine content (a reference video that *is* the
previous generation; a reaction that naturally says "oh my god" twice). Cut only real
flubs — then re-plan, re-render, re-QA.

### 6. Publish
```
python3 build_canvas.py hooks.json
bash ~/.agents/skills/here-now/scripts/publish.sh <review> --title "…" --client claude-code
```
Smoke-test before sending the link:
```
U=https://<slug>.here.now
curl -s -o /dev/null -w "%{http_code}\n" "$U/"                    # 200
curl -s -r 0-1000 -o /dev/null -w "%{http_code}\n" "$U/<file>.mp4"  # 206
curl -s "$U/.herenow/data/comments?limit=3"                        # {"records":[…]}
```
Save the slug into `hooks.json` so later rounds update the same URL.

**Reply LEADS with the URL.** Then a short table of what you cut per hook, and anything
you deliberately did NOT do.

## Round 2+: the reviewer's notes

```
python3 map_notes.py hooks.json <slug> v1
```
Every timestamp is in OUTPUT time; this walks it back to source and shows the words
either side.

**It maps through `work/cuts-<version>.json`, the snapshot `build_canvas.py` takes of the
cut that version was built from — not the live `cuts.json`.** The reviewer's notes are timestamped
against the video they watched, so once you start editing, the live cut no longer matches
and every note would silently point at the wrong second. If the script warns that no
snapshot exists, stop and reconstruct one before acting on anything.

Then, per note:
1. `isolate.py` that window (`--env` for exact boundaries)
2. decide the edit — a `kills` entry, or a change to the hook's `start`/`end`
3. re-run `plan.py` → `render.py` → **`qa.py`**

Bump `version` in `hooks.json`, rebuild the canvas, publish with `--slug`, and say
which of the reviewer's notes each change answers.

### Reading the reviewer's notes well

- **"end here" / "end the clip here"** at or within ~0.4s of the current end means the
  trailing air, i.e. `tail_pad`. If several hooks get this note, change `tail_pad`
  globally rather than patching the ones they happened to flag — the reviewer is describing a
  preference, not five separate bugs.
- **A marker inside a word** means the reviewer marked slightly early or late. Cut at the nearest
  envelope trough, never mid-word.
- **"cut the first one"** — check WHERE the reviewer pinned it. On the reference project this
  read as "the hook's opening line" but the marker was sitting on a real back-to-back
  double just before the video. When two readings are possible, the one the timestamp
  is closest to wins; and check whether the other hooks do the same thing unflagged
  (if they do, it is the speaker's style, not a flub).
- If a note asks for something inside a played video (dialogue in the generated ad),
  that is still a `kills` entry — kills apply to protected regions too.
