#!/usr/bin/env python3
"""Step 1 — read the source, split its audio streams, build dB envelopes.

Also decides WHICH stream is the mic and which is the system capture, by silence
fraction: a system-audio capture is digital silence whenever nothing is playing
(75.6% of the file on the reference project), a live mic never is.

    python3 probe.py [hooks.json] [--map]

--map prints a coarse level map of the system track, for hand-marking video regions
when the source has only one usable audio stream.
"""
import json, subprocess, sys
import numpy as np
from _cfg import load, w, FFMPEG, FFPROBE, HOP

cfg = load()
src = cfg["source"]

info = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                       "stream=index,codec_type,codec_name,channels,sample_rate,width,height,r_frame_rate",
                       "-show_entries", "format=duration",
                       "-of", "json", src], capture_output=True, text=True).stdout
meta = json.loads(info)
audio = [s for s in meta["streams"] if s["codec_type"] == "audio"]
video = [s for s in meta["streams"] if s["codec_type"] == "video"]
dur = float(meta["format"]["duration"])
print(f"source: {dur:.2f}s  video {video[0]['width']}x{video[0]['height']} @ {video[0]['r_frame_rate']}  "
      f"| {len(audio)} audio stream(s)")

report = {"duration": dur, "streams": []}
for n, s in enumerate(audio):
    wav = w(cfg, f"a{n}.wav")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-map", f"0:a:{n}",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav], check=True)
    import wave
    ww = wave.open(wav, "rb")
    a = np.frombuffer(ww.readframes(ww.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    h = int(16000 * HOP); m = len(a) // h
    env = 20 * np.log10(np.sqrt((a[:m*h].reshape(m, h) ** 2).mean(axis=1)) + 1e-12)
    np.save(w(cfg, f"env{n}.npy"), env)
    silent = float((env < -80).mean())
    report["streams"].append({"index": n, "silent_frac": round(silent, 4),
                              "mean_db": round(float(env.mean()), 1)})
    kind = "SYSTEM capture (digital-silent when nothing plays)" if silent > 0.5 else "MIC"
    print(f"  stream {n}: mean {env.mean():6.1f} dB   {silent*100:5.1f}% digital silence   -> {kind}")

sysidx = [s["index"] for s in report["streams"] if s["silent_frac"] > 0.5]
if len(audio) < 2 or not sysidx:
    print("\n!! No clean system-audio track. There is no free 'video is playing' mask —\n"
          "   hand-mark \"video_regions\" in hooks.json (run again with --map for a level map).")
else:
    print(f"\nmic = stream {[s['index'] for s in report['streams'] if s['silent_frac'] <= 0.5][0]}, "
          f"system = stream {sysidx[0]}")
    print("VERIFY ALIGNMENT before trusting the mask: transcribe the same 45s window from\n"
          "both tracks near the START and near the END of the file. A drifting mask corrupts\n"
          "every output silently.")
json.dump(report, open(w(cfg, "streams.json"), "w"), indent=1)

if "--map" in sys.argv:
    idx = sysidx[0] if sysidx else 0
    env = np.load(w(cfg, f"env{idx}.npy"))
    print(f"\nlevel map of stream {idx} (one char = 0.5s, '#' = playing):")
    per = 50
    for k in range(0, len(env), per * 10):
        row = env[k:k + per * 10]
        line = "".join("#" if row[i:i+50].max() > -80 else "." for i in range(0, len(row), 50))
        print(f"  {k*HOP:7.1f}s |{line}|")
