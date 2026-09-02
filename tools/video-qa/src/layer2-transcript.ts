/**
 * Layer 2 — deterministic audio/transcript edit-boundary QA.
 *
 * Runs on EVERY dialogue cut (near-free). The primary signal is SOURCE-side
 * word timings checked against the manifest's cut provenance — never a full
 * re-whisper of the render (it hallucinates at jump cuts; SESSION_LOG
 * 2026-08-14). Marginal calls escalate to an isolated short-window re-probe of
 * the render, the formalized `join_check.wav` practice.
 *
 * Checks:
 *   - clipped word      cut lands inside a spoken word (source-side straddle)
 *   - repeated word     same word both sides of a seam (duplicate stumble)
 *   - seam dead air     word gap across a cut beyond threshold, uncovered
 *   - caption mismatch  caption text vs words in its window / orphan captions
 *   - butt-splice click sample-difference spike in a ±40ms window at the join
 */
import type { EditManifest, LayerResult, QaIssue, Severity, WordTiming } from "./types";
import { ffmpegBin, runCapture } from "./ffmpeg";
import { eventsInWindow } from "./manifest/schema";
import { acquireWords, probeWindow } from "./transcribe";

export interface L2Options {
  /** Word must overlap the removed region by more than this to count as clipped. */
  clipToleranceSec?: number;
  seamDeadAirSec?: number;
  captionSimilarityMin?: number;
  /** astats Max difference above this in the join window = click risk. */
  clickMaxDiff?: number;
  maxProbes?: number;
  probeEnabled?: boolean;
}

const DEFAULTS: Required<L2Options> = {
  clipToleranceSec: 0.06,
  seamDeadAirSec: 0.7,
  captionSimilarityMin: 0.75,
  clickMaxDiff: 0.35,
  maxProbes: 40,
  probeEnabled: true,
};

const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}']/gu, "");

/** Coverage of `a`'s tokens inside `b` (0..1). Asymmetric on purpose: a
 *  caption is wrong when its words were never SPOKEN; extra spoken context
 *  around the caption window is normal and must not dilute the score. */
function coverage(a: string, b: string): number {
  const ta = a.split(/\s+/).map(norm).filter(Boolean);
  const tb = b.split(/\s+/).map(norm).filter(Boolean);
  if (!ta.length) return 1;
  if (!tb.length) return 0;
  // Prefix-stem matching (≥4 chars) so "info"/"information" and
  // "generate"/"generated" count as spoken — captions legitimately compress
  // morphology without being wrong.
  const stem = (t: string) => (t.length > 4 ? t.slice(0, 4) : t);
  const remaining = [...tb];
  let hit = 0;
  for (const t of ta) {
    const idx = remaining.findIndex(
      (r) => r === t || (t.length >= 4 && r.length >= 4 && stem(r) === stem(t))
    );
    if (idx >= 0) {
      hit += 1;
      remaining.splice(idx, 1);
    }
  }
  return hit / ta.length;
}

/** Physically measured silence spans in a window (silencedetect -40dB, ≥0.3s).
 *  Word-gap arithmetic alone lies when whisper mistimes words — a "gap" where
 *  the meter shows speech-level audio is a transcription artifact, not dead
 *  air (live false positive on the 0815 reel: "Marketing Pro" mistimed). */
async function measuredSilenceInWindow(
  video: string,
  start: number,
  end: number
): Promise<number> {
  try {
    const res = await runCapture(
      ffmpegBin(),
      [
        "-nostdin", "-hide_banner",
        "-ss", Math.max(0, start).toFixed(3),
        "-t", Math.max(0.1, end - start).toFixed(3),
        "-i", video,
        "-af", "silencedetect=noise=-40dB:d=0.3",
        "-vn", "-f", "null", "-",
      ],
      { allowNonZero: true }
    );
    const starts = [...res.stderr.matchAll(/silence_start:\s*([-\d.]+)/g)].map((m) => parseFloat(m[1]));
    const ends = [...res.stderr.matchAll(/silence_end:\s*([-\d.]+)/g)].map((m) => parseFloat(m[1]));
    let total = 0;
    for (let i = 0; i < starts.length; i++) {
      total += (ends[i] ?? end - start) - starts[i];
    }
    return total;
  } catch {
    return -1; // unknown — caller should trust the word gap
  }
}

