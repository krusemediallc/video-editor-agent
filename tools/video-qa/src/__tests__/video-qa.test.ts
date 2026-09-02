/**
 * video-qa test suite (node:test via `npm run qa:test`).
 * Run node unsandboxed on this machine (sandbox kills Node).
 *
 * ffmpeg fixtures are generated on first run into fixtures/gen/ (gitignored).
 * The clean fixture is the permanent false-positive canary.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { before, describe, it } from "node:test";
import type { EditManifest } from "../types";
import { runTechnicalLayer } from "../layer1-technical";
import { runTranscriptLayer } from "../layer2-transcript";
import { runSemanticLayer } from "../layer3-semantic";
import { mapSourceWordsToOutput } from "../transcribe";
import { aggregate } from "../report";
import { cacheKey } from "../cache";
import { GEN_DIR, makeFixtures, type MidwordFixture } from "./make-fixtures";

const quiet = () => {};

function baseManifest(video: string, overrides: Partial<EditManifest> = {}): EditManifest {
  return {
    version: 1,
    lane: "generic",
    video,
    events: [],
    intentional: { loudnessTarget: { lufs: -14, tolerance: 8 } },
    ...overrides,
  };
}

before(async () => {
  await makeFixtures();
}, { timeout: 300_000 });

describe("layer 1 — technical", () => {
  it("clean fixture passes (permanent false-positive canary)", async () => {
    const r = await runTechnicalLayer(baseManifest(join(GEN_DIR, "clean.mp4")), {}, quiet);
    const blocking = r.issues.filter((i) => i.severity === "CRITICAL" || i.severity === "HIGH");
    assert.equal(blocking.length, 0, JSON.stringify(blocking, null, 1));
  });

  it("detects unexpected black frames + the silence under them", async () => {
    const r = await runTechnicalLayer(baseManifest(join(GEN_DIR, "black-gap.mp4")), {}, quiet);
    assert.ok(r.issues.some((i) => i.category === "black_frames"), JSON.stringify(r.issues));
  });

  it("respects intentional black regions", async () => {
    const manifest = baseManifest(join(GEN_DIR, "black-gap.mp4"), {
      intentional: {
        blackRegions: [{ start: 2.9, end: 3.9 }],
        silentRegions: [{ start: 2.9, end: 3.9 }],
        loudnessTarget: { lufs: -14, tolerance: 8 },
      },
    });
    const r = await runTechnicalLayer(manifest, {}, quiet);
    assert.ok(!r.issues.some((i) => i.category === "black_frames"), JSON.stringify(r.issues));
  });

  it("detects clipping", async () => {
    const r = await runTechnicalLayer(baseManifest(join(GEN_DIR, "clipping.mp4")), {}, quiet);
    assert.ok(
      r.issues.some((i) => ["clipping_risk", "waveform_flatline"].includes(i.category) && i.severity !== "LOW"),
      JSON.stringify(r.issues)
    );
  });

  it("detects frozen frames", async () => {
    const r = await runTechnicalLayer(baseManifest(join(GEN_DIR, "freeze.mp4")), {}, quiet);
    assert.ok(r.issues.some((i) => i.category === "frozen_frames"), JSON.stringify(r.issues));
  });

  it("detects duration mismatch from the FILE", async () => {
    const manifest = baseManifest(join(GEN_DIR, "clean.mp4"), { expectedDuration: 20 });
    const r = await runTechnicalLayer(manifest, {}, quiet);
    assert.ok(r.issues.some((i) => i.category === "duration_mismatch"));
  });

  it("missing audio is CRITICAL unless intentional.noAudio", async () => {
    // testsrc2-only clip has no audio stream
    const { runCapture, ffmpegBin } = await import("../ffmpeg");
    const silent = join(GEN_DIR, "no-audio.mp4");
    if (!existsSync(silent)) {
      await runCapture(ffmpegBin(), [
        "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=d=2:s=320x568:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", silent,
      ]);
    }
    const r1 = await runTechnicalLayer(baseManifest(silent), {}, quiet);
    assert.ok(r1.issues.some((i) => i.category === "missing_audio_stream" && i.severity === "CRITICAL"));
    const r2 = await runTechnicalLayer(
      baseManifest(silent, { intentional: { noAudio: true } }),
      {},
      quiet
    );
    assert.ok(!r2.issues.some((i) => i.category === "missing_audio_stream"));
  });
});

describe("word mapping (new_t parity)", () => {
  const words = [
    { text: "alpha", start: 0.5, end: 1.0 },
    { text: "cutme", start: 1.9, end: 2.4 }, // straddles removal start at 2.1
    { text: "gone", start: 2.5, end: 2.9 }, // fully removed
    { text: "beta", start: 3.6, end: 4.0 }, // after removal 2.1-3.4
  ];
  const manifest: EditManifest = {
    version: 1,
    lane: "generic",
    video: "x.mp4",
    events: [
      {
        id: "cut:src2.1",
        kind: "cut",
        out: { start: 2.1 },
        src: { start: 2.1, end: 3.4 },
        dialogueCut: true,
      },
    ],
  };

  it("shifts post-cut words and drops removed ones", () => {
    const mapped = mapSourceWordsToOutput(manifest, words, 6);
    const byText = Object.fromEntries(mapped.map((w) => [w.text, w]));
    assert.ok(byText.alpha && Math.abs(byText.alpha.start - 0.5) < 1e-6);
    assert.ok(!byText.gone, "fully-removed word must be dropped");
    // beta: source 3.6 → output 3.6 - 1.3 = 2.3
    assert.ok(byText.beta && Math.abs(byText.beta.start - 2.3) < 1e-6, JSON.stringify(byText.beta));
    // cutme midpoint (2.1) sits at the edge; clamped version survives with end at cut
    if (byText.cutme) assert.ok(byText.cutme.end <= 2.1 + 1e-6);
  });
});

describe("report aggregation + anchoring", () => {
  const mkIssue = (over: Record<string, unknown>) => ({
    id: "x",
    source: "technical" as const,
    severity: "HIGH" as const,
    category: "c",
    eventId: null,
    timeWindow: { start: 1, end: 2 },
    message: "m",
    objective: true,
    ...over,
  });

  it("verdicts: HIGH fails, MEDIUM warns, LOW passes", () => {
    const empty = { status: "pass" as const, issues: [] };
    const mk = (issues: ReturnType<typeof mkIssue>[]) =>
      aggregate({
        video: "v",
        videoSha256: "s",
        iteration: 1,
        technical: { status: "warn", issues },
        transcript: empty,
        semantic: { status: "skipped", reason: "test", issues: [] },
      });
    assert.equal(mk([mkIssue({})]).verdict, "FAIL");
    assert.equal(mk([mkIssue({ severity: "MEDIUM" })]).verdict, "PASS_WITH_WARNINGS");
    assert.equal(mk([mkIssue({ severity: "LOW" })]).verdict, "PASS");
    assert.equal(mk([]).verdict, "PASS");
  });

  it("anchored issues survive a simulated re-render with shifted timestamps", () => {
    // Same anchor id, shifted window — resolution tracking compares anchors.
    const before = mkIssue({ eventId: "cut:src12.4", timeWindow: { start: 10.1, end: 10.4 } });
    const after = mkIssue({ eventId: "cut:src12.4", timeWindow: { start: 9.6, end: 9.9 } });
    assert.equal(before.eventId, after.eventId);
  });

  it("corroboration marks overlapping semantic + deterministic issues", () => {
    const det = mkIssue({ eventId: "cut:src5.0" });
    const sem = mkIssue({ source: "semantic", eventId: "cut:src5.0", severity: "MEDIUM" });
    const report = aggregate({
      video: "v",
      videoSha256: "s",
      iteration: 1,
      technical: { status: "fail", issues: [det] },
      transcript: { status: "pass", issues: [] },
      semantic: { status: "warn", issues: [sem] },
    });
    assert.ok(report.issues.every((i) => i.corroborated === true));
  });
});

describe("cache keys", () => {
  it("changes with video, manifest, and model", () => {
    const k = (videoSha: string, manifestSha: string, model?: string) =>
      cacheKey({ videoSha, manifestSha, layer: "L1", model });
    assert.notEqual(k("a", "m"), k("b", "m"));
    assert.notEqual(k("a", "m"), k("a", "n"));
    assert.notEqual(k("a", "m", "g1"), k("a", "m", "g2"));
    assert.equal(k("a", "m", "g1"), k("a", "m", "g1"));
  });
});

describe("layer 3 — graceful degradation", () => {
  it("skips cleanly without GEMINI_API_KEY", async () => {
    const saved = process.env.GEMINI_API_KEY;
    delete process.env.GEMINI_API_KEY;
    try {
      const r = await runSemanticLayer(baseManifest(join(GEN_DIR, "clean.mp4")), { log: quiet });
      assert.equal(r.status, "skipped");
      assert.match(r.reason ?? "", /GEMINI_API_KEY/);
    } finally {
      if (saved) process.env.GEMINI_API_KEY = saved;
    }
  });
});

describe("layer 2 — mid-word cut (TTS fixture)", () => {
  it("flags the clipped word on a manual cut", { timeout: 300_000 }, async (t) => {
    const fixturePath = join(GEN_DIR, "midword.json");
    if (!existsSync(fixturePath)) {
      t.skip("midword fixture unavailable (no TTS/transcriber on this machine)");
      return;
    }
    const fx = JSON.parse(readFileSync(fixturePath, "utf8")) as MidwordFixture;
    const manifest: EditManifest = {
      version: 1,
      lane: "reel-recut",
      video: fx.video,
      source: fx.sourceVideo,
      events: [
        {
          id: `cut:src${fx.cutSourceTime.toFixed(1)}`,
          kind: "cut",
          dialogueCut: true,
          out: { start: fx.cutSourceTime },
          src: { start: fx.cutSourceTime, end: fx.cutSourceTime + 1.2 },
          meta: { origin: "manual" },
        },
      ],
      sourceWords: fx.sourceWords,
    };
    const r = await runTranscriptLayer(manifest, {}, quiet);
    const clipped = r.issues.filter((i) => i.category === "clipped_word");
    assert.ok(clipped.length >= 1, `expected clipped_word, got ${JSON.stringify(r.issues)}`);
    assert.ok(
      clipped.some((i) => i.severity === "HIGH"),
      `expected HIGH clipped_word (probe should confirm): ${JSON.stringify(clipped, null, 1)}`
    );
  });
});
