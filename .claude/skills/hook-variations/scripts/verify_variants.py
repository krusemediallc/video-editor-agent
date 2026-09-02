#!/usr/bin/env python3
"""Prove every variant is a clean hook+body join.

    python3 verify_variants.py --body cut.mp4 --hooks hooks/ --out variants/

Checks, per variant:
  0. AVFOUNDATION decodes frames across the WHOLE timeline, and the file's avcC matches the
     body's. These two exist because a set once passed a thorough ffmpeg-only QA pass --
     every frame decoded, pixel-identical to source, constant fps, zero audio lag -- and was
     still broken in every real player. The build and the check both used libavcodec, which
     honours in-band SPS/PPS that AVFoundation ignores. A check that shares a blind spot
     with the thing it checks proves nothing. Never sign off an mp4 join on ffmpeg alone.
  1. the body half is pixel-identical to the body source (it is stream-copied)
  2. the hook half matches its source: bit-identical if it was copied, else PSNR
  3. frame count == hook frames + body frames
  4. constant frame rate end to end (no hitch at the junction)
  5. the body's audio starts on the exact sample its first video frame does (zero lag)
  6. the body's audio survives the single re-encode (SNR against the source)
  7. no loudness step at the seam, and the whole file honours the delivery spec
  8. both streams start at 0.000 and run the same length, with no decode errors
"""
import argparse, json, os, re, struct, subprocess, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor

FF = os.environ.get("FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
FP = os.environ.get("FFPROBE_PATH", "/opt/homebrew/bin/ffprobe")
HERE = os.path.dirname(os.path.abspath(__file__))
AVTEST = os.path.join(HERE, "avtest")
CH = 2


def dec_hashes(f):
    """md5 of every DECODED frame, plus any decoder errors."""
    p = subprocess.run([FF, "-v", "error", "-i", f, "-map", "v:0", "-f", "framemd5", "-"],
                       capture_output=True, text=True)
    return [l.rsplit(",", 1)[-1].strip() for l in p.stdout.splitlines()
            if not l.startswith("#")], p.stderr.strip()


def pcm(f, sr):
    p = subprocess.run([FF, "-v", "error", "-i", f, "-vn", "-f", "f32le", "-acodec",
                        "pcm_f32le", "-ar", str(sr), "-ac", str(CH), "-"], capture_output=True)
    return np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, CH).astype(np.float64)


