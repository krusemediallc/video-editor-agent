/** Offline regressions distilled from SESSION_LOG: omitted/zero-length overlays,
 * overlapping captions, long cut lists, reordered takes, false seam suspicions.
 * All inference is injected. No credentials, downloads, TTS or network are needed.
 */
import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";
import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runQa } from "../index";
import { aggregate, renderMarkdown } from "../report";
import { buildHyperframesManifest } from "../manifest/adapter-hyperframes";
import { editManifestSchema } from "../manifest/schema";
import { mapSourceWordsToOutput } from "../transcribe";
import { runTranscriptLayer } from "../layer2-transcript";
import { validateStoryboard, runStoryboardQa, storyboardSchema } from "../storyboard";
import { ffmpegBin, runCapture } from "../ffmpeg";
import type { EditManifest, LayerResult } from "../types";

let dir: string;
const pass = (): LayerResult => ({ status: "pass", issues: [] });
const manifest = (over: Partial<EditManifest> = {}): EditManifest => ({ version: 1, lane: "generic", video: join(dir, "render.mp4"), events: [], ...over });
before(async () => { dir = await mkdtemp(join(tmpdir(), "vqa-regressions-")); await writeFile(join(dir, "render.mp4"), "test identity; runners are injected"); });
after(async () => { await rm(dir, { recursive: true, force: true }); });

describe("storyboard coverage distinguishes schedule from visibility", () => {
  const plan = { version: 1 as const, elements: [{ id: "proof", start: 2, end: 4 }, { id: "cta", start: 5, end: 7 }] };
  it("fails a missing planned graphic even when the HTML is otherwise valid", () => {
    const r = validateStoryboard(plan, '<div id="proof" data-start="2" data-duration="2"></div><script>const hidden = `<div id="cta" data-start="5" data-duration="2">`;</script>');
    assert.equal(r.staticCoverage, "FAIL");
    assert.equal(r.elements[1].status, "missing");
    assert.equal(r.renderedVisibility, "not_verified");
  });
  it("detects a scheduled overlay whose end is before its start", () => {
    const r = validateStoryboard(plan, '<div id="proof" data-start="2" data-end="1"></div><div id="cta" data-start="5" data-duration="2"></div>');
    assert.equal(r.elements[0].status, "empty_interval");
    assert.equal(r.elements[1].status, "covered");
  });
  it("intersects ancestor timing and does not claim opaque/CSS visibility", () => {
    const r = validateStoryboard({ version: 1, elements: [{ id: "card", start: 2, end: 4 }] }, '<main data-start="0" data-duration="3"><div id="card" style="opacity:0" data-start="2" data-duration="2"></div></main>');
    assert.equal(r.elements[0].status, "timing_mismatch");
    assert.deepEqual(r.elements[0].scheduled, { start: 2, end: 3 });
    assert.equal(r.renderedVisibility, "not_verified");
  });
  it("rejects ambiguous IDs and invalid plan intervals", () => {
    assert.equal(validateStoryboard({ version: 1, elements: [{ id: "a", start: 0, end: 1 }] }, '<div id="a"></div><img id="a">').elements[0].status, "ambiguous");
    assert.equal(storyboardSchema.safeParse({ version: 1, elements: [{ id: "a", start: 2, end: 1 }] }).success, false);
    assert.equal(storyboardSchema.safeParse({ version: 1, elements: [plan.elements[0], plan.elements[0]] }).success, false);
  });
  it("extracts indexed samples from a real MP4 and records its identity", async () => {
    const video = join(dir, "storyboard.mp4"), html = join(dir, "storyboard.html"), json = join(dir, "storyboard.json"), outDir = join(dir, "storyboard-evidence");
    await runCapture(ffmpegBin(), ["-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=10:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", video]);
    await writeFile(html, '<div id="proof" data-start="0" data-duration="2"></div>');
    await writeFile(json, JSON.stringify({ version: 1, elements: [{ id: "proof", start: 0, end: 2 }] }));
    const r = await runStoryboardQa({ storyboard: json, html, video, outDir });
    assert.equal(r.staticCoverage, "PASS");
    assert.equal(r.evidenceStatus, "complete", JSON.stringify(r));
    assert.equal(r.renderedVisibility, "not_verified");
    const evidence = r.elements[0].evidence!;
    assert.equal(evidence.videoSha256.length, 64);
    assert.deepEqual(evidence.frames.map((f) => f.time), [0.2, 1, 1.8]);
    const png = await readFile(join(outDir, evidence.sheet));
    assert.equal(png.subarray(1, 4).toString(), "PNG");
    assert.equal(png.readUInt32BE(16), 960);
    // Same output directory, now an interval after the last decodable 10fps frame.
    // ffmpeg returns zero even when no image is written; old evidence must not pass.
    await writeFile(json, JSON.stringify({ version: 1, elements: [{ id: "proof", start: 1.99, end: 2 }] }));
    const emptySeek = await runStoryboardQa({ storyboard: json, html, video, outDir });
    assert.equal(emptySeek.evidenceStatus, "incomplete");
    assert.equal(emptySeek.elements[0].evidence, undefined);
    assert.ok(emptySeek.elements[0].evidenceError);
  });
});

