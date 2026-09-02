#!/usr/bin/env python3
"""Is a gap acoustically silent? argv: <take> <start> <end>  -> prints SILENT or NOT.

A gap this far under the take's speech level cannot contain a word, whatever Whisper's word
spans say. Without this check the duration test in verify_cuts.ts fires constantly, because
Whisper extends a word's span into the pause that follows it - so removing pure silence looks
like the word got shorter.
"""
import subprocess, sys, numpy as np, os
import shutil
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
take, g0, g1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
r = subprocess.run([(os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"), "-v", "error", "-i",
                    f"{BASE}/raw/Take {take} - Mic.wav", "-map", "0:a:0", "-ac", "1",
                    "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
x = np.frombuffer(r, dtype=np.float32).astype(float)
h = 320; n = len(x) // h
db = 20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-10)
seg = db[int(g0 / 0.02):int(g1 / 0.02)]
print("SILENT" if len(seg) and seg.max() < np.percentile(db, 95) - 24 else "NOT")
