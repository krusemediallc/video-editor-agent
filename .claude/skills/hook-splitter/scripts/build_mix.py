#!/usr/bin/env python3
"""Step 4 — work/mixed.mov: video stream-copied, both audio tracks summed.

The mic track alone is unusable: the played videos reach it ~22.6 dB below their own
clean capture, so on that track they are barely audible. Summed, the ad sits at
-35.1 dB against the speaker's -33.5 dB, which is the balance the recording was set up
to produce. `normalize=0` is essential — amix's default divides by input count.

Summing also gives a handle nothing else does: because the ad audio is ISOLATED on the
system track, each looping restart can be silenced without touching the voice. That
matters where the speaker reacts OVER the loop and no cut can help.

Video is `-c:v copy`, so this is fast (19s for a 16-minute 1.3 GB source) and lossless.

    python3 build_mix.py [hooks.json]
"""
import json, os
from _cfg import load, w, FFMPEG, run

cfg = load()
VR = [tuple(x) for x in json.load(open(w(cfg, "video_regions.json")))]
# A MISSING file means detect_loops.py was skipped or died — not "there are no loops".
# A genuine no-loop run still writes {}. Never let a skipped step silently disable
# loop muting and loop-tail removal.
_lp = w(cfg, "loop_points.json")
if not os.path.exists(_lp):
    raise SystemExit(f"{_lp} not found — run detect_loops.py first "
                     f"(a real no-loop result still writes an empty object).")
LOOPS = json.load(open(_lp))

mutes = [(lp, b + 0.05) for a, b in VR
         for lp in [LOOPS.get(f"{a:.2f}")] if lp is not None and b - lp > 0.05]

mic, sysi = cfg["audio"]["mic"], cfg["audio"]["system"]
if mutes:
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in mutes)
    fc = (f"[0:a:{sysi}]volume=0:enable='{expr}'[q];"
          f"[0:a:{mic}][q]amix=inputs=2:normalize=0[am];[am]alimiter=limit=0.98[a]")
else:
    fc = (f"[0:a:{mic}][0:a:{sysi}]amix=inputs=2:normalize=0[am];"
          f"[am]alimiter=limit=0.98[a]")

print(f"muting the ad track over {len(mutes)} loop tails "
      f"({sum(b-a for a,b in mutes):.1f}s)")
run([FFMPEG, "-y", "-v", "error", "-stats", "-i", cfg["source"],
     "-filter_complex", fc, "-map", "0:v:0", "-map", "[a]",
     "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
     "-movflags", "+faststart", w(cfg, "mixed.mov")])
print("wrote", w(cfg, "mixed.mov"))
