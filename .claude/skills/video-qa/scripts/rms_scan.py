#!/usr/bin/env python3
"""RMS-envelope lull scan (video-qa Layer 1, pass 2b).

Why this exists: silencedetect at -38/-40dB misses breathy -28..-36dB lulls that
human ears read as dead air. This script windows RMS at a fixed interval (default
50ms) and reports every sustained run below a threshold, so those lulls surface.
Cross-check the output against silencedetect: runs silencedetect ALSO caught are
already handled; runs it missed are the human-audible gaps.

usage:
  rms_scan.py MEDIA [--threshold-db -27] [--min-dur 0.35] [--window 0.05]
              [--start S] [--duration T]

MEDIA is any file ffmpeg can read (mp4/mov/wav/...). Output: JSON to stdout:
  {"windowSec": ..., "thresholdDb": ..., "lulls": [
      {"start": ..., "end": ..., "dur": ..., "minRmsDb": ..., "meanRmsDb": ...}]}

Times are absolute (the --start offset is added back). Uses stdlib only; ffmpeg
binary from $FFMPEG_PATH or "ffmpeg" on PATH.
"""
import argparse
import json
import os
import re
import subprocess
import sys

SR = 16000  # analysis sample rate; window size in samples derives from this


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("media")
    ap.add_argument("--threshold-db", type=float, default=-27.0,
                    help="RMS below this = lull (default -27dB; breathy gaps sit -28..-36)")
    ap.add_argument("--min-dur", type=float, default=0.35,
                    help="minimum sustained run to report (seconds)")
    ap.add_argument("--window", type=float, default=0.05, help="RMS window (seconds)")
    ap.add_argument("--start", type=float, default=None, help="analyze from this second")
    ap.add_argument("--duration", type=float, default=None, help="analyze this many seconds")
    args = ap.parse_args()

    ff = os.environ.get("FFMPEG_PATH", "ffmpeg")
    nsamples = max(1, int(round(SR * args.window)))
    cmd = [ff, "-nostdin", "-hide_banner", "-v", "error"]
    if args.start is not None:
        cmd += ["-ss", f"{args.start:.3f}"]
    if args.duration is not None:
        cmd += ["-t", f"{args.duration:.3f}"]
    cmd += [
        "-i", args.media,
        "-af",
        # aformat downmixes any layout to mono correctly (a pan hack halves mono input).
        f"aformat=sample_rates={SR}:channel_layouts=mono,asetnsamples=n={nsamples},"
        "astats=metadata=1:reset=1,"
        "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
        "-vn", "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"error: ffmpeg not found ({ff}); set FFMPEG_PATH or add ffmpeg to PATH",
              file=sys.stderr)
        return 2
    if res.returncode != 0:
        print(f"error: ffmpeg failed: {res.stderr[-500:]}", file=sys.stderr)
        return 2

    # Parse alternating "pts_time:X" / "lavfi...RMS_level=Y" lines from stdout.
    offset = args.start or 0.0
    t = None
    samples = []  # (abs_time, rms_db)
    for line in res.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1)) + offset
            continue
        m = re.search(r"RMS_level=(-?[\d.]+|-inf|nan)", line)
        if m and t is not None:
            v = m.group(1)
            rms = -120.0 if v in ("-inf", "nan") else float(v)
            samples.append((t, rms))
            t = None

    # Merge consecutive below-threshold windows into runs.
    lulls = []
    run = None
    for tt, rms in samples:
        if rms < args.threshold_db:
            if run is None:
                run = {"start": tt, "vals": []}
            run["vals"].append(rms)
            run["end"] = tt + args.window
        elif run is not None:
            lulls.append(run)
            run = None
    if run is not None:
        lulls.append(run)

    out = []
    for r in lulls:
        dur = r["end"] - r["start"]
        if dur + 1e-9 < args.min_dur:
            continue
        out.append({
            "start": round(r["start"], 3),
            "end": round(r["end"], 3),
            "dur": round(dur, 3),
            "minRmsDb": round(min(r["vals"]), 1),
            "meanRmsDb": round(sum(r["vals"]) / len(r["vals"]), 1),
        })
    json.dump({"windowSec": args.window, "thresholdDb": args.threshold_db,
               "lulls": out}, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
