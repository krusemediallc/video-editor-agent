/**
 * HyperFrames-lane manifest adapter.
 *
 * Builds the normalized EditManifest from the artifacts the branded-ad-edit /
 * HyperFrames builds already produce:
 *  - a placement manifest: [{id,label,start,dur,track,kind}] (output-time
 *    SFX/card/media placements, e.g. <project>/preview/manifest.json)
 *  - optionally an EDL: {fps, windows:[{raw_start,raw_end,master_start,master_end,…}]}
 *    (the picture-lock cut list, e.g. <project>/v916-edl.json)
 *  - optionally output-time words: [{text,start,end,win?}] (words-master.json —
 *    SOURCE transcript times mapped through the EDL, never a re-whisper)
 *  - optionally source-time words (whisper output on the raw footage)
 */
import { readFileSync } from "node:fs";
import type { EditManifest, ManifestEvent, WordTiming } from "../types";
import { z } from "zod";
import { editManifestSchema } from "./schema";

interface PlacementItem {
  id?: string;
  label?: string;
  start: number;
  dur?: number;
  end?: number;
  track?: number | string;
  kind?: string;
  text?: string;
}

interface EdlWindow {
  id?: string;
  raw_start: number;
  raw_end: number;
  master_start: number;
  master_end: number;
  origin?: "silence" | "manual";
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
  intentional?: EditManifest["intentional"];
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
        text: p.text,
        ...(p.track != null ? { meta: { track: p.track } } : {}),
      });
    });
  }

  let expectedDuration = input.expectedDuration;
  let edlFps: number | undefined;
  if (input.edlPath) {
    const edl = z.object({ fps: z.number().positive().optional(), windows: z.array(z.object({
      id: z.string().optional(), raw_start: z.number().nonnegative(), raw_end: z.number().nonnegative(),
      master_start: z.number().nonnegative(), master_end: z.number().nonnegative(),
      origin: z.enum(["silence", "manual"]).optional(),
    }).refine((w) => w.raw_end > w.raw_start && w.master_end > w.master_start, "EDL windows must have positive source and output durations")) }).parse(JSON.parse(readFileSync(input.edlPath, "utf8"))) as EdlFile;
    edlFps = edl.fps;
    const wins = edl.windows ?? [];
    if (wins.length) {
      const occurrences = new Map<string, number>();
      const segmentIds = wins.map((w, i) => {
        if (i && w.master_start < wins[i - 1].master_end - 1e-6) throw new Error("EDL output windows overlap or are out of order");
        const key = w.id ?? `src${w.raw_start}-${w.raw_end}`;
        const count = (occurrences.get(key) ?? 0) + 1;
        occurrences.set(key, count);
        const id = `segment:${key}${count > 1 ? `:repeat${count}` : ""}`;
        events.push({ id, kind: "segment", out: { start: w.master_start, end: w.master_end }, src: { start: w.raw_start, end: w.raw_end } });
        return id;
      });
      // Head trim: source material before the first window was dropped.
      if (wins[0].raw_start > 0.02) {
        events.push({
          id: `cut:head>${segmentIds[0]}`,
          kind: "cut",
          dialogueCut: true,
          out: { start: wins[0].master_start },
          src: { start: 0, end: wins[0].raw_start },
        });
      }
      for (let i = 1; i < wins.length; i++) {
        const removedStart = wins[i - 1].raw_end;
        events.push({
          id: `cut:${segmentIds[i - 1]}>${segmentIds[i]}`,
          kind: "cut",
          dialogueCut: true,
          out: { start: wins[i].master_start },
          ...(wins[i].raw_start > removedStart ? { src: { start: removedStart, end: wins[i].raw_start } } : {}),
          meta: { sourceBefore: removedStart, sourceAfter: wins[i].raw_start, ...(wins[i].origin ? { origin: wins[i].origin } : {}) },
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

  return editManifestSchema.parse({
    version: 1,
    lane: "hyperframes",
    video: input.video,
    source: input.source,
    expectedDuration,
    expected: input.expected ?? (edlFps ? { fps: edlFps } : undefined),
    events,
    intentional: input.intentional ?? {},
    words: input.wordsPath ? readWords(input.wordsPath) : undefined,
    sourceWords: input.sourceWordsPath ? readWords(input.sourceWordsPath) : undefined,
  }) as EditManifest;
}
