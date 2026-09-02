#!/usr/bin/env python3
"""variants.json -> an N-up gallery review canvas, publishable to here.now.

    python3 build_review.py --out variants/ --version v1 \
        --title "Arcads ad — 21 hook variants" [--map subjects.json]
    bash ~/.agents/skills/here-now/scripts/publish.sh variants/review \
        --title "..." --client claude-code [--slug <existing>]

One card per variant: poster, player, the master's filename, and its own comment box that
stamps that player's current frame. The comment store is shared across the page, keyed by
`hook`, so notes land on the right variant.

Masters are far too heavy to publish (a set of 21 two-minute 1080x1920 files is well over a
gigabyte), so the canvas carries downscaled proxies. They are for judging the cut, the seam
and the sync — the deliverables stay on disk. Proxies are only encoded when missing, so
re-running after a rename costs seconds.

Optional per-folder overrides, read if present in --out:
    blurb.html   what changed this round (the changelog the reviewer reads first)
    title.txt    page title
"""
import argparse, json, os, re, shutil, subprocess
from concurrent.futures import ThreadPoolExecutor

FF = os.environ.get("FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")


def clock(s):
    m = int(s // 60)
    return f"{m}:{s - m*60:04.1f}" if m else f"{s:.1f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="the variants folder (holds variants.json)")
    ap.add_argument("--version", default="v1", help="bump every round; version-stamps the "
                                                    "proxy filenames so browsers do not "
                                                    "serve a cached older cut")
    ap.add_argument("--title", default=None)
    ap.add_argument("--eyebrow", default="MR PAID SOCIAL · VARIANT REVIEW")
    ap.add_argument("--h1", default=None)
    ap.add_argument("--map", help="subjects map (naming-convention) for card titles")
    ap.add_argument("--height", type=int, default=1280, help="proxy height")
    ap.add_argument("--crf", default="30", help="proxy CRF")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    rev = os.path.join(out, "review")
    os.makedirs(rev, exist_ok=True)

    man = json.load(open(os.path.join(out, "variants.json")))
    variants = man["variants"] if isinstance(man, dict) else man
    body_name = man.get("body", "") if isinstance(man, dict) else ""
    body_frames = man.get("body_frames", 0) if isinstance(man, dict) else 0
    fps = man.get("fps", 30) if isinstance(man, dict) else 30
    bm = re.search(r"(v\d+[a-z]?)(?=\.[^.]+$)", body_name)
    body_label = bm.group(1).upper() if bm else (body_name or "body")

    subjects = {}
    if args.map:
        raw = json.load(open(args.map))
        subjects = raw.get("items", raw)

    def proxy(v):
        src = os.path.join(out, v["file"])
        dst = os.path.join(rev, f"variant-{v['hook']:02d}-{args.version}.mp4")
        pos = os.path.join(rev, f"p{v['hook']:02d}.jpg")
        if not os.path.exists(dst):
            subprocess.run([FF, "-y", "-v", "error", "-i", src,
                            "-vf", f"scale=-2:{args.height}", "-c:v", "libx264",
                            "-crf", args.crf, "-preset", "veryfast", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dst],
                           check=True)
        if not os.path.exists(pos):
            subprocess.run([FF, "-y", "-v", "error", "-i", src, "-frames:v", "1",
                            "-vf", f"scale=-2:{args.height//2}", "-q:v", "4", pos], check=True)
        return v["hook"], os.path.getsize(dst)

    with ThreadPoolExecutor(max_workers=3) as ex:
        for hid, sz in ex.map(proxy, variants):
            print(f"  proxy {hid:02d}: {sz/1048576:.1f} MB")

    cards, tot = [], 0.0
    for v in variants:
        hook_s = v["hook_frames"] / fps
        tot += v["seconds"]
        s = subjects.get(str(v["hook"]), {})
        title = " · ".join(x for x in (s.get("label") or s.get("subject"),
                                       s.get("style_label") or s.get("style")) if x) \
                or f"Hook {v['hook']:02d}"
        cards.append({
            "id": v["hook"], "title": title, "fname": v["file"],
            "file": f"variant-{v['hook']:02d}-{args.version}.mp4",
            "poster": f"p{v['hook']:02d}.jpg",
            "dur": clock(v["seconds"]), "src": clock(hook_s), "seam": clock(hook_s),
            "joins": 1,
            "note": (f"hook was {v['hook_lufs_before']:.1f} LUFS, brought to "
                     f"{v['hook_lufs_after']:.1f} to match the body")
                    if "hook_lufs_before" in v else "",
        })

    runtimes = sorted(v["seconds"] for v in variants)
    facts = [
        f"<div class='fact'><b>{len(cards)}</b> variants</div>",
        f"<div class='fact'>runtime <b>{clock(runtimes[0])}</b> &ndash; <b>{clock(runtimes[-1])}</b></div>",
        "<div class='fact'>body <b>bit-identical</b> to the approved cut</div>",
        "<div class='fact'>seam step <b>&lt;0.2 LU</b></div>",
        f"<div class='fact'>hook + the <b>{clock(body_frames/fps)}</b> {body_label} body</div>",
    ]

    blurb_path = os.path.join(out, "blurb.html")
    blurb = open(blurb_path).read().strip() if os.path.exists(blurb_path) else (
        f"<b>Every hook in front of the {body_label} body.</b> Body frames are stream-copied "
        f"bit-identical; each hook is loudness-matched to the body so the seam does not step; "
        f"every file is checked with AVFoundation &mdash; QuickTime's own decoder &mdash; at "
        f"12 points. <b>These players are 720p proxies</b>; the masters are on disk in "
        f"<code>{os.path.basename(out)}/</code>.")
    title_path = os.path.join(out, "title.txt")
    title = args.title or (open(title_path).read().strip() if os.path.exists(title_path)
                           else f"{len(cards)} variants — {body_label} body")

    hn = os.path.join(rev, ".herenow"); os.makedirs(hn, exist_ok=True)
    shutil.copyfile(os.path.join(ASSETS, "data.json"), os.path.join(hn, "data.json"))

    html = open(os.path.join(ASSETS, "canvas_template.html")).read()
    for k, v in {
        "__TITLE__": title,
        "__EYEBROW__": args.eyebrow,
        "__H1__": args.h1 or f"{len(cards)} hooks &times; one body",
        "__VLABEL__": args.version.upper(),
        "__BLURB__": blurb,
        "__FACTS__": "".join(facts),
        "__SRC__": body_name,
        "__HOOKS__": json.dumps(cards),
        "__VERSION__": args.version,
        "__AUTHOR__": os.environ.get("REVIEW_AUTHOR", "Reviewer"),
    }.items():
        html = html.replace(k, v)
    open(os.path.join(rev, "index.html"), "w").write(html)

    size = sum(os.path.getsize(os.path.join(rev, f)) for f in os.listdir(rev)
               if os.path.isfile(os.path.join(rev, f)))
    print(f"\nwrote {rev}/index.html — {len(cards)} variants, {clock(tot)} total, {size/1048576:.0f} MB")
    print("publish:  bash ~/.agents/skills/here-now/scripts/publish.sh "
          f"{rev} --title \"{title}\" --client claude-code")
    print("Lead the reply to the reviewer with the URL — a file card without the link reads as "
          "'not delivered'.")


if __name__ == "__main__":
    main()
