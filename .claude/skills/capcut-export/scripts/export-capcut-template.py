#!/usr/bin/env python3
"""Export a finished layered edit into a CapCut desktop draft with every element editable.

TEMPLATE — edit the CONFIG block below for your project, then run inside a venv
that has pyJianYingDraft installed:

    python3 -m venv .venv && .venv/bin/pip install pyJianYingDraft
    .venv/bin/python scripts/export-capcut-template.py                # build draft in staging
    .venv/bin/python scripts/export-capcut-template.py --patch-native ~/Movies/CapCut/"User Data"/Projects/com.lveditor.draft/<a-native-draft>
    .venv/bin/python scripts/export-capcut-template.py --install --register   # QUIT CAPCUT FIRST

Track layout produced (bottom -> top):
  footage   base video, split at zoom boundaries, per-segment scale
  overlay   positioned second video (e.g. head-card band during split-screen beats)
  cards     per-card opaque clips (ffmpeg-split from a cards-only render pass)
  fx        one alpha overlay (true-alpha ProRes .mov, yuva444p)
  image     static PNG overlays (e.g. vignette) as image segments
  captions  native TextSegments (editable text in CapCut)
  text-N    extra texts (CTAs) on greedy non-overlap tracks
  vo/music/sfx-N   audio tracks; SFX packed greedily so none overlap on a track

STATUS / HONESTY: pyJianYingDraft writes JianYing-era drafts (draft_content.json,
new_version "110.0.0"). Current CapCut desktop loads draft_info.json with
new_version ~"181.0.0" plus 8 extra top-level keys. Without the --patch-native
step CapCut showed "Couldn't use project: unusual path". The patch (clone those
keys from a native draft on the target machine, bump versions, write BOTH
filenames) is a documented work-in-progress and has NOT been field-verified end
to end. If CapCut still refuses the draft, diff it against a native draft made
by that exact CapCut install (see SKILL.md, Debugging).
"""
import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

# ════════════════════════════════════════════════════════════════════════════
# CONFIG — edit everything in this block for your project
# ════════════════════════════════════════════════════════════════════════════

# Project folder that holds the source media (renders, footage, vo, sfx).
# Default: the directory you run this script from; override with env var.
PROJECT_DIR = os.environ.get("CAPCUT_PROJECT_DIR", os.getcwd())

# Media MUST be staged onto the LOCAL disk. External-volume paths can trip
# macOS permission (TCC) prompts inside CapCut and break media resolution.
MEDIA_DIR = os.path.expanduser(os.environ.get("CAPCUT_MEDIA_DIR", "~/Movies/capcut-export-media"))
STAGING_DIR = os.path.expanduser(os.environ.get("CAPCUT_STAGING_DIR", "~/Movies/capcut-draft-staging"))
PROJECTS_DIR = os.path.expanduser(
    os.environ.get("CAPCUT_PROJECTS_DIR", "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"))

DRAFT_NAME = "my-edit-capcut-v1"
DUR = 28.7667                      # total timeline duration, seconds
WIDTH, HEIGHT = 1080, 1920         # canvas size

# ── Source media (paths relative to PROJECT_DIR) ────────────────────────────
FOOTAGE_MAIN = "public/footage-vert.mp4"      # base talking-head / footage pass
OVERLAY_VIDEO = "public/footage-band.mp4"     # positioned second video; None to skip
VO = "public/vo.mp3"                          # voiceover; None to skip
MUSIC = "music/bed.mp3"                       # music bed; None to skip
MUSIC_VOLUME = 0.18
FX_OVERLAY = "capcut-export/fx-pass.mov"      # true-alpha ProRes (yuva444p); None to skip
CANVAS_PASS = "capcut-export/canvas-pass.mp4" # cards-only render of the composition; None to skip
TRANSCRIPT = "transcript.json"                # word list: [{"text","start","end"},...]; None to skip
SFX_DIR = "sfx"                               # folder of <name>.mp3 hit files

