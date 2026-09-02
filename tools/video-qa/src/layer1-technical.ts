/**
 * Layer 1 — deterministic technical QA (video + audio) via ffprobe/ffmpeg.
 *
 * Three passes:
 *   0. ffprobe JSON — streams, duration, resolution, fps, channel layout
 *   1. video filters — blackdetect + freezedetect + scene-spike flash detection
 *   2. audio filters — silencedetect + ebur128 (LUFS/true peak) + astats
 *
 * Every detection is cross-checked against manifest.intentional before flagging.
 * Timestamps from this layer are EXACT — downstream windows can be tight.
 * Rule inherited from branded-ad-edit gotcha #6: measure the FILE, never trust
 * a render log.
 */
import type { EditManifest, QaIssue, LayerResult, Severity } from "./types";
import { ffmpegBin, ffprobeJson, fpsOf, runCapture } from "./ffmpeg";
import { inRegions, nearestEvent } from "./manifest/schema";

export interface Thresholds {
  durationSlackSec: number;
  blackMinSec: number;
  blackPixTh: number;
  blackCriticalSec: number;
  freezeNoiseDb: number;
  freezeMinSec: number;
  sceneSpike: number;
  flashPairMs: number;
  silenceNoiseDb: number;
  silenceMinSec: number;
  silenceHighSec: number;
  headTailGraceSec: number;
  cutSilenceLinkMs: number;
  lufsTarget: number;
  lufsTolerance: number;
  truePeakMaxDb: number;
}

export const DEFAULT_THRESHOLDS: Thresholds = {
  durationSlackSec: 0.15,
  blackMinSec: 0.1,
  blackPixTh: 0.1,
  blackCriticalSec: 0.5,
  freezeNoiseDb: -60,
  freezeMinSec: 1.5,
  sceneSpike: 0.45,
  flashPairMs: 100,
  silenceNoiseDb: -40,
  silenceMinSec: 0.6,
  silenceHighSec: 1.2,
  headTailGraceSec: 1.0,
  cutSilenceLinkMs: 150,
  lufsTarget: -14,
  lufsTolerance: 2,
  truePeakMaxDb: -1.0,
};

let issueSeq = 0;
function issue(
  category: string,
  severity: Severity,
  start: number,
  end: number,
  message: string,
  extra?: Partial<QaIssue>
): QaIssue {
  issueSeq += 1;
  return {
    id: `L1-${category}-${String(issueSeq).padStart(3, "0")}`,
    source: "technical",
    severity,
    category,
    eventId: null,
    timeWindow: { start, end },
    message,
    objective: true,
    ...extra,
  };
}

function parsePairs(log: string, startRe: RegExp, endRe: RegExp): Array<[number, number]> {
  const starts = [...log.matchAll(startRe)].map((m) => parseFloat(m[1]));
  const ends = [...log.matchAll(endRe)].map((m) => parseFloat(m[1]));
  return starts.map((s, i) => [s, ends[i] ?? s] as [number, number]);
}

