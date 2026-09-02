/**
 * Layer 3 — whole-video semantic QA: Gemini WATCHES AND LISTENS to the render.
 *
 * - Sends a compressed proxy (480p) with the AUDIO INTACT at 128k AAC — half of
 *   real editing mistakes are audible.
 * - Frame sampling rate is set via video_metadata.fps (default 5 for short ads;
 *   Gemini's 1fps default misses fast visual events).
 * - JSON output is ENFORCED via responseSchema, not prompt-please.
 * - Gemini timestamps are approximate (±1–2s); issues get padded windows and
 *   anchor to the nearest manifest event. Gemini's job is to tell Claude WHERE
 *   to look — Layer 4 verifies before anything is changed.
 * - Graceful skip when GEMINI_API_KEY is missing.
 */
import { mkdtempSync } from "node:fs";
import { rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { EditManifest, LayerResult, QaIssue, Severity } from "./types";
import { ffmpegBin, ffprobeJson, runCapture } from "./ffmpeg";
import { geminiGenerateJson, geminiKey, geminiModel, uploadFileToGemini, type GeminiPart } from "./gemini";
import { nearestEvent } from "./manifest/schema";

const RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    issues: {
      type: "array",
      items: {
        type: "object",
        properties: {
          startSec: { type: "number" },
          endSec: { type: "number" },
          severity: { type: "string", enum: ["high", "medium", "low"] },
          category: {
            type: "string",
            enum: [
              "abrupt_cut",
              "clipped_dialogue",
              "audio_glitch",
              "music_balance",
              "sync_issue",
              "dead_air",
              "caption_error",
              "visual_glitch",
              "duplicate_footage",
              "framing_crop",
              "graphic_timing",
              "pacing",
              "content_error",
              "other",
            ],
          },
          objective: { type: "boolean" },
          confidence: { type: "number" },
          description: { type: "string" },
        },
        required: ["startSec", "endSec", "severity", "category", "objective", "description"],
      },
    },
    overallNotes: { type: "string" },
  },
  required: ["issues"],
};

interface GeminiIssue {
  startSec: number;
  endSec: number;
  severity: "high" | "medium" | "low";
  category: string;
  objective: boolean;
  confidence?: number;
  description: string;
}

interface GeminiReview {
  issues: GeminiIssue[];
  overallNotes?: string;
}

function manifestSummary(manifest: EditManifest): string {
  const cuts = manifest.events.filter((e) => e.kind === "cut");
  const caps = manifest.events.filter((e) => e.kind === "caption");
  const other = manifest.events.filter((e) => !["cut", "caption"].includes(e.kind));
  const lines: string[] = [];
  lines.push(`Lane: ${manifest.lane}. Expected duration: ${manifest.expectedDuration ?? "?"}s.`);
  if (cuts.length) {
    lines.push(
      `Edit seams (intentional jump-cut style) at output seconds: ${cuts
        .map((c) => c.out.start.toFixed(1))
        .join(", ")}.`
    );
  }
  if (caps.length) {
    lines.push(`Captions: ${caps.length} timed caption events (word-synced karaoke style is intentional).`);
  }
  if (other.length) {
    lines.push(
      `Placed elements: ${other
        .slice(0, 40)
        .map((e) => `${e.kind}@${e.out.start.toFixed(1)}s${e.label ? ` (${e.label})` : ""}`)
        .join(", ")}.`
    );
  }
  const intent = manifest.intentional ?? {};
  if (intent.blackRegions?.length) {
    lines.push(
      `INTENTIONAL black/dark regions: ${intent.blackRegions.map((r) => `${r.start}-${r.end}s`).join(", ")}.`
    );
  }
  if (intent.silentRegions?.length) {
    lines.push(
      `INTENTIONAL silences: ${intent.silentRegions.map((r) => `${r.start}-${r.end}s`).join(", ")}.`
    );
  }
  return lines.join("\n");
}