# ── Base footage: split at zoom boundaries, per-segment scale ───────────────
# (start, end, scale). scale 1.0 = no punch-in.
ZOOM_SEGMENTS = [
    (0.0, 20.1, 1.0),
    (20.1, 21.12, 1.06),
    (21.12, 24.97, 1.0),
    (24.97, 26.0667, 1.13),
    (26.0667, DUR, 1.2),
]

# ── Overlay video windows + placement ───────────────────────────────────────
# ClipSettings: scale_x/scale_y shrink the clip; transform_y is NDC-ish,
# NEGATIVE = move DOWN, positive = up. transform_y=-0.5625 sits a 0.9556-scaled
# band in the lower half of a 9:16 canvas.
OVERLAY_WINDOWS = [(0.0, 1.0), (7.56, 10.65), (13.05, 17.5), (21.12, 23.0333)]
OVERLAY_CLIP = dict(scale_x=0.9556, scale_y=0.9556, transform_y=-0.5625)

# ── Cards: boundaries inside CANVAS_PASS to split into opaque clips ─────────
# (name, start, end). Gaps between cards are allowed (footage shows through).
CARDS = [
    ("c01-logo-hook", 0.0, 1.0),
    ("c02-feature-tiles", 1.0, 2.45),
    # ... one row per graphic card in the edit ...
]

# ── Static PNG overlays (e.g. vignette) shown during specific windows ───────
# (path relative to PROJECT_DIR or MEDIA_DIR, [(start, end), ...])
IMAGE_OVERLAYS = [
    # ("vignette.png", [(20.1, 21.12), (24.97, DUR)]),
]
GENERATE_VIGNETTE = False   # True: procedurally write MEDIA_DIR/vignette.png (needs PIL)
VIGNETTE_WINDOWS = []       # [(start, end), ...] windows for the generated vignette

# ── SFX hits: (time, name-of-mp3-in-SFX_DIR, volume 0..1) ───────────────────
HITS = [
    (0.05, "sub-drop", 0.55),
    (1.08, "pop-click", 0.32),
    # ... one row per sound-design hit ...
]
SFX_GAIN = 1.95            # master multiplier applied to each hit volume
SFX_MAX = 0.8              # ceiling after gain

# ── Captions ────────────────────────────────────────────────────────────────
CAPTION_MAX_WORDS = 2      # words per caption chunk
CAPTION_GAP = 0.42         # a silence longer than this starts a new chunk
CAPTION_MIN_DUR = 0.2
CAPTION_CUTOFF = None      # e.g. 26.0667 to stop captions when a CTA owns the screen

# Style windows: first matching window wins; fields override CAPTION_DEFAULT.
# transform_y: negative = lower on screen. size is CapCut text size.
# color is (r, g, b) floats 0..1. upper=True renders the chunk uppercase.
CAPTION_DEFAULT = dict(size=8.0, bold=True, italic=False, upper=False,
                       color=(1.0, 1.0, 1.0), border=True, transform_y=-0.64)
CAPTION_WINDOWS = [
    # (start, end, {overrides})
    # (13.05, 17.5, dict(color=(0.09, 0.094, 0.11), border=False, transform_y=-0.046)),
    # (23.0333, 24.97, dict(size=11.0, upper=True, italic=True)),
]

# ── Extra texts (CTAs, keywords). Overlapping ones are auto-split onto
#    separate tracks — a text track CANNOT hold overlapping segments. ────────
EXTRA_TEXTS = [
    # (text, start, dur, {style overrides incl. transform_y/border/color/size})
    # ("comment “START”", 26.1667, DUR - 26.1667,
    #  dict(size=9.0, italic=True, transform_y=-0.306)),
]

# ════════════════════════════════════════════════════════════════════════════
# END CONFIG
# ════════════════════════════════════════════════════════════════════════════

FFMPEG = os.environ.get("FFMPEG", shutil.which("ffmpeg") or "ffmpeg")

try:
    import pyJianYingDraft as jydraft
    from pyJianYingDraft import trange, TrackType, VideoMaterial, AudioMaterial
    from pyJianYingDraft.track import TrackSpec
