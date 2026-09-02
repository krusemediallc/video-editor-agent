#!/usr/bin/env python3
"""Generate one Seedance 2.5 clip through the Arcads external API and download it.

    python3 arcads_gen.py --prompt "..." --aspect 9:16 --duration 8
    python3 arcads_gen.py --prompt "..." --duration 6 --reference-image ref.png
    python3 arcads_gen.py --prompt "..." --duration 10 --reference-video ref.mp4
    python3 arcads_gen.py --prompt "..." --duration 6 --start-frame frame.png
    python3 arcads_gen.py --dry-run --prompt "..." --duration 6        # no network, no cost
    python3 arcads_gen.py --check                                      # read-only auth probe
    python3 arcads_gen.py --poll <assetId> [--slug name]               # resume a submitted job

Output lands next to this script:  mg/gen/<slug>.mp4  (+ _submitted.jsonl, _log.jsonl).
Every POST /v2/videos/generate is billed at create time (~42 credits/sec @720p,
~18.75 credits/sec @480p, more with reference video/audio). --dry-run never talks to the API.

Facts this script encodes (live OpenAPI docs-json + probes logged in
the arcads-claude-code pack, skills/arcads-external-api/prompting/prompt-library/seedance-2-5.md):
  * route: POST /v2/videos/generate, model "seedance-2.5"; response type "seedance_25"
  * poll:  GET /v1/assets/{id}   (NOT /v1/videos/{id} -> 404). Gate on status == "generated";
           the `url` field is populated while status is still "pending".
  * required: model, productId, prompt, duration (int 4-30), resolution (480p|720p), aspectRatio (9:16|16:9)
  * referenceImages max 9 (wrapper cap), referenceVideos max 3, referenceAudios max 3, audioEnabled bool
  * startFrame / endFrame are REJECTED for seedance-2.5 (400 "Unrecognized key"). --start-frame here
    uploads the image as Image 1 and prefixes a keyframe instruction to the prompt instead.
  * uploads: POST /v1/file-upload/get-presigned-url {fileType} -> PUT bytes to presignedUrl -> pass filePath.
    A filePath is consumed by exactly one generate call; re-upload for every submission.
  * credits: read data.creditsCharged on the asset (often null on the top level).
"""
import argparse
import base64
import json
import mimetypes
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
BASE = os.environ.get("ARCADS_BASE_URL", "https://external-api.arcads.ai").rstrip("/")
MODEL = "seedance-2.5"

# Your Arcads workspace ids: ARCADS_PRODUCT_ID / ARCADS_PROJECT_ID in the environment or .env.
DEFAULT_PRODUCT_ID = os.environ.get("ARCADS_PRODUCT_ID", "")
DEFAULT_PROJECT_ID = os.environ.get("ARCADS_PROJECT_ID", "")

# Auth gotcha (probed 2026-09-01): a prebuilt ARCADS_BASIC_AUTH header string is the value
# that worked; "Basic base64(ARCADS_API_KEY + ':')" returned 403 on every route at the time.
# Put whichever your account accepts in a .env; ARCADS_ENV_FILE points at a specific file,
# otherwise every .env from the current directory up to the filesystem root is tried.
def _env_candidates():
    out = [os.environ.get("ARCADS_ENV_FILE")]
    d = pathlib.Path.cwd()
    while True:
        out.append(str(d / ".env"))
        if d.parent == d:
            break
        d = d.parent
    return out

ENV_CANDIDATES = _env_candidates()

MAX_REF_IMAGES = 9
MAX_REF_VIDEOS = 3
MAX_REF_AUDIOS = 3
ASPECTS = ("9:16", "16:9")
RESOLUTIONS = ("480p", "720p")
CREDITS_PER_SEC = {"720p": 42.0, "480p": 18.75}  # measured t2v / i2v; video+audio refs run ~32% higher

SUBMITTED = HERE / "_submitted.jsonl"
LOG = HERE / "_log.jsonl"

AUTH = None  # set by load_auth()


def resolve_ids(args, env):
    """(productId, projectId): CLI flag, else the loaded .env (ARCADS_* or the legacy unprefixed
    names), else the process environment. Called AFTER the .env is read, never at import time."""
    pid = (args.product_id or env.get("ARCADS_PRODUCT_ID") or env.get("PRODUCT_ID")
           or os.environ.get("ARCADS_PRODUCT_ID") or "")
    if args.project_id is not None:
        prj = args.project_id
    else:
        prj = (env.get("ARCADS_PROJECT_ID") or env.get("PROJECT_ID")
               or os.environ.get("ARCADS_PROJECT_ID") or "")
    return pid, prj


