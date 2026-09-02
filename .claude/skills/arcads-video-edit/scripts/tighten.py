#!/usr/bin/env python3
"""Rebuild each EDL segment's keep-ranges from the mic waveform so every pause collapses.

Model: aggressive single-threshold VAD (this speaker's pauses are mostly 60-260ms, so a
conservative threshold removes almost nothing), plus two guardrails that QA proved necessary:

  MIN_GAP_TO_CUT  a gap this short saves nothing perceptible but still costs a jump cut
  MIN_PIECE       a kept piece under this is a 4-frame flash, not an edit

Word safety is NOT decided here - it is decided empirically by qa/verify_cuts.py, which A/B
transcribes every cut and vetoes the ones that actually shorten a word. Vetoes are stored in
edl.json as "veto" and re-applied on every run so the decision survives a re-tighten.

`protect` ranges (a video playing on screen) are unioned in and never cut.
"""
import subprocess, numpy as np, json, os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
SR, HOP = 16000, 320
PAD_HEAD, PAD_TAIL = 0.045, 0.055
MERGE_UNDER = 0.10
MIN_GAP_TO_CUT = 0.14
MIN_PIECE = 0.35
MERGE_SPAN = 0.60

CACHE = {}
def db_frames(take):
    if take not in CACHE:
        r = subprocess.run([(os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"), "-v", "error", "-i",
                            f"{RAW}/Take {take} - Mic.wav", "-map", "0:a:0", "-ac", "1",
                            "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
        x = np.frombuffer(r.stdout, dtype=np.float32).astype(float)
        n = len(x) // HOP
        CACHE[take] = 20 * np.log10(np.sqrt((x[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1)) + 1e-10)
    return CACHE[take]


def speech(take, lo, hi):
    db = db_frames(take)
    noise, p95 = np.percentile(db, 12), np.percentile(db, 95)
    # tightened after the creator's review: the creator marked four breaths at -25 to -33dB that the
    # old p95-22 threshold was keeping. Anything qa/verify_cuts.ts proves damages a
    # word gets vetoed, so this can be aggressive.
    thr = max(noise + 9.0, p95 - 18.0)
    a, b = int(lo / 0.02), min(len(db), int(hi / 0.02))
    on = db[a:b] > thr
    n = len(on)
    regs, i = [], 0
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            regs.append([lo + i * 0.02, lo + j * 0.02])
            i = j
        else:
            i += 1
    out = []
    for r in regs:
        a_, b_ = max(lo, r[0] - PAD_HEAD), min(hi, r[1] + PAD_TAIL)
        if out and a_ - out[-1][1] < MERGE_UNDER:
            out[-1][1] = b_
        else:
            out.append([a_, b_])
    return out


def enforce(ranges, vetoes):
    """Apply the flash guardrails and any empirically-proven word vetoes."""
    changed = True
    while changed and ranges:
        changed = False
        merged = [list(ranges[0])]
        for r in ranges[1:]:
            g0, g1 = merged[-1][1], r[0]
            vetoed = any(abs(g0 - v[0]) < 0.02 and abs(g1 - v[1]) < 0.02 for v in vetoes)
            if g1 - g0 < MIN_GAP_TO_CUT or vetoed:
                merged[-1][1] = r[1]; changed = True
            else:
                merged.append(list(r))
        ranges = merged
        for i, r in enumerate(ranges):
            if r[1] - r[0] >= MIN_PIECE or len(ranges) == 1:
                continue
            gp = r[0] - ranges[i - 1][1] if i > 0 else 1e9
            gn = ranges[i + 1][0] - r[1] if i + 1 < len(ranges) else 1e9
            if min(gp, gn) <= MERGE_SPAN:
                if gp <= gn:
                    ranges[i - 1][1] = r[1]
                else:
                    ranges[i + 1][0] = r[0]
            ranges.pop(i); changed = True
            break
    return ranges


def apply(seg):
    lo, hi = seg["in"], seg["out"]
    keeps = speech(seg["take"], lo, hi) + [list(p) for p in (seg.get("protect") or [])]
    keeps.sort()
    m = []
    for k in keeps:
        if m and k[0] - m[-1][1] < 0.02:
            m[-1][1] = max(m[-1][1], k[1])
        else:
            m.append(list(k))
    m = enforce(m, seg.get("veto") or [])
    return [[round(a, 3), round(b, 3)] for a, b in (m or [[lo, hi]])]


if __name__ == "__main__":
    d = json.load(open(os.path.join(BASE, "edl.json")))
    before = after = 0.0
    for s in d["segments"]:
        s["keep"] = apply(s)
        before += s["out"] - s["in"]
        after += sum(b - a for a, b in s["keep"])
    json.dump(d, open(os.path.join(BASE, "edl.json"), "w"), indent=2)
    cuts = sum(len(s["keep"]) - 1 for s in d["segments"])
    runts = [(s["id"], a, b) for s in d["segments"] for a, b in s["keep"] if b - a < MIN_PIECE]
    print(f"{before:.2f}s -> {after:.2f}s (removed {before-after:.2f}s) | {cuts} internal cuts")
    print("runt pieces:", runts if runts else "none")
