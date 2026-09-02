/**
 * Generate tiny ffmpeg test fixtures for the video-qa suite into
 * __tests__/fixtures/gen/ (gitignored — regenerate on demand).
 *
 * The mid-word-cut fixture uses macOS `say` TTS + a whisper.cpp transcription
 * captured at generation time, so the clipped-word path is exercised with real
 * speech and real word timings.
 */
import { existsSync, mkdirSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ffmpegBin, runCapture, extractAudioFull } from "../ffmpeg";

export const GEN_DIR = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "gen");

const FF = () => ffmpegBin();

async function gen(args: string[]): Promise<void> {
  await runCapture(FF(), ["-nostdin", "-y", ...args]);
}

export interface MidwordFixture {
  video: string;
  cutSourceTime: number;
  cutWord: { text: string; start: number; end: number };
  sourceWords: Array<{ text: string; start: number; end: number }>;
  sourceVideo: string;
  outputDuration: number;
}

export async function makeFixtures(): Promise<void> {
  mkdirSync(GEN_DIR, { recursive: true });
  const done = join(GEN_DIR, ".done");
  if (existsSync(done)) return;

  // 1. clean: 8s test pattern + gentle tone at sane levels
  await gen([
    "-f", "lavfi", "-i", "testsrc2=d=8:s=320x568:r=30",
    "-f", "lavfi", "-i", "sine=frequency=440:d=8",
    "-af", "volume=-14dB",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    join(GEN_DIR, "clean.mp4"),
  ]);

  // 2. black-gap: 3s pattern + 0.8s black/silence + 3s pattern
  await gen([
    "-f", "lavfi", "-i", "testsrc2=d=3:s=320x568:r=30",
    "-f", "lavfi", "-i", "color=black:d=0.8:s=320x568:r=30",
    "-f", "lavfi", "-i", "testsrc2=d=3:s=320x568:r=30",
    "-f", "lavfi", "-i", "sine=frequency=440:d=3,volume=-14dB",
    "-f", "lavfi", "-i", "anullsrc=d=0.8:r=44100:cl=mono",
    "-f", "lavfi", "-i", "sine=frequency=440:d=3,volume=-14dB",
    "-filter_complex",
    "[0:v][3:a][1:v][4:a][2:v][5:a]concat=n=3:v=1:a=1[v][a]",
    "-map", "[v]", "-map", "[a]",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    join(GEN_DIR, "black-gap.mp4"),
  ]);

  // 3. clipping: heavily overdriven tone
  await gen([
    "-f", "lavfi", "-i", "testsrc2=d=4:s=320x568:r=30",
    "-f", "lavfi", "-i", "sine=frequency=300:d=4",
    "-af", "volume=20dB",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    join(GEN_DIR, "clipping.mp4"),
  ]);

  // 4. freeze: 2s motion, then the last frame held ~2.5s
  await gen([
    "-f", "lavfi", "-i", "testsrc2=d=2:s=320x568:r=30",
    "-f", "lavfi", "-i", "sine=frequency=440:d=4.5",
    "-af", "volume=-14dB",
    "-vf", "tpad=stop_mode=clone:stop_duration=2.5",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
    join(GEN_DIR, "freeze.mp4"),
  ]);

  // 5. flash: white flash frames spliced into the pattern at t=2
  await gen([
    "-f", "lavfi", "-i", "testsrc2=d=5:s=320x568:r=30",
    "-f", "lavfi", "-i", "sine=frequency=440:d=5",
    "-af", "volume=-14dB",
    "-vf",
    "drawbox=enable='between(t,2.0,2.066)':x=0:y=0:w=iw:h=ih:color=white:t=fill",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    join(GEN_DIR, "flash.mp4"),
  ]);

  // 6. mid-word cut (macOS say TTS; skipped silently on non-darwin)
  try {
    await makeMidwordFixture();
  } catch (e) {
    console.warn(`midword fixture skipped: ${(e as Error).message.slice(0, 200)}`);
  }

  await writeFile(done, new Date().toISOString());
}

async function makeMidwordFixture(): Promise<void> {
  const aiff = join(GEN_DIR, "speech.aiff");
  const text =
    "Tracking your subscriptions manually is painful. Server side measurement finally fixed the attribution problem completely.";
  await runCapture("say", ["-o", aiff, text]);
  const speechWav = join(GEN_DIR, "speech.wav");
  await extractAudioFull(aiff, speechWav);

  // Source video: pattern + the TTS audio
  const src = join(GEN_DIR, "midword-source.mp4");
  await gen([
    "-f", "lavfi", "-i", "testsrc2=d=12:s=320x568:r=30",
    "-i", speechWav,
    "-map", "0:v", "-map", "1:a",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
    src,
  ]);

  // Word timings for the source, via whatever backend is available
  const { probeWindow } = await import("../transcribe");
  const words = await probeWindow(src, 0, 12);
  if (!words || words.length < 6) throw new Error("no transcriber available for midword fixture");

  // Pick a solid word past 1s and cut from its middle to +1.2s (removes its
  // tail plus following material) using the same select/aselect technique as
  // build_reel.py.
  const target = words.find((w) => w.start > 1 && w.end - w.start >= 0.25 && norm(w.text).length >= 6);
  if (!target) throw new Error("no suitable word to clip");
  const cutStart = (target.start + target.end) / 2;
  const cutEnd = cutStart + 1.2;
  const out = join(GEN_DIR, "midword-cut.mp4");
  const expr = `between(t,0,${cutStart})+gte(t,${cutEnd})`;
  await gen([
    "-i", src,
    "-filter_complex",
    `[0:v]select='${expr}',setpts=N/FRAME_RATE/TB[vc];[0:a]aselect='${expr}',asetpts=N/SR/TB[ac]`,
    "-map", "[vc]", "-map", "[ac]",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    out,
  ]);

  const fixture: MidwordFixture = {
    video: out,
    sourceVideo: src,
    cutSourceTime: cutStart,
    cutWord: target,
    sourceWords: words,
    outputDuration: 0, // filled by the test via ffprobe
  };
  await writeFile(join(GEN_DIR, "midword.json"), JSON.stringify(fixture, null, 1));
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9']/g, "");
