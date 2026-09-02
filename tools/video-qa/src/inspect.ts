/**
 * Layer 4 — targeted multi-modal inspection packet.
 *
 * One call returns everything Claude needs about a time window, so it can
 * reason across modalities instead of inferring everything from pixels:
 *   contact_sheet.png  frames from the ORIGINAL render (adaptive density)
 *   waveform.png       window waveform with edit-event markers (PIL-drawn)
 *   audio_stats.json   peak/RMS/silence spans for the window
 *   transcript.md      word timings with inline [cut:*] markers
 *   events.json        manifest events intersecting the window
 *   packet.md          the human/agent-readable index
 *
 * Padding rules: deterministic-layer timestamps are exact → tight windows;
 * Gemini-sourced windows should be padded ±VIDEO_QA_INSPECT_PADDING_S by the
 * caller before invoking this.
 */
import { existsSync, mkdirSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { EditManifest } from "./types";
import { ffmpegBin, runCapture } from "./ffmpeg";
import { eventsInWindow } from "./manifest/schema";

export interface InspectOptions {
  frames?: boolean;
  audio?: boolean;
  waveform?: boolean;
  transcript?: boolean;
  /** frames per second on the contact sheet; default adapts to window length. */
  fps?: number;
}

export interface InspectPacket {
  dir: string;
  files: string[];
  summary: string;
}

export async function inspectWindow(
  manifest: EditManifest,
  start: number,
  end: number,
  outDir: string,
  opts: InspectOptions = {},
  log: (m: string) => void = () => {}
): Promise<InspectPacket> {
  const video = manifest.video;
  const s = Math.max(0, start);
  const span = Math.max(0.2, end - s);
  const on = (v: boolean | undefined) => v !== false;
  mkdirSync(outDir, { recursive: true });
  const files: string[] = [];
  const lines: string[] = [
    `# Inspection packet — ${s.toFixed(2)}s → ${(s + span).toFixed(2)}s`,
    ``,
    `Video: ${video}`,
  ];

  const events = eventsInWindow(manifest.events, s, s + span);
  await writeFile(join(outDir, "events.json"), JSON.stringify(events, null, 1));
  files.push("events.json");
  lines.push(
    `EDITS: ${events.length ? events.map((e) => `${e.id} @${e.out.start.toFixed(2)}s`).join(" · ") : "none in window"}`
  );

  if (on(opts.frames)) {
    // Adaptive density: flash-hunting needs dense sampling; framing checks don't.
    const fps = opts.fps ?? (span <= 2 ? 10 : span <= 5 ? 6 : 3);
    const total = Math.max(1, Math.ceil(span * fps));
    const cols = Math.min(6, total);
    const rows = Math.ceil(total / cols);
    const sheet = join(outDir, "contact_sheet.png");
    await runCapture(ffmpegBin(), [
      "-nostdin", "-y",
      "-ss", s.toFixed(3), "-t", span.toFixed(3), "-i", video,
      "-vf", `fps=${fps},scale=320:-2,tile=${cols}x${rows}`,
      "-frames:v", "1", sheet,
    ]);
    files.push("contact_sheet.png");
    lines.push(`FRAMES: contact_sheet.png (${fps}fps, ${cols}x${rows}, read left→right top→bottom, first tile = ${s.toFixed(2)}s, one tile per ${(1 / fps).toFixed(2)}s)`);
  }

  if (on(opts.waveform)) {
    const wave = join(outDir, "waveform.png");
    await runCapture(ffmpegBin(), [
      "-nostdin", "-y",
      "-ss", s.toFixed(3), "-t", span.toFixed(3), "-i", video,
      "-filter_complex", "aformat=channel_layouts=mono,showwavespic=s=1600x400:colors=0x9be070",
      "-frames:v", "1", wave,
    ]);
    // Draw event markers with PIL (no drawtext in the local ffmpeg).
    const markersPath = join(outDir, "waveform_markers.json");
    await writeFile(
      markersPath,
      JSON.stringify({
        start: s,
        end: s + span,
        markers: events.map((e) => ({ t: e.out.start, label: e.id, kind: e.kind })),
      })
    );
    const script = join(dirname(fileURLToPath(import.meta.url)), "py", "draw_markers.py");
    if (existsSync(script)) {
      const res = await runCapture("python3", [script, wave, markersPath, wave], { allowNonZero: true });
      if (res.code !== 0) log(`[qa:L4] marker overlay skipped (${res.stderr.slice(0, 120)})`);
    }
    files.push("waveform.png");
    lines.push(`WAVEFORM: waveform.png (edit markers drawn; legend in events.json)`);
  }

  if (on(opts.audio)) {
    const res = await runCapture(
      ffmpegBin(),
      [
        "-nostdin", "-hide_banner",
        "-ss", s.toFixed(3), "-t", span.toFixed(3), "-i", video,
        "-af", "silencedetect=noise=-40dB:d=0.2,astats=metadata=0",
        "-vn", "-f", "null", "-",
      ],
      { allowNonZero: true }
    );
    const grab = (re: RegExp) => {
      const m = [...res.stderr.matchAll(re)];
      return m.length ? parseFloat(m[m.length - 1][1]) : null;
    };
    const silences = [...res.stderr.matchAll(/silence_start:\s*([-\d.]+)/g)].map((m, i) => {
      const ends = [...res.stderr.matchAll(/silence_end:\s*([-\d.]+)/g)];
      return {
        start: s + parseFloat(m[1]),
        end: ends[i] ? s + parseFloat(ends[i][1]) : null,
      };
    });
    const stats = {
      window: { start: s, end: s + span },
      peakDb: grab(/Peak level dB:\s*(-?[\d.]+)/g),
      rmsDb: grab(/RMS level dB:\s*(-?[\d.]+)/g),
      maxDifference: grab(/Max difference:\s*([\d.]+)/g),
      silences,
    };
    await writeFile(join(outDir, "audio_stats.json"), JSON.stringify(stats, null, 1));
    files.push("audio_stats.json");
    lines.push(
      `AUDIO: peak ${stats.peakDb ?? "?"} dB | RMS ${stats.rmsDb ?? "?"} dB | ${silences.length ? `${silences.length} silence span(s)` : "no silence"}`
    );
  }

  if (on(opts.transcript) && manifest.words?.length) {
    const words = manifest.words
      .filter((w) => w.end > s - 0.2 && w.start < s + span + 0.2)
      .sort((a, b) => a.start - b.start);
    const cutsInWin = events.filter((e) => e.kind === "cut").sort((a, b) => a.out.start - b.out.start);
    let line = "";
    let ci = 0;
    for (const w of words) {
      while (ci < cutsInWin.length && cutsInWin[ci].out.start <= w.start) {
        line += ` |[${cutsInWin[ci].id}]|`;
        ci += 1;
      }
      line += ` ${w.text}`;
    }
    while (ci < cutsInWin.length) {
      line += ` |[${cutsInWin[ci].id}]|`;
      ci += 1;
    }
    const md = [
      `# Transcript ${s.toFixed(2)}–${(s + span).toFixed(2)}s`,
      "",
      line.trim() || "(no words in window)",
      "",
      "| word | start | end |",
      "|---|---|---|",
      ...words.map((w) => `| ${w.text} | ${w.start.toFixed(2)} | ${w.end.toFixed(2)} |`),
    ].join("\n");
    await writeFile(join(outDir, "transcript.md"), md);
    files.push("transcript.md");
    lines.push(`TRANSCRIPT: ${line.trim().slice(0, 160) || "(no words)"}`);
  } else if (on(opts.transcript)) {
    lines.push("TRANSCRIPT: no word timings available in manifest");
  }

  const summary = lines.join("\n");
  await writeFile(join(outDir, "packet.md"), summary);
  files.push("packet.md");
  return { dir: outDir, files, summary };
}