def psnr(a, b):
    """The psnr filter logs its summary at INFO; -v error silently yields nothing."""
    p = subprocess.run([FF, "-hide_banner", "-nostats", "-i", a, "-i", b, "-lavfi",
                        "[0:v][1:v]psnr", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"average:(inf|[\d.]+)", p.stderr)
    if not m:
        return 0.0
    return float("inf") if m.group(1) == "inf" else float(m.group(1))


def loud(f, ss=None, t=None):
    cmd = [FF, "-hide_banner", "-nostats"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    if t is not None:
        cmd += ["-t", str(t)]
    cmd += ["-i", f, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True).stderr
    j = json.loads(e[e.rindex("{"):e.rindex("}") + 1])
    return float(j["input_i"]), float(j["input_tp"])


def av_decodes(f, dur):
    """Probe with AVFoundation -- QuickTime's decoder, not ffmpeg's."""
    if not os.path.exists(AVTEST):
        return None, "avtest not built (see SKILL.md)"
    pts = [f"{dur * k / 12:.2f}" for k in range(12)]
    p = subprocess.run([AVTEST, f] + pts, capture_output=True, text=True)
    return p.stdout.count(" OK") == len(pts), p.stdout.strip()


def param_sets(f):
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
    d = buf[r[0]:r[1]]; off = 6; sps = []
    for _ in range(d[5] & 0x1F):
        L = struct.unpack(">H", d[off:off + 2])[0]; sps.append(d[off + 2:off + 2 + L].hex()); off += 2 + L
    npps = d[off]; off += 1; pps = []
    for _ in range(npps):
        L = struct.unpack(">H", d[off:off + 2])[0]; pps.append(d[off + 2:off + 2 + L].hex()); off += 2 + L
    return d[3], sps, pps


def check(job):
    """job = (row, body, out_dir, hooks_dir, fps, sr).

    Config MUST be passed in, not read from module globals. ProcessPoolExecutor uses the
    `spawn` start method on macOS, so every worker re-imports this module with its OWN argv
    -- CLI flags are absent there. A previous version read the paths from globals and all
    five workers silently fell back to the defaults, verifying a DIFFERENT folder while the
    parent printed the labels you asked for: 21 confident "ALL PASS" lines about files that
    were never opened. It was caught only because a frame count came back 3 short."""
    row, BODY, OUT, HOOKS, fps, sr = job
    n = row["hook"]
    out = os.path.join(OUT, row["file"])
    hook = os.path.join(HOOKS, row["hook_source"])
    if not os.path.exists(out):
        return n, 0, 0.0, [(f"MISSING {out}", False)]

    bh, _ = dec_hashes(BODY)
    hh, _ = dec_hashes(hook)
    oh, err = dec_hashes(out)
    hf, bf = len(hh), len(bh)
    r = []

    r.append((f"frame count {len(oh)} == {hf}+{bf}", len(oh) == hf + bf))

    okav, avout = av_decodes(out, len(oh) / fps)
    if okav is None:
        r.append(("AVFoundation probe SKIPPED — build avtest, this is the check that "
                  "catches the freeze", False))
    else:
        r.append(("AVFoundation decodes the whole timeline"
                  + ("" if okav else " -> " + avout.replace(chr(10), " | ")), okav))
    r.append((f"avcC matches the body", param_sets(out) == param_sets(BODY)))

    nbad_b = sum(1 for a, b in zip(oh[hf:], bh) if a != b)
    r.append((f"body half pixel-identical ({bf} frames, {nbad_b} differ)", nbad_b == 0))

    if row.get("video") == "copied":
        nbad_h = sum(1 for a, b in zip(oh[:hf], hh) if a != b)
        r.append((f"hook half pixel-identical ({hf} frames, {nbad_h} differ)", nbad_h == 0))
    else:
        hv = os.path.join(OUT, ".tmp", f"hook-v-{n:02d}.mp4")
        if os.path.exists(hv):
            p = psnr(hv, hook)
            r.append((f"hook half PSNR {p:.1f} dB vs source (re-encoded)", p > 44))

    r.append(("decodes with no errors" + (f" [{err[:60]}]" if err else ""), not err))

    t = subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "packet=pts_time", "-of", "csv=p=0", out],
                       capture_output=True, text=True).stdout.split()
    d = np.diff(np.sort(np.array([float(x) for x in t if x.strip()])))
    r.append((f"constant {fps:g}fps (max dev {abs(d - 1/fps).max()*1000:.4f} ms)",
              abs(d - 1 / fps).max() < 1e-4))

    oa, ba = pcm(out, sr), pcm(BODY, sr)
    off = round(hf / fps * sr)
    seg = oa[off:off + sr * 4, 0]
    L = 60
    cors = [np.dot(seg[L:-L], ba[L + k:L + k + len(seg) - 2 * L, 0]) for k in range(-L, L + 1)]
    lag = int(np.argmax(cors)) - L
    r.append((f"body audio lag = {lag} samples", lag == 0))

    m = min(len(ba), len(oa) - off)
    diff = oa[off:off + m] - ba[:m]
    snr = 20 * np.log10(np.sqrt((ba[:m] ** 2).mean()) / (np.sqrt((diff ** 2).mean()) + 1e-12))
    r.append((f"body audio SNR {snr:.1f} dB after re-encode", snr > 30))

    # json, not positional csv: ffprobe orders fields its own way and a positional
    # unpack silently mis-assigns start_time and duration to each other
    st = subprocess.run([FP, "-v", "error", "-show_entries", "stream=start_time,duration",
                         "-of", "json", out], capture_output=True, text=True).stdout
    streams = json.loads(st)["streams"]
    starts = [float(s.get("start_time", 0)) for s in streams]
    durs = [float(s["duration"]) for s in streams]
    r.append((f"streams start 0.000, dur {durs[0]:.3f}/{durs[1]:.3f}s",
              all(abs(s) < 1e-6 for s in starts) and abs(durs[0] - durs[1]) < 0.05))

    hI, _ = loud(out, 0, hf / fps)
    bI2, _ = loud(out, hf / fps, None)
    wI, wTP = loud(out)
    r.append((f"seam step {hI - bI2:+.2f} LU (hook {hI:.2f} / body {bI2:.2f} LUFS)",
              abs(hI - bI2) < 1.0))
    r.append((f"whole file {wI:.2f} LUFS / {wTP:.2f} dBTP",
              abs(wI + 14.0) < 0.5 and wTP <= -1.0))

    return n, len(oh), len(oh) / fps, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True)
    ap.add_argument("--hooks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("only", nargs="*", type=int)
    args = ap.parse_args()

    body = os.path.abspath(args.body)
    out_dir = os.path.abspath(args.out)
    hooks_dir = os.path.abspath(args.hooks)
    man = json.load(open(os.path.join(out_dir, "variants.json")))
    rows = man["variants"] if isinstance(man, dict) else man
    if args.only:
        rows = [r for r in rows if r["hook"] in args.only]
    fps = man.get("fps", 30) if isinstance(man, dict) else 30
    sr = int(subprocess.run([FP, "-v", "error", "-select_streams", "a:0", "-show_entries",
                             "stream=sample_rate", "-of", "default=nw=1:nk=1", body],
                            capture_output=True, text=True).stdout.strip() or 48000)

    print(f"verifying {len(rows)} variants in {out_dir}\n  against body {body}\n")
    jobs = [(r, body, out_dir, hooks_dir, fps, sr) for r in rows]
    fails = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for n, nf, secs, res in sorted(ex.map(check, jobs)):
            bad = [m for m, ok in res if not ok]
            fails += len(bad)
            print(f"\nhook-{n:02d}  {nf} frames  {secs:.3f}s   "
                  f"{'ALL PASS' if not bad else 'FAILURES: ' + str(len(bad))}")
            for m, ok in res:
                if not ok or args.verbose:
                    print(f"     {'PASS' if ok else 'FAIL'}  {m}")
            if not bad and not args.verbose:
                print("     " + " | ".join(m for m, _ in res[-5:]))
    print(f"\n{'=' * 60}")
    print("ALL VARIANTS PASS EVERY CHECK" if not fails else f"{fails} FAILURES")
    print("=" * 60)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
