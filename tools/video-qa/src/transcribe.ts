/**
 * Word-timing acquisition for Layer 2.
 *
 * Priority order:
 *   1. manifest.words           — output-time words the editor emitted (best)
 *   2. manifest.sourceWords     — source-time words, mapped through the cut list
 *   3. transcribe the SOURCE    — whisper.cpp via `npx hyperframes transcribe`
 *                                 (local, free) or OpenAI whisper-1 word mode
 *
 * NEVER a full transcription of the RENDER — whisper hallucinates connective
 * phrases at jump cuts and fuses differently every run (SESSION_LOG
 * 2026-08-14). The only render-side transcription allowed is an ISOLATED short
 * window re-probe (probeWindow), used to confirm/clear a specific seam.
 */
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { EditManifest, WordTiming } from "./types";
import { extractAudioFull, extractAudioWindow, ffprobeJson, runCapture } from "./ffmpeg";

export type TranscriberBackend = "auto" | "whispercpp" | "openai" | "none";

function backend(): TranscriberBackend {
  return (process.env.VIDEO_QA_TRANSCRIBER as TranscriberBackend) || "auto";
}

/** whisper.cpp via the HyperFrames CLI (word-level `[{text,start,end}]`). */
async function whisperCppTranscribe(wavPath: string): Promise<WordTiming[] | null> {
  try {
    const res = await runCapture(
      "npx",
      ["hyperframes", "transcribe", wavPath, "--json", "--model", "small.en"],
      { allowNonZero: true, maxBuffer: 16 * 1024 * 1024 }
    );
    // The CLI either prints JSON to stdout or writes a sibling .json file.
    const tryParse = (raw: string): WordTiming[] | null => {
      try {
        const data = JSON.parse(raw) as unknown;
        const arr = Array.isArray(data)
          ? data
          : (data as { words?: unknown[] }).words;
        if (!Array.isArray(arr)) return null;
        const words = (arr as Array<{ text?: string; word?: string; start: number; end: number }>)
          .filter((w) => (w.text ?? w.word) != null)
          .map((w) => ({ text: (w.text ?? w.word ?? "").trim(), start: w.start, end: w.end }));
        return words.length ? words : null;
      } catch {
        return null;
      }
    };
    // The CLI prints {ok, transcriptPath} to stdout and writes the flat word
    // array to transcriptPath (verified live 2026-08-15).
    try {
      const status = JSON.parse(res.stdout.trim().split("\n").pop() ?? "") as {
        ok?: boolean;
        transcriptPath?: string;
      };
      if (status.transcriptPath && existsSync(status.transcriptPath)) {
        const parsed = tryParse(readFileSync(status.transcriptPath, "utf8"));
        if (parsed) return parsed;
      }
    } catch {
      /* fall through to sibling-file guesses */
    }
    for (const cand of [
      join(wavPath, "..", "transcript.json"),
      wavPath.replace(/\.\w+$/, ".json"),
      `${wavPath}.json`,
    ]) {
      if (existsSync(cand)) {
        const parsed = tryParse(readFileSync(cand, "utf8"));
        if (parsed) return parsed;
      }
    }
    return null;
  } catch {
    return null;
  }
}

async function openaiTranscribe(wavPath: string): Promise<WordTiming[] | null> {
  if (!process.env.OPENAI_API_KEY) return null;
  try {
    const { transcribeWithTimestamps } = await import("./openai-transcribe");
    const buf = await readFile(wavPath);
    const file = new File([buf], "audio.wav", { type: "audio/wav" });
    const result = await transcribeWithTimestamps(file, { granularity: ["word"] });
    return (result.words ?? []).map((w) => ({ text: w.word, start: w.start, end: w.end }));
  } catch {
    return null;
  }
}

async function transcribeFile(wavPath: string): Promise<{ words: WordTiming[]; via: string } | null> {
  const be = backend();
  if (be === "none") return null;
  if (be === "auto" || be === "whispercpp") {
    const words = await whisperCppTranscribe(wavPath);
    if (words) return { words, via: "whispercpp" };
    if (be === "whispercpp") return null;
  }
  const words = await openaiTranscribe(wavPath);
  return words ? { words, via: "openai" } : null;
}

