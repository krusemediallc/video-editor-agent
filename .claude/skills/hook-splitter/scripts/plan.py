#!/usr/bin/env python3
"""Step 5 — cuts.json: what survives in each hook.

  * inside a video region  -> NEVER cut. That is the only silence allowed.
  * outside one            -> talking; every gap collapses to a fixed RESIDUAL.

Targeting a residual rather than a fixed pad is what makes it read as one take: it is
the unevenness of the joins, not their average, that gives a cut away. One number
(join_gap) controls the whole feel — 0.09 breathes, 0.045 is normal recut pace, 0.03
is run-on, under 0.025 sounds spliced.

Joins are only ever made BETWEEN speech segments, never inside one. Energy cannot tell
a beat between words from a stop closure, and word-gap cutting is proven to destroy
words on this rig (reel-recut/references/workflow.md, pass B).

Every entry in a hook's `kills` must have been confirmed by slicing that window to its
own wav and transcribing it in ISOLATION. A full-file pass both hallucinates repeats
and smooths real ones away. See references/gotchas.md.

    python3 plan.py [hooks.json]
"""
import json, math, os, re
import numpy as np
from _cfg import load, w, HOP

cfg = load()
P = cfg["pacing"]
FPS = cfg.get("fps", 30)
env  = np.load(w(cfg, f"env{cfg['audio']['mic']}.npy"))
try:
    env1 = np.load(w(cfg, f"env{cfg['audio']['system']}.npy"))
except FileNotFoundError:
    env1 = None

VIDEO_RAW = [tuple(x) for x in json.load(open(w(cfg, "video_regions.json")))]
# A MISSING file means detect_loops.py was skipped or died — not "there are no loops".
# A genuine no-loop run still writes {}. Never let a skipped step silently disable
# loop muting and loop-tail removal.
_lp = w(cfg, "loop_points.json")
if not os.path.exists(_lp):
    raise SystemExit(f"{_lp} not found — run detect_loops.py first "
                     f"(a real no-loop result still writes an empty object).")
LOOPS = json.load(open(_lp))
# truncate each region at its loop restart so the hook cuts from the ad's real ending
VIDEO = [(a, min(b, LOOPS.get(f"{a:.2f}", b))) for a, b in VIDEO_RAW]

VAD = []
for line in open(w(cfg, "vad.txt")):
    m = re.search(r"start\s*=\s*([\d.]+),\s*end\s*=\s*([\d.]+)", line)
    if m:                       # CENTISECONDS, not ms. See transcribe.py.
        VAD.append((float(m.group(1)) / 100.0, float(m.group(2)) / 100.0))

_wj = json.load(open(w(cfg, "words.json")))["words"]
# Whisper stretches the odd word across a following pause (a 2.56s "that", a 2.52s
# one). Used as a don't-cut-inside-a-word guard those act as protected regions and
# block the very gaps this edit removes. Anything over max_word is that artifact.
WORDS     = [(x["start"], x["end"]) for x in _wj if 0 < x["end"] - x["start"] <= P["max_word"]]
WORDS_ALL = [(x["start"], x["end"]) for x in _wj if x["end"] > x["start"]]

def db(t):
    i = int(round(t / HOP))
    return -120.0 if i < 0 or i >= len(env) else float(env[i])

_g = []
for (a0, a1), (b0, b1) in zip(VAD, VAD[1:]):
    if any(a1 < vb and b0 > va for va, vb in VIDEO): continue
    t = a1
    while t < b0 - HOP:
        _g.append(db(t)); t += HOP
FLOOR = float(np.percentile(_g, 25)) if _g else -70.0

def edge_out(a1, limit):
    x = a1
    while x < min(a1 + P["max_extend"], limit) and db(x) > FLOOR + P["breath_margin"]: x += HOP
    if x <= a1 + 1e-9:
        while x > a1 - P["max_reclaim"] and db(x - HOP) <= FLOOR + P["quiet_margin"]: x -= HOP
    return x

def edge_in(b0, limit):
    x = b0
    while x > max(b0 - P["max_extend"], limit) and db(x - HOP) > FLOOR + P["breath_margin"]: x -= HOP
    if x >= b0 - 1e-9:
        while x < b0 + P["max_reclaim"] and db(x) <= FLOOR + P["quiet_margin"]: x += HOP
    return x

