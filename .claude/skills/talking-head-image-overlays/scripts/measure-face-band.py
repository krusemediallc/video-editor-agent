#!/usr/bin/env python3
"""
measure-face-band.py — derive the overlay band from THIS footage.

The talking-head-image-overlays style puts image inserts top-anchored above the
speaker. The reference reel has no face-avoidance logic at all (its rects are
absolutely positioned while the speaker moves, so the same rect clears the brow
in one shot and cuts through the eyebrows in another). We do not copy that: we
derive two floors from the MINIMUM across the whole take.

    EYE_FLOOR  = min eye-top - 24   # bottom limit for a WIDE insert (>=70% width)
    HEAD_FLOOR = min cap-top -  8   # bottom limit for a NARROW insert

Narrow inserts need the stricter floor because a narrow rect centred above a
head reads as a hat.

    python3 measure-face-band.py <video.mp4> <outdir> [--fps 6] [--dark 118]
    python3 measure-face-band.py <video.mp4> <outdir> --fps 0     # every frame

TWO THINGS THIS SCRIPT EXISTS TO STOP YOU DOING

1. Copying the reference's y-values. On a real build the difference between a
   guessed floor and the measured one was 278px — a usable insert versus a
   163px sliver.

2. Trusting a sparse sample. The binding constraint is usually a sub-second
   transient at record start or stop, when the subject is settling or reaching
   for the camera. On one take the true minimum eye line sat 65px above what a
   1fps grid reported, and the true highest head 76px above it. Default is 6fps;
   use --fps 0 before you commit to a floor for a narrow insert.

HOW IT MEASURES

On macOS it compiles and uses `face-landmarks.swift` (Apple's Vision framework)
for the eye, brow, chin and face box — every frame, no model download. Cap top
is then found by walking UP from the Vision face box through contiguous dark
pixels, so it is seeded on the face and cannot latch onto background objects.

Off macOS it falls back to a pure luminance heuristic, which is genuinely
unreliable in a real room and is gated behind a validation check. Two measured
failure modes on one ordinary clip: a dark framed print above the subject read
as the crown (124px too high), and a black t-shirt read as the face. If the
fallback runs, treat its numbers as provisional and eyeball annotated frames.

VALIDATION. A head is rigid, so (eye - cap) / (chin - cap) is near-constant for
one person. A high coefficient of variation means some frames measured something
that is not a head. The script reports it and refuses to present floors as
trustworthy when it is high.

Requires: ffmpeg, numpy, pillow. On macOS also swiftc (Xcode CLI tools).
"""
import argparse
import glob
import json
import os
import platform
import subprocess
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("needs numpy and pillow: pip install numpy pillow")

HERE = os.path.dirname(os.path.abspath(__file__))


def sample_frames(src, outdir, fps):
    os.makedirs(outdir, exist_ok=True)
    for old in glob.glob(os.path.join(outdir, "f_*.png")):
        os.remove(old)
    vf = "scale=270:480" if fps == 0 else f"fps={fps},scale=270:480"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src,
                    "-vf", vf, os.path.join(outdir, "f_%05d.png")], check=True)
    return sorted(glob.glob(os.path.join(outdir, "f_*.png")))


def build_vision_tool(outdir):
    """Compile face-landmarks.swift. Returns the binary path, or None."""
    if platform.system() != "Darwin":
        return None
    src = os.path.join(HERE, "face-landmarks.swift")
    if not os.path.exists(src):
        return None
    binp = os.path.join(outdir, "face-landmarks")
    if os.path.exists(binp):
        return binp
    r = subprocess.run(["swiftc", "-O", "-o", binp, src],
                       capture_output=True, text=True)
    return binp if r.returncode == 0 and os.path.exists(binp) else None