except ImportError:
    sys.exit("pyJianYingDraft not installed. Run inside a venv:\n"
             "  python3 -m venv .venv && .venv/bin/pip install pyJianYingDraft")


def src(rel):
    return rel if os.path.isabs(rel) else os.path.join(PROJECT_DIR, rel)


def stage(rel, dst_rel=None):
    """Copy a project file onto the local disk (MEDIA_DIR). Returns local path."""
    dst = os.path.join(MEDIA_DIR, dst_rel or os.path.basename(rel))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copyfile(src(rel), dst)
    return dst


def split_cards():
    """ffmpeg-split the cards-only render pass into one opaque clip per card."""
    out_files = []
    canvas = src(CANVAS_PASS)
    for name, s, e in CARDS:
        out = os.path.join(MEDIA_DIR, "cards", f"{name}.mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        out_files.append((name, s, e, out))
        if os.path.exists(out):
            continue
        r = subprocess.run(
            [FFMPEG, "-y", "-ss", f"{s:.4f}", "-i", canvas, "-t", f"{e - s:.4f}",
             "-c:v", "libx264", "-crf", "16", "-preset", "fast",
             "-g", "15", "-pix_fmt", "yuv420p", "-an", out],
            capture_output=True)
        if r.returncode:
            sys.exit(f"card split failed: {out}\n{r.stderr[-400:].decode(errors='replace')}")
    return out_files


def maybe_vignette():
    """Optional procedural vignette PNG (transparent middle, dark top/bottom)."""
    if not GENERATE_VIGNETTE:
        return None
    out = os.path.join(MEDIA_DIR, "vignette.png")
    if os.path.exists(out):
        return out
    try:
        from PIL import Image
    except ImportError:
        print("PIL not installed — vignette skipped"); return None
    im = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    px = im.load()
    for y in range(HEIGHT):
        f = y / float(HEIGHT)
        if f < 0.20:
            a = int(86 * (1 - f / 0.20))
        elif f < 0.58:
            a = 0
        else:
            a = int(208 * ((f - 0.58) / 0.42) ** 1.5)
        for x in range(WIDTH):
            px[x, y] = (0, 0, 0, min(a, 208))
    im.save(out)
    return out


def build_captions():
    """Rechunk word-level transcript into caption items with STRICTLY MONOTONIC,
    non-overlapping windows (a text track cannot hold overlapping segments)."""
    if not TRANSCRIPT:
        return []
    words = json.load(open(src(TRANSCRIPT)))
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= CAPTION_MAX_WORDS
                    or w["start"] - cur[-1]["end"] > CAPTION_GAP
                    or cur[-1]["text"].rstrip().endswith((".", "?", "!", ","))):
            chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)

    items, prev_end = [], -1.0
    for i, c in enumerate(chunks):
        t0, t1 = c[0]["start"], c[-1]["end"]
        t0 = max(t0, prev_end + 0.002)                       # never overlap previous
        if i + 1 < len(chunks):                              # never overlap next
            t1 = min(max(t1, t0 + CAPTION_MIN_DUR), chunks[i + 1][0]["start"] - 0.04)
        if CAPTION_CUTOFF is not None and t0 >= CAPTION_CUTOFF:
            continue
        dur = max(0.05, t1 - t0)
        prev_end = t0 + dur
        mid = t0 + dur / 2
        style = dict(CAPTION_DEFAULT)
        for a, b, over in CAPTION_WINDOWS:
            if a <= mid < b:
                style.update(over); break
        txt = " ".join(w["text"] for w in c)
        if style.get("upper"):
            txt = txt.upper()
        items.append((txt, t0, dur, style))
    return items


def greedy_tracks(items, key_start=lambda x: x[0], key_dur=lambda x: x[1]):
    """Pack (possibly overlapping) items onto the fewest tracks such that no
    two items on one track overlap. Returns list of tracks (lists of items)."""
    tracks = []
    for it in sorted(items, key=key_start):
        for tr in tracks:
            if key_start(it) >= key_start(tr[-1]) + key_dur(tr[-1]) - 1e-6:
                tr.append(it); break
        else:
            tracks.append([it])
    return tracks


