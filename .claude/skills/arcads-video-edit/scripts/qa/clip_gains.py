#!/usr/bin/env python3
"""Compute a per-clip gain so every spoken line lands at the same level.

Mic level varies take to take (and inside take 15 the creator says "Pixar" ~18dB quieter than "style
ads"). A single master loudnorm cannot fix that - it sets the average for the whole file and
leaves the quiet lines quiet. This measures the SPOKEN level of each segment's kept audio and
writes a `gain` (dB) into the EDL. Segments whose audio is a playing ad rather than the creator's voice
are skipped, so the ad beds keep their natural level.
"""
import subprocess, numpy as np, json, os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR, HOP = 16000, 320
TARGET = None            # set to the median once measured
CLAMP = 4.0
OVERRIDE = {"20-pixar": 14.0}   # the creator says "Pixar" ~19dB under "style ads" in the source

def mic(take):
    r = subprocess.run([(os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"), "-v", "error", "-i",
                        f"{BASE}/raw/Take {take} - Mic.wav", "-map", "0:a:0", "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).astype(float)

edl = json.load(open(f"{BASE}/edl.json"))
levels = {}
cache = {}
for s in edl["segments"]:
    if s["take"] not in cache:
        cache[s["take"]] = mic(s["take"])
    x = cache[s["take"]]
    # take-wide thresholds, so "voiced" means the same thing in every clip from that take
    n_all = len(x) // HOP
    all_db = 20 * np.log10(np.sqrt((x[:n_all * HOP].reshape(n_all, HOP) ** 2).mean(axis=1)) + 1e-10)
    # measure only the LOUD speech peaks. A lower threshold lets faint speaker
    # bleed from a playing ad into the average and drags the gain the wrong way.
    thr = np.percentile(all_db, 95) - 14.0
    frames = []
    for a, b in s["keep"]:
        seg = x[int(a * SR):int(b * SR)]
        n = len(seg) // HOP
        if n:
            frames.append(20 * np.log10(np.sqrt((seg[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1)) + 1e-10))
    if not frames:
        continue
    f = np.concatenate(frames)
    voiced = f[f > thr]                      # measure the speech only, never the silence
    if len(voiced) < 12:                     # under ~0.24s of speech: nothing to normalise to
        levels[s["id"]] = None
        continue
    levels[s["id"]] = float(np.percentile(voiced, 60))

# only a segment with NO speech at all is exempt; a clip that mixes the creator's voice with a playing
# ad still needs its voice matched to the rest
SKIP = {"21-pixarplay"}
voice = {k: v for k, v in levels.items() if v is not None and k not in SKIP}
target = float(np.median(list(voice.values())))
print(f"target spoken level {target:.1f} dB (median of {len(voice)} clips)\n")
print(f"{'segment':<16}{'measured':>10}{'gain':>8}")
for s in edl["segments"]:
    lv = levels.get(s["id"])
    if lv is None or s["id"] in SKIP:
        s.pop("gain", None)
        print(f"{s['id']:<16}{(lv or 0):10.1f}{'  (skipped)':>8}")
        continue
    g = OVERRIDE.get(s["id"], max(-CLAMP, min(CLAMP, target - lv)))
    if abs(g) < 0.4:
        s.pop("gain", None); g = 0.0
    else:
        s["gain"] = round(g, 2)
    print(f"{s['id']:<16}{lv:10.1f}{g:+8.2f}")
json.dump(edl, open(f"{BASE}/edl.json", "w"), indent=2)