# ----------------------------------------------------------------------------- auth / env

def read_env(path):
    env = {}
    p = pathlib.Path(path)
    if not p.is_file():
        return env
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'").strip('"')
    return env


def load_auth(env_file=None):
    """Return (Authorization header value, source path). Never print the value."""
    candidates = [env_file] if env_file else ENV_CANDIDATES
    for cand in candidates:
        if not cand:
            continue
        env = read_env(cand)
        v = env.get("ARCADS_BASIC_AUTH")
        if v:
            return (v if v.startswith("Basic ") else "Basic " + v), cand, env
        k = env.get("ARCADS_API_KEY")
        if k:
            return "Basic " + base64.b64encode((k + ":").encode()).decode(), cand, env
    raise SystemExit("no ARCADS_BASIC_AUTH / ARCADS_API_KEY found in: "
                     + ", ".join(c for c in candidates if c))


# ----------------------------------------------------------------------------- http

def req(method, path=None, body=None, raw=None, ctype=None, full_url=None, timeout=300):
    url = full_url or (BASE + path)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = {}
    if not full_url:
        headers["Authorization"] = AUTH
    if data is not None:
        headers["Content-Type"] = ctype or "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            payload = resp.read()
            is_json = resp.headers.get("content-type", "").startswith("application/json")
            return resp.status, (json.loads(payload) if payload and is_json else payload)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


# ----------------------------------------------------------------------------- uploads

def maybe_upscale(path):
    """Arcads rejects small images (422). If the longest side < 1024 px, upscale to 1080 px
    (Lanczos) into a temp JPEG next to this script. Requires Pillow; silently skipped otherwise."""
    try:
        from PIL import Image
    except Exception:
        return path
    try:
        im = Image.open(path)
    except Exception:
        return path
    w, h = im.size
    if max(w, h) >= 1024:
        return path
    scale = 1080.0 / max(w, h)
    im = im.convert("RGB").resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    tmp = HERE / ("_upscaled-" + path.stem + ".jpg")
    im.save(tmp, "JPEG", quality=93)
    print(f"  upscaled {path.name} {w}x{h} -> {im.size[0]}x{im.size[1]} ({tmp.name})")
    return tmp


