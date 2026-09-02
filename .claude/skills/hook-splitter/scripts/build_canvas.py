#!/usr/bin/env python3
"""Step 8 — the review gallery: every hook with its own comment box.

This is a GALLERY variant of video-review-canvas, not that skill's single-video page.
The `comments` collection carries a `hook` field, so a note binds to one video and
stamps that player's current frame.

Re-encodes each master into a lighter review copy (default 810x1440 CRF 24 — still
sharp enough to read prompt text in a screen recording, ~a third the bytes).

**Version stamping is per-hook, by content hash.** Only hooks whose master actually
changed get a new `hook-NN-<version>.mp4`; the rest keep their filename so the
browser cache stays valid and the re-publish stays small. Superseded files are
deleted — verify the old name 404s after publishing.

    python3 build_canvas.py [hooks.json]
"""
import hashlib, json, os, shutil, subprocess
from _cfg import load, w, FFMPEG, probe_dur

cfg = load()
VERSION = cfg.get("version", "v1")
VLABEL = cfg.get("version_label", VERSION.upper())
AUTHOR = cfg.get("author", "Reviewer")
R = cfg["review"]
os.makedirs(os.path.join(R, ".herenow"), exist_ok=True)
plans = json.load(open(cfg["_root"] + "/cuts.json"))

HERE = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(HERE, "..", "assets", "data.json"),
            os.path.join(R, ".herenow", "data.json"))

man_path = os.path.join(R, "_manifest.json")
man = json.load(open(man_path)) if os.path.exists(man_path) else {}
scale = cfg.get("review_scale", "810:1440")
crf = str(cfg.get("review_crf", 24))

def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()

def clock(s):
    m = int(s // 60)
    return f"{m}:{s-m*60:04.1f}" if m else f"{s:.1f}s"

hooks, total = [], 0.0
keep = set()
for p in plans:
    hid = p["id"]
    master = os.path.join(cfg["out"], f"hook-{hid:02d}.mp4")
    digest = md5(master)
    prev = man.get(str(hid))
    if prev and prev["md5"] == digest and os.path.exists(os.path.join(R, prev["file"])):
        fname = prev["file"]                      # unchanged: keep the cached name
    else:
        fname = f"hook-{hid:02d}-{VERSION}.mp4"
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", master,
                        "-c:v", "libx264", "-crf", crf, "-preset", "slow",
                        "-pix_fmt", "yuv420p", "-vf", f"scale={scale}",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                        os.path.join(R, fname)], check=True)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "0.4", "-i", master,
                        "-frames:v", "1", "-vf", "scale=405:-1,format=yuvj420p",
                        "-q:v", "6", os.path.join(R, f"p{hid:02d}.jpg")], check=True)
        print(f"  re-encoded hook {hid:02d} -> {fname}")
    man[str(hid)] = {"md5": digest, "file": fname}
    keep.add(fname)
    d = probe_dur(os.path.join(R, fname)); total += d
    hooks.append({"id": hid, "title": p["title"], "file": fname,
                  "poster": f"p{hid:02d}.jpg", "dur": clock(d),
                  "src": f"{int(p['source_start']//60)}:{p['source_start']%60:04.1f}",
                  "joins": p["joins"], "note": p["note"]})

for f in os.listdir(R):                            # drop superseded copies
    if f.startswith("hook-") and f.endswith(".mp4") and f not in keep:
        os.remove(os.path.join(R, f)); print(f"  removed stale {f}")
json.dump(man, open(man_path, "w"), indent=1)

removed = sum(p["source_span"] for p in plans) - sum(p["out_duration"] for p in plans)
src_total = cfg.get("source_label", "the rough cut")
facts = "".join([
    f"<div class='fact'><b>{len(hooks)}</b> hooks</div>",
    f"<div class='fact'>total <b>{int(total//60)}:{int(total%60):02d}</b> across the set</div>",
    f"<div class='fact'><b>{removed:.0f}s</b> of dead air &amp; flubs removed</div>",
    f"<div class='fact'><b>{sum(h['joins'] for h in hooks)}</b> cuts</div>",
    f"<div class='fact'><b>{sum(1 for h in hooks if h['note'])}</b> hooks had something cut</div>",
])

html = open(os.path.join(HERE, "..", "assets", "canvas-template.html")).read()
for k, v in {
    "__TITLE__": cfg.get("title", "Hook review"),
    "__EYEBROW__": cfg.get("eyebrow", "MR PAID SOCIAL · HOOK REVIEW"),
    "__H1__": cfg.get("headline", "Hooks, split and tightened"),
    "__VLABEL__": VLABEL,
    "__BLURB__": cfg.get("blurb", "Each hook is its own video, tightened so the only "
                                  "silence left is while a video is playing."),
    "__FACTS__": facts, "__SRC__": src_total,
    "__HOOKS__": json.dumps(hooks), "__VERSION__": VERSION, "__AUTHOR__": AUTHOR,
}.items():
    html = html.replace(k, v)
open(os.path.join(R, "index.html"), "w").write(html)

# Snapshot the cut this version was built from. His notes are timestamped against
# THIS cut, so the next round must map them back through this file, not through a
# cuts.json that has already moved on. Kept in work/ so it is not published.
shutil.copy(cfg["_root"] + "/cuts.json", w(cfg, f"cuts-{VERSION}.json"))

print(f"\nwrote {R}/index.html — {len(hooks)} hooks, {total:.0f}s, {removed:.0f}s removed")
slug = cfg.get("slug")
print("\npublish:\n  bash ~/.agents/skills/here-now/scripts/publish.sh "
      f"{R} {'--slug ' + slug + ' ' if slug else ''}"
      f"--title \"{cfg.get('title','Hook review')} — {VLABEL}\" --client claude-code")
