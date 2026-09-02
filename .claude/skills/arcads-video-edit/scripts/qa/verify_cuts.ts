/**
 * Empirically verify every cut in edl.json.
 *
 * For each cut, render ~0.9s of context either side TWO ways - with the cut applied, and with
 * the source left contiguous - transcribe both with word timestamps, and compare. If the cut
 * changes the words heard, or measurably shortens one, it is vetoed and written back into
 * edl.json so tighten.py will merge that gap on the next run.
 *
 * This exists because neither a VAD threshold nor Whisper's word spans can tell you whether a
 * cut damaged a word. Both produced false positives AND false negatives on this material.
 */
import "dotenv/config";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import { transcribeWithTimestamps } from "../../../src/services/openai.js";

function gapIsSilent(take: string, g0: number, g1: number): boolean {
  return execFileSync("python3", [`${DIR}/qa/silent_gap.py`, take, String(g0), String(g1)])
    .toString().includes("SILENT");
}

const FF = process.env.FFMPEG || "ffmpeg";
const DIR = process.argv[2] || process.env.PROJECT_DIR || ".";   // the project folder
const RAW = `${DIR}/raw`;
const CTX = 0.90;
const SHRINK_ABS = 0.08;
const SHRINK_REL = 0.20;

type Seg = { id: string; take: string; keep: [number, number][]; veto?: [number, number][] };

function render(take: string, ranges: [number, number][], out: string) {
  const parts = ranges.map(([a, b], i) => {
    const p = `/tmp/_vc_${i}.wav`;
    execFileSync(FF, ["-v","error","-y","-ss",String(a),"-to",String(b),"-i",`${RAW}/Take ${take} - Mic.wav`,p]);
    return p;
  });
  fs.writeFileSync("/tmp/_vc_list.txt", parts.map((p) => `file '${p}'`).join("\n"));
  execFileSync(FF, ["-v","error","-y","-f","concat","-safe","0","-i","/tmp/_vc_list.txt","-ar","16000","-ac","1",out]);
}

async function words(path: string) {
  const buf = fs.readFileSync(path);
  const f = new File([new Uint8Array(buf)], "s.wav", { type: "audio/wav" });
  const r = await transcribeWithTimestamps(f, { language: "en", granularity: ["word"] });
  return (r.words ?? []).map((w) => ({ w: w.word.toLowerCase().replace(/[^a-z0-9']/g, ""), d: w.end - w.start }));
}

async function main() {
  const edl = JSON.parse(fs.readFileSync(`${DIR}/edl.json`, "utf8"));
  let checked = 0, vetoed = 0;
  for (const seg of edl.segments as Seg[]) {
    const vetoes: [number, number][] = [];
    for (let i = 0; i < seg.keep.length - 1; i++) {
      const [a0, a1] = seg.keep[i];
      const [b0, b1] = seg.keep[i + 1];
      // A long gap is a deliberate structural cut (a video hold being trimmed), not a
      // silence-trim, and the verifier has no way to tell "removed a word" from "removed
      // background ad audio". Only silence-trims are in scope.
      if (b0 - a1 > 1.0) { console.log(`SKIP  ${seg.id.padEnd(16)} cut ${a1.toFixed(3)}-${b0.toFixed(3)} (structural, ${(b0 - a1).toFixed(2)}s)`); continue; }
      const ctxA: [number, number] = [Math.max(a0, a1 - CTX), a1];
      const ctxB: [number, number] = [b0, Math.min(b1, b0 + CTX)];
      if (gapIsSilent(seg.take, a1, b0)) {
        console.log(`SAFE  ${seg.id.padEnd(16)} cut ${a1.toFixed(3)}-${b0.toFixed(3)} (${(b0 - a1).toFixed(3)}s)  gap is acoustically silent`);
        checked++;
        continue;
      }
      render(seg.take, [ctxA, ctxB], "/tmp/_vc_with.wav");
      render(seg.take, [[ctxA[0], ctxB[1]]], "/tmp/_vc_without.wav");
      const [W, N] = await Promise.all([words("/tmp/_vc_with.wav"), words("/tmp/_vc_without.wav")]);
      checked++;
      let verdict = "SAFE", why = "";
      const seqW = W.map((x) => x.w).join(" ");
      const seqN = N.map((x) => x.w).join(" ");
      if (seqW !== seqN) {
        // Whisper is unstable on 2s fragments; make it reproduce before trusting it.
        const [W2, N2] = await Promise.all([words("/tmp/_vc_with.wav"), words("/tmp/_vc_without.wav")]);
        if (W2.map((x) => x.w).join(" ") !== N2.map((x) => x.w).join(" ")) {
          verdict = "VETO"; why = `words changed (x2): "${seqN}" -> "${seqW}"`;
        } else {
          why = `word-diff did not reproduce, ignored`;
        }
      }
      if (verdict === "SAFE") {
        for (let k = 0; k < W.length; k++) {
          const lost = N[k].d - W[k].d;
          if (lost > SHRINK_ABS && lost / N[k].d > SHRINK_REL) {
            verdict = "VETO";
            why = `"${N[k].w}" ${N[k].d.toFixed(2)}s -> ${W[k].d.toFixed(2)}s (-${Math.round((lost / N[k].d) * 100)}%)`;
            break;
          }
        }
      }
      if (verdict === "VETO") { vetoes.push([a1, b0]); vetoed++; }
      console.log(`${verdict.padEnd(5)} ${seg.id.padEnd(16)} cut ${a1.toFixed(3)}-${b0.toFixed(3)} (${(b0 - a1).toFixed(3)}s)  ${why}`);
    }
    // ADDITIVE. Once a gap is proven to damage a word, tighten.py merges it, so it stops
    // appearing as a cut on the next run - if we replaced the list here the veto would be
    // forgotten and the bad cut would come straight back.
    const prev: [number, number][] = seg.veto ?? [];
    const merged = [...prev];
    for (const v of vetoes) {
      if (!merged.some((p) => Math.abs(p[0] - v[0]) < 0.02 && Math.abs(p[1] - v[1]) < 0.02)) merged.push(v);
    }
    if (merged.length) seg.veto = merged;
  }
  fs.writeFileSync(`${DIR}/edl.json`, JSON.stringify(edl, null, 2));
  console.log(`\n${checked} cuts checked, ${vetoed} vetoed`);
}
main().catch((e) => { console.error(e); process.exit(1); });
