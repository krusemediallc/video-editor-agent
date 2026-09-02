#!/usr/bin/env python3
"""Step 6 — cuts.json -> one MP4 per hook.

Reads work/mixed.mov (video stream-copied, audio already summed and loop-muted) so a
single -ss input seek keeps picture and sound locked. That seek is frame-EXACT on this
material — verified byte-identical against a direct extract — so per-hook seeking plus
relative filter times is both safe and cheap.

    python3 render.py [hooks.json] [id ...]      # ids optional, default all
"""
import json, os, subprocess, sys
from _cfg import load, w, FFMPEG, FFPROBE, probe_dur

cfg = load()
FPS = cfg.get("fps", 30)
plans = json.load(open(cfg["_root"] + "/cuts.json"))
os.makedirs(cfg["out"], exist_ok=True)
only = {int(a) for a in sys.argv[1:] if a.isdigit()}
src = w(cfg, "mixed.mov")

for p in plans:
    if only and p["id"] not in only: continue
    segs = p["segments"]; S = segs[0][0]
    # plan.py already snapped these; re-snap the RELATIVE times so float error in the
    # subtraction cannot push a boundary off the frame grid and reintroduce concat padding.
    snap = lambda t: round(round(t * FPS) / FPS, 6)
    rel = [(snap(a - S), snap(b - S)) for a, b in segs]
    n = len(rel)
    out = os.path.join(cfg["out"], f"hook-{p['id']:02d}.mp4")

    if n == 1:
        fc = (f"[0:v]trim=start={rel[0][0]}:end={rel[0][1]},setpts=PTS-STARTPTS[vo];"
              f"[0:a]atrim=start={rel[0][0]}:end={rel[0][1]},asetpts=PTS-STARTPTS[ao]")
    else:
        parts = ["[0:v]split=%d%s" % (n, "".join(f"[v{i}]" for i in range(n))),
                 "[0:a]asplit=%d%s" % (n, "".join(f"[a{i}]" for i in range(n)))]
        for i, (a, b) in enumerate(rel):
            parts.append(f"[v{i}]trim=start={a}:end={b},setpts=PTS-STARTPTS[cv{i}]")
            parts.append(f"[a{i}]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[ca{i}]")
        parts.append("".join(f"[cv{i}][ca{i}]" for i in range(n)) +
                     f"concat=n={n}:v=1:a=1[vo][ao]")
        fc = ";".join(parts)

    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{S:.4f}", "-i", src,
                    "-filter_complex", fc, "-map", "[vo]", "-map", "[ao]",
                    "-c:v", "libx264", "-profile:v", "high", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", out], check=True)
    d = probe_dur(out)
    # tolerance is one frame. A looser bound hid 26-130 ms of concat padding per hook.
    flag = "" if abs(d - p["out_duration"]) <= (1.5 / FPS) else \
        f"   <-- MISMATCH exp {p['out_duration']:.3f} (concat padding? check frame snapping)"
    print(f"H{p['id']:02d}  {n:2d} segs -> {d:6.2f}s  {out}{flag}")
