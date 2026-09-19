/** Static storyboard scheduling checks plus evidence sampled from the actual render.
 * Presence/scheduling is NOT a rendered-visibility claim: animation, CSS, occlusion,
 * external compositions and dynamic DOM still require looking at the extracted frames.
 */
import { readFile, writeFile, mkdir, mkdtemp, rename, rm } from "node:fs/promises";
import { join, resolve, basename } from "node:path";
import { z } from "zod";
import { ffmpegBin, ffprobeJson, runCapture, sha256File } from "./ffmpeg";

export const storyboardSchema = z.object({
  version: z.literal(1),
  elements: z.array(z.object({
    id: z.string().min(1),
    label: z.string().optional(),
    selector: z.string().regex(/^#[^\s#]+$/, "Only a single #id selector is supported").optional(),
    start: z.number().finite().nonnegative(),
    end: z.number().finite().positive(),
  }).refine((e) => e.end > e.start, "end must be after start")).min(1),
}).superRefine((s, ctx) => {
  const ids = new Set<string>();
  for (const [i, e] of s.elements.entries()) {
    if (ids.has(e.id)) ctx.addIssue({ code: "custom", path: ["elements", i, "id"], message: `Duplicate storyboard ID: ${e.id}` });
    ids.add(e.id);
  }
});
export type Storyboard = z.infer<typeof storyboardSchema>;
export interface StoryboardElementResult {
  id: string;
  selector: string;
  expected: { start: number; end: number };
  scheduled?: { start: number; end: number };
  status: "covered" | "missing" | "ambiguous" | "unscheduled" | "empty_interval" | "timing_mismatch";
  message: string;
  evidence?: { sheet: string; frames: Array<{ path: string; time: number }>; videoSha256: string };
  evidenceError?: string;
}
export interface StoryboardReport {
  version: 1;
  staticCoverage: "PASS" | "FAIL";
  renderedVisibility: "not_verified";
  evidenceStatus: "not_requested" | "complete" | "incomplete";
  limitations: string;
  html?: string;
  video?: string;
  elements: StoryboardElementResult[];
}
interface HtmlNode { tag: string; attrs: Record<string, string>; parent?: HtmlNode }
const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);
function unescapeAttribute(s: string): string {
  return s.replace(/&(?:amp|quot|apos|lt|gt);/g, (v) => ({ "&amp;": "&", "&quot;": '"', "&apos;": "'", "&lt;": "<", "&gt;": ">" })[v]!);
}
/** A deliberately static tokenizer; never execute a composition's scripts. */
function htmlNodes(html: string): HtmlNode[] {
  const source = html.replace(/<!--[\s\S]*?-->/g, "").replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "");
  const nodes: HtmlNode[] = [], stack: HtmlNode[] = [];
  for (const match of source.matchAll(/<\/?[A-Za-z][^<>"']*(?:(?:"[^"]*"|'[^']*')[^<>"']*)*>/g)) {
    const raw = match[0];
    const tag = /^<\/?([\w:-]+)/.exec(raw)![1].toLowerCase();
    if (raw.startsWith("</")) {
      const i = stack.map((n) => n.tag).lastIndexOf(tag);
      if (i >= 0) stack.length = i;
      continue;
    }
    const attrs: Record<string, string> = {};
    const body = raw.slice(1 + tag.length, -1);
    for (const a of body.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
      attrs[a[1].toLowerCase()] = unescapeAttribute(a[2] ?? a[3] ?? a[4] ?? "");
    }
    const node: HtmlNode = { tag, attrs, parent: stack.at(-1) };
    nodes.push(node);
    if (!VOID.has(tag) && !raw.endsWith("/>")) stack.push(node);
  }
  return nodes;
}
function interval(node: HtmlNode): { start: number; end: number } | null {
  let n: HtmlNode | undefined = node;
  let result: { start: number; end: number } | null = null;
  while (n) {
    const a = n.attrs;
    const timed = ["data-start", "data-end", "data-duration"].some((k) => k in a);
    if (timed) {
      const start = a["data-start"] == null ? 0 : Number(a["data-start"]);
      const end = a["data-end"] != null ? Number(a["data-end"]) : a["data-duration"] != null ? start + Number(a["data-duration"]) : NaN;
      if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
      result = result ? { start: Math.max(result.start, start), end: Math.min(result.end, end) } : { start, end };
    }
    n = n.parent;
  }
  return result;
}

export function validateStoryboard(storyboard: Storyboard, html: string): StoryboardReport {
  const plan = storyboardSchema.parse(storyboard);
  const nodes = htmlNodes(html);
  const elements = plan.elements.map((item): StoryboardElementResult => {
    const selector = item.selector ?? `#${item.id}`;
    const found = nodes.filter((n) => n.attrs.id === selector.slice(1));
    const base = { id: item.id, selector, expected: { start: item.start, end: item.end } };
    if (!found.length) return { ...base, status: "missing", message: "No matching element in the static HTML." };
    if (found.length > 1) return { ...base, status: "ambiguous", message: "The target HTML ID is duplicated." };
    const scheduled = interval(found[0]);
    if (!scheduled) return { ...base, status: "unscheduled", message: "No finite data-start + data-duration/data-end interval on the target or a timed ancestor." };
    if (scheduled.start < 0 || scheduled.end <= scheduled.start) return { ...base, scheduled, status: "empty_interval", message: "Target and ancestor schedules have no positive intersection." };
    if (scheduled.start > item.start + 0.05 || scheduled.end < item.end - 0.05) return { ...base, scheduled, status: "timing_mismatch", message: "Static schedule does not cover the planned interval (50ms tolerance)." };
    return { ...base, scheduled, status: "covered", message: "Element exists and its static schedule covers the plan. Rendered visibility still needs visual review." };
  });
  return {
    version: 1,
    staticCoverage: elements.every((e) => e.status === "covered") ? "PASS" : "FAIL",
    renderedVisibility: "not_verified",
    evidenceStatus: "not_requested",
    limitations: "Static HTML IDs and absolute output-time data-start/data-duration/data-end only. Timed ancestors intersect the target interval. Does not evaluate JavaScript/GSAP, CSS visibility, occlusion, nested composition offsets, or external HTML. Actual-render samples are evidence for human/agent review, not proof of continuous visibility.",
    elements,
  };
}

