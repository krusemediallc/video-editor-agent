# Recap composition and timeline mechanics

## Storyboard by what the line means

Build a shot table with line/word anchor, layout, clip, media in-point, focus and
zoom, reason, caption, graphic and sound cue. An intentional visual for each
sentence can be proof, context or a creator cameo; it need not be a new cut on
every sentence. Match literal proof first, thematic footage second. Label an
illustration as such rather than making unrelated slides appear to substantiate
the narration.

Practical starting grammar, adjusted to the footage and brief:

| Beat | Treatment |
|---|---|
| Hook | Short creator opening; early burst of venue/travel/activity shots on the hook phrase |
| Main explanation | Full-screen slide, panel or demo footage over uninterrupted VO |
| Creator presence | Brief split with B-roll above and creator below; clean shared seam |
| Personal observation | Lifestyle, candid or travel cameo with a purposeful expression/action |
| Major figure | Short emphasis stamp; retain scope, population and timeframe of the claim |
| Summary | Takeaway rows enter on the words, with enough hold to read |
| Signature quote | One ghost-text typewriter treatment for the most useful statement |
| Closing | Finish the thought/CTA, then a short deliberate visual tail if needed |

Body shots around 1-3 seconds are a starting point; give dense slides more time.
One fast montage may use roughly 0.2-0.35 seconds per shot, but tune it to the
phrase and vary recognizable compositions. The delivered source edit grew its
opening to 17 shots starting 1.5 seconds in; that is evidence of the desired early
energy, not a fixed future shot count. Let speech duration drive the video.

## Layout, crops and captions

Keep the base VO audio continuous. The picture modes are `FULL` (creator), `BR`
(full-screen B-roll), and `SPLIT` (two panels). Do not split just to fill space;
use it when seeing the person deliver that line helps. The source adaptation
used B-roll on top, creator on bottom, which superseded a reference document's
proposed inverse arrangement.

At 1080x1920, a starting split seam is y=960. Reframe the creator using actual
face position so the seam clears the head, and account for captions on the lower
panel. Inspect frame grabs. Never carry a hardcoded translation from another
person's shot without measuring this footage.

Use focus-point crops and gentle pushes for handheld slides. Clamp movement so
the destination stays filled; inspect the headline at start, middle and end of
the shot. A later in-point often solves an off-center slide more cleanly than a
tighter crop. Pick a different clip when the needed text cannot fit legibly.

Phrase captions use sentence case, readable white type, dark outline/shadow and
near-instant entrances (about 0.05 seconds in the source adaptation). Place them roughly in the lower 68-73% of
the portrait frame, then adjust for the actual creator, slide text and platform
UI. Avoid inheriting unrelated purple banners or karaoke just because another
reel skill uses them. Correct names with evidence; do not rewrite spoken meaning.
For a close starting match at 1080x1920, use Inter 700 at 41 px, line-height 1.24,
5 px dark stroke, x=60 and width=960, with the 180 px caption region starting near
y=1310 (1350 for splits). These are the adaptation's measured settings, not a
substitute for inspecting readability on the new footage.

Give caption intervals half-open bounds `[start, end)`, clamp each to the next
caption start and the current line/video end, and inspect adjacent frames. A
two-frame overlap was visible even though the text looked fine in sparse samples.
Clear the last caption before an intentional outro card.

Use emphasis colors and typography from the current brief/brand. Stamps are
short enough to read immediately; number them only if the narration has numbered
chapters. Takeaways build sequentially on speech and hold as a complete list.
Check/cross symbols are suitable when they carry the actual comparison. A quote
can pre-render its full muted ghost text and overlay the revealed characters in
the **same inline-block**, keeping identical font, wrapping and line-height.
Do not reserve empty space with guessed per-character widths.

## Timing survives a recut

Keep a stable line ID and source occurrence on every editorial anchor. The safest
new beat format is `{lineId, sourceTime}` or `{lineId, offsetFromLineStart}`.
An old output-time anchor can be remapped through:

1. Old EDL span containing the output time.
2. Its source time: `old.src_in + (oldTime - old.out_in)`.
3. The current surviving span for the **same line/occurrence** containing that time.
4. New output time: `new.out_in + (sourceTime - new.src_in)`.

If the point was removed inside a surviving line, clamp to that line's next
surviving span (or its end) and inspect. Do not search globally by source time:
reordered or reused footage makes that ambiguous. If the whole line was removed,
remove its caption/beat. A word timestamp can begin in a removed pause, so
"anchor no longer maps" alone is not a reason to delete the caption.

Keep an immutable baseline EDL and each revision's map. Derive line starts/ends
from all surviving spans. After remapping, sort shot boundaries, drop zero-length
windows, recompute media offsets and re-audit captions/graphics/SFX through the
end. Changing the base beneath old literal timestamps is not a completed revision.

## Rendering traps worth retaining

- Use dense-GOP proxies of the selected source intervals at the target frame rate;
  record source offsets for every subclip. Check `mediaStart + playedDuration`
  against the proxy duration, including speed changes. Do not transcode a large
  library wholesale when short selected intervals suffice.
- Keep the split panel container transparent outside its own content. An opaque
  black background once covered the top half of full-screen shots.
- Initialize mode containers explicitly and set their visibility at every mode
  switch in the paused timeline. A video clip can paint one frame past its
  nominal media window. Gate its **container** at the seam; shortening every clip
  by a frame traded the flash for black gaps.
- Snapshot the hook, every caption/graphic family and crop; inspect mode seams
  at the boundary and +/-1 and +/-2 frames. Then verify those seams again from
  the actual MP4.
- For SDR delivery from HLG phone B-roll, the source project used HyperFrames
  `render --sdr` so Chrome's tone-mapped appearance matched its snapshots and
  avoided a huge HDR pre-extraction. Check the installed CLI's help and output
  color metadata, and compare an exported frame to the preview. For intentional
  HDR delivery choose and verify a consistent HDR pipeline instead.

## Sound and mastering

Tie effects to actual visual/word events; avoid a sound on every ordinary cut or
caption change. The source adaptation used clicks for its montage and restrained
pops/hits for graphics, with no whooshes per the creator's preferences. Reuse
cleared kits; generated assets and API spend are conditional, not required.

An optional low instrumental bed can add continuity. Its source `data-volume`
of 0.20 is asset-specific: gain alone is not a loudness target. Measure the bed
against speech, preserve intelligibility and fade it across the actual duration.
Mute B-roll audio by default so it cannot introduce PA chatter over the VO.

Use two-pass `loudnorm` with measured I/TP/LRA/threshold/offset and final encoding
at a consistent rate. For the source brand-delivery setting, I=-14 LUFS,
TP=-1.5 dBTP and LRA=11 followed by
`alimiter=limit=0.76:attack=5:release=60:level=false` produced a measured result
near -14.9 LUFS / -1.7 dBTP. These are starting parameters, not a guarantee:
measure the encoded master using `ebur128=peak=true`, meet the current delivery
spec and leave headroom for AAC. A prior setting measured -0.9 dBTP and needed
adjustment. Use explicit variable names/braces in shell filters; do not let
shell modifiers interpret a colon after a variable.