def inside_word(t):
    for a, b in WORDS:
        if a + P["word_guard"] < t < b - P["word_guard"]: return (a, b)
    return None

def sub(intervals, kills):
    out = []
    for a, b in intervals:
        pieces = [(a, b)]
        for ka, kb in kills:
            nxt = []
            for pa, pb in pieces:
                if kb <= pa or ka >= pb: nxt.append((pa, pb)); continue
                if pa < ka: nxt.append((pa, ka))
                if kb < pb: nxt.append((kb, pb))
            pieces = nxt
        out += [p for p in pieces if p[1] - p[0] > 0.02]
    return out

def clip(intervals, lo, hi):
    return [(max(a, lo), min(b, hi)) for a, b in intervals
            if min(b, hi) - max(a, lo) > 0.02]

def merge(intervals):
    if not intervals: return []
    iv = sorted(intervals); out = [list(iv[0])]
    for a, b in iv[1:]:
        if a <= out[-1][1] + 1e-6: out[-1][1] = max(out[-1][1], b)
        else: out.append([a, b])
    return [tuple(x) for x in out]

# ── speech map ────────────────────────────────────────────────────────────────────
# Segment on ENERGY, then require each run to overlap VAD-or-whisper before calling it
# speech. That cross-check is what throws out mouse clicks and key taps. An energy gate
# IS right here (floor -71.9 dB vs speech -33.5 dB); on a noisy source it is NOT — see
# reel-recut/references/workflow.md step 2b.
SEED = merge(VAD + WORDS_ALL)

def speech_segments(lo, hi):
    i0, i1 = int(lo / HOP), int(hi / HOP)
    loud = env[i0:i1] > (FLOOR + P["active_margin"])
    runs, i, n = [], 0, len(loud)
    while i < n:
        if loud[i]:
            j = i
            while j < n and loud[j]: j += 1
            runs.append([lo + i*HOP, lo + j*HOP]); i = j
        else: i += 1
    out = []
    for r in runs:
        if out and r[0] - out[-1][1] < P["merge_gap"]: out[-1][1] = r[1]
        else: out.append(r)
    return [(a, b) for a, b in out
            if b - a >= P["min_run"] and any(a < vb and b > va for va, vb in SEED)]

# ── loop-tail kills ───────────────────────────────────────────────────────────────
# The ad bleeds into the mic at ~bleed_db down, right on the speech threshold, so a
# loop tail would be re-detected as "speech" and kept. Kill them. But the speaker
# often reacts WHILE the loop runs, so each kill stops at the speaker's first genuinely loud
# run. A flat dB test is NOT enough — a speech-heavy ad trips it (hooks 9/17/19 kept
# their remnants that way). Predict the bleed from the system track instead.
BLEED_DB, BLEED_OVER, FLOOR_ABS = 22.6, 6.0, -52.0
def _first_loud(t0, t1, need=8):
    i0, i1, run = int(t0/HOP), int(t1/HOP), 0
    top = min(i1, len(env), len(env1) if env1 is not None else i1)
    for i in range(i0, top):
        ok = env[i] > FLOOR_ABS and (env1 is None or env[i] > env1[i] - BLEED_DB + BLEED_OVER)
        run = run + 1 if ok else 0
        if run >= need: return (i - need + 1) * HOP
    return None

LOOP_KILLS = []
for _a, _b in VIDEO_RAW:
    _lp = LOOPS.get(f"{_a:.2f}")
    if _lp is None: continue
    _fl = _first_loud(_lp, _b)
    _end = _fl if _fl is not None else _b
    if _end - _lp > 0.05: LOOP_KILLS.append((round(_lp, 3), round(_end, 3)))

def _residual_avoids_kills(lo, hi, kills):
    """The retained residual is [.., lo] and [hi, ..]; the CUT is [lo, hi]. Any kill that
    falls in this gap must sit entirely inside the cut, or gap collapse hands the flub
    back. Found by review after a whole loop-tail kill was silently restored."""
    for ka, kb in kills:
        if kb <= lo or ka >= hi: continue
        lo = min(lo, ka); hi = max(hi, kb)
    return lo, hi


