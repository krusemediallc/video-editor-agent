#!/usr/bin/env python3
"""The confirmation step. Slice one window out and transcribe it ALONE.

Never write a `kills` entry from a full-file transcript. That pass hallucinates
repeats that are not in the audio AND smooths away repeats that are. Isolation
resolves both — an aborted "fresh" comes back as "Fractured", a doubled take finally
prints twice.

If an isolated slice still disagrees with what the RENDER sounds like, slice each
candidate burst to its own wav (0.8-1.0s each) and believe the energy envelope over
any transcript. That is how a "Let's see how good it did." that whisper insisted was
one phrase resolved into two bursts 0.36s apart.

    python3 isolate.py [hooks.json] <start> <dur> [--sys] [--env]

      --sys  read the system-audio track instead of the mic
      --env  also print the 10 ms energy envelope, for exact cut boundaries
"""
import re, subprocess, sys
import numpy as np
from _cfg import load, w, FFMPEG, WHISPER, WMODEL, HOP

cfg = load()
nums = [a for a in sys.argv[1:] if re.fullmatch(r"[\d.]+", a)]
if len(nums) < 2:
    sys.exit("usage: isolate.py [hooks.json] <start> <dur> [--sys] [--env]")
start, dur = float(nums[0]), float(nums[1])
idx = cfg["audio"]["system"] if "--sys" in sys.argv else cfg["audio"]["mic"]

wav = w(cfg, "_iso.wav")
subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(dur),
                "-i", w(cfg, f"a{idx}.wav"), wav], check=True)
print(f"### stream {idx}   src {start}s +{dur}s ###")
print(subprocess.run([WHISPER, "-m", WMODEL, "-f", wav, "-np"],
                     capture_output=True, text=True).stdout.strip())

if "--env" in sys.argv:
    env = np.load(w(cfg, f"env{idx}.npy"))
    print("\nenvelope (0.04s steps) — cut in the troughs, never mid-word:")
    for t in np.arange(start, start + min(dur, len(env) * HOP - start), 0.04):
        k = int(t / HOP)
        if k >= len(env): break
        v = float(env[k])
        print(f"  {t:8.2f} {v:6.1f} {'#' * max(0, int((v + 72) / 2.0))}")
