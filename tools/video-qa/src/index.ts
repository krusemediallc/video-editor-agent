/**
 * video-qa orchestrator — the four-layer funnel, cheap → expensive:
 *   1. ffmpeg/ffprobe technical QA (video + audio)      — always
 *   2. transcript edit-boundary QA                       — always (degrades)
 *   3. Gemini whole-video watch+listen                   — unless skipped/no key
 *   4. targeted inspection packets                       — for issues that need eyes
 *
 * If a deterministic tool can answer something, the deterministic tool answers
 * it. Gemini's job is to tell Claude WHERE to look; Claude verifies with
 * inspection packets before changing any edit.
 */
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import type { EditManifest, LayerResult, QaReport, QaLayerName } from "./types";
import { sha256File, sha256Text } from "./ffmpeg";
import { runTechnicalLayer, DEFAULT_THRESHOLDS, type Thresholds } from "./layer1-technical";
import { runTranscriptLayer, DEFAULT_L2_OPTIONS, type L2Options } from "./layer2-transcript";
import { runSemanticLayer } from "./layer3-semantic";
import { inspectWindow } from "./inspect";
import { aggregate, writeReport } from "./report";
import { cacheGet, cacheKey, cachePut } from "./cache";
import { geminiModel } from "./gemini";
import { editManifestSchema } from "./manifest/schema";

export type { EditManifest, QaReport, QaIssue } from "./types";
export { loadManifest } from "./manifest/schema";
export { buildHyperframesManifest } from "./manifest/adapter-hyperframes";
export { inspectWindow } from "./inspect";
export { exitCode } from "./report";
export { validateStoryboard, runStoryboardQa, storyboardSchema } from "./storyboard";

export interface RunQaOptions {
  manifest: EditManifest;
  manifestPath?: string;
  skipSemantic?: boolean;
  instructions?: string;
  geminiFps?: number;
  /** Auto-build inspection packets for the top N issues (default 4). */
  autoInspect?: number;
  outDir?: string;
  noCache?: boolean;
  log?: (msg: string) => void;
  requiredLayers?: QaLayerName[];
  technicalThresholds?: Partial<Thresholds>;
  transcriptOptions?: L2Options;
  /** Dependency injection for offline regression tests and alternate backends. */
  runners?: Partial<{
    technical: typeof runTechnicalLayer;
    transcript: typeof runTranscriptLayer;
    semantic: typeof runSemanticLayer;
  }>;
}

function maxIterations(): number {
  return Number(process.env.VIDEO_QA_MAX_REPAIR_ITERATIONS || 3);
}

function inspectPadding(): number {
  return Number(process.env.VIDEO_QA_INSPECT_PADDING_S || 1.5);
}

