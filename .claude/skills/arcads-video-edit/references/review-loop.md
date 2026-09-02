# The review loop

Every cut goes on the here.now canvas (`video-review-canvas` skill). The reply to the creator leads
with the canvas URL, pasted in full, every round — even when it is the same link. The creator had to ask
twice on an earlier edit; a file card without the link reads as "not delivered".

## Mechanics

```bash
# canvas.json: video, outDir, title, version, blurb, facts, notes[], beats[]
node .claude/skills/video-review-canvas/scripts/build-canvas.mjs <project>/canvas.json
bash ~/.agents/skills/here-now/scripts/publish.sh "<project>/review" --title "<Title> — V<N> review" --client claude-code --slug <slug>
# smoke test: page 200, video 206 (range request), page contains >V<N><
node .claude/skills/video-review-canvas/scripts/read-notes.mjs <slug> v<N>
```

- One slug for the whole project; bump `version` every round so old notes filter out but stay
  in the store as history. The video filename carries the version (`arcads-ad-v8.mp4`) or the
  browser serves the cached old one.
- `blurb` is the changelog the creator reads first. `notes[]` is where each of the creator's notes gets an answer
  and where open decisions live (tone `amber`), risks to the brand at the top (tone `red`).
  `beats[]` name every moment so the creator's notes come back as timestamps, not "the middle bit".
- The file card is secondary: the master is ~80 MB and only opens on this Mac; say so.

## Reading notes: seek before you decide

Map each note's timestamp to the shot (`qa/v5-timeline.json`) and to source time (walk the
segment's `keep` ranges), grab the frame, and look. Then classify:

| The creator's note said | It meant | Fix pattern |
|---|---|---|
| "cut the silence / breath here" ×4 | the creator's breath standard is 4 dB tighter than the VAD guess | re-tune the threshold globally, verify every new cut, tell the creator you swept everywhere |
| "have me basically talking over myself… extremely fast paced" | pauses *inside* sentences, not just between clips | waveform-level tightening (`tighten.py`), 30 ms residual gaps |
| "don't have this ad playing with audio, start when I start talking" | example ads play silently under the creator; audio only when the creator is silent | drop `screenAudio`, start on the creator's first word |
| "zoom into X" | a static punch-in, split as a picture-only segment | new segment + tighter rect + `joinPrev` |
| "center me on the video" | the creator sat 104px left of the crop centre; the house offset is ~+27px | measure the cap centre, set `camX` |
| "no full-screen takeovers… go crazy" | on a brand-run ad, restraint reads as under-delivery | rebuild with takeovers; update the face-rule memory to two regimes |
| "make X stand out / hard to read" | a text element over busy footage | opaque pills / plates with rings — and apply it everywhere, not just at the note |
| "isn't in sync with my voice" | Whisper mis-timed the onsets (two words sharing a timestamp is the tell) | measure the syllable bursts on the waveform, hard-set the times |
| "the text at the top is missing Pixar / Lego" | the creator overrode the earlier no-trademark call | do it, note the trademark point once for the brand |
| "way too much movement… QA it and clean it up" | five transitions with blur in three seconds | hard cuts, one reframe, a fixed column; keep the slams (they are the beat) |
| "my voice cuts off on the last word" | the base cut's last keep ends before the consonant decays | extend the keep in `edl.json`, rebuild the base, re-encode the comp's base asset |
| "generate a new track or increase the volume" | the opening bed was inaudible at the by-the-book level | +11 dB limited on the opening (a first pass at +6 barely registered in the mix); offer the regenerate |

Treat every note as a calibration of the creator's taste that applies to the whole video, then say in
the reply that you applied it beyond the timestamp. Never re-open a decision the creator has already
made (the character-drift cut stayed cut), and never quietly widen scope — flag adjacent fixes
as offers ("0:38.4 is the same take at half the error; you didn't flag it, so I left it").

## What impressed the creator and what did not

V6 shipped 18 cards, 105 captions, 43 hits, measured face-safe placement, zero takeovers, a
`scaleY` tick fill — and got "really disappointed". V7 shipped five takeovers, the base video
reframing into cards, circles and a montage cell, six real ads flying in, the reference video
going full-bleed and flying back into the real UI, a live MCP terminal and the real prompt
streaming, checkboxes that press/fill/draw/ring/burst, a card that flips to its back, 85 hits —
and got "overall much better!!" with seven notes, six of them legibility/sync/cleanup. The gap
between the two was not polish; it was ambition grounded in real footage and the cut moving.