def upload(path, kind):
    """Presign + PUT. Returns a filePath valid for exactly ONE generate call."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise SystemExit(f"missing {kind}: {path}")
    if kind == "image":
        path = maybe_upscale(path)
    ftype = mimetypes.guess_type(path.name)[0]
    if not ftype:
        ftype = {"image": "image/png", "video": "video/mp4", "audio": "audio/mpeg"}[kind]
    if ftype == "video/x-m4v":
        ftype = "video/mp4"
    st, js = req("POST", "/v1/file-upload/get-presigned-url", {"fileType": ftype})
    if st >= 300:
        raise SystemExit(f"presign failed {st}: {str(js)[:300]}")
    max_size = js.get("maxFileSize")
    if max_size and path.stat().st_size > max_size:
        raise SystemExit(f"{path.name} is {path.stat().st_size} bytes > maxFileSize {max_size}")
    st2, _ = req("PUT", raw=path.read_bytes(), ctype=ftype, full_url=js["presignedUrl"])
    if st2 >= 300:
        raise SystemExit(f"PUT failed {st2} for {path.name}")
    print(f"  uploaded {kind}: {path.name} -> {js['filePath']}")
    return js["filePath"]


# ----------------------------------------------------------------------------- helpers

def slugify(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:limit].rstrip("-")) or "clip"


def unique_dest(slug):
    dest = HERE / f"{slug}.mp4"
    n = 2
    while dest.exists():
        dest = HERE / f"{slug}-v{n}.mp4"
        n += 1
    return dest


def append_jsonl(path, rec):
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def build_prompt(args, n_images, n_videos, start_frame_used):
    prompt = args.prompt.strip()
    if start_frame_used:
        prompt = ("Use Image 1 as the exact opening frame: the first frame of the video must match "
                  "Image 1 in framing, subject, lighting and style, then the action continues from it.\n\n"
                  + prompt)
    if args.no_subtitles and "no subtitles" not in prompt.lower():
        prompt += "\n\nNo subtitles. No on-screen text or captions of any kind."
    if args.no_bgm and "no bgm" not in prompt.lower():
        prompt += " No BGM."
    return prompt


# ----------------------------------------------------------------------------- polling / download

def poll_and_download(asset_id, dest, interval, timeout_min, quiet=False):
    deadline = time.time() + timeout_min * 60
    t0 = time.time()
    last_status = None
    while time.time() < deadline:
        st, js = req("GET", f"/v1/assets/{asset_id}")
        if st >= 300 or not isinstance(js, dict):
            print(f"  poll {st}: {str(js)[:200]}")
        else:
            status = js.get("status")
            data = js.get("data") or {}
            if status != last_status and not quiet:
                print(f"  [{int(time.time() - t0):>4}s] status={status}")
                last_status = status
            if status == "generated" and js.get("url"):
                urllib.request.urlretrieve(js["url"], dest)
                size_kb = dest.stat().st_size // 1024
                credits = data.get("creditsCharged")
                elapsed = int(time.time() - t0)
                print(f"  ok {dest}  ({size_kb} KB, creditsCharged={credits}, {elapsed}s of polling)")
                append_jsonl(LOG, {"ts": time.strftime("%FT%TZ", time.gmtime()), "event": "downloaded",
                                   "assetId": asset_id, "file": str(dest), "creditsCharged": credits,
                                   "pollSeconds": elapsed, "thumbnailUrl": js.get("thumbnailUrl")})
                return True
            if status == "failed":
                err = data.get("error") or data.get("failureReason") or json.dumps(data)[:600]
                print(f"  FAILED {asset_id}: {err}")
                append_jsonl(LOG, {"ts": time.strftime("%FT%TZ", time.gmtime()), "event": "failed",
                                   "assetId": asset_id, "error": str(err)[:800],
                                   "creditsCharged": data.get("creditsCharged")})
                return False
        time.sleep(interval)
    print(f"  TIMEOUT after {timeout_min} min; resume later with: --poll {asset_id} --slug <slug>")
    return False


# ----------------------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(
        description="Generate a Seedance 2.5 clip via Arcads and download it to mg/gen/<slug>.mp4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Facts this script encodes")[0])
    ap.add_argument("--prompt", help="video prompt (timestamped beats work on 2.5: '0-2s: ...')")
    ap.add_argument("--prompt-file", help="read the prompt from a text file instead of --prompt")
    ap.add_argument("--aspect", default="9:16", choices=ASPECTS, help="aspect ratio (default 9:16)")
    ap.add_argument("--duration", type=int, help="seconds, integer 4-30 (required by the API)")
    ap.add_argument("--resolution", default="720p", choices=RESOLUTIONS,
                    help="480p is ~2.2x cheaper (area-metered); 720p is the model ceiling")
    ap.add_argument("--audio", dest="audio", action="store_true", default=True,
                    help="audioEnabled=true (default)")
    ap.add_argument("--no-audio", dest="audio", action="store_false", help="audioEnabled=false")
    ap.add_argument("--reference-image", action="append", default=[], metavar="PATH",
                    help=f"reference image (repeatable, max {MAX_REF_IMAGES}); auto-upscaled if < 1024 px")
    ap.add_argument("--reference-video", action="append", default=[], metavar="PATH",
                    help=f"reference video (repeatable, max {MAX_REF_VIDEOS}); with a ref video keep the "
                         "prompt to timestamped beats only; tight face close-ups get rejected")
    ap.add_argument("--reference-audio", action="append", default=[], metavar="PATH",
                    help=f"reference audio (repeatable, max {MAX_REF_AUDIOS})")
    ap.add_argument("--start-frame", metavar="PATH",
                    help="image to open on. seedance-2.5 rejects the native startFrame field, so this is "
                         "sent as Image 1 in referenceImages plus a keyframe instruction in the prompt")
    ap.add_argument("--no-subtitles", action="store_true", default=True,
                    help="append 'No subtitles...' (default on)")
    ap.add_argument("--allow-subtitles", dest="no_subtitles", action="store_false")
    ap.add_argument("--no-bgm", action="store_true", help="append 'No BGM.'")
    ap.add_argument("--allow-mixed-refs", action="store_true",
                    help="allow referenceImages together with referenceVideos (500 on 2.0; unverified on 2.5)")
    ap.add_argument("--slug", help="output basename (default: derived from the prompt)")
    ap.add_argument("--product-id", default=None,
                    help="default: ARCADS_PRODUCT_ID (or PRODUCT_ID) from .env / the environment; required")
    ap.add_argument("--project-id", default=None,
                    help="Arcads project to file the asset under; default ARCADS_PROJECT_ID from .env / the environment ('' to omit)")
    ap.add_argument("--env-file", help="path to a .env with ARCADS_BASIC_AUTH or ARCADS_API_KEY")
    ap.add_argument("--poll", metavar="ASSET_ID", help="skip submission; poll + download an existing asset id")
    ap.add_argument("--no-poll", action="store_true", help="submit only; print the asset id and exit")
    ap.add_argument("--poll-interval", type=int, default=20, help="seconds between polls (default 20)")
    ap.add_argument("--timeout", type=int, default=60,
                    help="minutes to wait (default 60; 1-ref 10s clips took 4-9 min, 10-ref clips 8-47 min)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate args, print the payload that WOULD be sent, no network, no cost")
    ap.add_argument("--check", action="store_true",
                    help="read-only auth probe (GET /v1/assets on a known id + product folders); no cost")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation prompt")
    return ap


def main(argv=None):
    global AUTH
    ap = build_parser()
    args = ap.parse_args(argv)

    # ---- modes that need no prompt
    if args.check:
        AUTH, src, env = load_auth(args.env_file)
        pid, _ = resolve_ids(args, env)
        print(f"auth loaded from {src}")
        for ep in (f"/v1/products/{pid}/folders?pageSize=5", "/v1/brands?pageSize=5",
                   "/v1/assets/2e4b41d6-68cc-4d06-bc86-4a6b50e4e916"):
            st, js = req("GET", ep)
            extra = ""
            if st == 200 and isinstance(js, dict):
                extra = f" items={len(js.get('items', []))}" if "items" in js else \
                        f" type={js.get('type')} status={js.get('status')}"
            print(f"  GET {ep.split('?')[0]} -> {st}{extra}")
        return 0

    if args.poll:
        AUTH, src, env = load_auth(args.env_file)
        slug = args.slug or f"asset-{args.poll[:8]}"
        dest = unique_dest(slug)
        print(f"polling {args.poll} -> {dest}")
        return 0 if poll_and_download(args.poll, dest, args.poll_interval, args.timeout) else 1

    # ---- validation
    if args.prompt_file:
        args.prompt = pathlib.Path(args.prompt_file).read_text()
    if not args.prompt or not args.prompt.strip():
        ap.error("--prompt (or --prompt-file) is required")
    if args.duration is None:
        ap.error("--duration is required (integer seconds 4-30; the API 400s without it)")
    if not 4 <= args.duration <= 30:
        ap.error("--duration must be an integer from 4 to 30 for seedance-2.5")
    ref_images = list(args.reference_image)
    if args.start_frame:
        ref_images.insert(0, args.start_frame)
    if len(ref_images) > MAX_REF_IMAGES:
        ap.error(f"at most {MAX_REF_IMAGES} reference images (wrapper cap), got {len(ref_images)}")
    if len(args.reference_video) > MAX_REF_VIDEOS:
        ap.error(f"at most {MAX_REF_VIDEOS} reference videos, got {len(args.reference_video)}")
    if len(args.reference_audio) > MAX_REF_AUDIOS:
        ap.error(f"at most {MAX_REF_AUDIOS} reference audios, got {len(args.reference_audio)}")
    if ref_images and args.reference_video and not args.allow_mixed_refs:
        ap.error("referenceImages + referenceVideos in one call returned HTTP 500 on seedance-2.0 and is "
                 "unverified on 2.5; pass --allow-mixed-refs to try anyway")
    for p in ref_images + args.reference_video + args.reference_audio:
        if not pathlib.Path(p).is_file():
            ap.error(f"file not found: {p}")

    prompt = build_prompt(args, len(ref_images), len(args.reference_video), bool(args.start_frame))
    slug = slugify(args.slug or args.prompt)
    dest = unique_dest(slug)
    est = CREDITS_PER_SEC[args.resolution] * args.duration
    if args.reference_video or args.reference_audio:
        est *= 1.32
    pre_env = read_env(args.env_file) if args.env_file else {}
    pid, prj = resolve_ids(args, pre_env)   # re-resolved after the .env is actually loaded (below)

    payload = {
        "model": MODEL,
        "productId": pid,
        "prompt": prompt,
        "duration": args.duration,
        "resolution": args.resolution,
        "aspectRatio": args.aspect,
        "audioEnabled": bool(args.audio),
    }
    if prj:
        payload["projectId"] = prj

    print(f"model={MODEL} duration={args.duration}s {args.resolution} {args.aspect} audio={payload['audioEnabled']}")
    print(f"refs: images={len(ref_images)} videos={len(args.reference_video)} audios={len(args.reference_audio)}"
          + (" (start-frame as Image 1)" if args.start_frame else ""))
    print(f"estimated cost: ~{est:.0f} credits (estimate; confirm in the Arcads platform)")
    print(f"output: {dest}")

    if args.dry_run:
        preview = dict(payload)
        preview["referenceImages"] = [f"<upload:{pathlib.Path(p).name}>" for p in ref_images] or None
        preview["referenceVideos"] = [f"<upload:{pathlib.Path(p).name}>" for p in args.reference_video] or None
        preview["referenceAudios"] = [f"<upload:{pathlib.Path(p).name}>" for p in args.reference_audio] or None
        preview = {k: v for k, v in preview.items() if v is not None}
        print("\nDRY RUN - payload that would be POSTed to /v2/videos/generate:")
        print(json.dumps(preview, indent=2))
        return 0

    # ---- live
    AUTH, src, env = load_auth(args.env_file)
    pid, prj = resolve_ids(args, env)
    if not pid:
        sys.exit("ARCADS_PRODUCT_ID not set (put it in .env, the environment, or pass --product-id)")
    payload["productId"] = pid
    if prj:
        payload["projectId"] = prj
    else:
        payload.pop("projectId", None)
    print(f"auth loaded from {src}")
    if not args.yes:
        ans = input(f"Submit and spend ~{est:.0f} credits? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("aborted")
            return 2

    if ref_images:
        payload["referenceImages"] = [upload(p, "image") for p in ref_images]
    if args.reference_video:
        payload["referenceVideos"] = [upload(p, "video") for p in args.reference_video]
    if args.reference_audio:
        payload["referenceAudios"] = [upload(p, "audio") for p in args.reference_audio]

    st, js = req("POST", "/v2/videos/generate", payload)
    ts = time.strftime("%FT%TZ", time.gmtime())
    print(f"POST /v2/videos/generate -> {st}")
    if st >= 300:
        print(str(js)[:800])
        append_jsonl(LOG, {"ts": ts, "event": "submit-failed", "status": st, "error": str(js)[:800],
                           "slug": slug, "duration": args.duration, "resolution": args.resolution,
                           "aspectRatio": args.aspect, "nRefImages": len(ref_images),
                           "nRefVideos": len(args.reference_video)})
        return 1
    d = js if isinstance(js, dict) else {}
    asset = d.get("data") if isinstance(d.get("data"), dict) and d.get("data", {}).get("id") else d
    asset_id = asset.get("id")
    if not asset_id:
        print("no asset id in response:", json.dumps(d)[:600])
        return 1
    rec = {"ts": ts, "slug": slug, "assetId": asset_id, "type": asset.get("type"), "file": str(dest),
           "model": MODEL, "duration": args.duration, "resolution": args.resolution,
           "aspectRatio": args.aspect, "audioEnabled": payload["audioEnabled"],
           "nRefImages": len(ref_images), "nRefVideos": len(args.reference_video),
           "nRefAudios": len(args.reference_audio), "startFrameAsImage1": bool(args.start_frame),
           "promptWordCount": len(prompt.split()), "estimatedCredits": round(est),
           "creditsChargedAtCreate": (asset.get("data") or {}).get("creditsCharged")}
    append_jsonl(SUBMITTED, rec)              # persist BEFORE polling
    append_jsonl(LOG, {**rec, "event": "submitted", "status": st})
    print(f"asset {asset_id} (type={asset.get('type')}) recorded in {SUBMITTED.name}")
    if args.no_poll:
        print(f"resume with: python3 {pathlib.Path(__file__).name} --poll {asset_id} --slug {slug}")
        return 0
    ok = poll_and_download(asset_id, dest, args.poll_interval, args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