async function joinClickStat(video: string, t: number): Promise<number | null> {
  try {
    const res = await runCapture(
      ffmpegBin(),
      [
        "-nostdin",
        "-hide_banner",
        "-ss",
        Math.max(0, t - 0.04).toFixed(3),
        "-t",
        "0.08",
        "-i",
        video,
        "-af",
        "astats=metadata=0",
        "-vn",
        "-f",
        "null",
        "-",
      ],
      { allowNonZero: true }
    );
    const m = [...res.stderr.matchAll(/Max difference:\s*([\d.]+)/g)];
    if (!m.length) return null;
    return parseFloat(m[m.length - 1][1]);
  } catch {
    return null;
  }
}

export async function runTranscriptLayer(
  manifest: EditManifest,
  options: L2Options = {},
  log: (msg: string) => void = () => {}
): Promise<LayerResult> {
  const opt = { ...DEFAULTS, ...options };
  const issues: QaIssue[] = [];
  let seq = 0;
  const push = (
    category: string,
    severity: Severity,
    eventId: string | null,
    start: number,
    end: number,
    message: string,
    extra?: Partial<QaIssue>
  ) => {
    seq += 1;
    issues.push({
      id: `L2-${category}-${String(seq).padStart(3, "0")}`,
      source: "transcript",
      severity,
      category,
      eventId,
      timeWindow: { start, end },
      message,
      objective: true,
      ...extra,
    });
  };

  const cuts = manifest.events.filter((e) => e.kind === "cut");
  const dialogueCuts = cuts.filter((e) => e.dialogueCut !== false);
  const { words, sourceWords, via } = await acquireWords(manifest, log);

  if (!words && !sourceWords) {
    // Degraded: no transcript available at all — the click check still runs.
    log("[qa:L2] degraded: no word timings available (no manifest words, no source, or transcriber unavailable)");
    for (const cut of dialogueCuts) {
      const diff = await joinClickStat(manifest.video, cut.out.start);
      if (diff != null && diff > opt.clickMaxDiff) {
        push(
          "splice_click",
          "MEDIUM",
          cut.id,
          cut.out.start - 0.04,
          cut.out.start + 0.04,
          `Sample-difference spike (${diff.toFixed(2)}) at the ${cut.id} join — butt-splice click risk.`,
          { suggestedFix: { action: "add_crossfade", params: { ms: 25 } } }
        );
      }
    }
    return {
      status: "degraded",
      reason: "no word timings; ran click checks only",
      issues,
      stats: { dialogueCuts: dialogueCuts.length, wordsVia: via },
    };
  }

  log(`[qa:L2] boundary check: ${dialogueCuts.length} dialogue cuts, words via ${via}`);

  // ---- 1. Clipped words (source-side straddle) ------------------------------
  // A cut whose removed region was DERIVED FROM MEASURED SILENCE (reel-recut
  // silence_cut, meta.origin === "silence") cannot clip audible speech — any
  // word "overlap" there is whisper end-padding (word ends are routinely
  // stretched into the following pause; verified live on the shipped 0814
  // reel: 40/49 cuts false-flagged before this gate). Those become suspects
  // only via the probe; manual/EDL cuts get the strict treatment.
  const clippedSuspects: Array<{
    cutId: string;
    outT: number;
    word: WordTiming;
    side: "tail" | "head";
    overlap: number;
    silenceOrigin: boolean;
  }> = [];
  if (sourceWords) {
    for (const cut of dialogueCuts) {
      if (!cut.src || cut.src.end == null) continue;
      const rs = cut.src.start;
      const re = cut.src.end;
      const silenceOrigin = (cut.meta as { origin?: string } | undefined)?.origin === "silence";
      const tol = silenceOrigin ? 0.25 : opt.clipToleranceSec;
      for (const w of sourceWords) {
        // Word runs INTO the removed region: its tail may be cut off.
        if (w.start < rs - 1e-3 && w.end > rs + tol) {
          clippedSuspects.push({ cutId: cut.id, outT: cut.out.start, word: w, side: "tail", overlap: Math.min(w.end, re) - rs, silenceOrigin });
        }
        // Word begins INSIDE the removed region and continues past it: head cut off.
        if (w.start < re - tol && w.end > re + 1e-3 && w.start > rs - 1e-3) {
          clippedSuspects.push({ cutId: cut.id, outT: cut.out.start, word: w, side: "head", overlap: re - Math.max(w.start, rs), silenceOrigin });
        }
      }
    }
  }

  // Isolated re-probes (the formalized join_check.wav practice): whisper the
  // RENDER around the seam only, and arbitrate by whether the flagged word is
  // HEARD there. Word present near the seam → whisper source-timing overshoot,
  // not a real clip. Never trust whisper durations — only presence/absence.
  let probesUsed = 0;
  for (const s of clippedSuspects) {
    let severity: Severity = s.silenceOrigin ? "LOW" : "HIGH";
    let confidence = s.silenceOrigin ? 0.3 : 0.75;
    let probeVerdict = "not probed";
    const evidence: Record<string, unknown> = {
      word: s.word.text,
      sourceSpan: [Number(s.word.start.toFixed(2)), Number(s.word.end.toFixed(2))],
      clippedSide: s.side,
      overlapSec: Number(s.overlap.toFixed(3)),
      cutOrigin: s.silenceOrigin ? "silence" : "manual/edl",
    };
    if (opt.probeEnabled && probesUsed < opt.maxProbes) {
      probesUsed += 1;
      // 5.5s window: whisper drops words at the edges of short clips (a 3s
      // window failed to hear an intact word live on the 0814 reel), so give
      // it a full phrase either side of the seam.
      const probe = await probeWindow(manifest.video, s.outT - 2.75, 5.5);
      if (probe) {
        evidence.probeTranscript = probe.map((w) => w.text).join(" ");
        const target = norm(s.word.text);
        const heard = probe.some(
          (w) => norm(w.text) === target && Math.abs(w.start - s.outT) < 1.5
        );
        if (heard) {
          severity = "LOW";
          confidence = 0.2;
          probeVerdict = "word heard intact at seam — source-timing overshoot";
        } else {
          severity = "HIGH";
          confidence = 0.9;
          probeVerdict = "word NOT heard at seam — clip confirmed";
        }
        evidence.probeVerdict = probeVerdict;
      }
    }
    if (s.silenceOrigin && severity === "LOW" && probeVerdict !== "word NOT heard at seam — clip confirmed") {
      continue; // silence-origin + unconfirmed = whisper overshoot noise, drop entirely
    }
    const fixDelta = Math.round(s.overlap * 1000) + 60;
    push(
      "clipped_word",
      severity,
      s.cutId,
      s.outT - 0.3,
      s.outT + 0.3,
      `Cut ${s.cutId} lands inside "${s.word.text}" (source ${s.word.start.toFixed(2)}–${s.word.end.toFixed(2)}s) — ${s.side} of the word is cut off${probeVerdict.startsWith("word NOT") ? " (probe-confirmed)" : ""}.`,
      {
        confidence,
        evidence,
        suggestedFix: {
          action: "nudge_cut",
          params: {
            eventId: s.cutId,
            direction: s.side === "tail" ? "later" : "earlier",
            ms: fixDelta,
          },
        },
      }
    );
  }

  // ---- 2-3. Repeated words + seam dead air (output-time words) -------------
  if (words?.length) {
    const sorted = [...words].sort((a, b) => a.start - b.start);
    for (const cut of dialogueCuts) {
      const t = cut.out.start;
      if (t <= 0.02) continue; // head trim has no left side
      const before = sorted.filter((w) => w.end <= t + 0.02).slice(-2);
      const after = sorted.filter((w) => w.start >= t - 0.02).slice(0, 2);

      // A duplicate-from-trimming repeats ADJACENT to the seam (last word ==
      // first word) or repeats a whole bigram. A content word recurring one
      // position away is normal copy ("…the tracking issue. | Server-side
      // tracking…" — real example that false-flagged on a shipped branded edit).
      // Causal gate: a SILENCE-origin cut removes only a pause and cannot
      // manufacture duplicate dialogue — single-word repeats across it are
      // script style ("garbage in, | garbage out" false-flagged live). Only
      // manual/EDL cuts (retake splices) arm the single-word check.
      const silenceOriginCut = (cut.meta as { origin?: string } | undefined)?.origin === "silence";
      const lastB = before[before.length - 1];
      const firstA = after[0];
      const isDup =
        !silenceOriginCut &&
        lastB &&
        firstA &&
        norm(lastB.text).length >= 3 &&
        norm(lastB.text) === norm(firstA.text) &&
        firstA.start - lastB.end < 1.5;
      const isBigramDup =
        before.length >= 2 &&
        after.length >= 2 &&
        norm(before[0].text) === norm(after[0].text) &&
        norm(before[1].text) === norm(after[1].text) &&
        (norm(before[0].text).length >= 3 || norm(before[1].text).length >= 3);
      if (isDup || isBigramDup) {
        const phrase = isBigramDup ? `${before[0].text} ${before[1].text}` : lastB.text;
        push(
          "repeated_word",
          "HIGH",
          cut.id,
          (isBigramDup ? before[0] : lastB).start,
          (isBigramDup ? after[1] : firstA).end,
          `"${phrase}" is spoken on BOTH sides of ${cut.id} — duplicate dialogue from trimming.`,
          { suggestedFix: { action: "remove_duplicate", params: { eventId: cut.id, word: phrase } } }
        );
      }

      if (before.length && after.length) {
        const gapStart = before[before.length - 1].end;
        const gapEnd = after[0].start;
        const gap = gapEnd - gapStart;
        if (gap > opt.seamDeadAirSec) {
          const covered = eventsInWindow(manifest.events, gapStart, gapEnd)
            .some((e) => ["graphic", "broll", "callout", "sfx"].includes(e.kind));
          // Confirm against the meter: only real when the render is actually
          // quiet there — a word-gap over speech-level audio is whisper
          // mistiming, not dead air.
          const silent = covered ? 0 : await measuredSilenceInWindow(manifest.video, gapStart, gapEnd);
          if (!covered && (silent < 0 || silent >= gap * 0.5)) {
            push(
              "seam_dead_air",
              "MEDIUM",
              cut.id,
              gapStart,
              gapEnd,
              `${gap.toFixed(2)}s gap across ${cut.id} with nothing covering it (${silent >= 0 ? `${silent.toFixed(2)}s measured silence` : "silence unmeasured"}).`,
              { evidence: { wordGapSec: gap, measuredSilenceSec: silent } }
            );
          }
        }
      }
    }

    // ---- 4. Caption vs transcript -----------------------------------------
    for (const cap of manifest.events.filter((e) => e.kind === "caption" && e.text)) {
      const end = cap.out.end ?? cap.out.start;
      const inWin = sorted.filter((w) => w.end > cap.out.start - 0.15 && w.start < end + 0.15);
      if (!inWin.length) {
        push(
          "caption_orphaned",
          "HIGH",
          cap.id,
          cap.out.start,
          end,
          `Caption "${(cap.text ?? "").slice(0, 60)}" shows at ${cap.out.start.toFixed(2)}s but no words are spoken in its window — orphaned by a cut?`,
          { suggestedFix: { action: "retime_caption", params: { eventId: cap.id } } }
        );
        continue;
      }
      const capTokens = cap.text!.split(/\s+/).filter(Boolean).length;
      if (capTokens < 3) continue; // micro-captions are all noise for bag-of-words similarity
      // Prefer SOURCE-side comparison when the caption carries src provenance:
      // caption text was authored against the source transcript, and the
      // output-time word mapping is lossy at silence-cut edges (whisper-1
      // timing drift), which false-flagged 40+ correct captions before this.
      let compareWords = inWin;
      if (sourceWords?.length && cap.src && cap.src.end != null) {
        compareWords = sourceWords.filter(
          (w) => w.end > cap.src!.start - 0.2 && w.start < cap.src!.end! + 0.2
        );
      }
      const spoken = compareWords.map((w) => w.text).join(" ");
      const sim = coverage(cap.text!, spoken);
      if (sim < opt.captionSimilarityMin) {
        // reel-recut captions are "paraphrase-clean, not verbatim" by design
        // (SKILL.md step 3) — informational there, real elsewhere.
        push(
          "caption_mismatch",
          manifest.lane === "reel-recut" ? "LOW" : "MEDIUM",
          cap.id,
          cap.out.start,
          end,
          `Caption "${(cap.text ?? "").slice(0, 60)}" vs spoken "${spoken.slice(0, 60)}" — similarity ${(sim * 100).toFixed(0)}%.`,
          { evidence: { similarity: sim, spoken } }
        );
      }
    }
  }

  // ---- 5. Butt-splice clicks at every dialogue cut --------------------------
  for (const cut of dialogueCuts) {
    const diff = await joinClickStat(manifest.video, cut.out.start);
    if (diff != null && diff > opt.clickMaxDiff) {
      push(
        "splice_click",
        "MEDIUM",
        cut.id,
        cut.out.start - 0.04,
        cut.out.start + 0.04,
        `Sample-difference spike (${diff.toFixed(2)}) at the ${cut.id} join — butt-splice click risk; add a 25–30ms edge fade.`,
        { suggestedFix: { action: "add_crossfade", params: { ms: 25 } }, evidence: { maxDifference: diff } }
      );
    }
  }

  const status =
    issues.some((i) => i.severity === "CRITICAL" || i.severity === "HIGH")
      ? "fail"
      : issues.length
        ? "warn"
        : "pass";
  return {
    status,
    issues,
    stats: {
      dialogueCuts: dialogueCuts.length,
      wordsVia: via,
      probesUsed,
      clippedSuspects: clippedSuspects.length,
    },
  };
}
