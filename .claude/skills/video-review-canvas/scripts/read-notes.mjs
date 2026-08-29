#!/usr/bin/env node
/**
 * read-notes.mjs — pull the reviewer's timeline notes back off a published canvas.
 *
 *   node read-notes.mjs <slug-or-url> [version]
 *
 * Prints notes sorted by timestamp, so you can walk the cut in order and address each
 * one against the actual frame. Reading the notes back is the whole point of the canvas —
 * a round where you publish but never GET the store is a round of feedback dropped.
 *
 * Requires node >= 20 (global fetch + top-level await).
 */
const arg = process.argv[2];
if (!arg) { console.error("usage: node read-notes.mjs <slug-or-url> [version]"); process.exit(1); }
const version = process.argv[3] || null;
const base = arg.startsWith("http") ? arg.replace(/\/$/, "") : `https://${arg}.here.now`;

const r = await fetch(`${base}/.herenow/data/comments?limit=200`);
if (!r.ok) { console.error(`HTTP ${r.status} from ${base}`); process.exit(1); }
const j = await r.json();
let recs = j.records || [];
if (version) recs = recs.filter((x) => x.data.version === version);
recs.sort((a, b) => a.data.t - b.data.t);

if (!recs.length) { console.log(`no notes${version ? ` for ${version}` : ""} on ${base}`); process.exit(0); }

const fmt = (t) => { const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${(s < 10 ? "0" : "")}${s.toFixed(1)}`; };
console.log(`${recs.length} note(s) on ${base}${version ? ` (${version})` : ""}\n`);
for (const [i, c] of recs.entries()) {
  console.log(`#${i + 1}  ${fmt(c.data.t)}  [${c.data.version}]  ${c.data.author || ""}`);
  console.log(`    ${c.data.text.replace(/\n/g, "\n    ")}\n`);
}
