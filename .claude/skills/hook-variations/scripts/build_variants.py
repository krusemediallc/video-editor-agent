#!/usr/bin/env python3
"""Prepend each hook to one body cut -> one standalone variant per hook.

    python3 build_variants.py --body cut.mp4 --hooks hooks/ --out variants/
    python3 build_variants.py --body cut.mp4 --hooks hooks/ --out variants/ 3 7   # just those

Why this is not `ffmpeg -f concat -c copy`. That one-liner is wrong in four ways on real
material, and three of them fail SILENTLY:

 1. TIMEBASE. The concat demuxer takes its output timebase from the FIRST file and does not
    rescale the second. Hooks at 1/15360 in front of a body at 1/30000 stretch the body's
    timestamps by 1.95x -- a 121s file that reports 236s. No warning is printed.
 2. AUDIO OVERRUN. AAC frames are 1024 samples, which never lands on a 30fps boundary, so a
    hook's audio routinely runs past its last video frame. The demuxer offsets the next file
    by the CONTAINER duration, so the body starts off the frame grid and the whole body is
    lip-sync drifted by that much.
 3. PARAMETER SETS. If the hook and body were encoded with different settings they carry
    different SPS/PPS. An mp4 `avc1` track holds exactly ONE avcC, and concat writes the
    first file's. ffmpeg plays it anyway because it honours the in-band copies the demuxer
    inserts at each IDR -- but AVFoundation (QuickTime, Finder, Photos, most upload
    validators) reads only avcC and FREEZES on the body's first frame while audio runs on.
    This is the one that ships broken and gets caught by a human, not by QA.
 4. LOUDNESS. Hooks cut from a raw mix are commonly 10-20 LU quieter than a body that has
    been through a loudnorm pass. Joined raw you get a hook you can barely hear and then the
    body arriving at full level.

So the streams are built separately and muxed:

  VIDEO  body is remuxed video-only and stream-copied -- every frame stays bit-identical.
         Each hook is stream-copied TOO if its avcC already matches the body; only hooks
         that differ get re-encoded to the body's settings (+ `setsar=1`, which is usually
         the last byte of difference). Video-only matters twice: a video-only container's
         duration IS its video duration, and both files land on a common timescale.
         The concat list also pins `duration` to the hook's exact frames/fps, because mp4
         muxers sometimes write a track duration derived from a millisecond-rounded value.
  AUDIO  decoded to float, hook loudness-matched to the body, trimmed/padded to exactly
         frames/fps * sample_rate, body appended, encoded ONCE. Sample-exact: the body's
         audio starts on the same sample as the body's first video frame.

Every build asserts the two halves' avcC match before muxing. If that assertion ever fires,
do not work around it -- it is telling you the file would freeze.
"""
import argparse, json, os, re, struct, subprocess, sys