export async function runStoryboardQa(options: { storyboard: string; html: string; video?: string; outDir: string }): Promise<StoryboardReport> {
  const plan = storyboardSchema.parse(JSON.parse(await readFile(options.storyboard, "utf8")));
  const report = validateStoryboard(plan, await readFile(options.html, "utf8"));
  report.html = resolve(options.html);
  report.video = options.video ? resolve(options.video) : undefined;
  await mkdir(options.outDir, { recursive: true });
  if (options.video) {
    report.evidenceStatus = "complete";
    try {
      // A successful ffmpeg process can emit zero frames near EOF. Never reuse
      // a previous run's same-named images and relabel them with new timestamps.
      const evidenceDir = await mkdtemp(join(options.outDir, "evidence-"));
      const evidenceRelative = basename(evidenceDir);
      const verifyPng = async (path: string) => {
        const bytes = await readFile(path);
        if (bytes.length < 24 || bytes.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a" || bytes.readUInt32BE(16) === 0 || bytes.readUInt32BE(20) === 0) throw new Error("Frame extraction did not produce a nonempty PNG");
      };
      const probe = await ffprobeJson(options.video);
      const duration = Number(probe.format.duration);
      if (!probe.streams.some((s) => s.codec_type === "video") || !Number.isFinite(duration) || duration <= 0) throw new Error("Render has no readable video/duration");
      const videoSha256 = await sha256File(options.video);
      for (const [i, item] of report.elements.entries()) {
        try {
          if (item.expected.end > duration + 0.05) throw new Error(`Planned interval ends after the measured render (${duration.toFixed(3)}s)`);
          const prefix = `element-${String(i + 1).padStart(3, "0")}`;
          const span = item.expected.end - item.expected.start;
          const frames: Array<{ path: string; time: number }> = [];
          for (const [j, fraction] of [0.1, 0.5, 0.9].entries()) {
            const time = Math.min(duration - 0.001, item.expected.start + span * fraction);
            const path = join(evidenceRelative, `${prefix}-${j + 1}.png`);
            await runCapture(ffmpegBin(), ["-nostdin", "-y", "-ss", time.toFixed(6), "-i", options.video, "-frames:v", "1", "-vf", "scale=320:-2", join(options.outDir, path)]);
            await verifyPng(join(options.outDir, path));
            frames.push({ path, time });
          }
          const sheet = join(evidenceRelative, `${prefix}-contact-sheet.png`);
          await runCapture(ffmpegBin(), ["-nostdin", "-y", ...frames.flatMap((f) => ["-i", join(options.outDir, f.path)]), "-filter_complex", "[0:v][1:v][2:v]hstack=inputs=3", "-frames:v", "1", join(options.outDir, sheet)]);
          await verifyPng(join(options.outDir, sheet));
          item.evidence = { sheet, frames, videoSha256 };
        } catch (e) { item.evidenceError = (e as Error).message; report.evidenceStatus = "incomplete"; }
      }
    } catch (e) {
      report.evidenceStatus = "incomplete";
      for (const item of report.elements) item.evidenceError = (e as Error).message;
    }
  }
  const lines = ["# Storyboard coverage and render evidence", "", `Static coverage: **${report.staticCoverage}**. Evidence: **${report.evidenceStatus}**. Rendered visibility: **not verified**.`, "", report.limitations, ""];
  for (const item of report.elements) {
    lines.push(`## ${item.id}`, "", `${item.expected.start}–${item.expected.end}s · ${item.selector} · **${item.status}**`, "", item.message, "");
    if (item.scheduled) lines.push(`Static interval: ${item.scheduled.start}–${item.scheduled.end}s.`, "");
    if (item.evidence) lines.push(`![Actual render samples for ${item.id}](${item.evidence.sheet})`, "", `Requested sample positions, left to right: ${item.evidence.frames.map((f) => `${f.time.toFixed(3)}s`).join(", ")}. Render SHA-256: ${item.evidence.videoSha256}.`, "");
    if (item.evidenceError) lines.push(`Evidence unavailable: ${item.evidenceError}`, "");
  }
  const staging = await mkdtemp(join(options.outDir, ".report-"));
  try {
    await writeFile(join(staging, "storyboard-report.json"), JSON.stringify(report, null, 2));
    await writeFile(join(staging, "storyboard-report.md"), lines.join("\n"));
    await rename(join(staging, "storyboard-report.json"), join(options.outDir, "storyboard-report.json"));
    await rename(join(staging, "storyboard-report.md"), join(options.outDir, "storyboard-report.md"));
  } finally { await rm(staging, { recursive: true, force: true }); }
  return report;
}
