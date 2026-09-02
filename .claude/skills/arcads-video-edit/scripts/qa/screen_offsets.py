#!/usr/bin/env python3
"""Move each segment's screen window to where the example is actually PLAYING.

The screen recordings are a separate track from the voice, so the screen does not have to be
frame-synced to what the creator is saying - it only has to show the right thing. Large parts of these
captures are frozen (the video in the Arcads player is paused, or the creator is not scrolling), and
QA found 35s of the cut with a completely static screen half.

For every segment this measures liveness inside that segment's own crop rect, then picks the
offset that maximises moving frames, subject to staying in bounds and to screen time running
FORWARD across the segments that share a take (a rewind is visible; a jump forward is not).
"""
import subprocess, numpy as np, json, os, sys
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
STEP = 0.25
edl = json.load(open(os.path.join(BASE, "edl.json")))
RECTS = edl["screenRects"]
LIVE_PCT = 0.5          # % of pixels changing that counts as "moving"

cache = {}
def liveness(take, rect):
    key = (take, rect)
    if key in cache:
        return cache[key]
    w, h, x, y = RECTS[rect]
    r = subprocess.run([FF, "-v", "error", "-i", f"{BASE}/raw/Take {take} - Screen.mov",
                        "-vf", f"crop={w}:{h}:{x}:{y},fps={int(1/STEP)},scale=320:-2",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    b = np.frombuffer(r.stdout, dtype=np.uint8)
    H = int(round(320 * h / w / 2)) * 2
    n = len(b) // (320 * H)
    F = b[:n * 320 * H].reshape(n, H, 320).astype(np.int16)
    d = np.abs(np.diff(F, axis=0))
    live = ((d > 12).mean(axis=(1, 2)) * 100) > LIVE_PCT
    cache[key] = live
    return live

def dur(take):
    return float(subprocess.run([(os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"), "-v", "error", "-show_entries",
                                 "format=duration", "-of", "csv=p=0",
                                 f"{BASE}/raw/Take {take} - Screen.mov"],
                                capture_output=True, text=True).stdout.strip())

def coverage(live, s, e):
    a, b = int(s / STEP), int(e / STEP)
    a, b = max(0, a), min(len(live), b)
    if b <= a:
        return 0.0
    return float(live[a:b].mean())

report = []
by_take = {}
for seg in edl["segments"]:
    if seg["layout"] == "cam":
        continue
    by_take.setdefault(seg["take"], []).append(seg)

for take, segs in by_take.items():
    D = dur(take)
    floor_t = 0.0                     # screen time must run forward across this take
    for seg in segs:
        rect = seg["rect"]
        live = liveness(take, rect)
        k0 = seg["keep"][0][0]
        k1 = seg["keep"][-1][1]
        span = k1 - k0
        cur = seg.get("screenOffset", 0.0)
        best = None
        off = -k0 + 0.05
        while off <= D - k1 - 0.05:
            s, e = k0 + off, k1 + off
            if s >= floor_t - 0.01:
                cov = coverage(live, s, e)
                # tie-break toward the smallest move
                score = (round(cov, 3), -abs(off - cur))
                if best is None or score > best[0]:
                    best = (score, off, cov)
            off += STEP
        if best is None:
            report.append((seg["id"], take, rect, cur, cur, coverage(live, k0 + cur, k1 + cur), None, "no legal offset"))
            continue
        _, off, cov = best
        cur_cov = coverage(live, k0 + cur, k1 + cur)
        report.append((seg["id"], take, rect, cur, round(off, 2), cur_cov, cov, ""))
        floor_t = k0 + off + 0.0
        seg["_proposed_offset"] = round(off, 2)

print(f"{'segment':<16}{'take':>5} {'rect':<11}{'now':>7}{'best':>7}{'live now':>10}{'live best':>11}")
for sid, take, rect, cur, off, c0, c1, note in report:
    flag = "  <-- FIX" if c1 is not None and c1 - c0 > 0.15 else ""
    print(f"{sid:<16}{take:>5} {rect:<11}{cur:7.2f}{off:7.2f}{c0*100:9.0f}%{(c1 or 0)*100:10.0f}%{flag} {note}")
json.dump({s['id']: s.get('_proposed_offset') for s in edl['segments'] if '_proposed_offset' in s},
          open(os.path.join(BASE, "qa/proposed-offsets.json"), "w"), indent=1)