def plan_hook(h):
    hid, start, end = h["id"], h["start"], h["end"]
    kills = [tuple(k) for k in h.get("kills", [])]
    kills += [k for k in LOOP_KILLS if k[1] > start and k[0] < end]
    prot = sub(clip(VIDEO, start, end), kills)
    speech = sub(speech_segments(start, end), kills)
    refined = [(edge_in(a, start), edge_out(b, end)) for a, b in speech]
    keeps = merge(sub(merge(prot + refined), kills))
    if not keeps: return None

    def touches_video(t):
        return any(abs(t-va) < 0.06 or abs(t-vb) < 0.06 or (va < t < vb) for va, vb in prot)

    final = [list(keeps[0])]
    for a, b in keeps[1:]:
        prev = final[-1]
        gap = a - prev[1]
        target = P["video_gap"] if (touches_video(prev[1]) or touches_video(a)) else P["join_gap"]
        if gap <= target + 1e-6:
            prev[1] = max(prev[1], b); continue
        lo, hi = prev[1] + target/2.0, a - target/2.0
        lo, hi = _residual_avoids_kills(lo, hi, kills)
        wd = inside_word(lo)
        if wd: lo = min(wd[1], a - target/2.0)
        wd = inside_word(hi)
        if wd: hi = max(wd[0], lo)
        lo, hi = _residual_avoids_kills(lo, hi, kills)
        if hi - lo > 0.015:
            prev[1] = lo; final.append([hi, b])
        else:
            prev[1] = max(prev[1], b)

    final[0][0]  = max(start, final[0][0] - P["head_pad"])
    final[-1][1] = min(end,   final[-1][1] + P["tail_pad"])
    # Snap every boundary to the frame grid. ffmpeg's concat pads the shorter stream of
    # each pair, and `trim` is frame-quantised while `atrim` is sample-accurate — so any
    # off-grid segment injects up to a frame of digital SILENCE at that join. That was
    # adding 26-130 ms per hook and making the joins uneven, which is exactly what the
    # fixed-residual design exists to prevent.
    g  = lambda t: round(round(t * FPS) / FPS, 6)
    dn = lambda t: round(math.floor(t * FPS + 1e-9) / FPS, 6)
    up = lambda t: round(math.ceil(t * FPS - 1e-9) / FPS, 6)
    snapped = [(g(a), g(b)) for a, b in final]
    # Kills are subtracted AFTER snapping, and are themselves widened to the grid — round
    # a segment edge and it can land back inside a kill by up to half a frame. Widening
    # outward also means a flub loses a hair more rather than a hair less.
    gkills = [(dn(ka), up(kb)) for ka, kb in kills]
    segs = [(a, b) for a, b in sub(snapped, gkills) if b - a > 0.03]
    for (a1, b1), (a2, _) in zip(segs, segs[1:]):
        assert b1 <= a2 + 1e-9, f"H{hid}: overlapping segments {b1} > {a2}"
    for ka, kb in kills:
        for a, b in segs:
            assert min(b, kb) - max(a, ka) <= 1e-6, \
                f"H{hid}: kill [{ka},{kb}] survives inside segment [{a},{b}]"
    return {"id": hid, "title": h.get("title", f"Hook {hid}"), "note": h.get("note", ""),
            "source_start": start, "source_end": end, "source_span": round(end - start, 2),
            "segments": segs,
            "out_duration": round(sum(b - a for a, b in segs), 3),
            "removed": round((end - start) - sum(b - a for a, b in segs), 2),
            "joins": len(segs) - 1,
            "video_regions": [(round(a, 2), round(b, 2)) for a, b in prot],
            "kills": [list(k) for k in kills]}

plans = []
for h in cfg["hooks"]:
    p = plan_hook(h)
    if p is None:
        raise SystemExit(f"hook {h['id']} planned to NOTHING — bad span, or a kill that "
                         f"swallowed it. Fix hooks.json; a missing hook must not pass silently.")
    plans.append(p)
json.dump(plans, open(cfg["_root"] + "/cuts.json", "w"), indent=1)
print(f"floor = {FLOOR:.1f} dB   join {P['join_gap']}s / video {P['video_gap']}s / tail {P['tail_pad']}s\n")
ti = to = 0.0
for p in plans:
    ti += p["source_span"]; to += p["out_duration"]
    print(f"H{p['id']:02d}  {p['source_span']:6.2f}s -> {p['out_duration']:6.2f}s  "
          f"(-{p['removed']:5.2f}s, {p['joins']:2d} joins, {len(p['video_regions'])} video)  {p['title']}")
print(f"\nTOTAL {ti:.1f}s -> {to:.1f}s  (removed {ti-to:.1f}s)")
