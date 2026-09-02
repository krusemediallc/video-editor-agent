#!/usr/bin/env python3
"""Pre-flight for a hook+body join. Run this BEFORE building anything.

Every trap in this skill is visible here, in one table, in about ten seconds. Reading it
first is the difference between one clean build and three rebuilds.

    python3 probe_join.py --body cut.mp4 --hooks hooks/

Reports per hook:
  geometry     w/h/fps/pix_fmt vs the body           -> a mismatch means the join is off
  timebase     the body's vs the hook's              -> concat does NOT rescale file 2
  audio tail   audio duration - video duration       -> pushes the body off the frame grid
  avcC         SPS/PPS equal to the body's?          -> unequal = FREEZES in QuickTime
  loudness     integrated LUFS vs the body's         -> a step at the seam
and then says, per hook, what the build will have to do about it.
"""
import argparse, json, os, re, struct, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

FF = os.environ.get("FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
FP = os.environ.get("FFPROBE_PATH", "/opt/homebrew/bin/ffprobe")


def probe(f, args):
    return subprocess.run([FP, "-v", "error"] + args + [f],
                          capture_output=True, text=True).stdout.strip()


def kv(f, stream, keys):
    """ffprobe emits fields in ITS order, not the order you asked for, so positional
    unpacking of csv output silently mis-assigns. Parse key=value instead."""
    out = probe(f, ["-select_streams", stream, "-show_entries", "stream=" + ",".join(keys),
                    "-of", "default=nw=1"])
    d = {}
    for line in out.splitlines():
        k, _, v = line.partition("=")
        d[k.strip()] = v.strip()
    return d


def vinfo(f):
    d = kv(f, "v:0", ["width", "height", "r_frame_rate", "pix_fmt", "nb_frames",
                      "time_base", "duration"])
    num, den = d["r_frame_rate"].split("/")
    return {"w": int(d["width"]), "h": int(d["height"]), "fps": int(num) / int(den),
            "pix": d["pix_fmt"], "frames": int(d["nb_frames"]), "tb": d["time_base"],
            "vdur": float(d["duration"])}


def adur(f):
    d = probe(f, ["-select_streams", "a:0", "-show_entries", "stream=duration",
                  "-of", "default=nw=1:nk=1"])
    return float(d) if d else 0.0


def param_sets(f):
    """(level, [SPS hex], [PPS hex]) from the mp4 avcC box -- the only parameter sets a
    strict player (AVFoundation/QuickTime) will ever read."""
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
        return None

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
        return None
    d = buf[r[0]:r[1]]; off = 6; sps = []
    for _ in range(d[5] & 0x1F):
        L = struct.unpack(">H", d[off:off + 2])[0]; sps.append(d[off + 2:off + 2 + L].hex()); off += 2 + L
    npps = d[off]; off += 1; pps = []
    for _ in range(npps):
        L = struct.unpack(">H", d[off:off + 2])[0]; pps.append(d[off + 2:off + 2 + L].hex()); off += 2 + L
    return d[3], sps, pps


def loudness(f):
    err = subprocess.run([FF, "-hide_banner", "-nostats", "-i", f, "-af",
                          "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    try:
        j = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
        return float(j["input_i"]), float(j["input_tp"])
    except Exception:
        return None, None


def scan(f):
    v = vinfo(f)
    v["adur"] = adur(f)
    v["ps"] = param_sets(f)
    v["lufs"], v["tp"] = loudness(f)
    v["path"] = f
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True)
    ap.add_argument("--hooks", required=True, help="directory of hook mp4s, or a glob")
    args = ap.parse_args()

    if os.path.isdir(args.hooks):
        hooks = sorted(os.path.join(args.hooks, x) for x in os.listdir(args.hooks)
                       if x.lower().endswith((".mp4", ".mov")))
    else:
        import glob
        hooks = sorted(glob.glob(args.hooks))
    if not hooks:
        sys.exit(f"no hooks found at {args.hooks}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        body = ex.submit(scan, args.body).result()
        infos = list(ex.map(scan, hooks))

    print(f"BODY  {os.path.basename(body['path'])}")
    print(f"      {body['w']}x{body['h']} @ {body['fps']:g}fps {body['pix']}  "
          f"tb={body['tb']}  {body['frames']}f = {body['frames']/body['fps']:.3f}s")
    print(f"      {body['lufs']:.2f} LUFS / {body['tp']:.2f} dBTP")
    if body["ps"]:
        print(f"      avcC level {body['ps'][0]/10:.1f}  SPS {body['ps'][1][0][:24]}…")
    print()

    hdr = f"{'hook':<26}{'geom':<8}{'tb':<10}{'a-tail':>9}{'avcC':>7}{'LUFS':>9}{'Δ LU':>8}   what the build must do"
    print(hdr); print("-" * len(hdr))

    need_reenc = need_loud = 0
    for h in infos:
        geom = "ok" if (h["w"], h["h"], round(h["fps"], 3), h["pix"]) == \
                       (body["w"], body["h"], round(body["fps"], 3), body["pix"]) else "DIFF"
        tb = "ok" if h["tb"] == body["tb"] else h["tb"]
        tail = (h["adur"] - h["frames"] / h["fps"]) * 1000
        same_ps = h["ps"] == body["ps"]
        d = (body["lufs"] - h["lufs"]) if (h["lufs"] is not None) else 0.0

        todo = []
        if geom == "DIFF":
            todo.append("SCALE/FPS FIRST — not a drop-in")
        if not same_ps:
            todo.append("re-encode hook to body params")
            need_reenc += 1
        else:
            todo.append("hook can be stream-copied")
        if abs(d) >= 0.3:
            todo.append(f"gain {d:+.1f} LU")
            need_loud += 1

        print(f"{os.path.basename(h['path']):<26}{geom:<8}{tb:<10}{tail:>+8.1f}ms"
              f"{'ok' if same_ps else 'DIFF':>7}{h['lufs']:>9.2f}{d:>+8.2f}   {'; '.join(todo)}")

    print()
    print(f"{len(infos)} hooks: {need_reenc} need a re-encode to match the body's parameter "
          f"sets, {need_loud} need a loudness match.")
    if need_reenc:
        print("  avcC DIFF is the one that silently ships broken: ffmpeg plays such a join "
              "fine,\n  but QuickTime/AVFoundation reads only avcC and FREEZES at the seam. "
              "build_variants.py\n  re-encodes those hooks and refuses to mux if they still "
              "do not match.")
    off_grid = sum(1 for h in infos if abs(h["adur"] - h["frames"] / h["fps"]) > 0.5e-3)
    if off_grid:
        print(f"  {off_grid} hooks have audio that overruns their video — the build pins the "
              f"concat\n  offset to frames/fps so the body still lands on the frame grid.")


if __name__ == "__main__":
    main()
