# The edit manifest — format, EDL adaptation, word mapping

**Provenance rule:** the manifest is emitted by the EDITOR from edit intent (the build
script's own computed timeline, an EDL, a placement list) — never derived by analyzing
the rendered output. A manifest derived from the render inherits the exact bugs QA
exists to catch. If your build pipeline doesn't emit one, add a `--qa-manifest` dump to
the build step; do not reverse-engineer one afterwards.

## Normalized manifest (JSON)

```jsonc
{
  "version": 1,
  "lane": "generic",              // free label for the pipeline that produced the edit
  "video": "out/final.mp4",        // the render under test (relative to the manifest file)
  "source": "raw/take1.mp4",       // original footage, when applicable
  "expectedDuration": 62.43,       // from the build's computed timeline
  "expected": { "width": 1080, "height": 1920, "fps": 30 },
  "events": [
    { "id": "cut:src48.8",         // STABLE id from lane-native keys — issue anchor
      "kind": "cut",               // cut|caption|callout|sfx|music|broll|graphic|segment|other
      "dialogueCut": true,          // seam interrupts speech → full L2 boundary battery
      "out": { "start": 31.52 },   // output-timeline seconds (cuts: start only)
      "src": { "start": 48.80, "end": 50.12 },  // REMOVED source range (provenance)
      "meta": { "origin": "silence" } },        // silence-derived cut → L2 gates apply
    { "id": "caption:12", "kind": "caption",
      "out": { "start": 30.9, "end": 33.4 },
      "src": { "start": 47.1, "end": 49.6 },    // lets captions compare source-side
      "text": "the whole funnel runs on autopilot" }
  ],
  "intentional": {                 // detections that must NOT be flagged
    "blackRegions":  [{ "start": 0.0, "end": 0.4 }],
    "silentRegions": [{ "start": 58.0, "end": 60.0 }],
    "stillRegions":  [{ "start": 12.0, "end": 14.5 }],   // cards/freezeframes — exempt from freezedetect
    "loudnessTarget": { "lufs": -14, "tolerance": 2 },
    "noAudio": false
  },
  "words":       [{ "text": "funnel", "start": 31.1, "end": 31.4 }],  // OUTPUT-time
  "sourceWords": [{ "text": "funnel", "start": 47.9, "end": 48.2 }]   // SOURCE-time
}
```

`words` must be the source transcript **mapped through the EDL** — never a
re-transcription of the render (whisper hallucinates at jump cuts). Stable ids like
`cut:src48.8` (keyed on the removed source start) survive re-renders that shift the
output timeline; that's what makes fixed-vs-not comparable across iterations.

## Adapting a picture-lock EDL

A common EDL shape from cut-planning scripts:

```jsonc
{ "fps": 30, "windows": [
  { "raw_start": 0.8,  "raw_end": 12.4, "master_start": 0.0,  "master_end": 11.6 },
  { "raw_start": 14.1, "raw_end": 30.0, "master_start": 11.6, "master_end": 27.5 }
]}
```

Each window is a KEPT span (raw = source time, master = output time). Derive cuts:

- `windows[0].raw_start > 0.02` → head trim: cut `id=cut:src0.0`, `out.start=0`,
  `src={start:0, end:raw_start}`.
- For each adjacent pair: cut at `out.start = windows[i].master_start`,
  `src = {start: windows[i-1].raw_end, end: windows[i].raw_start}`,
  `id = cut:src<removed-start, 1 decimal>`. Mark `dialogueCut: true` unless known
  otherwise.
- `expectedDuration = last window's master_end`.

Placement lists (`[{id,label,start,dur,track,kind}]`, output-time) map kind→event kind
(`media`→`broll`, `card`/`text`→`graphic`, `sfx`→`sfx`, …) with
`id = <kind>:<native id>`.

## Mapping SOURCE words → OUTPUT time through the cut list

1. Sort the removed ranges (`src` of every cut with an end); complement them over
   [0, source duration] to get the kept spans.
2. `outT(x)` = sum of kept-span lengths fully before x, plus the partial span up to x.
3. **Midpoint containment with edge clamping:** place each word by the point 40% into it
   (`w.start + 0.4*(w.end-w.start)`), because whisper word ENDS are routinely padded into
   the following pause — strict full-containment drops a large share of real words at
   silence-cut edges (observed live). If the 40%-point lands in a kept span, clamp the
   word to that span, map both ends via `outT`, and keep it if > 20ms survives.
4. Words straddling a boundary are excluded from the output mapping — L2 detects those
   as clipped-word suspects directly from `sourceWords` + cut provenance.

## No manifest at all?

Run the "generic lane": L1 (minus intent-dependent checks: duration/resolution vs
expected, intentional-region gating, cut-linked severities) + L3. Say so in the report —
the boundary battery needs intent data, and shipping without it is a weaker guarantee.