export async function runTechnicalLayer(
  manifest: EditManifest,
  thresholds: Partial<Thresholds> = {},
  log: (msg: string) => void = () => {}
): Promise<LayerResult> {
  issueSeq = 0;
  const th = { ...DEFAULT_THRESHOLDS, ...thresholds };
  const video = manifest.video;
  const issues: QaIssue[] = [];
  const intentional = manifest.intentional ?? {};

  // ---- Pass 0: ffprobe ------------------------------------------------------
  let probe;
  try {
    probe = await ffprobeJson(video);
  } catch (e) {
    return {
      status: "fail",
      issues: [
        issue("corrupt_file", "CRITICAL", 0, 0, `ffprobe cannot read the file: ${(e as Error).message}`),
      ],
    };
  }
  const vStream = probe.streams.find((s) => s.codec_type === "video");
  const aStream = probe.streams.find((s) => s.codec_type === "audio");
  const duration = parseFloat(probe.format.duration ?? "0");

  if (!vStream) {
    issues.push(issue("missing_video_stream", "CRITICAL", 0, 0, "No video stream in the file."));
    return { status: "fail", issues };
  }
  if (!aStream && !intentional.noAudio) {
    issues.push(
      issue("missing_audio_stream", "CRITICAL", 0, duration, "No audio stream, but audio was expected.")
    );
  }

  if (manifest.expectedDuration != null) {
    const diff = Math.abs(duration - manifest.expectedDuration);
    if (diff > th.durationSlackSec) {
      issues.push(
        issue(
          "duration_mismatch",
          diff > 1 ? "CRITICAL" : "HIGH",
          0,
          duration,
          `Rendered duration ${duration.toFixed(3)}s vs expected ${manifest.expectedDuration.toFixed(3)}s (Δ ${diff.toFixed(3)}s). Render logs lie — this is measured from the file.`,
          { evidence: { duration, expected: manifest.expectedDuration } }
        )
      );
    }
  }
  const exp = manifest.expected ?? {};
  if (exp.width && exp.height && (vStream.width !== exp.width || vStream.height !== exp.height)) {
    issues.push(
      issue(
        "resolution_mismatch",
        "HIGH",
        0,
        duration,
        `Resolution ${vStream.width}x${vStream.height} vs expected ${exp.width}x${exp.height}.`
      )
    );
  }
  const fps = fpsOf(vStream);
  if (exp.fps && fps && Math.abs(fps - exp.fps) > 0.5) {
    issues.push(
      issue("fps_mismatch", "MEDIUM", 0, duration, `Frame rate ${fps.toFixed(2)} vs expected ${exp.fps}.`)
    );
  }

  // ---- Pass 1: video filters ------------------------------------------------
  log(`[qa:L1] video filter pass (blackdetect/freezedetect/scene) on ${video}`);
  const vf =
    `blackdetect=d=${th.blackMinSec}:pix_th=${th.blackPixTh},` +
    `freezedetect=n=${th.freezeNoiseDb}dB:d=${th.freezeMinSec},` +
    `select='gt(scene,${th.sceneSpike})',showinfo`;
  const vres = await runCapture(
    ffmpegBin(),
    ["-nostdin", "-hide_banner", "-i", video, "-vf", vf, "-an", "-f", "null", "-"],
    { allowNonZero: true }
  );
  if (vres.code !== 0) {
    issues.push(
      issue("decode_error", "CRITICAL", 0, duration, `Video decode pass failed: ${vres.stderr.slice(-400)}`)
    );
  }
  const decodeErrors = vres.stderr
    .split("\n")
    .filter((l) => /error|corrupt|invalid data/i.test(l) && !/Parsed_/.test(l));
  if (decodeErrors.length > 0 && vres.code === 0) {
    issues.push(
      issue("decode_warnings", "HIGH", 0, duration, `Decoder reported problems: ${decodeErrors[0]}`, {
        evidence: { lines: decodeErrors.slice(0, 5) },
      })
    );
  }

  for (const [bs, be] of parsePairs(
    vres.stderr,
    /black_start:\s*([\d.]+)/g,
    /black_end:\s*([\d.]+)/g
  )) {
    if (inRegions(intentional.blackRegions, bs, be)) continue;
    const len = be - bs;
    issues.push(
      issue(
        "black_frames",
        len >= th.blackCriticalSec ? "CRITICAL" : "HIGH",
        bs,
        be,
        `Unexpected black frames ${bs.toFixed(2)}–${be.toFixed(2)}s (${len.toFixed(2)}s).`
      )
    );
  }

  for (const [fs, fe] of parsePairs(
    vres.stderr,
    /freeze_start:\s*([\d.]+)/g,
    /freeze_end:\s*([\d.]+)/g
  )) {
    if (inRegions(intentional.stillRegions, fs, fe, 0.5)) continue;
    issues.push(
      issue(
        "frozen_frames",
        "HIGH",
        fs,
        fe,
        `Frozen/static video ${fs.toFixed(2)}–${fe.toFixed(2)}s (${(fe - fs).toFixed(2)}s) — classic un-synced b-roll / dead canvas signature.`
      )
    );
  }

  // Scene spikes from showinfo (only frames passing the select filter print).
  const spikes = [...vres.stderr.matchAll(/pts_time:([\d.]+)/g)].map((m) => parseFloat(m[1]));
  const cutTimes = manifest.events.filter((e) => e.kind === "cut").map((e) => e.out.start);
  const frameDur = fps ? 1 / fps : 1 / 30;
  for (let i = 1; i < spikes.length; i++) {
    const gap = spikes[i] - spikes[i - 1];
    if (gap > 0 && gap <= th.flashPairMs / 1000) {
      const nearCut = cutTimes.some((c) => Math.abs(c - spikes[i - 1]) < 2 * frameDur);
      issues.push(
        issue(
          "flash_frame",
          nearCut ? "HIGH" : "MEDIUM",
          spikes[i - 1],
          spikes[i],
          `Two hard visual discontinuities ${(gap * 1000).toFixed(0)}ms apart at ${spikes[i - 1].toFixed(2)}s — single-frame glitch / stray frames${nearCut ? " right at an edit seam" : ""}.`,
          {
            eventId: nearCut
              ? nearestEvent(manifest.events, spikes[i - 1], 0.2, ["cut"])?.id ?? null
              : null,
          }
        )
      );
    }
  }

  // ---- Pass 2: audio filters ------------------------------------------------
  const stats: Record<string, unknown> = {
    duration,
    width: vStream.width,
    height: vStream.height,
    fps,
    sceneSpikes: spikes.length,
  };
  if (aStream) {
    log(`[qa:L1] audio filter pass (silencedetect/ebur128/astats)`);
    const af =
      `silencedetect=noise=${th.silenceNoiseDb}dB:d=${th.silenceMinSec},` +
      `astats=metadata=0,ebur128=peak=true`;
    const ares = await runCapture(
      ffmpegBin(),
      ["-nostdin", "-hide_banner", "-i", video, "-af", af, "-vn", "-f", "null", "-"],
      { allowNonZero: true }
    );
    if (ares.code !== 0) {
      issues.push(
        issue("audio_decode_error", "CRITICAL", 0, duration, `Audio pass failed: ${ares.stderr.slice(-400)}`)
      );
    }

    for (const [ss, se] of parsePairs(
      ares.stderr,
      /silence_start:\s*([-\d.]+)/g,
      /silence_end:\s*([-\d.]+)/g
    )) {
      const len = se - ss;
      if (len < th.silenceMinSec) continue;
      if (inRegions(intentional.silentRegions, ss, se)) continue;
      // Trailing/leading grace (outro cards, fade-ins)
      if (se <= th.headTailGraceSec || ss >= duration - th.headTailGraceSec) continue;
      const linkedCut = nearestEvent(manifest.events, ss, th.cutSilenceLinkMs / 1000, ["cut"]);
      issues.push(
        issue(
          "dead_air",
          len >= th.silenceHighSec || linkedCut ? "HIGH" : "MEDIUM",
          ss,
          se,
          `Silence ${ss.toFixed(2)}–${se.toFixed(2)}s (${len.toFixed(2)}s)` +
            (linkedCut ? ` starting right at ${linkedCut.id} — over-trim suspicion.` : "."),
          { eventId: linkedCut?.id ?? null }
        )
      );
    }

    // ebur128 summary block
    const lufsMatch = ares.stderr.match(/Integrated loudness:[\s\S]*?I:\s*(-?[\d.]+)\s*LUFS/);
    const peakMatch = ares.stderr.match(/True peak:[\s\S]*?Peak:\s*(-?[\d.]+)\s*dBFS/);
    const integrated = lufsMatch ? parseFloat(lufsMatch[1]) : null;
    const truePeak = peakMatch ? parseFloat(peakMatch[1]) : null;
    stats.integratedLufs = integrated;
    stats.truePeakDb = truePeak;
    const target = intentional.loudnessTarget ?? { lufs: th.lufsTarget, tolerance: th.lufsTolerance };
    if (integrated != null && Number.isFinite(integrated)) {
      const tol = target.tolerance ?? th.lufsTolerance;
      if (Math.abs(integrated - target.lufs) > tol) {
        issues.push(
          issue(
            "loudness_off_target",
            "MEDIUM",
            0,
            duration,
            `Integrated loudness ${integrated.toFixed(1)} LUFS vs target ${target.lufs}±${tol}.`,
            { evidence: { integrated, target } }
          )
        );
      }
    }
    if (truePeak != null && truePeak > th.truePeakMaxDb) {
      // Social masters routinely peak between -1 and -0.2 dBTP; only genuinely
      // hot/clipped audio blocks the verdict.
      const sev: Severity = truePeak >= 0 ? "CRITICAL" : truePeak >= -0.1 ? "HIGH" : "LOW";
      issues.push(
        issue(
          "clipping_risk",
          sev,
          0,
          duration,
          `True peak ${truePeak.toFixed(1)} dBTP (limit ${th.truePeakMaxDb} dBTP)${truePeak >= 0 ? " — hard clipping" : sev === "LOW" ? " — hot master, informational" : ""}.`,
          { evidence: { truePeak } }
        )
      );
    }
    // astats overall flat factor (sustained clipping shows as high flat factor)
    const flat = ares.stderr.match(/Flat factor:\s*([\d.]+)/g);
    if (flat) {
      const last = parseFloat(flat[flat.length - 1].split(":")[1]);
      stats.flatFactor = last;
      if (last > 10) {
        issues.push(
          issue("waveform_flatline", "HIGH", 0, duration, `astats flat factor ${last.toFixed(1)} — sustained clipped/flat samples.`)
        );
      }
    }
  }

  const status =
    issues.some((i) => i.severity === "CRITICAL" || i.severity === "HIGH")
      ? "fail"
      : issues.length > 0
        ? "warn"
        : "pass";
  return { status, issues, stats };
}
