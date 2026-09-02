#!/usr/bin/env python3
"""Step 2 — the "a video is playing" mask, from the system-audio track.

The track is digital silence between plays, so a flat -80 dB gate is exact. Gaps
shorter than `close_gap` are closed (quiet beats inside an ad) and blips shorter than
`min_dur` dropped (UI clicks).

Honours a hand-written "video_regions" in hooks.json and skips detection entirely.

    python3 video_regions.py [hooks.json]
"""
import json
import numpy as np
from _cfg import load, w, HOP

cfg = load()
out = w(cfg, "video_regions.json")

if cfg.get("video_regions"):
    json.dump([list(map(float, r)) for r in cfg["video_regions"]], open(out, "w"), indent=0)
    print(f"using {len(cfg['video_regions'])} hand-marked regions from hooks.json")
    raise SystemExit

env = np.load(w(cfg, f"env{cfg['audio']['system']}.npy"))
M = cfg["mask"]
act = env > M["silence_db"]

def close_gaps(m, max_gap):
    m = m.copy(); n = len(m); i = 0
    while i < n:
        if not m[i]:
            j = i
            while j < n and not m[j]: j += 1
            if i > 0 and j < n and (j - i) * HOP <= max_gap: m[i:j] = True
            i = j
        else: i += 1
    return m

def drop_short(m, min_s):
    m = m.copy(); n = len(m); i = 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]: j += 1
            if (j - i) * HOP < min_s: m[i:j] = False
            i = j
        else: i += 1
    return m

act = drop_short(close_gaps(act, M["close_gap"]), M["min_dur"])
iv = []; n = len(act); i = 0
while i < n:
    if act[i]:
        j = i
        while j < n and act[j]: j += 1
        iv.append((round(i * HOP, 2), round(j * HOP, 2)))
        i = j
    else: i += 1

json.dump(iv, open(out, "w"), indent=0)
tot = sum(b - a for a, b in iv)
print(f"{len(iv)} video regions, {tot:.1f}s of {len(env)*HOP:.1f}s "
      f"({tot/(len(env)*HOP)*100:.0f}%)\n")
prev = 0.0
for k, (a, b) in enumerate(iv, 1):
    ts = lambda x: f"{int(x//60)}:{x%60:05.2f}"
    print(f"{k:3d}  talk {a-prev:6.2f}s   VIDEO {ts(a)} -> {ts(b)}  ({b-a:5.2f}s)")
    prev = b