/** Map SOURCE-time words to OUTPUT time through the manifest's cut list
 *  (the removed source ranges on cut events). Words fully inside removed
 *  ranges are dropped; words fully inside kept spans are shifted. Words
 *  STRADDLING a boundary are excluded here — Layer 2 detects those as
 *  clipped words from sourceWords + cut provenance directly. */
export function mapSourceWordsToOutput(
  manifest: EditManifest,
  sourceWords: WordTiming[],
  sourceDuration: number
): WordTiming[] {
  const removed = manifest.events
    .filter((e) => e.kind === "cut" && e.src && e.src.end != null)
    .map((e) => [e.src!.start, e.src!.end!] as [number, number])
    .sort((a, b) => a[0] - b[0]);
  const keep: Array<[number, number]> = [];
  let t = 0;
  for (const [rs, re] of removed) {
    if (rs > t) keep.push([t, rs]);
    t = Math.max(t, re);
  }
  if (t < sourceDuration) keep.push([t, sourceDuration]);

  const newT = (x: number): number => {
    let acc = 0;
    for (const [s, e] of keep) {
      if (x >= e) acc += e - s;
      else if (x > s) {
        acc += x - s;
        break;
      } else break;
    }
    return acc;
  };

  // Midpoint containment with edge clamping: whisper word ENDS are routinely
  // padded into the following pause, so full-containment would drop a large
  // share of real words at silence-cut edges (observed live on the 0814 reel).
  const out: WordTiming[] = [];
  for (const w of sourceWords) {
    const mid = w.start + (w.end - w.start) * 0.4;
    const span = keep.find(([s, e]) => mid >= s && mid <= e);
    if (span) {
      const cs = Math.max(w.start, span[0]);
      const ce = Math.min(w.end, span[1]);
      if (ce - cs > 0.02) out.push({ text: w.text, start: newT(cs), end: newT(ce) });
    }
  }
  return out;
}

export interface AcquiredWords {
  words: WordTiming[] | null;
  sourceWords: WordTiming[] | null;
  via: string;
}

/** Resolve the best available word timings for a manifest. May transcribe the
 *  source (cached per session in a temp dir); never transcribes the render. */
export async function acquireWords(
  manifest: EditManifest,
  log: (msg: string) => void = () => {}
): Promise<AcquiredWords> {
  if (manifest.words?.length) {
    return { words: manifest.words, sourceWords: manifest.sourceWords ?? null, via: "manifest" };
  }
  if (manifest.sourceWords?.length && manifest.source) {
    const probe = await ffprobeJson(manifest.source);
    const dur = parseFloat(probe.format.duration ?? "0");
    return {
      words: mapSourceWordsToOutput(manifest, manifest.sourceWords, dur),
      sourceWords: manifest.sourceWords,
      via: "manifest-source-words",
    };
  }
  if (manifest.source && existsSync(manifest.source)) {
    log(`[qa:L2] transcribing SOURCE audio (${backend()}) — this is the only full transcription; the render is never fully re-whispered`);
    const dir = mkdtempSync(join(tmpdir(), "vqa-words-"));
    const wav = join(dir, "source.wav");
    await extractAudioFull(manifest.source, wav);
    const result = await transcribeFile(wav);
    if (result) {
      const probe = await ffprobeJson(manifest.source);
      const dur = parseFloat(probe.format.duration ?? "0");
      return {
        words: mapSourceWordsToOutput(manifest, result.words, dur),
        sourceWords: result.words,
        via: result.via,
      };
    }
  }
  return { words: null, sourceWords: null, via: "none" };
}

/** Isolated seam re-probe: transcribe ONLY a short window of the RENDER around
 *  a suspect seam. Confirms/clears a specific flag; small windows avoid the
 *  jump-cut hallucination failure mode of full-render transcription. */
export async function probeWindow(
  video: string,
  start: number,
  duration: number
): Promise<WordTiming[] | null> {
  const dir = mkdtempSync(join(tmpdir(), "vqa-probe-"));
  const wav = join(dir, "probe.wav");
  await extractAudioWindow(video, Math.max(0, start), duration, wav);
  const result = await transcribeFile(wav);
  if (!result) return null;
  const offset = Math.max(0, start);
  return result.words.map((w) => ({ text: w.text, start: w.start + offset, end: w.end + offset }));
}
