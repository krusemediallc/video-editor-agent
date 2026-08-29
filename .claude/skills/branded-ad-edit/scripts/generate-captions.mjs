#!/usr/bin/env node
/**
 * generate-captions.mjs — karaoke caption generator for branded-ad-edit compositions.
 *
 * Reads a word-level transcript and a config, emits two fragments to inject into the
 * composition template (e.g. via {{CAPTION_SPANS}} / {{CAPTION_TWEENS}} placeholders):
 *   <out>/caption-spans.html   — positioned <div class="cap cap-<mode>"> spans
 *   <out>/caption-tweens.js    — GSAP statements for the single paused timeline
 *
 * Usage:  node generate-captions.mjs transcript.json config.json <outDir>
 *
 * transcript.json: [{ "text": "word", "start": 1.23, "end": 1.5 }, ...]   (flat array)
 *
 * config.json:
 * {
 *   "fps": 30,
 *   "duration": 72.03,                       // composition duration (clamp target)
 *   "maxWordsPerChunk": 3,
 *   "gapBreak": 0.45,                        // start a new chunk after a pause this long
 *   "modeRanges": [                          // first match wins; default "split"
 *     { "from": 12.6, "to": 17.2,  "mode": "solo" },
 *     { "from": 44.0, "to": 48.8,  "mode": "full" },
 *     { "from": 8.57, "to": 12.95, "mode": "fullhim" }
 *   ],
 *   "colorRanges": [                         // highlight color by beat sentiment; default "r"
 *     { "from": 44.0, "to": 48.97, "color": "g" },
 *     { "from": 48.97, "to": 57.2, "color": "b" }
 *   ],
 *   "highlight": "^(?:\\$[\\d,.]+|[\\d,.]+%|[\\d][\\d,.]*|free|roas)$",   // token regex (case-insensitive)
 *   "merges": [["Brand", "name.io", "brandname.io"]]   // fix ASR splits: [wordA, wordB, replacement]
 * }
 *
 * Corresponding CSS the template must provide:
 *   .cap { position:absolute; left:40px; width:1000px; text-align:center; font-weight:800;
 *          font-size:78px; line-height:1.14; color:#fff; visibility:hidden; opacity:0;
 *          text-shadow:0 4px 10px rgba(0,0,0,.85), 0 12px 40px rgba(0,0,0,.6); }
 *   .cap em { font-style:normal; font-weight:900; }
 *   .cap em.r { color:var(--red); } .cap em.g { color:var(--green); } .cap em.b { color:var(--brand-accent-soft); }
 *   .cap-split { top:880px; } .cap-solo { top:1440px; } .cap-fullhim { top:1500px; } .cap-full { top:1560px; }
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

const [, , transcriptPath, configPath, outDir] = process.argv;
if (!outDir) {
  console.error("usage: node generate-captions.mjs transcript.json config.json <outDir>");
  process.exit(1);
}
const words = JSON.parse(readFileSync(transcriptPath, "utf8"));
const cfg = JSON.parse(readFileSync(configPath, "utf8"));
const FPS = cfg.fps ?? 30;
const DUR = cfg.duration;
const Q = (t) => Math.round(t * FPS) / FPS;

// ── ASR merges (brand names split across words) ──
for (const [a, b, repl] of cfg.merges ?? []) {
  for (let i = 0; i < words.length - 1; i++) {
    if (words[i].text === a && words[i + 1].text.toLowerCase() === b.toLowerCase()) {
      words[i] = { text: repl, start: words[i].start, end: words[i + 1].end };
      words.splice(i + 1, 1);
    }
  }
}
// clamp Whisper's overshoot on the final word
for (const w of words) w.end = Math.min(w.end, DUR - 0.02);

const inRange = (ranges, t, key, dflt) => {
  for (const r of ranges ?? []) if (t >= r.from && t < r.to) return r[key];
  return dflt;
};
const HL = new RegExp(cfg.highlight ?? "^$", "i");
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// ── chunking: 1-N words, break at punctuation / gaps ──
const chunks = [];
let cur = [];
for (const w of words) {
  const prev = cur[cur.length - 1];
  if (cur.length && (cur.length >= (cfg.maxWordsPerChunk ?? 3) || w.start - prev.end > (cfg.gapBreak ?? 0.45))) {
    chunks.push(cur);
    cur = [];
  }
  cur.push(w);
  if (/[.!?,]$/.test(w.text)) {
    chunks.push(cur);
    cur = [];
  }
}
if (cur.length) chunks.push(cur);

// ── display windows: start−0.04 → next chunk's RAW start −0.04, ALWAYS.
//    (Holding past the next chunk's start renders a mashed double-caption.) ──
const windows = chunks.map((c, i) => {
  const rawStart = c[0].start;
  const next = chunks[i + 1];
  return {
    words: c,
    start: Math.max(0, rawStart - 0.04),
    end: next ? next[0].start - 0.04 : Math.min(c[c.length - 1].end + 0.3, DUR - 0.05),
    mid: (rawStart + c[c.length - 1].end) / 2,
  };
});

const spans = [];
const tweens = [];
windows.forEach((c, i) => {
  const mode = inRange(cfg.modeRanges, c.mid, "mode", "split");
  const color = inRange(cfg.colorRanges, c.mid, "color", "r");
  const html = c.words
    .map((w) => {
      const clean = w.text.replace(/[.,!?]$/, "");
      return HL.test(clean) || HL.test(w.text) ? `<em class="${color}">${esc(w.text)}</em>` : esc(w.text);
    })
    .join(" ");
  const id = `cap-${String(i).padStart(2, "0")}`;
  spans.push(`        <div class="cap cap-${mode}" id="${id}">${html}</div>`);
  const t0 = Q(c.start).toFixed(4);
  const t1 = Q(Math.min(c.end, DUR - 0.04)).toFixed(4);
  tweens.push(
    `          tl.set("#${id}", { visibility: "visible" }, ${t0});\n` +
      `          tl.fromTo("#${id}", { opacity: 0, scale: 0.92 }, { opacity: 1, scale: 1, duration: 0.12, ease: "power2.out" }, ${t0});\n` +
      `          tl.set("#${id}", { opacity: 0, visibility: "hidden" }, ${t1});`
  );
});

mkdirSync(outDir, { recursive: true });
writeFileSync(`${outDir}/caption-spans.html`, spans.join("\n"));
writeFileSync(`${outDir}/caption-tweens.js`, tweens.join("\n"));
console.log(`captions: ${windows.length} chunks → ${outDir}/caption-{spans.html,tweens.js}`);

// sanity: no two caption windows may overlap
for (let i = 0; i < windows.length - 1; i++) {
  if (Q(Math.min(windows[i].end, DUR - 0.04)) > Q(windows[i + 1].start) + 1e-6) {
    console.error(`WARN overlap: cap-${i} ends after cap-${i + 1} starts`);
  }
}
