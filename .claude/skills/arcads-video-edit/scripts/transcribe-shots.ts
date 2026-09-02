import "dotenv/config";
import fs from "node:fs";
import path from "node:path";
import { transcribeWithTimestamps } from "../../../src/services/openai";

const BASE = process.argv[2] || process.env.PROJECT_DIR || ".";   // the project folder
async function main() {
  const man = JSON.parse(fs.readFileSync(path.join(BASE, "mg/seg-audio/manifest.json"), "utf8"));
  const words: any[] = [];
  for (const m of man) {
    const buf = fs.readFileSync(path.join(BASE, m.wav));
    const f = new File([new Uint8Array(buf)], `${m.id}.wav`, { type: "audio/wav" });
    const r: any = await transcribeWithTimestamps(f, {
      granularity: ["word"],
      prompt: process.env.WHISPER_PROMPT || "Arcads, Seedance, Claude Code, UGC, claymation, ad creative, media buyers",   // brand + product names the speaker says
    });
    const ws = (r.words ?? []).map((w: any) => ({
      text: w.word ?? w.text,
      start: +(m.master_start + w.start).toFixed(3),
      end: +(m.master_start + w.end).toFixed(3),
      seg: m.id,
    }));
    words.push(...ws);
    console.log(`${m.id.padEnd(16)} ${String(ws.length).padStart(3)}w  ${(r.text ?? "").trim().slice(0, 78)}`);
  }
  words.sort((a, b) => a.start - b.start);
  fs.writeFileSync(path.join(BASE, "mg/words.json"), JSON.stringify(words, null, 1));
  console.log(`\nTOTAL ${words.length} words -> mg/words.json`);
}
main().catch((e) => { console.error(e); process.exit(1); });