def run_vision(binp, frames):
    """{path: {...}} from the Vision tool, batched to stay under ARG_MAX."""
    out = {}
    for i in range(0, len(frames), 200):
        r = subprocess.run([binp] + frames[i:i + 200],
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("ok"):
                out[d["f"]] = d
    return out


def cap_top_from(path, box_top_px, dark_thresh):
    """Walk UP from the Vision face box through contiguous dark pixels."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    H, W, _ = a.shape
    lum = a.mean(2)
    mid = lum[:, int(W * 0.2):int(W * 0.8)]
    cols = mid.shape[1]
    dark = (mid < dark_thresh).sum(1)
    y0 = max(0, min(H - 1, int(box_top_px)))
    quit_at = cols * 0.05
    cap = y0
    for y in range(y0, -1, -1):
        if dark[y] < quit_at:
            break
        cap = y
    return cap * (1920.0 / H)


def heuristic(path, dark_thresh):
    """Fallback: no face detector. Unreliable — gated by validation."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    H, W, _ = a.shape
    lum = a.mean(2)
    mid = lum[:, int(W * 0.2):int(W * 0.8)]
    cols = mid.shape[1]
    dark = (mid < dark_thresh).sum(1)
    idx = np.where(dark > cols * 0.12)[0]
    if not len(idx):
        return None
    cap = int(idx[0])
    lo, hi = cap + int(0.05 * H), min(H, cap + int(0.22 * H))
    if hi <= lo:
        return None
    eye = lo + int(np.argmax(dark[lo:hi]))
    below = dark[eye:min(H, eye + int(0.30 * H))]
    thin = np.where(below < cols * 0.06)[0]
    chin = eye + (int(thin[0]) if len(thin) else int(0.18 * H))
    k = 1920.0 / H
    return cap * k, eye * k, chin * k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--fps", type=float, default=6.0, help="0 = every frame")
    ap.add_argument("--dark", type=int, default=118)
    ap.add_argument("--no-vision", action="store_true",
                    help="force the luminance fallback (for testing it)")
    args = ap.parse_args()

    frames = sample_frames(args.video, args.outdir, args.fps)
    binp = None if args.no_vision else build_vision_tool(args.outdir)
    caps, eyes, chins = [], [], []

    if binp:
        det = run_vision(binp, frames)
        scale = None
        for f in frames:
            d = det.get(f)
            if not d or "eyeTop" not in d:
                continue
            if scale is None:
                scale = 1920.0 / Image.open(f).size[1]
            eyes.append(d["eyeTop"] * scale)
            chins.append(d.get("chin", d["boxBottom"]) * scale)
            caps.append(cap_top_from(f, d["boxTop"], args.dark))
        method = f"Apple Vision landmarks ({len(eyes)}/{len(frames)} frames detected)"
    else:
        for f in frames:
            m = heuristic(f, args.dark)
            if m:
                caps.append(m[0]); eyes.append(m[1]); chins.append(m[2])
        method = "luminance heuristic (NO face detector — provisional numbers)"

    if len(eyes) < 20:
        sys.exit(f"only {len(eyes)} usable samples — measurement failed.")

    caps, eyes, chins = map(np.array, (caps, eyes, chins))
    print(f"method: {method}")
    print(f"sampled: {'every frame' if args.fps == 0 else f'{args.fps} fps'}\n")
    print("             min    p10    median   max")
    for name, arr in (("cap top", caps), ("eye top", eyes), ("chin", chins)):
        print(f"{name:9} {arr.min():7.0f}{np.percentile(arr,10):7.0f}"
              f"{np.median(arr):9.0f}{arr.max():7.0f}")

    denom = chins - caps
    ok = denom > 1
    ratio = (eyes[ok] - caps[ok]) / denom[ok]
    cv = ratio.std() / ratio.mean() if ratio.mean() else 9.9
    print(f"\nvalidation: (eye-cap)/(chin-cap) = {ratio.mean():.3f} "
          f"+/- {ratio.std():.3f}  (CV {cv*100:.1f}%)")
    trust = cv <= 0.08
    print("  OK — consistent with a single rigid head." if trust else
          "  !! CV above 8% — some frames measured something that is not a head.\n"
          "  !! Do not trust these floors; annotate frames and check by eye.")

    eye_floor, head_floor = eyes.min() - 24, caps.min() - 8
    print(f"\nEYE_FLOOR  = {eye_floor:.0f}   # wide inserts (>=70% frame width)")
    print(f"HEAD_FLOOR = {head_floor:.0f}   # narrow inserts (<70%)")
    print(f"usable band (wide)   = y 40..{eye_floor:.0f}  ({eye_floor-40:.0f}px tall)")
    print(f"usable band (narrow) = y 40..{head_floor:.0f}  ({head_floor-40:.0f}px tall)")

    n = len(eyes)
    t_of = (lambda i: i / args.fps) if args.fps else (lambda i: None)
    ei, ci = int(np.argmin(eyes)), int(np.argmin(caps))
    for label, i in (("min eye top", ei), ("min cap top", ci)):
        t = t_of(i)
        print(f"  {label} at sample {i}" + (f" (t~{t:.1f}s)" if t is not None else ""))
    edge = 0.02 * n
    if ei < edge or ei > n - edge or ci < edge or ci > n - edge:
        print("  ^ a binding minimum is at the head or tail of the take — that is "
              "the subject\n    settling after record start or reaching to stop. "
              "Trimming those frames\n    typically buys back 30-90px of band.")

    if head_floor - 40 < 200:
        print("\nWARNING: narrow band under 200px. The subject sits very high in "
              "frame. Reframe the base, or carry Act 2 with wide sources only.")


if __name__ == "__main__":
    main()
