# Gotchas & working style

Every entry below cost real time on the proving run. Skim before starting; return
whenever something looks wrong.

## The table

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | An element is BLACK/invisible during its early appearance, fine later | a LATER `fromTo(el, {opacity:0}, …)` stamps inline `opacity:0` at page load (`immediateRender` defaults true, even mid-timeline) and the early fade-in that would undo it was removed | `immediateRender: false` on the later fromTo. Tell: the element's own background doesn't paint — page backdrop shows through — so it's a stamped style, not media |
| 2 | Frame 0 shows the un-hidden state | `tl.set(..., 0)` doesn't render at playhead exactly 0 | initial hidden states in CSS (`opacity: 0` rule), animate in with fromTo |
| 3 | Motion stutters in renders | animating `top/left/width/height` (layout props snap to integer px under seek-capture) | transforms only: `x/y/scale/opacity` |
| 4 | A video renders FROZEN | `<video>` with `data-start` but no `id` | unique `id` on every media element |
| 5 | Video freezes under overlays on seeks | sparse GOP | re-encode ALL media `-g 30 -keyint_min 30` |
| 6 | A shortened variant renders full-length with a frozen tail | pretty-printed stage div splits attrs across lines; single-line attr regex missed `data-duration` | patch stage duration explicitly; ffprobe the RENDERED file, never trust the render log |
| 7 | SFX inaudible in the mix | ~1/3 of ElevenLabs sound-generations are near-silent; min duration 0.5s | volumedetect-audit every file; regenerate duds ("loud", "punchy", prompt_influence 0.6); normalize kit to −3dB |
| 8 | Music API 400 | artist name in prompt (ToS) | describe the style; the error body includes a `prompt_suggestion` |
| 9 | Two captions mashed on top of each other | a chunk held past the next chunk's start (long last word) | display window always ends at next chunk's raw start − 0.04 |
| 10 | Junk in B-roll frames (dialogs, widgets, personal windows) | Chrome-for-Testing keychain prompt (survives pkill as an orphan), chat widgets remounting | system Chrome + fresh userDataDir + `ignoreDefaultArgs:["--enable-automation"]`; sweep junk selectors on an interval; frame-extract-review EVERY take |
| 11 | Scripted scroll silently never moves | text-anchor matched an ancestor div whose top is 0 | target the SMALLEST matching node |
| 12 | Transcript oddities | last word ends past media end; brand names split into two words; hallucinated phrases on non-speech | clamp, merge (keep timestamps), null out Whisper-noise phrases |
| 13 | Missing glyph in renders | Apple private-use chars (, SF symbols) absent in headless Chrome | emoji or text labels |
| 14 | Overlap lint on an intentional stamp-over-content | two text blocks colliding | dim the underlayer to ~0.12 as the stamp lands — reads better anyway |
| 15 | `check` track-overlap errors in a cut variant | fully-cut cards left with stale times | excise their host blocks |
| 16 | Card text across the speaker's face | overlay card entering while a full-bleed segment still runs | delay the card to the framing cut; snapshot QA catches it |
| 17 | Consecutive `snapshot` calls leave only one frame | each call overwrites the output | ONE call with comma-separated `--at` list |
| 18 | A repeated take / false start survives into the edit but the transcript reads clean | **Whisper DEDUPES back-to-back retakes** on continuous audio — "and sub-agents your… and sub-agents your project…" transcribes as ONE slow phrase | transcribe silence-split segments in ISOLATION (per-clip, or concat with 1s silence separators); flag segments < ~1.6 words/sec and clip-transcribe those; ALSO re-transcribe the assembled master — each pass catches flubs the other hides |
| 19 | Karaoke captions drift late toward the back half ("captions are delayed") | Whisper on a full concatenated cut accumulates late drift — up to +1.1s by 70s, on every pass | never caption from whisper-on-the-cut: transcribe EVERY EDL window as an isolated clip and stitch word times through the EDL (`master = window.master_start + clip_time`) — frame-accurate; validate against `silencedetect` speech onsets |
| 20 | After a scripted retime, some animations fire at t=0 or wrong times | regex replacement callback args shift when a pattern has a NESTED capture group (the countUp bug: `parseFloat("\"#sel\"")` → NaN → mapped to 0) | count groups in every retime regex; remember positions NOT wrapped in `Q()`: helper call-sites (enter/exit/pop/rise/hide), wordSwap time arrays + endAt, countUp's at-arg, framing fns — enumerate all of them |

## Working style that made the proving run work

- **Verify pixels and dB, not intentions.** Extract frames / snapshot contact sheets
  and look with vision; measure audio windows with volumedetect against a baseline
  render. Every bug above was caught that way — none by re-reading code.
- **Generate the repetitive 90%** (caption spans/tweens, SFX elements, EDL remaps)
  from the transcript with a build script; hand-author only the cards, where design
  judgment lives. Template + generator also makes every revision a cheap
  regenerate-and-re-render.
- **Bisect with the cheapest tool.** snapshot (~30s) before render (~3min). The
  immediateRender bug survived three renders and fell to a snapshot loop in minutes.
- **Ask preferences once** (ratio, layout mix, variants), then run autonomously to a
  reviewable draft. Deliver drafts; incorporate redirects.
- **Never overwrite an approved cut** — new versions are new files.
- **Real brand assets over recreations**, always.
- **Timestamped review beats prose feedback.** A frame.io-style review page (video +
  scrubber + pinned comments the agent reads back via API) turned vague notes into
  surgical fixes — 20 timestamped comments across two rounds, every one actionable.
  See SKILL.md §10.
