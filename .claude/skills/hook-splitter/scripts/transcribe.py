#!/usr/bin/env python3
"""Step 2b — the two speech maps the planner needs, off the MIC track.

  work/vad.txt    silero VAD speech segments
  work/words.json OpenAI Whisper verbose_json with word timestamps

Both are needed and neither is sufficient. VAD clips word ONSETS (it started
"Alright" at 3.52s where the energy and whisper both put it at 2.48s); whisper drifts
and stretches. plan.py uses them only as a cross-check on an energy gate.

    python3 transcribe.py [hooks.json]

Needs OPENAI_API_KEY (env, or a .env anywhere up the tree from the config).
"""
import json, os, re, subprocess, sys
from _cfg import load, w, FFMPEG, VAD_BIN, VAD_MODEL

cfg = load()
mic = w(cfg, f"a{cfg['audio']['mic']}.wav")

# ── VAD ───────────────────────────────────────────────────────────────────────────
raw = subprocess.run([VAD_BIN, "-f", mic, "-vm", VAD_MODEL, "-vt", "0.5"],
                     capture_output=True, text=True).stdout
lines = [l for l in raw.splitlines() if "start" in l and "end" in l]
open(w(cfg, "vad.txt"), "w").write("\n".join(lines))
print(f"VAD: {len(lines)} segments")
# NOTE: this binary prints CENTISECONDS. Dividing by 1000 silently throws away
# everything past ~98s. plan.py divides by 100 — do not "fix" that.

# ── words, via the OpenAI Whisper API ─────────────────────────────────────────────
key = os.environ.get("OPENAI_API_KEY")
if not key:
    d = cfg["_root"]
    for _ in range(6):
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            m = re.search(r"^OPENAI_API_KEY=(.+)$", open(p).read(), re.M)
            if m: key = m.group(1).strip().strip('"').strip("'"); break
        d = os.path.dirname(d)
if not key:
    sys.exit("OPENAI_API_KEY not found (env or .env)")

mp3 = w(cfg, "mic.mp3")
subprocess.run([FFMPEG, "-y", "-v", "error", "-i", mic,
                "-c:a", "libmp3lame", "-b:a", "48k", mp3], check=True)
size = os.path.getsize(mp3) / 1e6
print(f"mic.mp3 {size:.1f} MB  (API limit 25 MB — mono 48k mp3 holds ~2h)")

args = ["curl", "-sS", "https://api.openai.com/v1/audio/transcriptions",
        "-H", f"Authorization: Bearer {key}",
        "-F", f"file=@{mp3}", "-F", "model=whisper-1", "-F", "language=en",
        "-F", "response_format=verbose_json",
        "-F", "timestamp_granularities[]=word",
        "-F", "timestamp_granularities[]=segment"]
if cfg.get("prompt"):
    args += ["-F", f"prompt={cfg['prompt']}"]
out = subprocess.run(args, capture_output=True, text=True).stdout
try:
    data = json.loads(out)
except json.JSONDecodeError:
    sys.exit(f"whisper API returned non-JSON:\n{out[:600]}")
if "error" in data:
    sys.exit(f"whisper API error: {data['error']}")
json.dump(data, open(w(cfg, "words.json"), "w"), indent=1)
print(f"words: {len(data.get('words') or [])}   segments: {len(data.get('segments') or [])}")
