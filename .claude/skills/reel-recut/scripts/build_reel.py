#!/usr/bin/env python3
"""
build_reel.py - turn an "edit spec" (JSON) into a finished, styled short-form reel.

One deterministic pass:
  1. render full-frame transparent PNGs (title banner, karaoke captions, callouts)
  2. (optional) silence-cut the talking-head pauses for the tight "talking over
     myself" feel, then remap every caption/callout onto the shortened timeline
  3. composite all graphics into ONE transparent overlay video (qtrle/argb)
  4. final ffmpeg: select/aselect cut (if any) -> overlay graphics -> H.264

ALL visual styling (accent color, font, weights, sizes, positions) comes from the
spec's optional "style" block. The defaults below are ONE example brand's values
(purple #8030F8 boxes + Montserrat) so the script runs out of the box — replace
them with your own brand via "style" in the spec. See references/spec.md.

A spec with no banner/captions/callouts is a legal "raw cut" spec: the overlay
pass is skipped entirely and the render is just the cut. Set "fps": "source" to
keep the source frame rate (e.g. 60fps footage handed to a client's editor).

Why this shape: some ffmpeg builds (e.g. slim Homebrew builds) ship with NO
libass and NO libfreetype, so the `subtitles` and `drawtext` filters do not
exist there. All text therefore goes through PIL -> PNG -> overlay, which works
on ANY ffmpeg build. And feeding ~35 looped PNG inputs into one libx264 render
can OOM a 16 GB machine (one such render ran ~55 min before being killed), so
the graphics are pre-composed into a single transparent overlay video and the
final render is just 2 inputs.

If an agent sandbox kills ffmpeg (SIGURG / odd exit codes), re-run with the
sandbox disabled.

Binaries: ffmpeg/ffprobe are found on PATH; override with the FFMPEG / FFPROBE
environment variables.

Usage:  python3 build_reel.py spec.json [--qa-manifest-only]
See ../assets/spec.example.json for a complete example.
"""
import json, os, sys, subprocess, re, shutil, urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"
W, H, FPS = 1080, 1920, 30

# ---------------------------------------------------------------------------
# Style. These defaults are an EXAMPLE brand (purple boxes, Montserrat, thick
# black caption stroke). Every key can be overridden per-spec via "style": {}.
# font_url must point at a TTF; a Google Fonts *variable* TTF lets the named
# weights (Black / ExtraBold / ...) work — on a static font the weight request
# silently no-ops and you get whatever weight the file is.
# ---------------------------------------------------------------------------
DEFAULT_STYLE = {
    "accent_color":   "#8030F8",   # banner + callout box fill
    "text_color":     "#FFFFFF",   # all text
    "stroke_color":   "#000000",   # caption outline color
    "font_url": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "banner_weight":  "Black",     # variable-font named instance for the banner
    "caption_weight": "ExtraBold", # ... for captions and callout text
    "banner_size":    76,          # base px; auto-shrinks until lines fit
    "caption_size":   64,
    "callout_size":   66,          # a callout's own "size" field overrides this
    "caption_stroke": 11,          # caption outline width, px
    "caption_cy":     1560,        # caption block vertical center (bottom third)
}

def hex_rgba(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)

STYLE = dict(DEFAULT_STYLE)
ACCENT = hex_rgba(STYLE["accent_color"])
TEXT   = hex_rgba(STYLE["text_color"])
STROKE = hex_rgba(STYLE["stroke_color"])


def ensure_font(path):
    if os.path.exists(path):
        return path
    print(f"fetching font -> {path}")
    urllib.request.urlretrieve(STYLE["font_url"], path)
    return path

def font(path, size, weight):
    f = ImageFont.truetype(path, size)
    try: f.set_variation_by_name(weight)
    except Exception: pass
    return f


def line_w(d, t, f):
    b = d.textbbox((0, 0), t, font=f); return b[2] - b[0]

