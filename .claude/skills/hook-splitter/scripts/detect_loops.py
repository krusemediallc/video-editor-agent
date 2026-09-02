#!/usr/bin/env python3
"""Step 3 — find where each played video RESTARTS inside its region.

Players loop. On the reference project most regions ended with 0.3-2.1s of the ad
playing again from the top ("One customer…", "40 batches…" all reappeared in the QA
transcripts), which is dead weight before the reaction — and where the speaker reacts
OVER the loop, no cut can remove it. build_mix.py mutes the system track from these
points; plan.py also kills the part the speaker is not talking over.

Method: spectral self-similarity on the CLEAN system track. Correlate a short
reference from the region's head against every later offset.

Three things this gets wrong if you change them:
  * Raw-waveform correlation does NOT work (0.06 — phase differences). Log-band
    spectra do.
  * The search MUST be windowed near the known render length. These ads are musically
    self-similar and an unconstrained search peaks on a repeated stinger at 8.5s.
  * A peak pinned to either edge of the window is a boundary artifact, not a loop.

Regions whose tail is shorter than the reference cannot be confirmed and fall back to
the measured consensus length. On the reference project seven confirmable regions all
resolved to 10.12-10.19s (two at corr 1.00), hence consensus 10.15.

    python3 detect_loops.py [hooks.json]
"""
import json, wave
import numpy as np
from _cfg import load, w

cfg = load(); L = cfg["loop"]
CONSENSUS, MIN_DUR = L["consensus"], L["min_dur"]
WIN_LO, WIN_HI, MIN_CORR = L["window"][0], L["window"][1], L["min_corr"]
REF_A, REF_B = L["ref"]

ww = wave.open(w(cfg, f"a{cfg['audio']['system']}.wav"), "rb")
y = np.frombuffer(ww.readframes(ww.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
N, HOPS = 1024, 160                      # 10 ms hop at 16 kHz
win = np.hanning(N).astype(np.float32)
nf = (len(y) - N) // HOPS
S = np.empty((nf, N // 2 + 1), dtype=np.float32)
for i in range(nf):
    S[i] = np.abs(np.fft.rfft(y[i*HOPS:i*HOPS+N] * win))
edges = np.unique(np.geomspace(2, N // 2, 49).astype(int))
B = np.stack([S[:, edges[k]:edges[k+1]].mean(axis=1) for k in range(len(edges)-1)], axis=1)
B = np.log10(B + 1e-6); B -= B.mean(axis=1, keepdims=True)
B /= (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)

VR = [tuple(x) for x in json.load(open(w(cfg, "video_regions.json")))]
out = {}
for a, b in VR:
    dur = b - a
    if dur < MIN_DUR:
        continue
    f0 = int(a / 0.010)
    ref = B[f0 + int(REF_A*100): f0 + int(REF_B*100)]
    best = (None, -1.0); t = WIN_LO + REF_A
    while t < min(WIN_HI + REF_A, dur - 0.12):
        # clamp to the region: reading past its end lets whatever plays NEXT contribute
        # to the correlation and can invent a loop point, muting or cutting good audio
        hi = min(f0 + int(t*100) + len(ref), f0 + int(dur*100))
        seg = B[f0 + int(t*100): hi]
        m = min(len(seg), len(ref))
        if m < len(ref) // 2: break
        c = float((ref[:m] * seg[:m]).sum() / m)
        if c > best[1]: best = (t - REF_A, c)
        t += 0.01
    edge = best[0] is not None and (abs(best[0]-WIN_LO) < 0.025 or abs(best[0]-WIN_HI) < 0.025)
    if best[0] is not None and best[1] >= MIN_CORR and not edge:
        off, how = best[0], f"measured corr={best[1]:.2f}"
    else:
        off, how = CONSENSUS, "consensus (tail too short to confirm)"
    if dur - off < 0.20:
        continue
    out[f"{a:.2f}"] = round(a + off, 3)
    print(f"{a:8.2f}-{b:7.2f} ({dur:5.2f}s)  loop at +{off:5.2f}s  trims {dur-off:4.2f}s  [{how}]")

json.dump(out, open(w(cfg, "loop_points.json"), "w"), indent=1)
print(f"\n{len(out)} loop tails found")
