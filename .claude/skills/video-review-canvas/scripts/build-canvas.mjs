#!/usr/bin/env node
/**
 * build-canvas.mjs — assemble a here.now review canvas directory from a video + a beat map.
 *
 *   node build-canvas.mjs <config.json>
 *
 * Writes <outDir>/{index.html, <video-vN.mp4>, .herenow/data.json} ready for the here-now
 * skill's publish.sh. It probes the video with ffprobe for duration/fps so the scrubber is
 * frame-accurate — a note pinned to the wrong frame sends the next cut chasing the wrong beat.
 *
 * Env:
 *   FFPROBE          path to ffprobe (default: "ffprobe" on PATH)
 *   HERENOW_PUBLISH  path to the here-now skill's publish.sh (only used in the printed hint)
 *
 * config.json:
 * {
 *   "video":   "videos/proj/output-v2.mp4",    // source file to copy in
 *   "outDir":  "videos/proj/review",
 *   "title":   "Product launch ad",
 *   "version": "v1",                           // ALSO the notes filter + the video filename suffix
 *   "versionLabel": "V1",                      // optional, defaults to version.toUpperCase()
 *   "eyebrow": "STUDIO · EDIT REVIEW",
 *   "blurb":   "Motion graphic on every line, cut like the reference ad.",
 *   "author":  "Reviewer",
 *   "accents": ["#0082fb", "#a033ff", "#ff5c87"],   // optional, defaults to a neutral blue→pink
 *   "playerWidth": "min(52vh,430px)",               // optional
 *   "facts":   ["30.03s · 1080×1920 · 30fps", "8 designed cards"],
 *   "beats":   [ { "t": 0.0, "n": "Hook", "s": "why it's here", "tone": "mute" }, ... ]
 * }
 *
 * tone: "" (accent) | "red" | "green" | "amber" | "mute" — colours the beat's left rule so the
 * arc of the edit is legible at a glance in the sidebar.
 */
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath, not new URL().pathname — the latter percent-encodes spaces, and project
// paths often contain them.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE = path.join(HERE, "..", "assets", "canvas-template.html");
const MANIFEST = path.join(HERE, "..", "assets", "data.json");
const FFPROBE = process.env.FFPROBE || "ffprobe";
const PUBLISH_SH =
  process.env.HERENOW_PUBLISH || "~/.agents/skills/here-now/scripts/publish.sh";

const cfgPath = process.argv[2];
if (!cfgPath) {
  console.error("usage: node build-canvas.mjs <config.json>");
  process.exit(1);
}
const cfg = JSON.parse(readFileSync(cfgPath, "utf8"));
const cfgDir = path.dirname(path.resolve(cfgPath));
const resolve = (p) => (path.isAbsolute(p) ? p : path.resolve(cfgDir, p));

const video = resolve(cfg.video);
const outDir = resolve(cfg.outDir);
if (!existsSync(video)) throw new Error(`video not found: ${video}`);

/* ── probe the real file, never trust intent ── */
function probe(file) {
  let out;
  try {
    out = execFileSync(
      FFPROBE,
      ["-v", "error", "-select_streams", "v:0",
       "-show_entries", "format=duration", "-show_entries", "stream=r_frame_rate,width,height",
       "-of", "default=noprint_wrappers=1", file],
      { encoding: "utf8" }
    );
  } catch (e) {
    if (e.code === "ENOENT") {
      throw new Error(
        `ffprobe not found ("${FFPROBE}"). Install ffmpeg or set the FFPROBE env var to the binary.`
      );
    }
    throw e;
  }
  const get = (k) => (out.match(new RegExp(`^${k}=(.+)$`, "m")) || [])[1];
  const [num, den] = (get("r_frame_rate") || "30/1").split("/").map(Number);
  return {
    duration: parseFloat(get("duration")),
    fps: Math.round((num / (den || 1)) * 1000) / 1000,
    width: parseInt(get("width"), 10),
    height: parseInt(get("height"), 10),
  };
}
const meta = probe(video);

