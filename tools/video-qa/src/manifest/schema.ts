/**
 * Normalized edit-manifest schema + loader.
 *
 * PROVENANCE RULE: manifests are emitted by the EDITOR from edit intent
 * (build_reel.py --qa-manifest, the branded-ad-edit build scripts, a Palmier
 * project.json) — never derived by analyzing the rendered output.
 */
import { readFileSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { z } from "zod";
import type { EditManifest, ManifestEvent, TimeRange } from "../types";

const timeRange = z.object({ start: z.number(), end: z.number() });

const manifestEvent = z.object({
  id: z.string().min(1),
  kind: z.enum([
    "cut",
    "caption",
    "callout",
    "sfx",
    "music",
    "broll",
    "graphic",
    "segment",
    "other",
  ]),
  out: z.object({ start: z.number(), end: z.number().optional() }),
  src: z.object({ start: z.number(), end: z.number().optional() }).optional(),
  label: z.string().optional(),
  text: z.string().optional(),
  dialogueCut: z.boolean().optional(),
  meta: z.record(z.string(), z.unknown()).optional(),
});

const wordTiming = z.object({
  text: z.string(),
  start: z.number(),
  end: z.number(),
});

export const editManifestSchema = z.object({
  version: z.literal(1),
  lane: z.enum(["reel-recut", "hyperframes", "palmier", "generic"]),
  video: z.string(),
  source: z.string().optional(),
  expectedDuration: z.number().optional(),
  expected: z
    .object({
      width: z.number().optional(),
      height: z.number().optional(),
      fps: z.number().optional(),
    })
    .optional(),
  events: z.array(manifestEvent),
  intentional: z
    .object({
      blackRegions: z.array(timeRange).optional(),
      silentRegions: z.array(timeRange).optional(),
      stillRegions: z.array(timeRange).optional(),
      loudnessTarget: z
        .object({ lufs: z.number(), tolerance: z.number().optional() })
        .optional(),
      noAudio: z.boolean().optional(),
    })
    .optional(),
  words: z.array(wordTiming).optional(),
  sourceWords: z.array(wordTiming).optional(),
});

/** Load + validate a normalized manifest; resolves video/source paths relative
 *  to the manifest file's directory. */
export function loadManifest(path: string): EditManifest {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  const parsed = editManifestSchema.parse(raw) as EditManifest;
  const base = dirname(resolve(path));
  const abs = (p: string) => (isAbsolute(p) ? p : resolve(base, p));
  parsed.video = abs(parsed.video);
  if (parsed.source) parsed.source = abs(parsed.source);
  return parsed;
}

/** Does [start,end] overlap any region (with slack seconds of tolerance)? */
export function inRegions(
  regions: TimeRange[] | undefined,
  start: number,
  end: number,
  slack = 0.2
): boolean {
  if (!regions) return false;
  return regions.some((r) => start >= r.start - slack && end <= r.end + slack);
}

/** Nearest event of the given kinds within `within` seconds of time t. */
export function nearestEvent(
  events: ManifestEvent[],
  t: number,
  within: number,
  kinds?: ManifestEvent["kind"][]
): ManifestEvent | null {
  let best: ManifestEvent | null = null;
  let bestDist = Infinity;
  for (const e of events) {
    if (kinds && !kinds.includes(e.kind)) continue;
    const s = e.out.start;
    const en = e.out.end ?? e.out.start;
    const dist = t < s ? s - t : t > en ? t - en : 0;
    if (dist < bestDist && dist <= within) {
      best = e;
      bestDist = dist;
    }
  }
  return best;
}

/** Events whose output window intersects [start,end]. */
export function eventsInWindow(
  events: ManifestEvent[],
  start: number,
  end: number
): ManifestEvent[] {
  return events.filter((e) => {
    const s = e.out.start;
    const en = e.out.end ?? e.out.start;
    return en >= start && s <= end;
  });
}