def text_segment(txt, t0, dur, style):
    kw = dict(size=style.get("size", 8.0), bold=style.get("bold", True),
              color=tuple(style.get("color", (1, 1, 1))), align=1)
    if style.get("italic"):
        # Some pyJianYingDraft versions lack the italic kwarg — degrade gracefully.
        try:
            ts = jydraft.TextStyle(italic=True, **kw)
        except TypeError:
            ts = jydraft.TextStyle(**kw)
    else:
        ts = jydraft.TextStyle(**kw)
    seg_kw = {"style": ts,
              "clip_settings": jydraft.ClipSettings(transform_y=style.get("transform_y", -0.64))}
    if style.get("border", True):
        bc = tuple(style.get("border_color", (0, 0, 0)))
        seg_kw["border"] = jydraft.TextBorder(width=style.get("border_width", 8.0), color=bc)
    return jydraft.TextSegment(txt, trange(f"{t0}s", f"{dur}s"), **seg_kw)


def build_draft():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    CS = jydraft.ClipSettings

    footage = stage(FOOTAGE_MAIN, "footage-main.mp4")
    overlay = stage(OVERLAY_VIDEO, "footage-overlay.mp4") if OVERLAY_VIDEO else None
    vo = stage(VO, "vo.mp3") if VO else None
    music = stage(MUSIC, "music.mp3") if MUSIC else None
    fx = stage(FX_OVERLAY, "fx-overlay.mov") if FX_OVERLAY else None
    for _, n, _ in HITS:
        stage(os.path.join(SFX_DIR, f"{n}.mp3"), os.path.join("sfx", f"{n}.mp3"))
    cards = split_cards() if (CANVAS_PASS and CARDS) else []
    vig = maybe_vignette()

    folder = jydraft.DraftFolder(STAGING_DIR)
    script = folder.create_draft(DRAFT_NAME, WIDTH, HEIGHT, allow_replace=True)

    def vseg(path, s, d, source_s=None, **clip):
        mat = VideoMaterial(path)
        # Segment duration MUST be clamped to material.duration or the lib throws.
        d = min(d, mat.duration / 1e6 - (source_s or 0))
        kw = {}
        if source_s is not None:
            kw["source_timerange"] = trange(f"{source_s}s", f"{d}s")
        if clip:
            kw["clip_settings"] = CS(**clip)
        return jydraft.VideoSegment(mat, trange(f"{s}s", f"{d}s"), volume=0.0, **kw)

    # footage: split at zoom boundaries, per-segment scale
    script.append_track(TrackSpec(TrackType.video, "footage"))
    for s, e, sc in ZOOM_SEGMENTS:
        clip = {"scale_x": sc, "scale_y": sc} if sc != 1.0 else {}
        script.add_segment(vseg(footage, s, e - s, source_s=s, **clip), "footage")

    # positioned overlay video
    if overlay and OVERLAY_WINDOWS:
        script.append_track(TrackSpec(TrackType.video, "overlay"))
        for s, e in OVERLAY_WINDOWS:
            script.add_segment(vseg(overlay, s, e - s, source_s=s, **OVERLAY_CLIP), "overlay")

    # per-card opaque clips
    if cards:
        script.append_track(TrackSpec(TrackType.video, "cards"))
        for name, s, e, f in cards:
            script.add_segment(vseg(f, s, e - s), "cards")

    # single alpha fx overlay
    if fx:
        script.append_track(TrackSpec(TrackType.video, "fx"))
        script.add_segment(vseg(fx, 0, DUR), "fx")

    # static PNG overlays as image segments
    png_layers = list(IMAGE_OVERLAYS)
    if vig and VIGNETTE_WINDOWS:
        png_layers.append((vig, list(VIGNETTE_WINDOWS)))
    for pi, (png, windows) in enumerate(png_layers):
        if not windows:
            continue
        p = png if os.path.isabs(png) and os.path.exists(png) else stage(png)
        tname = f"image-{pi + 1}"
        try:
            script.append_track(TrackSpec(TrackType.video, tname))
            for s, e in windows:
                mat = VideoMaterial(p)
                script.add_segment(
                    jydraft.VideoSegment(mat, trange(f"{s}s", f"{e - s}s"), volume=0.0), tname)
        except Exception as ex:
            print(f"image overlay {png} skipped: {ex}")

    # captions (native, editable text)
    caps = build_captions()
    if caps:
        script.append_track(TrackSpec(TrackType.text, "captions"))
        for txt, t0, dur, style in caps:
            script.add_segment(text_segment(txt, t0, dur, style), "captions")
        print(f"captions: {len(caps)} chunks")

    # extra texts on greedy non-overlap tracks
    if EXTRA_TEXTS:
        packed = greedy_tracks([(t0, dur, txt, style) for txt, t0, dur, style in EXTRA_TEXTS])
        for i, tr in enumerate(packed):
            tname = f"text-{i + 1}"
            script.append_track(TrackSpec(TrackType.text, tname))
            for t0, dur, txt, style in tr:
                st = dict(CAPTION_DEFAULT); st.update(style)
                script.add_segment(text_segment(txt, t0, dur, st), tname)

    # audio: vo + music
    if vo:
        script.append_track(TrackSpec(TrackType.audio, "vo"))
        vm = AudioMaterial(vo)
        script.add_segment(jydraft.AudioSegment(
            vm, trange("0s", f"{min(DUR, vm.duration / 1e6)}s"), volume=1.0), "vo")
    if music:
        script.append_track(TrackSpec(TrackType.audio, "music"))
        mm = AudioMaterial(music)
        script.add_segment(jydraft.AudioSegment(
            mm, trange("0s", f"{min(DUR, mm.duration / 1e6)}s"), volume=MUSIC_VOLUME), "music")

    # sfx hits packed onto greedy non-overlap tracks
    sx = []
    for t, n, v in HITS:
        p = os.path.join(MEDIA_DIR, "sfx", f"{n}.mp3")
        m = AudioMaterial(p)
        d = min(m.duration / 1e6, DUR - t - 0.01)
        sx.append((t, d, p, min(SFX_MAX, round(v * SFX_GAIN, 2))))
    for i, tr in enumerate(greedy_tracks(sx)):
        tname = f"sfx-{i + 1}"
        script.append_track(TrackSpec(TrackType.audio, tname))
        for t, d, p, v in tr:
            script.add_segment(jydraft.AudioSegment(
                AudioMaterial(p), trange(f"{t}s", f"{d}s"), volume=v), tname)

    script.save()
    draft_dir = os.path.join(STAGING_DIR, DRAFT_NAME)
    print(f"draft written: {draft_dir}")
    return draft_dir


