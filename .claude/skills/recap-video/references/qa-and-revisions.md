# QA and reviewer revisions

## Verify what the viewer receives

Run the pack's `video-qa` on the encoded master. Use full decode, duration/frame checks,
black/freeze/flash detection and measured loudness. Add semantic watch/listen
when the configured tools and current scope allow it. Record skipped layers.

**Adapter limitation:** the current HyperFrames adapter creates a removed source
range between each pair of spans. It assumes forward source order. A join from
source 20–22 seconds back to 2–4 seconds becomes a reversed range, and reused
source points can share event IDs. Do not use that adapter as source-boundary
proof for reordered/reused takes. It also defaults expected output to
1080x1920/30fps; the CLI's `--fps` controls semantic sampling, not this expectation.

For a chronological, nonoverlapping 1080x1920/30fps edit, use the matching EDL
plus **both** source and output words (output words alone skip source clipping
checks):

```bash
npm --prefix "$PACK/tools/video-qa" run qa:video -- \
  --lane hyperframes --video "$PROJECT/output-v1.mp4" \
  --source "$PROJECT/source.mp4" \
  --edl "$PROJECT/_cut_work/v1/qa-edl.json" \
  --words "$PROJECT/_cut_work/v1/words-master.json" --words-are-output \
  --source-words "$PROJECT/_cut_work/v1/source-words.json"
```

For reordered/reused takes or other output geometry/rates, run the generic
technical/semantic lane and separately audit **every** boundary by occurrence:

```bash
npm --prefix "$PACK/tools/video-qa" run qa:video -- \
  --video "$PROJECT/output-v1.mp4"
```

From `edl.json`, make a seam table keyed by adjacent `line_index`/`span_index`
with output join time, outgoing source end and incoming source start. Inspect
source windows around those **two independent points**, and the corresponding
output audio window; do not turn them into one presumed removed interval.
Compare source words crossing each edge, listen for complete tails/heads and
repeats, measure base-audio join steps, and check dead air. Audit the first and
last retained boundaries too. Use `dialogue.wav` for exact sample inspection,
and verify against the final mix. Record verdict/evidence per occurrence. This
manual L2 audit is required until the engine supports these joins; label the
generic engine's L2 coverage as absent. Probe actual dimensions/FPS and compare
them with the project spec manually in this lane. An independently validated
explicit manifest with correct per-occurrence events is another option.

Define `PACK` as this repository and `PROJECT` as the media project. If additional
dialogue cuts occur after assembly, regenerate the EDL and words before this run;
the unmodified base's map no longer describes the output. Do not use an output
analysis to invent the intended EDL.

Compare the intended line list to an independent listen/read of the final audio
for missing clauses and repeats. Whole-render ASR is only supplemental; it can
hallucinate connective words or normalize a real duplicate. A high similarity
score or zero repeated n-grams does not establish clean speech. Resolve issues
with isolated source and output windows and a disfluency-aware read.

## Adjudicate each finding

| Finding | Evidence to inspect | Correct response |
|---|---|---|
| Clipped-word risk at a silence cut | Source waveform, surviving audio, isolated verbatim read | Restore audible consonant/tail when missing; retain the cut if only ASR padding was removed |
| Duplicate delivery | Read forward from candidate in-points and inspect short gaps | Remove the incomplete attempt, including loud fragments; keep the complete final attempt |
| Splice click in final mix | Same narrow window in the base VO with SFX/bed muted | Fix a real base seam; if the transient belongs to an intended effect, tune only if it sounds wrong |
| Flash at split/full switch | Frames around the seam in the encoded output | Gate the outgoing layout container at the boundary |
| Overlapping captions | Adjacent frames and resolved caption intervals | Use exclusive end times and clear the old block before the next begins |
| Off-center / unreadable slide | Actual chosen source interval and final crop | Shift media in-point, reduce push or choose a legible alternative |
| Abrupt ending | Last complete spoken thought and trailing audio/picture | End on the complete CTA/thought; preserve a short deliberate tail or obtain needed VO |

The source workflow had dozens of HIGH boundary flags caused by ASR word timing
extending into removed silence. Some early flags were real clipped words. Inspect
each finding; neither accept all flags nor dismiss them as a class. A semantic
reviewer's repeat finding turned out to be real after two plain readers denied it.

A final-mix `splice_click` once came from a pop whose strongest transient was
151 ms after the asset start. Its attack landed near an edit boundary, while the
base voice seam was clean. Inspect the effect's waveform as well as its placement
timestamp before moving a good dialogue cut.

Keep a table of issue ID, original engine verdict, source/output timestamps,
evidence and disposition. Do not rename the engine's FAIL to PASS when manually
adjudicating false positives. Report the raw verdict and the explained exceptions;
unverified findings remain unresolved. A repaired cut must pass listening after
the change, since trimming one restart can clip the preceding word.

## Copy and restricted visuals

Check each added graphic against speech and visible evidence. Preserve the stat's
population, timeframe and attribution; do not turn "this year" into an annual
claim or a named audience into "everyone". Verify names/company spellings and
speaker identities. Keep captions faithful to the recording; substantive claim
changes need an editorial decision or replacement audio, not a silent subtitle
rewrite. Apply the user's configured copy review process when available.

Restricted slide labels indicate the content needs clearance, even if the label
can be cropped out. Keep an unresolved-use list and omit those assets pending
clearance. A clean visual export does not settle that question.

## Revision loop

Read all timeline notes for the exact delivered version. Capture each note's frame
and, for audio notes, its short listening window **before** changing anything.
Distinguish questions from edit requests: a verified speaker identity may resolve
a note without swapping footage. Record the evidence and answer.

Fix at the correct layer:

- Take/restart/dead-air change: edit `edl-lines.json` and rebuild the base/maps.
- Crop/clip choice: change the shot's media in-point or focus before forcing zoom.
- Intro pace: move the burst earlier and add coherent activity shots if requested.
- Outro: remove an aborted/non-substantive fragment without chopping the complete
  CTA; required copy needs a complete alternate or replacement/decision. Use a
  `raw` tail when needed to prevent the silence gate removing the ending hold.
- Caption lost after a veto: check whether the **line** survives before dropping it.

Use the time-map procedure in `composition.md` to rebuild downstream beats.
Check neighboring cuts too: outward frame rounding across two adjacent lines can
replay one frame of room tone; the assembler clamps this specific overlap.

Render to a new filename, master and inspect the exact changed windows plus
affected downstream sync. Update the review page on the existing slug with a
per-note evidence table and version selector. Preserve old masters and comments.
Continue routine revisions within existing authorization; do not require the
same approval twice. Hosting, client delivery and public social posting retain
their own requested scope.

For a requested source-folder handoff, upload the exact verified master, record
the returned file ID and destination, and compare bytes/checksum when available.
Preserve sharing unless the user asks to change it. Return the link; sending it
to an outside recipient is a separate action.
