/**
 * HyperFrames-lane manifest adapter.
 *
 * Builds the normalized EditManifest from the artifacts the branded-ad-edit /
 * HyperFrames builds already produce:
 *  - a placement manifest: [{id,label,start,dur,track,kind}] (output-time
 *    SFX/card/media placements, e.g. Videos/grok-bot-edit/preview/manifest.json)
 *  - optionally an EDL: {fps, windows:[{raw_start,raw_end,master_start,master_end,…}]}
 *    (the picture-lock cut list, e.g. <project>/v916-edl.json)
 *  - optionally output-time words: [{text,start,end,win?}] (words-master.json —
 *    SOURCE transcript times mapped through the EDL, never a re-whisper)
 *  - optionally source-time words (whisper output on the raw footage)
 */
import { readFileSync } from "node:fs";
import type { EditManifest, ManifestEvent, WordTiming } from "../types";

interface PlacementItem {
  id?: string;
  label?: string;
  start: number;
  dur?: number;
  end?: number;
  track?: number | string;
  kind?: string;
}

interface EdlWindow {
  raw_start: number;
  raw_end: number;
  master_start: number;
  master_end: number;
}

interface EdlFile {
  fps?: number;
  windows: EdlWindow[];
}

const KIND_MAP: Record<string, ManifestEvent["kind"]> = {
  sfx: "sfx",
  media: "broll",
  broll: "broll",
  card: "graphic",
  graphic: "graphic",
  caption: "caption",
  music: "music",
  text: "graphic",
};

export interface HyperframesAdapterInput {
  video: string;
  source?: string;
  placementPath?: string;
  edlPath?: string;
  /** Output-time words file (words-master.json style; `win` field tolerated). */
  wordsPath?: string;
  sourceWordsPath?: string;
  expectedDuration?: number;
  expected?: { width?: number; height?: number; fps?: number };
}

export function buildHyperframesManifest(input: HyperframesAdapterInput): EditManifest {
  const events: ManifestEvent[] = [];

  if (input.placementPath) {
    const placements = JSON.parse(
      readFileSync(input.placementPath, "utf8")
    ) as PlacementItem[];
    placements.forEach((p, i) => {
      const kind = KIND_MAP[(p.kind ?? "").toLowerCase()] ?? "other";
      const end = p.end ?? (p.dur != null ? p.start + p.dur : undefined);
      events.push({
        id: `${kind}:${p.id ?? p.label ?? i}`,
        kind,
        out: { start: p.start, end },
        label: p.label,
      });
    });
  }

  let expectedDuration = input.expectedDuration;
  if (input.edlPath) {
    const edl = JSON.parse(readFileSync(input.edlPath, "utf8")) as EdlFile;
    const wins = edl.windows ?? [];
    if (wins.length) {
      // Head trim: source material before the first window was dropped.
      if (wins[0].raw_start > 0.02) {
        events.push({
          id: "cut:src0.0",
          kind: "cut",
          dialogueCut: true,
          out: { start: 0 },
          src: { start: 0, end: wins[0].raw_start },
        });
      }
      for (let i = 1; i < wins.length; i++) {
        const removedStart = wins[i - 1].raw_end;
        events.push({
          id: `cut:src${removedStart.toFixed(1)}`,
          kind: "cut",
          dialogueCut: true,
          out: { start: wins[i].master_start },
          src: { start: removedStart, end: wins[i].raw_start },
        });
      }
      expectedDuration = expectedDuration ?? wins[wins.length - 1].master_end;
    }
  }

  const readWords = (path: string): WordTiming[] =>
    (JSON.parse(readFileSync(path, "utf8")) as Array<
      { text?: string; word?: string; start: number; end: number }
    >).map((w) => ({
      text: (w.text ?? w.word ?? "").trim(),
      start: w.start,
      end: w.end,
    }));

  return {
    version: 1,
    lane: "hyperframes",
    video: input.video,
    source: input.source,
    expectedDuration,
    expected: input.expected ?? { width: 1080, height: 1920, fps: 30 },
    events,
    intentional: {},
    words: input.wordsPath ? readWords(input.wordsPath) : undefined,
    sourceWords: input.sourceWordsPath ? readWords(input.sourceWordsPath) : undefined,
  };
}