function buildPrompt(manifest: EditManifest, instructions?: string): string {
  return [
    "You are a professional short-form video editor doing final QA on an export before it ships.",
    "The file has BOTH video and audio. Review them TOGETHER — listen while you watch. Roughly half of real editing mistakes are audible, not visible (clipped words at cuts, duplicate phrases, abrupt music, dead air, clicks at splices, SFX drowning the voice).",
    "",
    "Report across both modalities:",
    "- VISUAL: glitches, stray/duplicate frames, wrong or repeated footage, jarring transitions, bad crop or framing, subject cut off, graphics appearing/disappearing at wrong times, captions covering the speaker's face, caption timing/text problems, unintended blank space, abrupt start or ending, b-roll that doesn't match what is being said.",
    "- AUDIO & AUDIO-VISUAL: words cut off mid-syllable, dialogue repeated across a cut, audio/video desync, dead air, unintentional silence, music starting/stopping abruptly, music/dialogue balance, sound effects mistimed or masking speech, pacing problems.",
    "",
    "Calibration — follow exactly:",
    "- Zero issues is a valid and expected outcome for a clean video. Do not invent problems.",
    "- Report mistakes, unintended behavior, deviations from instructions, and obvious quality problems. Do not fail the video because you would make a different creative choice.",
    "- Separate objective errors (objective=true) from subjective suggestions (objective=false) and label each.",
    "- Fast jump cuts, karaoke captions, and bold graphic cards are the INTENTIONAL style of these edits — only flag a cut if something is audibly or visibly broken at it.",
    "- Your timestamps may be off by ±2 seconds; report your best estimate without agonizing over precision.",
    "",
    "Edit intent (from the editing system — treat as ground truth for what is deliberate):",
    manifestSummary(manifest),
    instructions ? `\nOriginal editing request/instructions:\n${instructions}` : "",
    "",
    "Return JSON only, matching the response schema.",
  ].join("\n");
}

async function makeProxy(video: string, outPath: string): Promise<void> {
  await runCapture(ffmpegBin(), [
    "-nostdin",
    "-y",
    "-i",
    video,
    "-vf",
    "scale=-2:480,fps=15",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "30",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-movflags",
    "+faststart",
    outPath,
  ]);
}

const sevMap: Record<string, Severity> = { high: "HIGH", medium: "MEDIUM", low: "LOW" };

export async function runSemanticLayer(
  manifest: EditManifest,
  opts: { instructions?: string; fps?: number; log?: (m: string) => void } = {}
): Promise<LayerResult> {
  const log = opts.log ?? (() => {});
  if (!geminiKey()) {
    log("[qa:L3] semantic QA skipped — GEMINI_API_KEY not set");
    return { status: "skipped", reason: "GEMINI_API_KEY not set", issues: [] };
  }

  const probe = await ffprobeJson(manifest.video);
  const duration = parseFloat(probe.format.duration ?? "0");
  const fps =
    opts.fps ??
    (process.env.VIDEO_QA_GEMINI_FPS ? Number(process.env.VIDEO_QA_GEMINI_FPS) : duration < 180 ? 5 : 1);

  const dir = mkdtempSync(join(tmpdir(), "vqa-proxy-"));
  const proxyPath = join(dir, "proxy.mp4");
  try {
    log(`[qa:L3] building 480p proxy (audio intact @128k)`);
    await makeProxy(manifest.video, proxyPath);
    log(`[qa:L3] uploading proxy; gemini reviewing ${duration.toFixed(1)}s @ ${fps}fps sampling (audio included)`);
    const file = await uploadFileToGemini(proxyPath, "video/mp4", "qa-proxy.mp4", log);

    const parts: GeminiPart[] = [
      {
        file_data: { file_uri: file.uri, mime_type: "video/mp4" },
        video_metadata: { fps },
      },
      { text: buildPrompt(manifest, opts.instructions) },
    ];

    let review: GeminiReview;
    try {
      review = await geminiGenerateJson<GeminiReview>(parts, RESPONSE_SCHEMA);
    } catch (e) {
      return {
        status: "skipped",
        reason: `Gemini call failed: ${(e as Error).message.slice(0, 300)}`,
        issues: [],
      };
    }

    const issues: QaIssue[] = (review.issues ?? []).map((gi, i) => {
      const start = Math.max(0, Math.min(gi.startSec, duration));
      const end = Math.max(start, Math.min(gi.endSec, duration));
      const anchor = nearestEvent(manifest.events, (start + end) / 2, 2.0);
      return {
        id: `L3-${gi.category}-${String(i + 1).padStart(3, "0")}`,
        source: "semantic",
        // Gemini alone never exceeds HIGH; corroboration is applied in report.ts.
        severity: sevMap[gi.severity] ?? "LOW",
        category: gi.category,
        eventId: anchor?.id ?? null,
        timeWindow: { start, end },
        message: gi.description,
        objective: gi.objective,
        confidence: gi.confidence,
        evidence: { geminiReported: [gi.startSec, gi.endSec], model: geminiModel() },
      };
    });

    log(`[qa:L3] gemini identified ${issues.length} possible issue(s)`);
    return {
      status: issues.some((i) => i.severity === "HIGH") ? "fail" : issues.length ? "warn" : "pass",
      issues,
      stats: { model: geminiModel(), fps, overallNotes: review.overallNotes, proxyDuration: duration },
    };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