const version = cfg.version || "v1";
const versionLabel = cfg.versionLabel || version.toUpperCase();
const accents = cfg.accents || ["#4aa8ff", "#a033ff", "#ff5c87"];
const hexToRgba = (hex, a) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

/* Cache-bust the video filename per version. Republishing a new cut under the SAME
   filename leaves reviewers staring at the browser-cached old one ("why isn't it on
   here.now?"). The filename is the cache key — change it every round. */
const slugBase = (cfg.title || "cut").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const videoFile = `${slugBase}-${version}${path.extname(video)}`;

const facts = (cfg.facts || [`${meta.duration.toFixed(2)}s · ${meta.width}×${meta.height} · ${meta.fps}fps`])
  .map((f) => `<span class="fact">${f}</span>`)
  .join("\n      ");

const beats = (cfg.beats || []).map((b) => ({ t: b.t, n: b.n, s: b.s || "", tone: b.tone || "" }));

/* Optional "Editor's notes" card: the decisions and flags that belong with the cut but
   have no single timestamp (what got removed and why, what still needs a human call).
   Rendered server-side so the page needs no extra JS. `b` may contain <b>. */
const notesCard = (cfg.notes || []).length
  ? `<div class="card">
        <h2>Editor's notes${cfg.notesCount === false ? "" : ` <span class="cnt">${cfg.notes.length}</span>`}</h2>
        <p class="hint">${cfg.notesHint || "What I changed, what I deliberately left alone, and what needs your call."}</p>
        <div class="notes">${cfg.notes
          .map((n) => `<div class="note" data-tone="${n.tone || ""}"><span class="nn">${n.n}</span><span class="nb">${n.b || ""}</span></div>`)
          .join("")}</div>
      </div>`
  : "";

let html = readFileSync(TEMPLATE, "utf8");
const subs = {
  TITLE: cfg.title || "Cut",
  VERSION: version,
  VERSION_LABEL: versionLabel,
  EYEBROW: cfg.eyebrow || "EDIT REVIEW",
  BLURB: cfg.blurb || "",
  AUTHOR: cfg.author || "Reviewer",
  VIDEO_FILE: videoFile,
  FPS: String(meta.fps),
  DURATION: String(meta.duration),
  FACTS: facts,
  NOTES_CARD: notesCard,
  BEATS_JSON: JSON.stringify(beats, null, 2),
  ACCENT_1: accents[0],
  ACCENT_2: accents[1],
  ACCENT_3: accents[2],
  GLOW_1: hexToRgba(accents[0], 0.2),
  GLOW_2: hexToRgba(accents[1], 0.14),
  PLAYER_WIDTH: cfg.playerWidth || "min(52vh,430px)",
};
for (const [k, v] of Object.entries(subs)) html = html.split(`{{${k}}}`).join(v);
const leftover = html.match(/\{\{[A-Z_0-9]+\}\}/g);
if (leftover) throw new Error(`unreplaced placeholders: ${[...new Set(leftover)].join(", ")}`);

mkdirSync(path.join(outDir, ".herenow"), { recursive: true });
writeFileSync(path.join(outDir, "index.html"), html);
copyFileSync(MANIFEST, path.join(outDir, ".herenow", "data.json"));
copyFileSync(video, path.join(outDir, videoFile));

console.log(`canvas built → ${outDir}`);
console.log(`  video   ${videoFile}  (${meta.duration.toFixed(2)}s, ${meta.width}×${meta.height}, ${meta.fps}fps)`);
console.log(`  beats   ${beats.length}`);
console.log(`  notes   filtered to version "${version}"`);
console.log(`\nnext: bash ${PUBLISH_SH} "${outDir}" \\`);
console.log(`        --title "${subs.TITLE} — ${versionLabel} review" --client claude-code`);
console.log(`      (add --slug <existing-slug> to keep the same URL across versions;`);
console.log(`       set HERENOW_PUBLISH if the here-now skill lives elsewhere)`);
