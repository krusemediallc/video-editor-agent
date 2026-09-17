#!/usr/bin/env python3
"""
measure-face-band.py — derive the overlay band from THIS footage.

The talking-head-image-overlays style puts image inserts top-anchored above the
speaker. The reference reel has no face-avoidance logic at all (its rects are
absolutely positioned while the speaker moves, so the same rect clears the brow
in one shot and cuts through the eyebrows in another). We do not copy that: we
derive two floors from the minimum across the whole take.

    EYE_FLOOR  = min eye line - 24   # bottom limit for a WIDE insert
    HEAD_FLOOR = min head top  -  8  # bottom limit for a NARROW insert

Narrow inserts need the stricter floor because a narrow rect centred above a
head reads as a hat.

Usage:
    python3 measure-face-band.py <video.mp4> <outdir> [--fps 1] [--dark 110]

Requires: ffmpeg on PATH, numpy, pillow.

Method and its limits: the head is segmented as the darkest connected mass in
the middle 60% of frame width, scanning down from the top. That works when the
subject is darker than the background behind them (dark hair or a cap against a
light wall) and the background's top strip is not itself dark. ALWAYS eyeball
the printed per-frame boxes on a few frames, and fall back to reading a montage
by hand if the distributions look implausible. This script prints the evidence
it used so you can check it.
"""
import argparse
import glob
import os
import subprocess
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("needs numpy and pillow: pip install numpy pillow")


def sample_frames(src, outdir, fps):
    os.makedirs(outdir, exist_ok=True)
    for old in glob.glob(os.path.join(outdir, "f_*.png")):
        os.remove(old)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src,
         "-vf", f"fps={fps},scale=270:480", os.path.join(outdir, "f_%04d.png")],
        check=True)
    return sorted(glob.glob(os.path.join(outdir, "f_*.png")))


def measure(path, dark_thresh):
    """Return (head_top, eye_line) in 0..1920 space, or None."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    H, W, _ = a.shape
    lum = a.mean(2)
    mid = lum[:, int(W * 0.2):int(W * 0.8)]
    dark = (mid < dark_thresh).sum(1)
    idx = np.where(dark > mid.shape[1] * 0.12)[0]
    if not len(idx):
        return None
    head_top = idx[0]
    lo = head_top + int(0.05 * H)
    hi = min(H, head_top + int(0.22 * H))
    band = dark[lo:hi]
    if not len(band):
        return None
    eye = lo + int(np.argmax(band))          # glasses/brow = densest dark row
    return head_top / H * 1920, eye / H * 1920


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--dark", type=int, default=110,
                    help="luminance below which a pixel counts as head (0-255)")
    args = ap.parse_args()

    frames = sample_frames(args.video, args.outdir, args.fps)
    rows = [(f, m) for f in frames if (m := measure(f, args.dark))]
    if len(rows) < 5:
        sys.exit(f"only {len(rows)} usable samples — segmentation likely failed. "
                 f"Try --dark, or measure by hand from a montage.")

    tops = np.array([m[0] for _, m in rows])
    eyes = np.array([m[1] for _, m in rows])

    print(f"samples: {len(rows)} of {len(frames)} frames\n")
    print("             min    p10    median   max")
    print(f"head top  {tops.min():7.0f}{np.percentile(tops,10):7.0f}"
          f"{np.median(tops):9.0f}{tops.max():7.0f}")
    print(f"eye line  {eyes.min():7.0f}{np.percentile(eyes,10):7.0f}"
          f"{np.median(eyes):9.0f}{eyes.max():7.0f}\n")

    eye_floor = eyes.min() - 24
    head_floor = tops.min() - 8
    print(f"EYE_FLOOR  = {eye_floor:.0f}   # wide inserts (>=70% frame width)")
    print(f"HEAD_FLOOR = {head_floor:.0f}   # narrow inserts (<70%)")
    print(f"usable band (wide)   = y 40..{eye_floor:.0f}  ({eye_floor-40:.0f}px tall)")
    print(f"usable band (narrow) = y 40..{head_floor:.0f}  ({head_floor-40:.0f}px tall)")
    if head_floor - 40 < 200:
        print("\nWARNING: the narrow band is under 200px. The subject sits very "
              "high in frame. Consider reframing the base, or carrying Act 2 "
              "with wide/landscape sources only.")

    print("\nspot-check these three (verify the boxes look right):")
    for f, m in rows[:: max(1, len(rows) // 3)][:3]:
        print(f"  {os.path.basename(f)}  head_top={m[0]:.0f}  eye={m[1]:.0f}")


if __name__ == "__main__":
    main()
