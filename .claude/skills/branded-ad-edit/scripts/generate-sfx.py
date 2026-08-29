#!/usr/bin/env python3
"""generate-sfx.py — ElevenLabs SFX kit: generate → audit → retry duds → normalize.

Automates the biggest audio time-sink: ~1/3 of ElevenLabs sound-generations come back
near-silent, and un-normalized files make data-volume values meaningless. This script
generates every effect in a kit config, audits each file with ffmpeg volumedetect,
regenerates duds once with a louder prompt + higher prompt_influence, peak-normalizes
the whole kit to a target dB, and writes durations.json for the composition builder.

Auth: reads ELEVENLABS_API_KEY from the environment, falling back to a `.env` file
found in the current directory or any parent (the repo-root `.env` pattern). Errors
clearly if neither is set.

Usage:
  python3 generate-sfx.py kit.json <outDir>
  # or: ELEVENLABS_API_KEY=… python3 generate-sfx.py kit.json <outDir>

kit.json:
{
  "normalize_db": -3.0,          // target peak for every file
  "min_peak_db": -12.0,          // audit threshold: quieter than this = dud, regenerate
  "effects": [
    {"name": "whoosh-soft", "prompt": "short soft airy whoosh, UI card sliding in, clean swipe", "seconds": 0.7},
    {"name": "stamp-slam",  "prompt": "loud heavy thud slam impact, stamp hitting a desk, punchy bass", "seconds": 0.8}
  ]
}

Notes: duration_seconds minimum is 0.5 (the API 400s below it — clamped here).
Onset is also checked: a file whose first sound starts later than 0.15s gets flagged
(late hits land off-beat); regenerate manually with a "sharp attack" prompt if flagged.
"""
import json
import os
import subprocess
import sys
import urllib.request

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
API = "https://api.elevenlabs.io/v1/sound-generation"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def api_key():
    """ELEVENLABS_API_KEY from the environment, else from a .env in cwd or any parent."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    d = os.getcwd()
    while True:
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ELEVENLABS_API_KEY="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            return v
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def gen(key, prompt, seconds, influence, out):
    req = urllib.request.Request(
        API,
        data=json.dumps({
            "text": prompt,
            "duration_seconds": max(float(seconds), 0.5),
            "prompt_influence": influence,
        }).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
        f.write(r.read())


def peak_db(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "/dev/null"],
                       capture_output=True, text=True).stderr
    line = [l for l in r.splitlines() if "max_volume" in l]
    if not line:
        return None
    return float(line[0].split(":")[1].replace("dB", "").strip())


def onset_s(path):
    """Seconds until the first sound. Only nonzero when the file OPENS with silence:
    parse silencedetect events in order; if the first silence starts at ~0, the onset
    is that silence's end. Sound-then-trailing-silence (the normal shape) returns 0."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-af", "silencedetect=n=-30dB:d=0.05", "-f", "null", "/dev/null"],
                       capture_output=True, text=True).stderr
    events = []  # (kind, t) in stream order
    for l in r.splitlines():
        if "silence_start:" in l:
            events.append(("start", float(l.split("silence_start:")[1].strip())))
        elif "silence_end:" in l:
            events.append(("end", float(l.split("silence_end:")[1].split("|")[0].strip())))
    if events and events[0][0] == "start" and events[0][1] < 0.05:
        for kind, t in events[1:]:
            if kind == "end":
                return t
    return 0.0


def duration_s(path):
    d = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True).stdout.strip()
    return round(float(d), 3)


def main():
    if len(sys.argv) != 3:
        die("usage: generate-sfx.py kit.json <outDir>")
    key = api_key() or die("ELEVENLABS_API_KEY not set — export it or put ELEVENLABS_API_KEY=… in a .env at the repo root")
    cfg = json.load(open(sys.argv[1]))
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    target = float(cfg.get("normalize_db", -3.0))
    min_peak = float(cfg.get("min_peak_db", -12.0))
    durs, flagged = {}, []

    for fx in cfg["effects"]:
        path = os.path.join(out_dir, f"{fx['name']}.mp3")
        if not os.path.exists(path):
            gen(key, fx["prompt"], fx["seconds"], 0.35, path)
            print(f"generated  {fx['name']}")
        # audit: near-silent generations are common — retry once, louder
        p = peak_db(path)
        if p is None or p < min_peak:
            print(f"DUD ({p} dB)  {fx['name']} — regenerating louder…")
            os.remove(path)
            gen(key, f"loud, punchy: {fx['prompt']}", fx["seconds"], 0.6, path)
            p = peak_db(path)
            if p is None or p < min_peak - 8:
                flagged.append((fx["name"], f"still very quiet after retry ({p} dB) — normalization will rescue it, but listen"))
        # normalize peak to target
        gain = target - p
        tmp = path + ".norm.mp3"
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", path, "-af", f"volume={gain:.1f}dB", "-b:a", "192k", tmp], check=True)
        os.replace(tmp, path)
        # onset check: late-starting hits land off-beat
        on = onset_s(path)
        if on and on > 0.15:
            flagged.append((fx["name"], f"first sound at ~{on:.2f}s — hit will land late; regenerate with 'sharp attack' or trim"))
        durs[fx["name"]] = duration_s(path)
        print(f"ok  {fx['name']:16s} peak → {peak_db(path):.1f} dB  ({durs[fx['name']]}s)")

    json.dump(durs, open(os.path.join(out_dir, "durations.json"), "w"), indent=1)
    print(f"\nwrote {out_dir}/durations.json ({len(durs)} effects)")
    if flagged:
        print("\nFLAGGED for manual attention:")
        for name, why in flagged:
            print(f"  - {name}: {why}")


if __name__ == "__main__":
    main()