def wrap(d, text, f, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if line_w(d, t, f) <= maxw or not cur: cur = t
        else: out.append(cur); cur = w
    if cur: out.append(cur)
    return out

def fit_wrap(d, fp, text, base, minsz, maxw, max_lines, weight):
    """Largest font (<=base) that wraps text into <= max_lines within maxw."""
    sz = base
    while sz >= minsz:
        f = font(fp, sz, weight)
        ls = wrap(d, text, f, maxw)
        if len(ls) <= max_lines: return f, ls
        sz -= 2
    f = font(fp, minsz, weight); return f, wrap(d, text, f, maxw)

def fit_fixed(d, fp, lines, base, minsz, maxw, weight):
    """Largest font so each pre-broken line fits maxw."""
    sz = base
    while sz > minsz:
        f = font(fp, sz, weight)
        if max(line_w(d, l, f) for l in lines) <= maxw: return f
        sz -= 2
    return font(fp, minsz, weight)

def block_metrics(d, lines, f, lsp):
    asc, desc = f.getmetrics(); lh = asc + desc
    return max(line_w(d, l, f) for l in lines), lh * len(lines) + lsp * (len(lines) - 1), lh

def draw_block(d, lines, f, cx, top, lsp, fill, stroke=0):
    asc, desc = f.getmetrics(); lh = asc + desc; y = top
    for l in lines:
        d.text((cx - line_w(d, l, f) / 2, y), l, font=f, fill=fill,
                stroke_width=stroke, stroke_fill=STROKE)
        y += lh + lsp

def rounded_box(lines, f, cy, padx=34, pady=24, radius=22, lsp=6, shadow=True):
    """Full-frame transparent layer: accent rounded box hugging centered text."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    wmax, htot, lh = block_metrics(d, lines, f, lsp)
    bw, bh = wmax + 2 * padx, htot + 2 * pady
    bx0, by0, bx1, by1 = W / 2 - bw / 2, cy - bh / 2, W / 2 + bw / 2, cy + bh / 2
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([bx0, by0 + 10, bx1, by1 + 10], radius=radius, fill=(0, 0, 0, 120))
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(12))); d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=radius, fill=ACCENT)
    draw_block(d, lines, f, W / 2, by0 + pady, lsp, TEXT)
    return img

def caption_layer(fp, text, cy=None):
    """Karaoke caption: bold text with thick stroke + soft shadow, bottom third."""
    cy = cy if cy is not None else STYLE["caption_cy"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f, lines = fit_wrap(d, fp, text, STYLE["caption_size"], 50, W - 100, 2, STYLE["caption_weight"])
    _, htot, _ = block_metrics(d, lines, f, 8); top = cy - htot / 2
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_block(ImageDraw.Draw(sh), lines, f, W / 2, top, 8, (0, 0, 0, 200))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(8))); d = ImageDraw.Draw(img)
    draw_block(d, lines, f, W / 2, top, 8, TEXT, stroke=STYLE["caption_stroke"])
    return img


def probe_duration(path):
    out = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]).decode()
    return float(out.strip())

def probe_fps(path):
    out = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of",
        "default=noprint_wrappers=1:nokey=1", path]).decode().strip()
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def detect_pauses(path, noise_db, min_pause):
    p = subprocess.run([FFMPEG, "-nostdin", "-hide_banner", "-i", path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_pause}", "-f", "null", "-"],
        stderr=subprocess.PIPE).stderr.decode()
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", p)]
    ends   = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", p)]
    return list(zip(starts, ends))


def load_words(path):
    """Load word timings from whisper.cpp / OpenAI verbose / flat-array JSON."""
    data = json.load(open(path))
    words = []
    if isinstance(data, list):                      # flat [{text|word,start,end}]
        for w in data:
            t = w.get("text") or w.get("word")
            if t is not None and "start" in w and "end" in w:
                words.append({"text": t.strip(), "start": float(w["start"]), "end": float(w["end"])})
    elif isinstance(data, dict):
        if isinstance(data.get("words"), list):     # OpenAI verbose_json word granularity
            for w in data["words"]:
                words.append({"text": (w.get("word") or "").strip(),
                              "start": float(w["start"]), "end": float(w["end"])})
        elif isinstance(data.get("transcription"), list):   # whisper.cpp full output (-ojf)
            for seg in data["transcription"]:
                for tok in seg.get("tokens", []):
                    t = (tok.get("text") or "").strip()
                    off = tok.get("offsets") or {}
                    if t and not t.startswith("[_") and "from" in off:
                        words.append({"text": t, "start": off["from"] / 1000.0,
                                      "end": off["to"] / 1000.0})
    return words


def dump_qa_manifest(spec_path, spec, src, out, dur, new_dur, keep, new_t, captions, callouts):
    """Write a normalized edit manifest next to the spec.

    Emitted from edit INTENT (this build's own computed timeline), which is the
    provenance any QA pass needs: every cut with source + output times and its
    origin, every caption/callout with remapped windows, and (if the spec names
    a "words" file) the source word timings mapped onto the output timeline.
    Feed it to whatever seam-verification tooling you have, or drive manual
    checks from it (see references/workflow.md step 5b).
    Event ids are stable: cuts keyed by removed source-time (survives
    re-renders), captions/callouts by spec index.
    """
    events = []
    manual = [tuple(m) for m in spec.get("manual_cuts", [])]
    def origin_of(rs, re_):
        # A silence-derived cut removes MEASURED silence — it cannot clip audible
        # speech, so word-overlap flags there are usually transcript-timing overshoot.
        for ms, me in manual:
            if abs(ms - rs) < 0.15 or abs(me - re_) < 0.15 or (rs >= ms - 0.05 and re_ <= me + 0.05):
                return "manual"
        return "silence"
    def cut_event(out_t, rs, re_):
        events.append({
            "id": f"cut:src{rs:.1f}", "kind": "cut", "dialogueCut": True,
            "out": {"start": round(out_t, 3)},
            "src": {"start": round(rs, 3), "end": round(re_, 3)},
            "meta": {"origin": origin_of(rs, re_)},
        })
    if keep and keep[0][0] > 0.02:                  # head trim
        cut_event(0.0, 0.0, keep[0][0])
    acc = 0.0
    for i, (s, e) in enumerate(keep):
        acc += e - s
        nxt = keep[i + 1][0] if i + 1 < len(keep) else None
        if nxt is not None:
            cut_event(acc, e, nxt)
    if keep and dur - keep[-1][1] > 0.02:           # tail trim
        cut_event(new_dur, keep[-1][1], dur)
    for i, c in enumerate(captions):
        s, e = new_t(c["start"]), new_t(c["end"])
        if e - s > 0.05:
            events.append({"id": f"caption:{i}", "kind": "caption", "text": c["text"],
                           "out": {"start": round(s, 3), "end": round(e, 3)},
                           "src": {"start": c["start"], "end": c["end"]}})
    for i, c in enumerate(callouts):
        s, e = new_t(c["start"]), new_t(c["end"])
        events.append({"id": f"callout:{i}", "kind": "callout", "text": c["text"],
                       "out": {"start": round(s, 3), "end": round(e, 3)},
                       "src": {"start": c["start"], "end": c["end"]}})

    manifest = {
        "version": 1, "lane": "reel-recut",
        "video": os.path.relpath(out, os.path.dirname(os.path.abspath(spec_path))),
        "source": os.path.relpath(src, os.path.dirname(os.path.abspath(spec_path))),
        "expectedDuration": round(new_dur, 3),
        "expected": {"width": W, "height": H, "fps": FPS},
        "events": events,
        "intentional": spec.get("qa_intentional", {}),
    }

    words_file = spec.get("words")
    if words_file:
        wf = words_file if os.path.isabs(words_file) else os.path.join(
            os.path.dirname(os.path.abspath(spec_path)), words_file)
        if os.path.exists(wf):
            src_words = load_words(wf)
            mapped = []
            for w in src_words:
                inside = any(w["start"] >= s - 1e-3 and w["end"] <= e + 1e-3 for s, e in keep)
                if inside:
                    mapped.append({"text": w["text"],
                                   "start": round(new_t(w["start"]), 3),
                                   "end": round(new_t(w["end"]), 3)})
            manifest["words"] = mapped
            manifest["sourceWords"] = src_words

    stem = os.path.splitext(os.path.basename(spec_path))[0]
    mpath = os.path.join(os.path.dirname(os.path.abspath(spec_path)), f"{stem}.qa-manifest.json")
    json.dump(manifest, open(mpath, "w"), indent=1)
    print("qa-manifest:", mpath)


def build(spec_path, manifest_only=False):
    spec = json.load(open(spec_path))
    base = os.path.dirname(os.path.abspath(spec_path))
    def rel(p): return p if os.path.isabs(p) else os.path.join(base, p)

    global STYLE, ACCENT, TEXT, STROKE, W, H, FPS
    STYLE = {**DEFAULT_STYLE, **spec.get("style", {})}
    ACCENT = hex_rgba(STYLE["accent_color"])
    TEXT   = hex_rgba(STYLE["text_color"])
    STROKE = hex_rgba(STYLE["stroke_color"])
    W = int(spec.get("width", 1080)); H = int(spec.get("height", 1920))

    src = rel(spec["source"]); out = rel(spec["output"])
    work = rel(spec.get("work_dir", "_reel_work")); os.makedirs(work, exist_ok=True)
    dur = spec.get("duration") or probe_duration(src)

    fps_spec = spec.get("fps", 30)
    FPS = probe_fps(src) if fps_spec == "source" else float(fps_spec)

    captions = spec.get("captions", [])
    callouts = spec.get("callouts", [])
    banner_lines = spec.get("banner") or []
    # A spec with no graphics at all is a plain cut: skip the whole overlay pass.
    has_gfx = bool(banner_lines or captions or callouts)
    fp = None if (manifest_only or not has_gfx) else ensure_font(
        rel(spec.get("font", os.path.join(work, "font.ttf"))))
    banner = None
    if not manifest_only and has_gfx:
        d0 = ImageDraw.Draw(Image.new("RGBA", (W, H)))
        if banner_lines:
            banner_f = fit_fixed(d0, fp, banner_lines, STYLE["banner_size"], 50,
                                 W - 220, STYLE["banner_weight"])
            banner = rounded_box([l.upper() for l in banner_lines], banner_f,
                                 cy=spec.get("banner_cy", 320))
        cap_layers = {i: caption_layer(fp, c["text"]) for i, c in enumerate(captions)}
        callout_layers = []
        for c in callouts:
            f2, lines = fit_wrap(d0, fp, c["text"], c.get("size", STYLE["callout_size"]),
                                 46, W - 200, 3, STYLE["caption_weight"])
            callout_layers.append(rounded_box(lines, f2, cy=c.get("cy", 620)))

    sc = spec.get("silence_cut", {})
    cuts = [tuple(m) for m in spec.get("manual_cuts", [])]
    if sc.get("enabled"):
        edge = sc.get("edge", 0.035); minp = sc.get("min_pause", 0.13)
        for a, b in detect_pauses(src, sc.get("noise_db", -30), minp):
            if b - a >= minp:
                ca, cb = a + edge, b - edge
                if cb > ca: cuts.append((ca, cb))
    cuts.sort()
    keep, t = [], 0.0
    for ca, cb in cuts:
        if ca > t: keep.append((t, ca))
        t = max(t, cb)
    if t < dur: keep.append((t, dur))
    keep = [(round(s, 3), round(e, 3)) for s, e in keep if e - s > 0.02]
    if not keep: keep = [(0.0, round(dur, 3))]
    new_dur = sum(e - s for s, e in keep)

    def new_t(x):
        acc = 0.0
        for s, e in keep:
            if x >= e: acc += e - s
            elif x > s: acc += x - s; break
            else: break
        return acc

    dump_qa_manifest(spec_path, spec, src, out, dur, new_dur, keep, new_t, captions, callouts)
    if manifest_only:
        print(f"orig {dur:.2f}s -> new {new_dur:.2f}s | cuts={len(cuts)} keep={len(keep)} (manifest only)")
        return

    suppress = set(); cwins = []; cap_win = []
    if not has_gfx:
        cap_layers = {}; callout_layers = []
    for c, layer in zip(callouts, callout_layers):
        cwins.append((new_t(c["start"]), new_t(c["end"]), layer))
        suppress |= set(c.get("suppress_captions", []))
    cap_win = [(new_t(c["start"]), new_t(c["end"]), i)
               for i, c in enumerate(captions)
               if i not in suppress and new_t(c["end"]) - new_t(c["start"]) > 0.05]

    if has_gfx:
        overlay = os.path.join(work, "overlay.mov")
        empty = Image.new("RGBA", (W, H), (0, 0, 0, 0)); N = int(new_dur * FPS) + 2
        proc = subprocess.Popen([FFMPEG, "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "qtrle", "-pix_fmt", "argb", overlay],
            stdin=subprocess.PIPE)
        def cap_at(tn):
            for s, e, i in cap_win:
                if s <= tn < e: return i
            return None
        for fr_i in range(N):
            tn = fr_i / FPS
            fr = Image.alpha_composite(empty, banner) if banner is not None else empty.copy()
            ci = cap_at(tn)
            if ci is not None: fr = Image.alpha_composite(fr, cap_layers[ci])
            for s, e, layer in cwins:
                if s <= tn < e: fr = Image.alpha_composite(fr, layer)
            proc.stdin.write(fr.tobytes())
        proc.stdin.close(); proc.wait()

    cutting = len(keep) > 1 or keep[0] != (0.0, round(dur, 3))
    gfx_in = "[1:v]overlay=0:0" if has_gfx else "null"
    if cutting:
        expr = "+".join(f"between(t,{s},{e})" for s, e in keep)
        filt = (f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[vc];"
                f"[0:a]aselect='{expr}',asetpts=N/SR/TB[ac];[vc]{gfx_in}[vout]")
        amap, acodec = "[ac]", ["-c:a", "aac", "-b:a", "192k"]
    else:
        filt = f"[0:v]{gfx_in}[vout]" if has_gfx else "[0:v]null[vout]"
        amap, acodec = "0:a", ["-c:a", "copy"]
    filt_path = os.path.join(work, "filt.txt"); open(filt_path, "w").write(filt)
    inputs = ["-i", src] + (["-i", overlay] if has_gfx else [])
    cmd = [FFMPEG, "-nostdin", "-y", *inputs,
           "-filter_complex_script", filt_path, "-map", "[vout]", "-map", amap,
           "-c:v", "libx264", "-crf", str(spec.get("crf", 18)), "-preset", spec.get("preset", "veryfast"),
           "-pix_fmt", "yuv420p", "-r", str(FPS), *acodec, "-movflags", "+faststart", out]
    print(f"orig {dur:.2f}s -> new {new_dur:.2f}s | cuts={len(cuts)} keep={len(keep)} "
          f"fps={FPS:g} captions={len(cap_win)} callouts={len(cwins)}")
    rc = subprocess.call(cmd)
    if rc == 0: print("OK:", out)
    sys.exit(rc)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    if len(args) != 1:
        print("usage: python3 build_reel.py spec.json [--qa-manifest-only]"); sys.exit(2)
    build(args[0], manifest_only="--qa-manifest-only" in flags)