export async function runQa(opts: RunQaOptions): Promise<{ report: QaReport; outDir: string }> {
  const log = opts.log ?? ((m: string) => console.log(m));
  const manifest = editManifestSchema.parse(opts.manifest) as EditManifest;
  const video = manifest.video;
  if (!existsSync(video)) {
    throw new Error(`Rendered video not found: ${video}`);
  }

  const outDir =
    opts.outDir ?? join(dirname(video), "_qa", basename(video).replace(/\.\w+$/, ""));
  mkdirSync(outDir, { recursive: true });

  const videoSha = await sha256File(video);
  const manifestSha = sha256Text(JSON.stringify(manifest));
  const sourceSha = manifest.source && existsSync(manifest.source) ? await sha256File(manifest.source) : null;

  // Iteration counter persists across fix→rerender→re-QA rounds in this dir.
  let iteration = 1;
  const prevPath = join(outDir, "qa-report.json");
  if (existsSync(prevPath)) {
    try {
      const prev = JSON.parse(readFileSync(prevPath, "utf8")) as QaReport;
      iteration = prev.videoSha256 === videoSha ? prev.iteration : prev.iteration + 1;
    } catch {
      /* fresh start */
    }
  }
  if (iteration > maxIterations()) {
    log(
      `[qa] MAX_ITERATIONS (${maxIterations()}) exceeded — stop looping; surface remaining issues for human review.`
    );
  }

  const runLayer = async (
    layer: string,
    model: string | undefined,
    fn: () => Promise<LayerResult>,
    config: unknown
  ): Promise<LayerResult> => {
    const key = cacheKey({ videoSha, manifestSha, layer, model, config });
    if (!opts.noCache) {
      try {
      const hit = cacheGet(key);
      if (hit && hit.status !== "degraded" && hit.status !== "skipped") {
        log(`[qa:${layer}] cache hit — unchanged video+manifest`);
        return hit;
      }
      } catch (e) { log(`[qa:${layer}] cache unavailable: ${(e as Error).message}`); }
    }
    try {
      const result = await fn();
      if (!opts.noCache && result.status !== "skipped" && result.status !== "degraded") {
        try { await cachePut(key, result); }
        catch (e) { log(`[qa:${layer}] could not cache completed checks: ${(e as Error).message}`); }
      }
      return result;
    } catch (e) {
      const reason = `${layer} failed: ${(e as Error).message}`;
      log(`[qa] ${reason}`);
      return { status: "degraded", reason, issues: [] };
    }
  };

  log(`[qa] Technical analysis (video+audio) started`);
  const technical = await runLayer("L1", undefined, () => (opts.runners?.technical ?? runTechnicalLayer)(manifest, opts.technicalThresholds, log),
    { thresholds: { ...DEFAULT_THRESHOLDS, ...opts.technicalThresholds }, ffmpeg: process.env.FFMPEG_PATH, ffprobe: process.env.FFPROBE_PATH });
  log(`[qa] Technical analysis ${technical.status} (${technical.issues.length} issues)`);

  const transcript: LayerResult = technical.issues.some((i) => ["corrupt_file", "missing_video_stream"].includes(i.category))
    ? { status: "skipped" as const, reason: "Video could not be read", issues: [] }
    : await runLayer("L2", undefined, () => (opts.runners?.transcript ?? runTranscriptLayer)(manifest, opts.transcriptOptions, log),
      { sourceSha, options: { ...DEFAULT_L2_OPTIONS, ...opts.transcriptOptions }, backend: process.env.VIDEO_QA_TRANSCRIBER ?? "auto", cloudAvailable: Boolean(process.env.OPENAI_API_KEY) });
  log(
    `[qa] Transcript boundary check ${transcript.status}: ${(transcript.stats?.dialogueCuts as number) ?? 0} dialogue cuts analyzed, ${transcript.issues.length} issues`
  );

  let semantic: LayerResult;
  if (opts.skipSemantic) {
    semantic = { status: "skipped", reason: "--skip-semantic", issues: [] };
  } else {
    const fps = opts.geminiFps ?? (process.env.VIDEO_QA_GEMINI_FPS ? Number(process.env.VIDEO_QA_GEMINI_FPS) : Number(technical.stats?.duration ?? manifest.expectedDuration ?? 0) < 180 ? 5 : 1);
    semantic = await runLayer("L3", geminiModel(), () => {
      if (!Number.isFinite(fps) || fps <= 0) throw new Error("Semantic FPS must be a positive finite number");
      return (opts.runners?.semantic ?? runSemanticLayer)(manifest, { instructions: opts.instructions, fps, log });
    },
      { instructions: opts.instructions ?? "", fps, available: Boolean(process.env.GEMINI_API_KEY) }
    );
  }

  const report = aggregate({
    video,
    videoSha256: videoSha,
    manifestPath: opts.manifestPath,
    manifestSha256: manifestSha,
    model: semantic.status === "skipped" ? undefined : geminiModel(),
    iteration,
    technical,
    transcript,
    semantic,
    requiredLayers: opts.requiredLayers,
  });

  // Layer 4: auto-inspect the top issues so the packet is ready for review.
  const toInspect = report.issues
    .filter((i) => i.severity === "CRITICAL" || i.severity === "HIGH")
    .slice(0, opts.autoInspect ?? 4);
  for (const issue of toInspect) {
    const pad = issue.source === "semantic" ? inspectPadding() : 0.5;
    const dir = join(outDir, "inspect", issue.id);
    log(
      `[qa] Inspecting ${(issue.timeWindow.start - pad).toFixed(1)}s–${(issue.timeWindow.end + pad).toFixed(1)}s (${issue.id}: frames+waveform+audio+transcript)`
    );
    try {
      await inspectWindow(
        { ...manifest, words: transcript.outputWords ?? manifest.words },
        issue.timeWindow.start - pad,
        issue.timeWindow.end + pad,
        dir,
        {},
        log
      );
    } catch (e) {
      log(`[qa] inspection failed for ${issue.id}: ${(e as Error).message.slice(0, 200)}`);
    }
  }

  await writeReport(report, outDir);
  log(
    `[qa] Final QA: ${report.verdict} — ${report.summary.CRITICAL} critical, ${report.summary.HIGH} high, ${report.summary.MEDIUM} medium, ${report.summary.LOW} low → ${join(outDir, "qa-report.md")}`
  );
  return { report, outDir };
}
