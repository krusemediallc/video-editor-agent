#!/usr/bin/env node
// gen-music.mjs — ElevenLabs music bed: ToS-check the prompt → generate → trim/fade → report.
//
// ToS trap this script exists for: artist names in the prompt → HTTP 400 (film and
// brand names are likely filtered too). Describe the STYLE in words instead — genre,
// bpm, drum character, bass, melody policy, energy arc, "mixed quiet and dry to sit
// under a spoken voiceover", "no vocals", "seamless loop feel". On a 400 the error
// body often includes a usable `prompt_suggestion`; this script surfaces it.
//
// Usage:
//   node gen-music.mjs --prompt "..." --seconds 30 --out music/bed.mp3
//   node gen-music.mjs --prompt-file bed-prompt.txt --seconds 30 --out music/bed.mp3
//
// Options:
//   --seconds <n>       length of the FINISHED bed (required)
//   --pad-seconds <n>   extra length requested from the API, trimmed off locally
//                       (default 2 — gives the fade-out real material instead of
//                       relying on the track's own ending)
//   --fade-out <n>      fade the last n seconds of the finished bed (default 2.2; 0 disables)
//   --out <path>        output mp3 (default music-bed.mp3)
//
// Auth: ELEVENLABS_API_KEY from the environment, else from a .env found in cwd or any
// parent directory (the repo-root .env pattern). Requires Node >= 20 and ffmpeg/ffprobe.

import { readFileSync, writeFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, dirname } from "node:path";

const API = "https://api.elevenlabs.io/v1/music";
const FFMPEG = process.env.FFMPEG_PATH || "ffmpeg";
const FFPROBE = process.env.FFPROBE_PATH || "ffprobe";

function die(msg) {
  console.error(`ERROR: ${msg}`);
  process.exit(1);
}

function apiKey() {
  if (process.env.ELEVENLABS_API_KEY) return process.env.ELEVENLABS_API_KEY;
  let d = process.cwd();
  for (;;) {
    const p = join(d, ".env");
    if (existsSync(p)) {
      const line = readFileSync(p, "utf8")
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("ELEVENLABS_API_KEY="));
      if (line) {
        const v = line.slice("ELEVENLABS_API_KEY=".length).trim().replace(/^["']|["']$/g, "");
        if (v) return v;
      }
    }
    const parent = dirname(d);
    if (parent === d) return null;
    d = parent;
  }
}

function run(cmd, args) {
  const r = spawnSync(cmd, args, { encoding: "utf8" });
  if (r.error) die(`could not run ${cmd} — install ffmpeg/ffprobe and put them on PATH (${r.error.message})`);
  return r;
}

function peakDb(path) {
  const r = run(FFMPEG, ["-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"]);
  const m = r.stderr.match(/max_volume:\s*(-?[\d.]+)\s*dB/);
  return m ? parseFloat(m[1]) : null;
}

function durationS(path) {
  const r = run(FFPROBE, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]);
  const d = parseFloat(r.stdout.trim());
  return Number.isFinite(d) ? Math.round(d * 10) / 10 : null;
}

// Depth-first search for a key anywhere in a parsed error body.
function findKey(obj, key) {
  if (obj && typeof obj === "object") {
    if (key in obj) return obj[key];
    for (const v of Object.values(obj)) {
      const hit = findKey(v, key);
      if (hit !== undefined) return hit;
    }
  }
  return undefined;
}

// ---- args ----

const args = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  if (argv[i].startsWith("--")) {
    args[argv[i].slice(2)] = argv[i + 1];
    i++;
  }
}

const prompt = args.prompt ?? (args["prompt-file"] ? readFileSync(args["prompt-file"], "utf8").trim() : null);
if (!prompt) die('usage: node gen-music.mjs --prompt "..." --seconds 30 --out music/bed.mp3');
const seconds = parseFloat(args.seconds);
if (!Number.isFinite(seconds) || seconds <= 0) die("--seconds <n> is required (length of the finished bed)");
const pad = args["pad-seconds"] !== undefined ? parseFloat(args["pad-seconds"]) : 2;
const fade = args["fade-out"] !== undefined ? parseFloat(args["fade-out"]) : 2.2;
const out = args.out || "music-bed.mp3";

const key = apiKey();
if (!key) die("ELEVENLABS_API_KEY not set — export it or put ELEVENLABS_API_KEY=… in a .env at the repo root");

// ---- pre-flight ToS heuristic: catch named-work references before spending a call ----

const RISKY = [
  /\bin the style of\b/i,
  /\bstyle of\b/i,
  /\bsounds? like\b/i,
  /\blike the (song|track|score|soundtrack|theme)\b/i,
  /\bsoundtrack (of|to|from)\b/i,
  /\btheme (from|of)\b/i,
  /\bby [A-Z][a-z]+/,
];
if (RISKY.some((re) => re.test(prompt))) {
  console.warn(
    "WARNING: the prompt looks like it references a named artist/work. Artist names " +
      "(and likely film/brand names) violate ToS and return HTTP 400. Describe the " +
      "style in plain words instead (see references/style-matching.md). Trying anyway…\n"
  );
}

// ---- generate ----

console.log(`requesting ${(seconds + pad).toFixed(1)}s of music (${seconds}s bed + ${pad}s pad)…`);
const res = await fetch(API, {
  method: "POST",
  headers: { "xi-api-key": key, "Content-Type": "application/json" },
  body: JSON.stringify({ prompt, music_length_ms: Math.round((seconds + pad) * 1000) }),
});
if (!res.ok) {
  const body = await res.text();
  console.error(`ERROR: /v1/music ${res.status}: ${body}`);
  if (res.status === 400) {
    console.error(
      "\nA 400 here is usually the ToS filter: an artist, film, or brand name in the " +
        "prompt. Describe the sound in plain words — genre, bpm, drums, bass, energy arc."
    );
  }
  let suggestion;
  try {
    suggestion = findKey(JSON.parse(body), "prompt_suggestion");
  } catch {}
  if (suggestion) {
    console.error(`\nThe API suggests this rewritten prompt:\n  ${suggestion}\nRe-run with it if it still says what you want.`);
  }
  process.exit(1);
}

const outDirName = dirname(out);
if (outDirName && outDirName !== ".") mkdirSync(outDirName, { recursive: true });
const rawPath = `${out}.raw.mp3`;
writeFileSync(rawPath, Buffer.from(await res.arrayBuffer()));

// ---- trim to length + fade out ----

const ffArgs = ["-y", "-v", "error", "-i", rawPath, "-t", String(seconds)];
if (fade > 0) {
  ffArgs.push("-af", `afade=t=out:st=${Math.max(seconds - fade, 0).toFixed(2)}:d=${fade}`);
}
ffArgs.push("-b:a", "192k", out);
const trim = run(FFMPEG, ffArgs);
if (trim.status !== 0) die(`ffmpeg trim/fade failed: ${trim.stderr}`);
rmSync(rawPath, { force: true });

// ---- report ----

const dur = durationS(out);
const peak = peakDb(out);
console.log(`\nbed ready: ${out}  ${dur}s  peak ${peak?.toFixed(1)} dB`);
console.log(
  "mix hint: against a VO loudnorm'd to -14 LUFS / TP -1.2, a bed peaking near 0 dB " +
    "sits ~19-20 dB under VO peaks at track volume 0.13-0.18. Start at 0.15 and " +
    "verify in a word gap (see SKILL.md section 5)."
);
console.log(
  "note: generated tracks often open with a 2-4s warm-up. If the bed must hit from " +
    "frame one, find the energy plateau with per-second volumedetect and re-cut with -ss."
);