describe("edit intent and source word mapping", () => {
  it("maps 160 cuts without cumulative transcript drift", () => {
    const events = Array.from({ length: 160 }, (_, i) => ({ id: `cut:${i}`, kind: "cut" as const, src: { start: i * 2 + 1, end: i * 2 + 2 }, out: { start: i + 1 } }));
    const words = Array.from({ length: 160 }, (_, i) => ({ text: `word${i}`, start: i * 2 + 0.2, end: i * 2 + 0.6 }));
    const mapped = mapSourceWordsToOutput(manifest({ events }), words, 320);
    assert.equal(mapped.length, 160);
    mapped.forEach((w, i) => assert.ok(Math.abs(w.start - i - 0.2) < 1e-10));
  });
  it("preserves reordered and repeated takes, caption text, and precise seam IDs", async () => {
    const edlPath = join(dir, "edl.json"), placementPath = join(dir, "placements.json");
    await writeFile(edlPath, JSON.stringify({ fps: 24, windows: [
      { id: "take-b", raw_start: 10, raw_end: 12, master_start: 0, master_end: 2 },
      { id: "take-a", raw_start: 2, raw_end: 4, master_start: 2, master_end: 4 },
      { id: "take-b-repeat", raw_start: 10, raw_end: 12, master_start: 4, master_end: 6 },
    ] }));
    await writeFile(placementPath, JSON.stringify([{ id: "caption", kind: "caption", text: "A preserved caption", start: 1, dur: 1 }]));
    const m = buildHyperframesManifest({ video: "out.mp4", edlPath, placementPath });
    const mapped = mapSourceWordsToOutput(m, [{ text: "A", start: 2.2, end: 2.6 }, { text: "B", start: 10.2, end: 10.6 }], 12);
    assert.deepEqual(mapped.map((w) => w.text), ["B", "A", "B"]);
    mapped.forEach((w, i) => assert.ok(Math.abs(w.start - (i * 2 + 0.2)) < 1e-10));
    assert.equal(m.events.find((e) => e.kind === "caption")?.text, "A preserved caption");
    assert.equal(new Set(m.events.map((e) => e.id)).size, m.events.length);
    assert.deepEqual(m.expected, { fps: 24 });
  });
  it("rejects reversed intervals, duplicate anchors and overlapping EDL output windows", async () => {
    assert.equal(editManifestSchema.safeParse(manifest({ events: [{ id: "a", kind: "caption", out: { start: 3, end: 1 } }] })).success, false);
    const e = { id: "same", kind: "cut" as const, out: { start: 1 } };
    assert.equal(editManifestSchema.safeParse(manifest({ events: [e, e] })).success, false);
    const edlPath = join(dir, "overlap-edl.json");
    await writeFile(edlPath, JSON.stringify({ windows: [
      { raw_start: 0, raw_end: 2, master_start: 0, master_end: 2 },
      { raw_start: 3, raw_end: 5, master_start: 1, master_end: 3 },
    ] }));
    assert.throws(() => buildHyperframesManifest({ video: "out.mp4", edlPath }), /overlap/);
  });
});

