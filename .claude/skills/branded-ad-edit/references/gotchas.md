# Gotchas & working style

Every entry below cost real time on a proving run (#1–20 on a paid brand ad and a
style-clone reel, #21–30 on a product-news explainer built from a generated likeness). Skim before starting; return
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
| 21 | **Every card square renders EMPTY** and `check` still passes with 0 errors | `class="clip"` + `data-start`/`data-duration` only *schedules* a host on its track — it does not clear the inline `visibility:hidden;opacity:0` you put on the host | give every card host an `enter()` (set visible + fromTo opacity) and `exit()` (to opacity 0 + set hidden) pair inside its clip window. The lint can't see this because the markup is valid; only a snapshot shows it |
| 22 | A control-render diff says most SFX are missing, but they're all there | the VO is loudness-normalised (−14 LUFS, peaks −1.2 dB), so a −13 dB hit can't move a window's peak *or* its 300ms RMS; and subtracting two AAC renders leaves the whole VO as residue, not the SFX | render a **SFX-only** take (`source-audio` and music `data-volume="0"`) and measure each hit window in that file — hits should land ~3–8 dB under the VO peak. Peak-diffing only works when the VO has headroom |
| 23 | The whole kit sits too quiet against the voice | the reference `data-volume` values assume a ~−7 dB VO | scale the kit to the VO you actually have (a −14 LUFS VO needed ×1.95, capped at 0.8) — decide this from a measurement, not from the reference numbers |
| 24 | A real page screenshot is unreadable inside a browser frame | on-canvas text size is `display_width ÷ css_width_of_the_crop`; capturing at 1440 and cropping barely helps | capture at a **narrow viewport (~620px)** so the page reflows to its mobile layout — the same text comes out ~1.5× larger on a 1080 canvas |
| 25 | Site B-roll looks soft or hitches on seek | it's a video, so it inherits GOP/seek problems and a re-encode generation | for page content, scroll a **tall PNG** inside the browser frame with a `y` tween instead. Sharper, perfectly deterministic, no keyframe concerns |
| 26 | A card element vanishes completely, no lint error | it's a sibling of `.sq` (which is `height:100%`), so it flows past the 1080 square and is clipped by the host's `overflow:hidden` | put it inside `.sq`, or make it `position:absolute` against `.root` |
| 27 | Card content clusters at the top with a dead void above the captions | `justify-content: flex-start` on the card stack | use `center` — opacity-0 elements still occupy layout, so nothing reflows as beats pop in |
| 28 | Two Whisper models disagree on a word | small vs medium hear it differently; you must not "fix" it by cutting or altering the speaker's audio | re-transcribe an **isolated 1–2s slice** with the bigger model; two of three agreeing decides the caption. Design the card around the accurate fact even when the caption keeps the speaker's wording |
| 29 | A build script dies `ENOENT` on a path containing `%20` | `new URL(import.meta.url).pathname` percent-encodes, and project paths often contain spaces | `fileURLToPath(import.meta.url)` |
| 30 | The delivered master clips — sample peak pinned at 0 dBFS, **true peak over 0 dBTP** | scaling the SFX kit up (gotcha 23) raises the SUM, and per-hit levels can all look right while the mix total goes over. AAC then overshoots the PCM peaks by another ~1.5 dB | after ANY level change, measure the render itself: `ffmpeg -i out.mp4 -af ebur128=peak=true -f null -`. Target ≈ −14 LUFS integrated and **≤ −1 dBTP**. Fix without re-rendering by mastering the audio and copying the video: `-c:v copy -af "aresample=192000,alimiter=limit=0.69:attack=1:release=40:level=disabled,aresample=48000" -c:a aac -b:a 192k`. Sweep the ceiling — the post-AAC true peak is what counts, not the limiter setting. Then confirm the limiter stayed transparent by re-measuring the SFX-only render through the same chain (should move ≤1 dB per hit) |

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
