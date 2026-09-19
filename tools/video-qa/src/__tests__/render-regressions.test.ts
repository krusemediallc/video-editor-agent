import assert from "node:assert/strict";
import { it } from "node:test";
import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { ffmpegBin, ffprobeBin, ffprobeJson, runCapture } from "../ffmpeg";
import { runTechnicalLayer } from "../layer1-technical";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
async function decodedFrames(video: string): Promise<number> {
  const r = await runCapture(ffprobeBin(), ["-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "json", video]);
  return Number(JSON.parse(r.stdout).streams[0].nb_read_frames);
}
async function pcmSamples(path: string): Promise<number> {
  const bytes = await readFile(path);
  assert.equal(bytes.subarray(0, 4).toString(), "RIFF");
  let align = 0;
  for (let pos = 12; pos + 8 <= bytes.length;) {
    const id = bytes.subarray(pos, pos + 4).toString(), size = bytes.readUInt32LE(pos + 4);
    if (id === "fmt ") align = bytes.readUInt16LE(pos + 8 + 12);
    if (id === "data") { assert.ok(align > 0); return size / align; }
    pos += 8 + size + size % 2;
  }
  throw new Error("No PCM data in the produced WAV");
}

it("renders 128 separated kept spans with the production cut assembler and checks the actual MP4", { timeout: 120_000 }, async () => {
  const dir = await mkdtemp(join(tmpdir(), "vqa-long-render-"));
  try {
    const source = join(dir, "source.mp4"), output = join(dir, "edited.mp4"), keepsPath = join(dir, "keeps.json");
    await runCapture(ffmpegBin(), ["-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=26", "-f", "lavfi", "-i", "sine=frequency=431:sample_rate=48000:duration=26", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", source]);
    // 128 independently assembled spans, beyond the previously unreliable >70-cut
    // select/aselect path. Each kept span is exactly three output frames.
    const keeps = Array.from({ length: 128 }, (_, i) => [i / 5, i / 5 + 0.1]);
    await writeFile(keepsPath, JSON.stringify(keeps));
    await runCapture("python3", [join(root, ".claude/skills/reel-recut/scripts/cut_timeline.py"), "--source", source, "--output", output, "--work", join(dir, "work"), "--keeps", keepsPath, "--fps", "30"], { maxBuffer: 16 * 1024 * 1024 });
    const measured = await ffprobeJson(output);
    const video = measured.streams.find((s) => s.codec_type === "video")!;
    const audio = measured.streams.find((s) => s.codec_type === "audio")!;
    assert.equal(Number(video.nb_frames), 384, "128 × 3 kept frames must survive actual rendering");
    assert.equal(await decodedFrames(output), 384);
    assert.equal(await pcmSamples(join(dir, "work", "dialogue.wav")), 614400);
    assert.ok(Math.abs(Number(video.duration) - 12.8) <= 1 / 30, JSON.stringify(measured));
    assert.ok(audio, "render must retain audio");
    assert.ok(Math.abs(Number(audio.duration) - 12.8) <= 1 / 48000, "sample-level assembly must prevent cumulative A/V duration drift");
    const qa = await runTechnicalLayer({ version: 1, lane: "reel-recut", video: output, expectedDuration: 12.8, expected: { width: 160, height: 90, fps: 30 }, events: [] });
    assert.ok(!qa.issues.some((i) => ["duration_mismatch", "decode_error", "audio_decode_error", "missing_audio_stream", "missing_video_stream"].includes(i.category)), JSON.stringify(qa.issues));
  } finally { await rm(dir, { recursive: true, force: true }); }
});

it("renders rational FPS with cumulative sample rounding across batch boundaries", { timeout: 120_000 }, async () => {
  const dir = await mkdtemp(join(tmpdir(), "vqa-rational-render-"));
  try {
    const source = join(dir, "source.mp4"), output = join(dir, "edited.mp4"), keepsPath = join(dir, "keeps.json");
    await runCapture(ffmpegBin(), ["-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=30000/1001:d=2", "-f", "lavfi", "-i", "sine=frequency=431:sample_rate=48000:duration=2", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", source]);
    const keeps = Array.from({ length: 17 }, (_, i) => [i * 3 * 1001 / 30000, (i * 3 + 1) * 1001 / 30000]);
    await writeFile(keepsPath, JSON.stringify(keeps));
    await runCapture("python3", [join(root, ".claude/skills/reel-recut/scripts/cut_timeline.py"), "--source", source, "--output", output, "--work", join(dir, "work"), "--keeps", keepsPath, "--fps", "30000/1001"]);
    assert.equal(await decodedFrames(output), 17);
    assert.equal(await pcmSamples(join(dir, "work", "dialogue.wav")), Math.round(17 * 48000 * 1001 / 30000));
    const measured = await ffprobeJson(output);
    assert.equal(measured.streams.find((s) => s.codec_type === "video")!.r_frame_rate, "30000/1001");
    const timeline = JSON.parse(await readFile(join(dir, "work", "timeline.json"), "utf8"));
    assert.deepEqual(new Set(timeline.spans.map((s: { samples: number }) => s.samples)), new Set([1601, 1602]));
  } finally { await rm(dir, { recursive: true, force: true }); }
});