describe("dialogue/caption regressions without inference", () => {
  const fixedWords = async () => ({ words: [{ text: "tracking", start: 0.2, end: 0.9 }, { text: "works", start: 1.05, end: 1.5 }], sourceWords: [{ text: "tracking", start: 0.2, end: 1.3 }], via: "fixed-offline-fixture" });
  it("only confirms a silence-cut suspicion when an isolated fixed probe misses the word", async () => {
    const m = manifest({ events: [{ id: "cut:1", kind: "cut", out: { start: 1 }, src: { start: 1, end: 2 }, meta: { origin: "silence" } }] });
    const deps = { acquireWords: fixedWords, joinClickStat: async () => 0, probeWindow: async () => [{ text: "tracking", start: 0.2, end: 1 }] };
    const intact = await runTranscriptLayer(m, {}, () => {}, deps);
    assert.ok(!intact.issues.some((i) => i.category === "clipped_word"));
    const broken = await runTranscriptLayer(m, {}, () => {}, { ...deps, probeWindow: async () => [{ text: "works", start: 1.05, end: 1.5 }] });
    assert.ok(broken.issues.some((i) => i.category === "clipped_word" && i.severity === "HIGH"));
  });
  it("detects overlapping caption windows and permits deliberate separate tracks", async () => {
    const m = manifest({ words: [{ text: "hello", start: 0.1, end: 3 }], events: [
      { id: "caption:a", kind: "caption", text: "hello", out: { start: 0, end: 2 } },
      { id: "caption:b", kind: "caption", text: "hello", out: { start: 1.9, end: 3 } },
    ] });
    const r = await runTranscriptLayer(m, { probeEnabled: false });
    assert.ok(r.issues.some((i) => i.category === "caption_overlap"));
    m.events[0].meta = { track: 1 }; m.events[1].meta = { track: 2 };
    assert.ok(!(await runTranscriptLayer(m, { probeEnabled: false })).issues.some((i) => i.category === "caption_overlap"));
  });
  it("accepts point ASR timestamps without aborting and marks their coverage incomplete", async () => {
    const m = manifest({ sourceWords: [{ text: "anchor", start: 0.5, end: 0.5 }] });
    assert.equal(editManifestSchema.safeParse(m).success, true);
    const result = await runTranscriptLayer(m, { probeEnabled: false });
    assert.equal(result.status, "degraded");
    assert.match(result.reason!, /Zero-duration ASR/);
  });
  it("does not mistake one short seam-straddling word for two spoken occurrences", async () => {
    const m = manifest({ events: [{ id: "join", kind: "cut", out: { start: 1 } }], words: [
      { text: "came", start: 0.95, end: 0.99 }, { text: "out", start: 0.995, end: 1.005 }, { text: "well", start: 1.02, end: 1.2 },
    ] });
    const r = await runTranscriptLayer(m, { probeEnabled: false }, () => {}, { joinClickStat: async () => 0 });
    assert.ok(!r.issues.some((i) => i.category === "repeated_word"), JSON.stringify(r.issues));
    m.words = [{ text: "tracking", start: 0.5, end: 0.9 }, { text: "tracking", start: 1.1, end: 1.4 }];
    const duplicate = await runTranscriptLayer(m, { probeEnabled: false }, () => {}, { joinClickStat: async () => 0 });
    assert.ok(duplicate.issues.some((i) => i.category === "repeated_word" && i.severity === "HIGH"));
  });
  it("detects a real PCM step at a seam, with a smooth-tone negative control", async () => {
    const click = join(dir, "click.wav"), smooth = join(dir, "smooth.wav");
    await runCapture(ffmpegBin(), ["-nostdin", "-y", "-f", "lavfi", "-i", "aevalsrc=if(lt(t\\,1)\\,0.6\\,-0.6):s=48000:d=2", "-c:a", "pcm_f32le", click]);
    await runCapture(ffmpegBin(), ["-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2", "-c:a", "pcm_f32le", smooth]);
    const m = manifest({ video: click, words: (await fixedWords()).words, events: [{ id: "join", kind: "cut", out: { start: 1 } }] });
    assert.ok((await runTranscriptLayer(m, { probeEnabled: false })).issues.some((i) => i.category === "splice_click"));
    assert.ok(!(await runTranscriptLayer({ ...m, video: smooth }, { probeEnabled: false })).issues.some((i) => i.category === "splice_click"));
  });
});

