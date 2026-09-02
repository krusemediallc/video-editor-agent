/**
 * video-qa — shared types.
 *
 * Design rules (from a shipped branded edit's post-mortem + the QA plan):
 * - A rendered .mp4 is an AUDIO + VIDEO artifact; every layer treats both streams
 *   as first-class.
 * - Issues anchor to STABLE manifest event ids (lane-native keys), never to raw
 *   timestamps, so issue tracking survives re-renders that shift the timeline.
 * - The manifest describes edit INTENT (emitted by the editor at build time),
 *   never derived by analyzing the rendered output.
 */

export type Lane = "reel-recut" | "hyperframes" | "palmier" | "generic";

export type EventKind =
  | "cut" // an edit seam in the output (material was removed / joined here)
  | "caption"
  | "callout"
  | "sfx"
  | "music"
  | "broll"
  | "graphic"
  | "segment" // a kept span (provenance)
  | "other";

export interface TimeRange {
  start: number;
  end: number;
}

export interface ManifestEvent {
  /** Stable id derived from lane-native keys, e.g. "cut:src12.4", "caption:3". */
  id: string;
  kind: EventKind;
  /** Output-timeline seconds. Instant events (cuts) carry only `start`. */
  out: { start: number; end?: number };
  /** Source-timeline provenance, when known. */
  src?: { start: number; end?: number };
  label?: string;
  /** Caption/callout text for mismatch checks. */
  text?: string;
  /** True when the seam interrupts speech (gets the full boundary battery). */
  dialogueCut?: boolean;
  meta?: Record<string, unknown>;
}

export interface WordTiming {
  text: string;
  start: number;
  end: number;
}

/** Detections that must NOT be flagged because they are deliberate. */
export interface IntentionalSpec {
  blackRegions?: TimeRange[];
  silentRegions?: TimeRange[];
  /** Static cards / freezeframes — exempt from freezedetect. */
  stillRegions?: TimeRange[];
  loudnessTarget?: { lufs: number; tolerance?: number };
  /** Video intentionally has no audio track (e.g. silent carousel slide). */
  noAudio?: boolean;
}

export interface EditManifest {
  version: 1;
  lane: Lane;
  /** Path to the rendered output under test. */
  video: string;
  /** Path to the original source footage, when applicable. */
  source?: string;
  expectedDuration?: number;
  expected?: { width?: number; height?: number; fps?: number };
  events: ManifestEvent[];
  intentional?: IntentionalSpec;
  /** OUTPUT-time word timings, mapped from the SOURCE transcript through the
   *  EDL. NEVER produced by re-transcribing the render (whisper hallucinates at
   *  jump cuts — SESSION_LOG 2026-08-14). */
  words?: WordTiming[];
  /** SOURCE-time words, kept for provenance / re-probe comparisons. */
  sourceWords?: WordTiming[];
}

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type IssueSource = "technical" | "transcript" | "semantic" | "inspection";

export interface SuggestedFix {
  action:
    | "nudge_cut"
    | "retime_caption"
    | "gain_change"
    | "trim_delta"
    | "remove_duplicate"
    | "add_crossfade"
    | "manual";
  params?: Record<string, number | string>;
}

export interface QaIssue {
  /** e.g. "L1-black-001", "L2-clipped-cut:src12.4" */
  id: string;
  source: IssueSource;
  severity: Severity;
  category: string;
  /** Stable manifest anchor — the primary key for fix tracking. */
  eventId: string | null;
  /** Informational; timestamps shift across re-renders, anchors don't. */
  timeWindow: TimeRange;
  message: string;
  /** Objective defect vs subjective suggestion. */
  objective: boolean;
  confidence?: number;
  evidence?: Record<string, unknown>;
  suggestedFix?: SuggestedFix;
  /** Set when two independent layers found the same problem. */
  corroborated?: boolean;
}

export type LayerStatus = "pass" | "warn" | "fail" | "skipped" | "degraded";

export interface LayerResult {
  status: LayerStatus;
  /** Populated for skipped/degraded (e.g. "GEMINI_API_KEY not set"). */
  reason?: string;
  issues: QaIssue[];
  stats?: Record<string, unknown>;
}

export type Verdict = "PASS" | "PASS_WITH_WARNINGS" | "FAIL";

export interface QaReport {
  video: string;
  videoSha256: string;
  manifestPath?: string;
  manifestSha256?: string;
  promptVersion: string;
  model?: string;
  generatedAt: string;
  iteration: number;
  verdict: Verdict;
  layers: {
    technical: LayerResult;
    transcript: LayerResult;
    semantic: LayerResult;
  };
  issues: QaIssue[];
  summary: Record<Severity, number>;
}

/** Bump when detection logic / the Gemini rubric changes — part of the cache key. */
export const QA_PROMPT_VERSION = "1";