# ── Schema patch (WORK IN PROGRESS — not field-verified) ─────────────────────
EXTRA_TOP_LEVEL_KEYS = [
    "draft_type", "function_assistant_info", "is_drop_frame_timecode",
    "lyrics_effects", "mixed_track_mode_on", "path", "smart_ads_info",
    "uneven_animation_template_info",
]


def patch_schema(draft_dir, native_dir):
    """Clone the modern-CapCut top-level keys + version fields from a NATIVE
    draft made by the target machine's CapCut, then write the result as BOTH
    draft_content.json (JianYing name) and draft_info.json (CapCut name)."""
    native_file = None
    for fn in ("draft_info.json", "draft_content.json"):
        p = os.path.join(native_dir, fn)
        if os.path.exists(p):
            native_file = p; break
    if not native_file:
        sys.exit(f"no draft_info.json/draft_content.json in native draft: {native_dir}")
    native = json.load(open(native_file))
    data = json.load(open(os.path.join(draft_dir, "draft_content.json")))

    for k in EXTRA_TOP_LEVEL_KEYS:
        if k in native:
            data[k] = copy.deepcopy(native[k])
    for vk in ("new_version", "version", "app_version"):
        if vk in native:
            data[vk] = native[vk]
    # 'path' must point at THIS draft's final installed location, not the native one.
    data["path"] = os.path.join(PROJECTS_DIR, DRAFT_NAME)

    for fn in ("draft_content.json", "draft_info.json"):
        with open(os.path.join(draft_dir, fn), "w") as f:
            json.dump(data, f, ensure_ascii=False)
    print(f"schema patched from {native_file} -> both filenames "
          f"(new_version={data.get('new_version')})")
    print("WARNING: this patch is a work-in-progress and has not been "
          "field-verified — open CapCut and check; if it refuses, diff against "
          "the native draft (see SKILL.md).")