describe("QA coverage, caching and unavailable backends", () => {
  it("warns for partial coverage, gates required layers, and never calls it a clean pass", () => {
    const args = { video: "v", videoSha256: "s", iteration: 1, technical: pass(), transcript: { status: "degraded" as const, issues: [] }, semantic: { status: "skipped" as const, issues: [] } };
    const r = aggregate(args);
    assert.equal(r.verdict, "PASS_WITH_WARNINGS");
    assert.deepEqual(r.coverage.unavailable, ["transcript", "semantic"]);
    assert.doesNotMatch(renderMarkdown(r), /Clean pass/);
    assert.equal(aggregate({ ...args, requiredLayers: ["technical", "transcript"] }).verdict, "FAIL");
  });
  it("does not corroborate a visual glitch with global loudness", () => {
    const issue = { id: "x", source: "technical" as const, severity: "MEDIUM" as const, category: "loudness_off_target", eventId: null, timeWindow: { start: 0, end: 100 }, objective: true, message: "m" };
    const r = aggregate({ video: "v", videoSha256: "s", iteration: 1, technical: { status: "warn", issues: [issue] }, transcript: pass(), semantic: { status: "warn", issues: [{ ...issue, id: "s", source: "semantic", category: "visual_glitch", timeWindow: { start: 4, end: 5 } }] } });
    assert.ok(r.issues.every((i) => !i.corroborated));
  });
  it("invalidates instructions/FPS/config and retries degraded layers while saving a partial report", async () => {
    const previous = process.env.VIDEO_QA_CACHE_DIR;
    process.env.VIDEO_QA_CACHE_DIR = join(dir, "cache");
    try {
      let semanticCalls = 0, transcriptCalls = 0;
      let failTranscript = true;
      const base = { manifest: manifest(), autoInspect: 0, outDir: join(dir, "report"), log: () => {}, runners: {
        technical: async () => ({ ...pass(), stats: { duration: 2 } }),
        transcript: async () => { transcriptCalls++; if (failTranscript) throw new Error("offline fixture: transcriber unavailable"); return pass(); },
        semantic: async () => { semanticCalls++; return pass(); },
      } };
      const a = await runQa({ ...base, instructions: "check headline", geminiFps: 5 });
      assert.equal(a.report.verdict, "PASS_WITH_WARNINGS");
      assert.equal(JSON.parse(await readFile(join(base.outDir, "qa-report.json"), "utf8")).coverage.complete, false);
      failTranscript = false;
      await runQa({ ...base, instructions: "check headline", geminiFps: 5 });
      assert.equal(transcriptCalls, 2, "a degraded result must be retried");
      assert.equal(semanticCalls, 1, "unchanged semantic evaluation is cached");
      await runQa({ ...base, instructions: "check CTA", geminiFps: 5 });
      await runQa({ ...base, instructions: "check CTA", geminiFps: 1 });
      assert.equal(semanticCalls, 3);
      await runQa({ ...base, instructions: "check CTA", geminiFps: 1, transcriptOptions: { clickMaxDiff: 0.1 } });
      assert.equal(transcriptCalls, 3);
      const broken = await runQa({ ...base, noCache: true, requiredLayers: ["semantic"], runners: { ...base.runners, semantic: async () => { throw new Error("upload failed"); } } });
      assert.equal(broken.report.verdict, "FAIL");
      assert.equal(broken.report.layers.technical.status, "pass");
      assert.match(broken.report.layers.semantic.reason!, /upload failed/);
      const invalidCache = join(dir, "not-a-cache-directory");
      await writeFile(invalidCache, "a file blocks cache directory creation");
      process.env.VIDEO_QA_CACHE_DIR = invalidCache;
      const uncached = await runQa(base);
      assert.equal(uncached.report.verdict, "PASS", "cache I/O failure must not discard completed QA");
    } finally { if (previous == null) delete process.env.VIDEO_QA_CACHE_DIR; else process.env.VIDEO_QA_CACHE_DIR = previous; }
  });
});
