#!/usr/bin/env python3
"""map-words.py - accurate cut-timeline word map for a reel-recut base cut.

Why: a full-file whisper.cpp large-v3 pass smeared word onsets INTO the surrounding silence on this
footage ("ByteDance" placed 0.7 s inside a silencedetect span), and transcribing each 1-2 s keep span in
isolation was worse: whisper.cpp token offsets collapse to the segment start on short clips and it
hallucinates ("and many more"). What IS reliable here: (1) OpenAI whisper-1 verbose_json word times, which
run a consistent ~0.15 s LATE and never smear into silence, and (2) the silencedetect edges themselves,
which are the true onset of every phrase-initial word. So: take the cloud words, shift them by SHIFT,
assign each to the keep span that contains it, and snap the first word of every span to the span edge.

Inputs (in the project dir): cut-spec.qa-manifest.json (cut events, source time), cloud-words.json
(whisper-1 verbose_json with words[]), source.mp4 (for duration).
Outputs: words-cut.json, words-master.json, edl.json, v916-edl.json, source-words-accurate.json

usage: python3 map-words.py <project-dir> [--shift 0.15]
"""
import json, os, subprocess, sys
proj = sys.argv[1]
SHIFT = float(sys.argv[sys.argv.index("--shift") + 1]) if "--shift" in sys.argv else 0.15
man = json.load(open(os.path.join(proj, "cut-spec.qa-manifest.json")))
dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.join(proj, man["source"])]).decode().strip())
fps = man.get("expected", {}).get("fps", 30)
cuts = sorted([(e["src"]["start"], e["src"]["end"]) for e in man["events"] if e["kind"] == "cut"])
keeps, cur = [], 0.0
for a, b in cuts:
    if a > cur + 1e-6: keeps.append([cur, a])
    cur = max(cur, b)
if cur < dur - 1e-6: keeps.append([cur, dur])
windows, out_t = [], 0.0
for a, b in keeps:
    windows.append({"raw_start": round(a, 3), "raw_end": round(b, 3), "master_start": round(out_t, 3), "master_end": round(out_t + b - a, 3),
                    "src_in_f": round(a * fps), "src_out_f": round(b * fps), "master_in_f": round(out_t * fps), "master_out_f": round((out_t + b - a) * fps)})
    out_t += b - a
cloud = json.load(open(os.path.join(proj, "cloud-words.json")))["words"]
src = []
for w in cloud:
    s, e = w["start"] - SHIFT, w["end"] - SHIFT
    if s >= dur - 0.08: continue                      # hallucinated tail past the media end
    if e <= s: e = s + 0.05
    src.append({"text": w["word"], "start": max(0.0, s), "end": min(dur, e)})
# assign to keep spans by start time; a word starting inside a cut snaps to the NEXT keep span
def span_of(w):
    t, e = w["start"], w["end"]
    for i, (a, b) in enumerate(keeps):
        if a - 0.02 <= t < b: return i
    # inside a cut. Cloud onsets can sit early OR late by ~0.2 s, so a word whose END reaches the next
    # keep span is real and snaps forward to it; a word that ends well before any keep span is a
    # hallucination (the trailing "Seedance 2.5" past the media end) and is dropped.
    for i, (a, b) in enumerate(keeps):
        if t < a and b - a >= 0.1:
            return i if e >= a - 0.25 else None
    return None
groups = {}
for w in src:
    i = span_of(w)
    if i is not None: groups.setdefault(i, []).append(w)
out, fixed_src = [], []
for i, (a, b) in enumerate(keeps):
    ws = groups.get(i, []); prev = a
    for k, w in enumerate(ws):
        s, e = w["start"], w["end"]
        if k == 0: s = a + 0.02                        # phrase-initial word: the silence edge is the onset
        elif s < prev + 0.03: s = prev + 0.03          # keep word starts monotonic inside a span
        s = min(max(s, a), b - 0.02); e = min(max(e, s + 0.03), b); prev = s
        fixed_src.append({"text": w["text"], "start": round(s, 3), "end": round(e, 3)})
        ms = windows[i]["master_start"]
        out.append({"text": w["text"], "start": round(ms + s - a, 3), "end": round(ms + e - a, 3), "src": round(s, 3), "kept": True})
json.dump(out, open(os.path.join(proj, "words-cut.json"), "w"), indent=0)
json.dump([{k: w[k] for k in ("text", "start", "end")} for w in out], open(os.path.join(proj, "words-master.json"), "w"), indent=0)
json.dump(fixed_src, open(os.path.join(proj, "source-words-accurate.json"), "w"), indent=0)
json.dump({"keep": [[round(a, 3), round(b, 3)] for a, b in keeps], "source": man["source"], "duration_out": round(out_t, 3)}, open(os.path.join(proj, "edl.json"), "w"), indent=1)
json.dump({"fps": fps, "source": man["source"], "windows": windows}, open(os.path.join(proj, "v916-edl.json"), "w"), indent=1)
print(f"{os.path.basename(proj)}: {len(keeps)} keep spans, out {out_t:.3f}s, {len(out)} words (shift -{SHIFT}s, span heads snapped)")
print(" ".join(f"{w['text']}@{w['start']:.2f}" for w in out))