FF = os.environ.get("FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
FP = os.environ.get("FFPROBE_PATH", "/opt/homebrew/bin/ffprobe")
TIMESCALE = 30000
CH = 2
BPF = 4 * CH            # f32le stereo bytes per sample-frame


# ---------------------------------------------------------------- probing helpers
def probe(f, args):
    return subprocess.run([FP, "-v", "error"] + args + [f],
                          capture_output=True, text=True).stdout.strip()


def vframes(f):
    return int(probe(f, ["-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                         "-of", "default=nw=1:nk=1"]))


def vfps(f):
    n, d = probe(f, ["-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                     "-of", "default=nw=1:nk=1"]).split("/")
    return int(n) / int(d)


def param_sets(f):
    """(level, [SPS hex], [PPS hex]) from the mp4 avcC box."""
    fh = open(f, "rb"); fh.seek(0, 2); flen = fh.tell(); fh.seek(0); buf = None
    while fh.tell() < flen:
        hdr = fh.read(8)
        if len(hdr) < 8:
            break
        sz = struct.unpack(">I", hdr[:4])[0]; typ = hdr[4:8]; extra = 0
        if sz == 1:
            sz = struct.unpack(">Q", fh.read(8))[0]; extra = 8
        elif sz == 0:
            sz = flen - (fh.tell() - 8)
        if typ == b"moov":
            buf = hdr + b"\x00" * extra + fh.read(sz - 8 - extra); break
        fh.seek(sz - 8 - extra, 1)
    fh.close()
    if buf is None:
        raise RuntimeError(f"no moov in {f}")

    def walk(b, path, start=0, end=None):
        end = len(b) if end is None else end
        want = path[0]; i = start
        while i + 8 <= end:
            sz = struct.unpack(">I", b[i:i + 4])[0]; typ = b[i + 4:i + 8]; body = i + 8
            if sz == 1:
                sz = struct.unpack(">Q", b[i + 8:i + 16])[0]; body = i + 16
            elif sz == 0:
                sz = end - i
            if typ == want:
                if len(path) == 1:
                    return body, i + sz
                nb = body + (8 if want == b"stsd" else (78 if want == b"avc1" else 0))
                return walk(b, path[1:], nb, i + sz)
            i += sz
        return None

    r = walk(buf, [b"moov", b"trak", b"mdia", b"minf", b"stbl", b"stsd", b"avc1", b"avcC"])
    if not r:
        raise RuntimeError(f"no avcC in {f}")
    d = buf[r[0]:r[1]]; off = 6; sps = []
    for _ in range(d[5] & 0x1F):
        L = struct.unpack(">H", d[off:off + 2])[0]; sps.append(d[off + 2:off + 2 + L].hex()); off += 2 + L
    npps = d[off]; off += 1; pps = []
    for _ in range(npps):
        L = struct.unpack(">H", d[off:off + 2])[0]; pps.append(d[off + 2:off + 2 + L].hex()); off += 2 + L
    return d[3], sps, pps


# ---------------------------------------------------------------- audio helpers
def pcm(src, sr):
    return subprocess.run([FF, "-v", "error", "-i", src, "-vn", "-f", "f32le",
                           "-acodec", "pcm_f32le", "-ar", str(sr), "-ac", str(CH), "-"],
                          capture_output=True, check=True).stdout


def afilter(raw, filt, sr):
    return subprocess.run([FF, "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(CH),
                           "-i", "pipe:0", "-af", filt, "-f", "f32le", "-acodec",
                           "pcm_f32le", "-ar", str(sr), "-ac", str(CH), "-"],
                          input=raw, capture_output=True, check=True).stdout


def measure(raw, sr, target_i, target_tp):
    err = subprocess.run([FF, "-hide_banner", "-f", "f32le", "-ar", str(sr), "-ac", str(CH),
                          "-i", "pipe:0", "-af",
                          f"loudnorm=I={target_i}:TP={target_tp}:LRA=11:print_format=json",
                          "-f", "null", "-"], input=raw, capture_output=True).stderr.decode()
    j = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    return float(j["input_i"]), float(j["input_tp"])


def match_loudness(raw, sr, target_i, target_tp, limit, label):
    """Bring a hook up to the body's level: static gain (dynamics preserved) + a limiter.

    `loudnorm:linear=true` cannot do this job when the lift is large: +15..+19 dB would put
    peaks well above 0 dBTP, so linear mode caps the gain to protect the ceiling and lands
    several LU short. Gain-then-limit reaches the target and the limiter only ever touches
    the loudest transients.

    Note `alimiter` limits SAMPLE peaks, not true peaks, so inter-sample peaks overshoot it.
    The default ceiling here is deliberately below -1 dBFS to leave room for that; a hotter
    ceiling has shipped files at -0.1 dBTP, hot enough to clip in a platform transcode."""
    I, TP = measure(raw, sr, target_i, target_tp)
    start = (I, TP)
    if abs(target_i - I) < 0.3:
        return raw, start, start, 0.0      # already matched: do not touch the dynamics
    g = 0.0
    for _ in range(4):
        g = target_i - I
        out = afilter(raw, f"volume={g:.3f}dB,alimiter=limit={limit}:level=disabled", sr)
        newI, newTP = measure(out, sr, target_i, target_tp)
        if abs(newI - target_i) <= 0.15:
            break
        # The limiter ate some loudness. We need MORE gain, i.e. a LOWER assumed I.
        # (g = target - I, so adding the negative shortfall to I raises g.) Getting this
        # sign backwards walks the quietest hooks the wrong way and only shows up on the
        # hard cases, because easy ones converge on the first pass and never reach here.
        I += (newI - target_i)
    warn = ""
    if abs(newI - target_i) > 0.15:
        warn += "   <-- MISSED loudness target"
    if newTP > -1.0:
        warn += "   <-- TRUE PEAK HOT"
    print(f"     loudness {label}: {start[0]:+.2f} LUFS / {start[1]:+.2f} dBTP  ->  "
          f"{newI:+.2f} / {newTP:+.2f}   (gain {g:+.2f} dB){warn}")
    return out, start, (newI, newTP), g


# ---------------------------------------------------------------- video helpers
def video_only(src, dst):
    """Strip audio and pin the track timescale, without touching a single frame."""
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-c:v", "copy",
                    "-an", "-video_track_timescale", str(TIMESCALE), dst], check=True)
    return dst


def reencode_to_body(src, dst, enc):
    """Re-encode a hook video-only with the body's settings.

    `setsar=1` is load-bearing: matching preset/CRF/pix_fmt gets the PPS and level to agree
    but leaves the SPS one byte off when the body signals square pixels explicitly
    (aspect_ratio_info_present_flag=1) and a plain re-encode does not."""
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-an",
                    "-vf", "setsar=1", "-c:v", "libx264", "-preset", enc["preset"],
                    "-crf", str(enc["crf"]), "-pix_fmt", enc["pix_fmt"],
                    "-video_track_timescale", str(TIMESCALE), dst], check=True)
    return dst


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True)
    ap.add_argument("--hooks", required=True, help="directory of hook mp4s, or a glob")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preset", default="slow", help="x264 preset the BODY was made with")
    ap.add_argument("--crf", default="18", help="x264 CRF the BODY was made with")
    ap.add_argument("--pix-fmt", default="yuv420p")
    ap.add_argument("--abitrate", default="320k")
    ap.add_argument("--limit", type=float, default=0.79,
                    help="alimiter sample-peak ceiling (0.79 = -2.05 dBFS)")
    ap.add_argument("only", nargs="*", type=int, help="only these hook indexes (1-based)")
    args = ap.parse_args()

    body = os.path.abspath(args.body)
    out_dir = os.path.abspath(args.out)
    tmp = os.path.join(out_dir, ".tmp")
    os.makedirs(tmp, exist_ok=True)

    if os.path.isdir(args.hooks):
        hooks = sorted(os.path.join(args.hooks, x) for x in os.listdir(args.hooks)
                       if x.lower().endswith((".mp4", ".mov")))
    else:
        import glob
        hooks = sorted(glob.glob(args.hooks))
    if not hooks:
        sys.exit(f"no hooks found at {args.hooks}")

    enc = {"preset": args.preset, "crf": args.crf, "pix_fmt": args.pix_fmt}
    fps = vfps(body)
    sr = int(probe(body, ["-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                          "-of", "default=nw=1:nk=1"]) or 48000)

    body_frames = vframes(body)
    body_v = video_only(body, os.path.join(tmp, "body-v.mp4"))
    body_ps = param_sets(body_v)
    body_pcm = pcm(body, sr)
    target_i, target_tp = measure(body_pcm, sr, -14.0, -1.5)

    tag = (re.search(r"(v\d+[a-z]?)(?=\.[^.]+$)", os.path.basename(body)) or [None])
    tag = tag.group(1) if hasattr(tag, "group") else os.path.splitext(os.path.basename(body))[0]

    print(f"body {os.path.basename(body)} -> {out_dir}")
    print(f"  {body_frames} frames @ {fps:g}fps ({body_frames/fps:.4f}s), "
          f"{len(body_pcm)//BPF} samples, {target_i:.2f} LUFS / {target_tp:.2f} dBTP")

    # Pin the body's audio to its exact video length. A decode that is short or long would
    # otherwise shift every variant by the same hidden amount.
    want_body = round(body_frames / fps * sr) * BPF
    body_pcm = (body_pcm + b"\x00" * max(0, want_body - len(body_pcm)))[:want_body]

    rows = []
    for idx, hook in enumerate(hooks, 1):
        if args.only and idx not in args.only:
            continue
        hf = vframes(hook)
        name = f"{tag}-hook-{idx:02d}.mp4"
        out = os.path.join(out_dir, name)

        # ---- video ------------------------------------------------------------------
        hv_tmp = os.path.join(tmp, f"hook-v-{idx:02d}.mp4")
        if param_sets(hook) == body_ps:
            hook_v = video_only(hook, hv_tmp)          # already compatible: no re-encode
            how = "copied"
        else:
            hook_v = reencode_to_body(hook, hv_tmp, enc)
            how = "re-encoded"
        hp_sets = param_sets(hook_v)
        if hp_sets != body_ps:
            raise SystemExit(
                f"hook {idx:02d}: SPS/PPS still do not match the body after {how}.\n"
                f"  This file would play in ffmpeg and FREEZE after the hook in QuickTime.\n"
                f"  hook {hp_sets}\n  body {body_ps}\n"
                f"  Check --preset/--crf/--pix-fmt actually match how the body was encoded.")
        if vframes(hook_v) != hf:
            raise SystemExit(f"hook {idx:02d}: {how} changed the frame count {hf} -> {vframes(hook_v)}")

        lst = os.path.join(tmp, f"list-{idx:02d}.txt")
        with open(lst, "w") as fh:
            # concat-list quoting: a ' inside a single-quoted path is written '\''
            fh.write("file '%s'\n" % hook_v.replace("'", "'\\''"))
            # Pin the offset to the hook's exact video length rather than trusting its
            # container duration: mp4 muxers sometimes write a track duration derived from a
            # millisecond-rounded seconds value, which starts the body a fraction of a frame
            # early. NB this directive is only trustworthy once both files share a timebase;
            # with a mismatch it compounds the offset instead of setting it.
            fh.write(f"duration {hf / fps:.6f}\n")
            fh.write("file '%s'\n" % body_v.replace("'", "'\\''"))
        vonly = os.path.join(tmp, f"v-{idx:02d}.mp4")
        subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-map", "0:v:0", "-c:v", "copy", "-an",
                        "-video_track_timescale", str(TIMESCALE), vonly], check=True)

        # ---- audio ------------------------------------------------------------------
        hp, before, after, gain = match_loudness(pcm(hook, sr), sr, target_i, target_tp,
                                                 args.limit, f"hook-{idx:02d}")
        want = round(hf / fps * sr) * BPF
        hp = (hp + b"\x00" * max(0, want - len(hp)))[:want]

        aonly = os.path.join(tmp, f"a-{idx:02d}.m4a")
        subprocess.run([FF, "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(CH),
                        "-i", "pipe:0", "-c:a", "aac", "-b:a", args.abitrate,
                        "-ar", str(sr), aonly], input=hp + body_pcm, check=True)

        subprocess.run([FF, "-y", "-v", "error", "-i", vonly, "-i", aonly,
                        "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                        "-movflags", "+faststart", out], check=True)

        got = vframes(out)
        exp = hf + body_frames
        print(f"{'OK ' if got == exp else 'BAD'} hook-{idx:02d}  {hf:5d}+{body_frames} = "
              f"{got:5d} frames  {got/fps:7.3f}s  video {how}  -> {name}\n")
        rows.append({"hook": idx, "hook_source": os.path.basename(hook), "hook_frames": hf,
                     "frames": got, "seconds": round(got / fps, 4), "file": name,
                     "video": how, "hook_lufs_before": round(before[0], 2),
                     "hook_lufs_after": round(after[0], 2), "gain_db": round(gain, 2)})

    json.dump({"body": os.path.basename(body), "body_frames": body_frames, "fps": fps,
               "tag": tag, "variants": rows},
              open(os.path.join(out_dir, "variants.json"), "w"), indent=1)
    print(f"wrote {len(rows)} variants + variants.json to {out_dir}")
    print("NEXT: verify_variants.py — an ffmpeg-only check cannot catch the freeze.")


if __name__ == "__main__":
    main()
