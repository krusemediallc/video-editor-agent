# Ingest, reference forensics and the spoken edit

## Source inventory

List remote files before downloading a large folder. Keep original filenames and
IDs in a private manifest; record bytes, local path and probe results. Do not
assume a folder contains only video: photographs can be useful too. Check the
decoded orientation rather than the coded dimensions alone. Phone display
matrices can turn a nominal landscape frame into a portrait image.

Probe width/height, nominal and average FPS, duration, start time, sample rate,
channels, pixel format, color primaries, transfer and rotation. Normalize copies
for editing; retain raw footage. A clip re-encoded to 8-bit may still carry HLG
transfer metadata, so bit depth alone does not establish SDR.

For each B-roll clip, seek independently to several positions across its duration
and tile the resulting frames. Inspect the sheet itself. A `select` followed by
`fps=1` and `tile` produced mostly black panels in the originating workflow;
those panels were extraction errors, not unusable footage. Use full-size frames
around the intended source in-point to read slides or verify identities.

Suggested catalog entry:

```json
{
  "clip": "venue-014",
  "file": "broll/venue-014.mov",
  "duration": 18.2,
  "category": "stage-slide",
  "creatorVisible": false,
  "description": "Wide speaker and audience with a customer journey slide",
  "onScreenText": ["Customer journey"],
  "usefulRanges": [{"in": 9.8, "out": 13.0, "reason": "headline centered"}],
  "focus": {"x": 0.50, "y": 0.44},
  "restrictions": [],
  "evidence": ["_look/broll/venue-014-10s.jpg"]
}
```

A filename or a neighboring shot does not establish who is on stage. Read lower
thirds, slides or another reliable source. Record uncertainty when evidence is
insufficient. If a slide is marked confidential, cropping the label does not
clear the material for use: omit it unless its use is cleared for this deliverable.

## Reference analysis

Use `reel-style-clone` to measure cuts, caption geometry, full/split/PIP usage,
creator cameos, holds, graphic entrances and audio. Scene detection alone misses
overlays, captions and container transitions; inspect sampled frames and short
before/after strips. Listen to speech gaps and inspect their spectrum to establish
whether there is music rather than adding a bed from habit.

Write separate sections for **measured**, **inferred**, and **requested deviations**.
A previous event reference had roughly half a cut per second, mostly full-screen
slide footage, phrase captions, chapter stamps, a takeaway list and a ghost-text
quote. It had no split screen or music. The finished adaptation deliberately added
splits, a much faster opening montage, different emphasis colors and a resolved
outro. Copy the useful grammar, not superseded build directives or the old script.

## Choose takes by complete line

Create word transcripts for each take. Use a domain vocabulary prompt for names
and terminology, but check the audio and slide evidence before spelling corrections.
Keep both the original transcript and a corrected intended line list.

Compare each candidate line for:

- Complete words and sentence meaning, with no restarts carried into the cut.
- Audible mic level, room/PA interference and clarity at the quietest phrase.
- Delivery and natural connection to the adjacent chosen lines.
- Visual continuity, such as a badge appearing in only one take, when visible.

Use another take for one weak sentence without replacing an otherwise good take.
Avoid stitching syllables to manufacture a new claim. Silence removal and retake
removal are not permission to shorten approved substantive copy to a reference's
runtime. Remove an unfinished trailing clause only when it is an aborted take or
non-substantive fragment. If it contains required copy, use a complete approved
alternate or obtain replacement VO/an editorial decision. Retain a short
intentional tail when it helps the ending resolve.

Record each chosen range in narrative list order, with a stable line ID, source
take/piece, in/out, intended text, selection reason and useful alternate. All
in/out times fed to the assembler must refer to the same mezzanine clock.

## Normalize the mezzanine without shifting audio

Create a source-piece table mapping `(original file, original in/out)` to
`(mezzanine in/out)`. It may contain a whole main take plus excerpts from alternates.
Normalize dimensions, orientation, FPS, pixel format, audio rate/layout and PTS
before the concat filter. Trim each audio piece to its intended video length.
Verify cumulative durations and sync at each take change. Do not use a demuxer
stream copy for unlike phone takes: a 75 ms audio offset survived that shortcut.

Rebase each original word into its mezzanine piece:
`mezz_start + original_word_time - original_piece_start`. Preserve original source
identity as metadata for later QA. A repeated source excerpt is a separate
occurrence with its own output mapping.

## Silence and disfluency are separate problems

Start speech-gap detection around -30 dB with pauses of 0.13 s and 0.03 s edge
handles, then inspect the specific recording. These are starting parameters,
not a universal voice threshold. A noisy PA can defeat a silence gate; a soft
consonant can sit below it. Use listening, waveforms and VAD/manual ranges where
the threshold does not distinguish voice from noise.

Listen/read every kept line with an independent verbatim pass:

> Transcribe every repeated word, partial word, restart and false start exactly
> as spoken. Do not clean up or normalize disfluencies.

Two ordinary transcribers can agree and still hide the same repeated phrase.
When a listening reviewer says something is said twice, inspect that exact window.
For a stubborn restart, transcribe forward from each candidate in-point to find
the complete final attempt. A triple restart can look like only two attempts in
a coarse envelope. Read gap-only slices too: a loud 200 ms partial-word sliver
can survive as its own keep while a whole-line transcript silently removes it.

Use `veto` ranges to remove confirmed restart/breath fragments regardless of
level. Use `raw: true` for intentional room tone or a breathing tail. Preserve
quiet word tails until listening establishes that they are only breath; blindly
trimming the low-energy end of a word created a real clipped ending in the source
workflow. Verify the base end-to-end before compositing, with special attention
to line boundaries and every manual edit.
