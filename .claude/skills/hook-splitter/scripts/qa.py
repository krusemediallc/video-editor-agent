#!/usr/bin/env python3
"""Step 7 — the gate. Re-transcribe every RENDER and scan it.

DO NOT SKIP THIS. Whisper smooths a repeated take into one clean line on a full-file
pass, so real doubles are invisible in every source-side transcript. They appear
immediately in a transcript of the cut. Four flubs the client caught in review — two
doubled "a fast", a leftover "let's see it", a doubled "let's see how" — were all of
this kind, and all of them would have been caught here.

Checks:
  1. repeated 3+ word phrases inside one hook   (3, not 4 — a 4-word floor missed
     "let's see how" and shipped it)
  2. leftover dead air inside kept segments, outside video regions

Anything it flags still needs a human read: a repeat may be genuine content (a
reference video that IS the previous generation) or natural speech ("oh my god" twice
in a reaction). Investigate each; cut only real flubs.

    python3 qa.py [hooks.json] [--skip-transcribe]
"""
import json, os, re, subprocess, sys
import numpy as np
from _cfg import load, w, FFMPEG, WHISPER, WMODEL, HOP

cfg = load()
plans = json.load(open(cfg["_root"] + "/cuts.json"))
qa = w(cfg, "qa"); os.makedirs(qa, exist_ok=True)
txt_path = os.path.join(qa, "renders.txt")

if "--skip-transcribe" not in sys.argv:
    chunks = []
    for p in plans:
        mp4 = os.path.join(cfg["out"], f"hook-{p['id']:02d}.mp4")
        wav = os.path.join(qa, f"h{p['id']:02d}.wav")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", mp4,
                        "-ac", "1", "-ar", "16000", wav], check=True)
        res = subprocess.run([WHISPER, "-m", WMODEL, "-f", wav, "-nt", "-np"],
                             capture_output=True, text=True)
        t = res.stdout.strip()
        # An empty transcript would sail through every check below and report a clean
        # gate. This gate is the whole reason the skill catches doubles at all — it must
        # fail loudly, never quietly pass.
        if res.returncode != 0 or not t:
            raise SystemExit(f"whisper FAILED on hook {p['id']:02d} "
                             f"(rc={res.returncode}, {len(t)} chars). QA cannot pass.\n"
                             f"{res.stderr[-400:]}")
        chunks.append(f"########## HOOK {p['id']:02d} ##########\n{t}\n")
        print(f"  transcribed hook {p['id']:02d}  ({len(t)} chars)")
    open(txt_path, "w").write("\n".join(chunks))

body = open(txt_path).read()
blocks = re.split(r"#+ HOOK (\d+) #+", body)[1:]
pairs = list(zip(blocks[0::2], blocks[1::2]))

print(f"\n=== repeated 3+ word phrases ({len(pairs)} hooks) ===")
flagged = 0
for hid, text in pairs:
    words = re.sub(r"[^a-z ]", "", " ".join(text.split()).lower()).split()
    hits = set()
    for n in range(3, 9):
        seen = {}
        for i in range(len(words) - n + 1):
            g = " ".join(words[i:i+n])
            if g in seen and i - seen[g] < 40: hits.add(g)
            seen[g] = i
    hits = {h for h in hits if not any(h != o and h in o for o in hits)}
    if hits:
        flagged += 1
        print(f"  HOOK {hid}:")
        for h in sorted(hits): print(f'      "{h}"')
print(f"  {flagged} hook(s) flagged — read each; genuine content is common" if flagged
      else "  none")

print("\n=== leftover dead air (kept, outside a video region) ===")
env = np.load(w(cfg, f"env{cfg['audio']['mic']}.npy"))
floor = float(np.percentile(env, 10))
thr = floor + cfg["pacing"]["active_margin"]
tot, rows = 0.0, []
for p in plans:
    for a, b in p["segments"]:
        quiet = env[int(a/HOP):int(b/HOP)] <= thr
        i, n = 0, len(quiet)
        while i < n:
            if quiet[i]:
                j = i
                while j < n and quiet[j]: j += 1
                t0, t1 = a + i*HOP, a + j*HOP
                # subtract the protected overlap rather than exempting the whole span —
                # a quiet run that merely TOUCHES a video region still has dead air in it
                free = t1 - t0
                for va, vb in p["video_regions"]:
                    free -= max(0.0, min(t1, vb) - max(t0, va))
                if free > 0.30:
                    tot += free; rows.append((round(free, 2), p["id"], round(t0, 2)))
                i = j
            else: i += 1
rows.sort(reverse=True)
for d, hid, t0 in rows[:12]:
    print(f"  {d:.2f}s  H{hid:02d} @ src {t0}")
print(f"  total {tot:.1f}s across {len(rows)} spans "
      f"(spans under ~0.5s are usually word-guard protected and correct)")
