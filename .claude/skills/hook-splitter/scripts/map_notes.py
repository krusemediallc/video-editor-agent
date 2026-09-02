#!/usr/bin/env python3
"""Round 2+ — pull the canvas notes and map each one back to SOURCE time.

Every timestamp a reviewer leaves is in OUTPUT time. Before you can act on a note you
have to walk it back through that hook's kept segments. This prints, per note, the
source second it lands on and the words either side of it.

    python3 map_notes.py [hooks.json] <slug> [version]

Then, for each note, BEFORE cutting anything:
  1. slice that window out of the mic wav and transcribe it in ISOLATION
  2. look at the energy envelope for the real boundaries
  3. only then write a `kills` entry (or move the hook's start/end)

A note pinned at or within ~0.4s of a hook's END is almost always "cut the trailing
air", i.e. tail_pad — not a request to lose a word. Check the envelope: if the speaker's last
word is still sounding at the mark, the reviewer marked slightly early; end just after the word.
"""
import json, os, re, subprocess, sys
from _cfg import load, w

cfg = load()
args = [a for a in sys.argv[1:] if not a.endswith(".json")]
if not args: sys.exit("usage: map_notes.py [hooks.json] <slug> [version]")
slug = args[0]
version = args[1] if len(args) > 1 else cfg.get("version", "v1")

url = f"https://{slug}.here.now/.herenow/data/comments?limit=500"
data = json.loads(subprocess.run(["curl", "-sS", url], capture_output=True, text=True).stdout)
notes = [r for r in data.get("records", []) if r["data"].get("version") == version]
notes.sort(key=lambda r: (r["data"]["hook"], r["data"]["t"]))

# The reviewer's timestamps are in the OUTPUT time of the version they reviewed, so they must be
# walked back through the cut that BUILT that version. Using a cuts.json that has since
# moved on silently points every note at the wrong second.
snap = w(cfg, f"cuts-{version}.json")
cuts = snap if os.path.exists(snap) else cfg["_root"] + "/cuts.json"
if cuts != snap and "--force" not in sys.argv:
    raise SystemExit(
        f"no {snap}.\nHis timestamps are in the OUTPUT time of {version}; mapping them "
        f"through a cuts.json that has moved on puts every note at the wrong second "
        f"(measured: seconds off, landing on the wrong word).\nRestore that snapshot, or "
        f"re-run with --force if you are certain cuts.json is unchanged since {version}.")
plans = {p["id"]: p for p in json.load(open(cuts))}
W = [(x["start"], x["end"], x["word"]) for x in json.load(open(w(cfg, "words.json")))["words"]
     if x["end"] > x["start"]]

def out2src(hid, t):
    acc = 0.0
    for a, b in plans[hid]["segments"]:
        if t <= acc + (b - a) + 1e-9: return a + (t - acc)
        acc += b - a
    return plans[hid]["segments"][-1][1]

print(f"{len(notes)} note(s) on {version}\n")
for r in notes:
    d = r["data"]; hid, t = d["hook"], d["t"]
    if hid not in plans:
        print(f"HOOK {hid}: (not in cuts.json)  {d['text']}\n"); continue
    s = out2src(hid, t); p = plans[hid]
    endgap = p["out_duration"] - t
    tail = "   [at the END — probably tail air]" if endgap < 0.45 else ""
    print(f"HOOK {hid:>2}  out {t:6.2f}/{p['out_duration']:.2f}s -> SRC {s:8.2f}s{tail}")
    print(f"    \"{d['text']}\"")
    ctx = [x for x in W if x[1] > s - 4.0 and x[0] < s + 4.0]
    print(f"    context: {' '.join(x[2] for x in ctx)}")
    near = [x for x in ctx if abs(x[0] - s) < 1.2 or abs(x[1] - s) < 1.2]
    print(f"    at mark: {'  '.join(f'[{x[0]:.2f}-{x[1]:.2f} {x[2]}]' for x in near) or '(silence)'}\n")
