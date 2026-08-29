#!/usr/bin/env python3
"""verify_cuts.py - per-cut seam validation: does applying this cut change the words?

For each cut, build two short clips from the SOURCE audio with identical context
(CTX seconds either side) — one uncut, one with the cut applied — transcribe both
with the same local whisper model, and diff the word sequences. Any word that
disappears or changes is a clipped phoneme, not an artifact of a full-file pass.

This is the control a full-file transcript cannot give you: on one paid
deliverable the full-file pass dropped an "of" that was actually present in the
audio, and it took an isolated slice to prove that "teams" really was damaged
by a cut. Never act on a full-file transcript alone.

dependencies:
  - ffmpeg on PATH (or FFMPEG env var)
  - whisper-cli (whisper.cpp) on PATH (or WHISPER_CLI env var)
  - a ggml whisper model; set WHISPER_MODEL to its path, e.g.
      WHISPER_MODEL=~/models/ggml-large-v3.bin python3 verify_cuts.py cuts.json

usage:
  python3 verify_cuts.py [cuts.json] [--src raw-audio.wav] [--annotated cuts-annotated.json]

cuts.json is [[start, end]] (what plan_cuts.py writes, and the same shape as the
spec's manual_cuts). If the annotated file exists, head/tail trims and whole-take
FLUB removals are skipped (a discarded take's first word is SUPPOSED to vanish).
Writes cuts-rejected.json (the cuts that change words) and _verify/transcripts.json.
"""
import argparse, json, os, re, shutil, subprocess, sys, difflib

ap = argparse.ArgumentParser()
ap.add_argument("cuts", nargs="?", default="cuts.json")
ap.add_argument("--src", default="raw-audio.wav")
ap.add_argument("--annotated", default=None, help="default: <cuts stem>-annotated.json if present")
args = ap.parse_args()

CTX = 1.8
TRIM = 2      # ignore this many tokens at each end — the window edge truncates words
              # ("automated" -> "automate") and that is not the seam
FF = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
WH = os.environ.get("WHISPER_CLI") or shutil.which("whisper-cli")
MODEL = os.path.expanduser(os.environ.get("WHISPER_MODEL", ""))
if not WH:
    sys.exit("whisper-cli not found — install whisper.cpp or set WHISPER_CLI")
if not MODEL or not os.path.exists(MODEL):
    sys.exit("set WHISPER_MODEL to a ggml model path (e.g. ggml-large-v3.bin)")
WORK = "_verify"; os.makedirs(WORK, exist_ok=True)

def say(path):
    r = subprocess.run([WH, "-m", MODEL, "-f", path, "--language", "en", "-nt", "-np"],
                       capture_output=True, text=True)
    return r.stdout.strip()

def words(t): return [w for w in re.sub(r"[^a-z0-9 ]", " ", t.lower()).split() if w]

cuts = json.load(open(args.cuts))
ann_path = args.annotated or (os.path.splitext(args.cuts)[0] + "-annotated.json")
ann = {}
if os.path.exists(ann_path):
    ann = {(c["start"], c["end"]): c["why"] for c in json.load(open(ann_path))}
cache = {}
bad = []
print(f"{'#':>3} {'cut':>16} {'len':>6}  verdict")
for i, (a, b) in enumerate(cuts, 1):
    why = ann.get((a, b), "?")
    if why.startswith("head") or why.startswith("tail") or why.startswith("FLUB"):
        print(f"{i:3d} {a:7.2f}-{b:6.2f} {b-a:6.3f}  skipped ({why.split(':')[0]})"); continue
    lo, hi = max(0, a - CTX), b + CTX
    un = f"{WORK}/{i}_uncut.wav"; cu = f"{WORK}/{i}_cut.wav"
    subprocess.run([FF, "-y", "-v", "error", "-ss", str(lo), "-to", str(hi), "-i", args.src, "-c", "copy", un])
    subprocess.run([FF, "-y", "-v", "error", "-i", args.src, "-af",
                    f"aselect='between(t,{lo},{a})+between(t,{b},{hi})',asetpts=N/SR/TB",
                    "-c:a", "pcm_s16le", cu])
    wu_all, wc_all = words(say(un)), words(say(cu))
    cache[str(i)] = {"uncut": " ".join(wu_all), "cut": " ".join(wc_all)}
    wu, wc = wu_all[TRIM:-TRIM], wc_all[TRIM:-TRIM]
    sm = difflib.SequenceMatcher(None, wu, wc)
    lost = [wu[i1:i2] for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ("delete", "replace")]
    lost = [w for grp in lost for w in grp]
    if lost:
        bad.append((i, a, b, why, lost, " ".join(wu), " ".join(wc)))
        print(f"{i:3d} {a:7.2f}-{b:6.2f} {b-a:6.3f}  CHANGES WORDS: {lost}")
    else:
        print(f"{i:3d} {a:7.2f}-{b:6.2f} {b-a:6.3f}  ok ({why})")
print(f"\n{len(bad)} cut(s) change words at the seam")
for i, a, b, why, lost, wu, wc in bad:
    print(f"\n  cut #{i} {a:.3f}-{b:.3f} ({why})  lost {lost}")
    print(f"    uncut: {wu}")
    print(f"    cut  : {wc}")
json.dump([[a, b] for i, a, b, *_ in bad], open("cuts-rejected.json", "w"), indent=1)
json.dump(cache, open(f"{WORK}/transcripts.json", "w"), indent=1)