# ── Install + registry (edit ONLY while CapCut is fully quit) ────────────────
def capcut_running():
    return subprocess.run(["pgrep", "-x", "CapCut"], capture_output=True).returncode == 0


def install(draft_dir):
    dst = os.path.join(PROJECTS_DIR, DRAFT_NAME)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(draft_dir, dst)
    # cover thumbnail for the project browser
    cover = os.path.join(dst, "draft_cover.jpg")
    if not os.path.exists(cover):
        subprocess.run([FFMPEG, "-y", "-ss", "0.5",
                        "-i", os.path.join(MEDIA_DIR, "footage-main.mp4"),
                        "-frames:v", "1", cover], capture_output=True)
    print(f"installed: {dst}")
    return dst


def register(installed_dir):
    """Add the draft to root_meta_info.json (all_draft_store) by cloning a
    native entry. Registry is backed up first."""
    meta_path = os.path.join(PROJECTS_DIR, "root_meta_info.json")
    if not os.path.exists(meta_path):
        sys.exit(f"registry not found: {meta_path} — open CapCut once, make any "
                 "project, quit, then retry.")
    backup = f"{meta_path}.bak-{int(time.time())}"
    shutil.copyfile(meta_path, backup)
    print(f"registry backed up: {backup}")

    meta = json.load(open(meta_path))
    store = meta.get("all_draft_store") or []
    if any(e.get("draft_name") == DRAFT_NAME for e in store):
        print("already registered — skipping"); return
    if not store:
        sys.exit("all_draft_store is empty — make one native project in CapCut "
                 "first so there is an entry to clone.")

    entry = copy.deepcopy(store[0])
    old_name = entry.get("draft_name", "")
    for k, v in list(entry.items()):
        if isinstance(v, str) and old_name and old_name in v:
            entry[k] = v.replace(old_name, DRAFT_NAME)
    entry["draft_name"] = DRAFT_NAME
    entry["draft_id"] = str(uuid.uuid4()).upper()
    if "draft_fold_path" in entry:
        entry["draft_fold_path"] = installed_dir
    if "tm_duration" in entry:
        entry["tm_duration"] = int(DUR * 1e6)
    now_us = int(time.time() * 1e6)
    for k in ("tm_draft_create", "tm_draft_modified"):
        if k in entry:
            entry[k] = now_us
    store.insert(0, entry)
    meta["all_draft_store"] = store
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False)
    print(f"registered '{DRAFT_NAME}' in root_meta_info.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--patch-native", metavar="NATIVE_DRAFT_DIR",
                    help="native CapCut draft folder to clone modern schema keys from")
    ap.add_argument("--install", action="store_true",
                    help="copy the staged draft into the CapCut projects folder")
    ap.add_argument("--register", action="store_true",
                    help="add the draft to root_meta_info.json (CapCut must be quit)")
    ap.add_argument("--skip-build", action="store_true",
                    help="reuse the already-staged draft; only patch/install/register")
    args = ap.parse_args()

    draft_dir = os.path.join(STAGING_DIR, DRAFT_NAME)
    if not args.skip_build:
        draft_dir = build_draft()
    if args.patch_native:
        patch_schema(draft_dir, os.path.expanduser(args.patch_native))
    if args.install or args.register:
        if capcut_running():
            sys.exit("CapCut is running — quit it completely (Cmd+Q) before "
                     "installing/registering, then rerun with --skip-build.")
    installed = install(draft_dir) if args.install else os.path.join(PROJECTS_DIR, DRAFT_NAME)
    if args.register:
        register(installed)


if __name__ == "__main__":
    main()
