#!/usr/bin/env node
// gen-sfx.mjs — ElevenLabs SFX kit: generate → audit → retry duds → normalize to a common peak.
//
// Why the loop exists: roughly 1/3 of /v1/sound-generation calls come back near-silent
// or quiet, and un-normalized files make composition volume values meaningless. This
// script measures every file with ffmpeg volumedetect, regenerates duds once with
// "loud, punchy" prepended, then peak-normalizes the whole kit to a common target
// (default -3dB) so a given track volume means the same loudness for every effect.
// It also flags late onsets (first sound after ~0.15s lands off-beat) and writes
// durations.json for the composition builder.
//
// Usage:
//   node gen-sfx.mjs kit.json <outDir>
//
// kit.json — either a bare array of effects, or:
// {
//   "normalize_db": -3,     // target peak for every file (default -3)
//   "min_peak_db": -12,     // audit threshold: quieter = dud, regenerate (default -12)
//   "effects": [
//     { "name": "whoosh-soft", "duration": 0.7, "prompt": "short soft airy whoosh, clean swipe" },
//     { "name": "stamp-slam",  "duration": 0.8, "prompt": "loud heavy thud slam impact, punchy bass" }
//   ]
// }
//
// Idempotent: an effect whose .mp3 already exists in outDir is not re-generated (it is
// still audited + re-normalized). Delete a file to force regeneration.
//
// Auth: ELEVENLABS_API_KEY from the environment, else from a .env found in cwd or any
// parent directory (the repo-root .env pattern). Requires Node >= 20 and ffmpeg/ffprobe.

import { readFileSync, writeFileSync, mkdirSync, existsSync, renameSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, dirname } from "node:path";

const API = "https://api.elevenlabs.io/v1/sound-generation";
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

// Seconds until the first sound. Nonzero only when the file OPENS with silence: if the
// first silencedetect event is a silence_start at ~0, the onset is that silence's end.
// Sound-then-trailing-silence (the normal shape) returns 0.
function onsetS(path) {
  const r = run(FFMPEG, ["-hide_banner", "-i", path, "-af", "silencedetect=n=-30dB:d=0.05", "-f", "null", "-"]);
  const events = [];
  for (const line of r.stderr.split("\n")) {
    let m;
    if ((m = line.match(/silence_start:\s*(-?[\d.]+)/))) events.push(["start", parseFloat(m[1])]);
    else if ((m = line.match(/silence_end:\s*(-?[\d.]+)/))) events.push(["end", parseFloat(m[1])]);
  }
  if (events.length && events[0][0] === "start" && events[0][1] < 0.05) {
    for (const [kind, t] of events.slice(1)) if (kind === "end") return t;
  }
  return 0;
}

function durationS(path) {
  const r = run(FFPROBE, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]);
  const d = parseFloat(r.stdout.trim());
  return Number.isFinite(d) ? Math.round(d * 1000) / 1000 : null;
}

async function generate(key, prompt, seconds, out) {
  const res = await fetch(API, {
    method: "POST",
    headers: { "xi-api-key": key, "Content-Type": "application/json" },
    body: JSON.stringify({
      text: prompt,
      duration_seconds: Math.max(Number(seconds), 0.5), // API 400s below 0.5s
      prompt_influence: 0.6,
    }),
  });
  if (!res.ok) die(`sound-generation ${res.status} for "${prompt.slice(0, 60)}…": ${await res.text()}`);
  writeFileSync(out, Buffer.from(await res.arrayBuffer()));
}

// ---- main ----

const [cfgPath, outDir] = process.argv.slice(2);
if (!cfgPath || !outDir) die("usage: node gen-sfx.mjs kit.json <outDir>");
const key = apiKey();
if (!key) die("ELEVENLABS_API_KEY not set — export it or put ELEVENLABS_API_KEY=… in a .env at the repo root");

const rawCfg = JSON.parse(readFileSync(cfgPath, "utf8"));
const cfg = Array.isArray(rawCfg) ? { effects: rawCfg } : rawCfg;
if (!Array.isArray(cfg.effects) || cfg.effects.length === 0) die("kit config has no effects");
const target = Number(cfg.normalize_db ?? -3);
const minPeak = Number(cfg.min_peak_db ?? -12);
mkdirSync(outDir, { recursive: true });

const durations = {};
const flagged = [];

for (const fx of cfg.effects) {
  const seconds = fx.duration ?? fx.seconds;
  if (!fx.name || !fx.prompt || !seconds) die(`bad effect entry ${JSON.stringify(fx)} — need {name, duration, prompt}`);
  const path = join(outDir, `${fx.name}.mp3`);

  if (!existsSync(path)) {
    await generate(key, fx.prompt, seconds, path);
    console.log(`generated  ${fx.name}`);
  }

  // Audit: ~1/3 of generations are near-silent. Retry once, louder + higher influence bias.
  let p = peakDb(path);
  if (p === null || p < minPeak) {
    console.log(`DUD (peak ${p === null ? "unreadable" : p + " dB"})  ${fx.name} — regenerating louder…`);
    rmSync(path, { force: true });
    await generate(key, `loud, punchy: ${fx.prompt}`, seconds, path);
    p = peakDb(path);
    if (p === null) die(`could not measure ${fx.name} after retry — unreadable file; delete ${path} and rerun`);
    if (p < minPeak - 8) {
      flagged.push([fx.name, `still very quiet after retry (${p} dB) — normalization will rescue the level, but listen to it`]);
    }
  }

  // Normalize to the common target peak so composition volume values behave predictably.
  const gain = target - p;
  const tmp = `${path}.norm.mp3`;
  const norm = run(FFMPEG, ["-y", "-v", "error", "-i", path, "-af", `volume=${gain.toFixed(1)}dB`, "-b:a", "192k", tmp]);
  if (norm.status !== 0) die(`ffmpeg normalize failed for ${fx.name}: ${norm.stderr}`);
  renameSync(tmp, path);

  // Late onsets land off-beat when the hit is placed on an exact word.
  const on = onsetS(path);
  if (on > 0.15) {
    flagged.push([fx.name, `first sound at ~${on.toFixed(2)}s — the hit will land late; regenerate with "sharp attack" in the prompt or trim the head`]);
  }

  durations[fx.name] = durationS(path);
  console.log(`ok  ${fx.name.padEnd(16)} peak → ${peakDb(path)?.toFixed(1)} dB  (${durations[fx.name]}s)`);
}

writeFileSync(join(outDir, "durations.json"), JSON.stringify(durations, null, 1) + "\n");
console.log(`\nwrote ${join(outDir, "durations.json")} (${Object.keys(durations).length} effects)`);
if (flagged.length) {
  console.log("\nFLAGGED for manual attention:");
  for (const [name, why] of flagged) console.log(`  - ${name}: ${why}`);
}
