/**
 * qa-video — run the 4-layer video QA funnel on a rendered .mp4.
 *
 *   npm run qa:video -- --manifest Videos/_reel-recut-0814/spec.qa-manifest.json
 *   npm run qa:video -- --lane hyperframes --video out.mp4 \
 *       --edl v916-edl.json --words v916/words-master.json [--placement manifest.json]
 *   flags: --skip-semantic  --fps N  --instructions file.txt  --words file.json
 *          --source file.mp4  --out dir  --no-cache  --json (print report JSON)
 *
 * Exit codes: 0 = PASS, 1 = PASS_WITH_WARNINGS, 2 = FAIL.
 * If an agent sandbox kills Node, run with the sandbox disabled.
 */
import { resolveFromInvoker } from "../src/env";
import { existsSync, readFileSync } from "node:fs";

import { loadManifest } from "../src/manifest/schema";
import { buildHyperframesManifest } from "../src/manifest/adapter-hyperframes";
import { runQa } from "../src/index";
import { exitCode } from "../src/report";
import type { EditManifest, WordTiming } from "../src/types";

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}
const flag = (name: string) => process.argv.includes(`--${name}`);

/** Accepts flat [{text|word,start,end}], OpenAI verbose {words:[…]}, or
 *  whisper.cpp {transcription:[{tokens:[…]}]} word files. */
function readWordsFile(path: string): WordTiming[] {
  const data = JSON.parse(readFileSync(path, "utf8")) as unknown;
  type RawWord = { text?: string; word?: string; start: number; end: number };
  let arr: RawWord[] = [];
  if (Array.isArray(data)) {
    arr = data as RawWord[];
  } else if (data && typeof data === "object") {
    const obj = data as {
      words?: RawWord[];
      transcription?: Array<{ tokens?: Array<{ text?: string; offsets?: { from: number; to: number } }> }>;
    };
    if (Array.isArray(obj.words)) {
      arr = obj.words;
    } else if (Array.isArray(obj.transcription)) {
      for (const seg of obj.transcription) {
        for (const tok of seg.tokens ?? []) {
          const t = (tok.text ?? "").trim();
          if (t && !t.startsWith("[_") && tok.offsets) {
            arr.push({ text: t, start: tok.offsets.from / 1000, end: tok.offsets.to / 1000 });
          }
        }
      }
    }
  }
  return arr
    .filter((w) => (w.text ?? w.word) != null)
    .map((w) => ({ text: (w.text ?? w.word ?? "").trim(), start: w.start, end: w.end }));
}

async function main() {
  let manifest: EditManifest;
  let manifestPath: string | undefined;

  if (arg("manifest")) {
    manifestPath = resolveFromInvoker(arg("manifest")!);
    manifest = loadManifest(manifestPath);
    if (arg("video")) manifest.video = resolveFromInvoker(arg("video")!);
  } else if (arg("lane") === "hyperframes") {
    if (!arg("video")) throw new Error("--lane hyperframes requires --video");
    manifest = buildHyperframesManifest({
      video: resolveFromInvoker(arg("video")!),
      source: arg("source") ? resolveFromInvoker(arg("source")!) : undefined,
      placementPath: arg("placement") ? resolveFromInvoker(arg("placement")!) : undefined,
      edlPath: arg("edl") ? resolveFromInvoker(arg("edl")!) : undefined,
      wordsPath: arg("words") ? resolveFromInvoker(arg("words")!) : undefined,
      sourceWordsPath: arg("source-words") ? resolveFromInvoker(arg("source-words")!) : undefined,
      expectedDuration: arg("duration") ? Number(arg("duration")) : undefined,
    });
  } else if (arg("video")) {
    // Generic lane: technical + semantic layers only (no edit intent available).
    manifest = {
      version: 1,
      lane: "generic",
      video: resolveFromInvoker(arg("video")!),
      events: [],
      intentional: {},
    };
  } else {
    console.error(
      "usage: qa-video --manifest <qa-manifest.json> | --video <mp4> [--lane hyperframes --edl ... --words ...]"
    );
    process.exit(2);
    return;
  }

  // Late word injection for manifests that lack them (e.g. a reel-recut spec
  // without a "words" entry — pass the project's whisper JSON here).
  if (arg("manifest") && arg("words")) {
    const wordsPath = resolveFromInvoker(arg("words")!);
    if (existsSync(wordsPath)) {
      const words = readWordsFile(wordsPath);
      // Heuristic: words files given here are SOURCE-time unless --words-are-output.
      if (flag("words-are-output")) manifest.words = words;
      else manifest.sourceWords = words;
    }
  }

  const { report } = await runQa({
    manifest,
    manifestPath,
    skipSemantic: flag("skip-semantic"),
    instructions: arg("instructions") ? readFileSync(resolveFromInvoker(arg("instructions")!), "utf8") : undefined,
    geminiFps: arg("fps") ? Number(arg("fps")) : undefined,
    outDir: arg("out") ? resolveFromInvoker(arg("out")!) : undefined,
    noCache: flag("no-cache"),
  });

  if (flag("json")) console.log(JSON.stringify(report, null, 1));
  process.exit(exitCode(report.verdict));
}

main().catch((e) => {
  console.error(`[qa] fatal: ${(e as Error).message}`);
  process.exit(2);
});
