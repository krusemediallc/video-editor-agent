#!/usr/bin/env python3
"""Render the Arcads ad from edl.json. 9:16, no graphics, layout + hard silence cuts.

Each segment carries a `keep` list of sub-ranges (written by tighten.py); every range is
trimmed out of the source and concatenated, so the pauses inside a take disappear and the
delivery runs over itself. All windowing happens in the filter graph, never with -ss/-t:
the ReplayKit screen captures are variable-frame-rate and input seeking returns the wrong
window on them.
"""
import json, os, subprocess, sys
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
SEG = os.path.join(BASE, "segments")
FF = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
EDL = json.load(open(os.path.join(BASE, "edl.json")))
CAN = EDL["canvas"]; W, H, FPS = CAN["w"], CAN["h"], CAN["fps"]
CAM = EDL["cam"]; RECTS = EDL["screenRects"]
STILLS = "--stills" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
XF = 0.010          # micro fade at every audio sub-cut, kills the click


def _PUSH_REMOVED(seg, r, dur):
    """Crop expression for the screen half. With `pushIn` the rect shrinks slowly toward its
    centre over the shot, which reads as a gentle move in. Only used where the source screen
    is frozen for the entire shot - otherwise the rect is static."""
    w, h, x, y = r
    p = seg.get("pushIn")
    if not p or dur <= 0:
        return f"crop={w}:{h}:{x}:{y},"
    # scale goes 1.0 -> 1+p across the shot; crop shrinks by the same factor about the centre
    k = f"(1+{p}*min(1\,t/{dur:.3f}))"
    return (f"crop=w='{w}/{k}':h='{h}/{k}':"
            f"x='{x}+({w}-{w}/{k})/2':y='{y}+({h}-{h}/{k})/2',")


def qdur(seg):
    """A segment's video length, quantised up to a whole frame. The audio track is built to
    exactly this so the two never drift and no gap opens at a cut."""
    import math
    d = sum(b - a for a, b in seg["keep"])
    return math.ceil(d * FPS) / FPS


def src(take, kind):
    return os.path.join(RAW, f"Take {take} - {kind}.mov" if kind != "Mic"
                        else f"Take {take} - Mic.wav")


def vtrim(label, ranges, off, out):
    """split -> trim each range -> concat, for one video input."""
    n = len(ranges)
    if n == 1:
        a, b = ranges[0]
        return [f"[{label}]trim=start={a+off:.3f}:end={b+off:.3f},setpts=PTS-STARTPTS[{out}]"]
    fc = [f"[{label}]split={n}" + "".join(f"[{out}s{i}]" for i in range(n))]
    for i, (a, b) in enumerate(ranges):
        fc.append(f"[{out}s{i}]trim=start={a+off:.3f}:end={b+off:.3f},setpts=PTS-STARTPTS[{out}t{i}]")
    fc.append("".join(f"[{out}t{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[{out}]")
    return fc


def atrim(label, ranges, out, fin=True, fout=True):
    """`fin`/`fout` are the fades at the segment's own edges. They exist to kill the click at a
    cut, but a segment split for PICTURE ONLY - the zoom at "reference ad as a video in your
    prompt" lands mid-word - is sample-contiguous with its neighbour, and fading there puts an
    audible notch inside the word. `joinPrev` on the second half drops both fades at that seam.
    The internal sub-cut fades are never dropped; those really are joins between distant audio."""
    n = len(ranges)
    fc = ([f"[{label}]asplit={n}" + "".join(f"[{out}s{i}]" for i in range(n))] if n > 1 else [])
    for i, (a, b) in enumerate(ranges):
        inp = f"[{out}s{i}]" if n > 1 else f"[{label}]"
        d = b - a
        f = [f"atrim=start={a:.3f}:end={b:.3f}", "asetpts=PTS-STARTPTS"]
        if fin or i > 0:
            f.append(f"afade=t=in:st=0:d={XF}")
        if fout or i < n - 1:
            f.append(f"afade=t=out:st={max(0,d-XF):.3f}:d={XF}")
        fc.append(inp + ",".join(f) + f"[{out}t{i}]")
    if n > 1:
        fc.append("".join(f"[{out}t{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[{out}]")
    else:
        fc.append(f"[{out}t0]anull[{out}]")
    return fc


def build(seg):
    take = seg["take"]
    # A segment may borrow another take's screen capture. The camera/voice take is unchanged;
    # only the screen half is sourced elsewhere. Used where a take's own screen is frozen for
    # its whole duration and no offset can fix it.
    stake = seg.get("screenTake", take)
    ranges = [tuple(r) for r in seg["keep"]]
    dur = round(sum(b - a for a, b in ranges), 3)
    soff = seg.get("screenOffset", 0.0)
    layout = seg["layout"]
    ins, fc, n = [], [], 0

    if layout in ("split", "screen"):
        r = RECTS[seg["rect"]]
        ins += ["-i", src(stake, "Screen")]; si = n; n += 1
        fc.append(f"[{si}:v]fps={FPS},setpts=PTS-STARTPTS[sfr]")
        fc += vtrim("sfr", ranges, soff, "scut")
    ins += ["-i", src(take, "Camera")]; ci = n; n += 1
    fc.append(f"[{ci}:v]fps={FPS},setpts=PTS-STARTPTS[cfr]")
    fc += vtrim("cfr", ranges, 0.0, "ccut")

    if layout == "cam":
        c = list(CAM["full"]["crop"])
        if "camX" in seg:
            c[2] = seg["camX"]
        fc.append(f"[ccut]crop={c[0]}:{c[1]}:{c[2]}:{c[3]},scale={W}:{H}:flags=lanczos,"
                  f"setsar=1,format=yuv420p[v]")
    elif layout == "split":
        c = CAM["half"]["crop"]
        flip = ",hflip" if seg.get("flipScreen") else ""
        fc.append(f"[scut]crop={r[0]}:{r[1]}:{r[2]}:{r[3]}{flip},scale={W}:{H//2}:flags=lanczos,setsar=1[top]")
        fc.append(f"[ccut]crop={c[0]}:{c[1]}:{c[2]}:{c[3]},scale={W}:{H//2}:flags=lanczos,setsar=1[bot]")
        fc.append("[top][bot]vstack=inputs=2,format=yuv420p[v]")
    else:
        cc = CAM["circle"]; c = cc["crop"]; S = cc["size"]; R = S / 2
        flip = ",hflip" if seg.get("flipScreen") else ""
        fc.append(f"[scut]crop={r[0]}:{r[1]}:{r[2]}:{r[3]}{flip},scale={W}:{H}:flags=lanczos,setsar=1[bg]")
        fc.append(f"[ccut]crop={c[0]}:{c[1]}:{c[2]}:{c[3]},scale={S}:{S}:flags=lanczos,"
                  f"setsar=1,format=rgba[cam]")
        fc.append(f"color=c=black:s={S}x{S}:r={FPS}:d={dur:.3f},format=gray,"
                  f"geq=lum='clip(({R-2}-hypot(X-{R},Y-{R}))*255\\,0\\,255)'[mask]")
        fc.append("[cam][mask]alphamerge[camc]")
        fc.append(f"[bg][camc]overlay={cc['x']}:{cc['y']}:format=auto,format=yuv420p[v]")

    if STILLS:
        out = os.path.join(SEG, f"still-{seg['id']}.jpg")
        subprocess.run([FF, "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc),
                        "-map", "[v]", "-frames:v", "1", out], check=True)
        return out


    out = os.path.join(SEG, f"{seg['id']}.mp4")
    subprocess.run([FF, "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc),
                    "-map", "[v]", "-an", "-t", f"{qdur(seg):.5f}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                    "-r", str(FPS), "-movflags", "+faststart", out], check=True)
    return out


os.makedirs(SEG, exist_ok=True)
made = []
for s in EDL["segments"]:
    if ONLY and ONLY not in s["id"]:
        continue
    p = build(s)
    print("ok", os.path.basename(p))
    made.append(p)

if STILLS or ONLY:
    sys.exit(0)

def seg_frames(path):
    """Exact frame count of a rendered segment. The audio is built to match THIS, not a
    predicted length - -t and the fps filter can land a frame either side of the estimate,
    and any per-segment mismatch accumulates across 29 joins."""
    out = subprocess.run([(os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"), "-v", "error", "-select_streams", "v:0",
                          "-count_frames", "-show_entries", "stream=nb_read_frames",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    return int(out.rstrip(","))


def build_audio(out_wav, seg_durs):
    """Build the ENTIRE audio track in one pass, sample-accurate.

    Rendering audio per-segment and concatenating the MP4s cannot work: AAC quantises to
    1024-sample (21.3ms) frames and video to 33.3ms frames, so every join ended up with a few
    ms of mismatch - 29 small silent gaps, and 0.23s of accumulated drift by the CTA. Here each
    segment's audio is padded to exactly its frame-quantised video length before concatenation,
    so picture and sound stay locked for the whole file.
    """
    ins, fc, n = [], [], 0
    seg_labels = []
    for si, seg in enumerate(EDL["segments"]):
        ranges = [tuple(r) for r in seg["keep"]]
        soff = seg.get("screenOffset", 0.0)
        stake = seg.get("screenTake", seg["take"])
        ins += ["-i", src(seg["take"], "Mic")]; mi = n; n += 1
        fc.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo[m{si}]")
        nxt = EDL["segments"][si + 1] if si + 1 < len(EDL["segments"]) else {}
        if seg.get("joinPrev"):
            # only contiguous if the previous segment needed no apad, i.e. its keep is a whole
            # number of frames. Otherwise the pad puts silence between the two halves.
            pv = EDL["segments"][si - 1]
            pd = sum(y - x for x, y in pv["keep"])
            assert abs(pd * FPS - round(pd * FPS)) < 1e-6, \
                f"{seg['id']} joinPrev but {pv['id']} keep {pd}s is not a whole frame count"
            assert pv["take"] == seg["take"] and pv["keep"][-1][1] == seg["keep"][0][0], \
                f"{seg['id']} joinPrev but audio is not contiguous with {pv['id']}"
        fc += atrim(f"m{si}", ranges, f"v{si}",
                    fin=not seg.get("joinPrev"), fout=not nxt.get("joinPrev"))
        tag = f"v{si}"
        g = seg.get("gain", 0.0)
        if g:
            fc.append(f"[{tag}]volume={g}dB[v{si}g]"); tag = f"v{si}g"
        if seg.get("screenAudio"):
            ins += ["-i", src(stake, "Screen")]; ai = n; n += 1
            fc.append(f"[{ai}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={seg['screenAudio']}[s{si}]")
            # the screen's PICTURE and its AUDIO can be taken from different moments of the
            # same recording: here the example ad is playing on screen at one point and its
            # dialogue is audible at another, and the shot wants both
            aoff = seg.get("screenAudioOffset", soff)
            fc += atrim(f"s{si}", [(a + aoff, b + aoff) for a, b in ranges], f"sc{si}")
            stag = f"sc{si}"
            if seg.get("duckUntil"):
                d = round(seg["duckUntil"] - ranges[0][0], 3)
                fc.append(f"[sc{si}]volume=enable='lt(t\\,{d})':volume=0.22[sd{si}]"); stag = f"sd{si}"
            fc.append(f"[{tag}][{stag}]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mx{si}]")
            tag = f"mx{si}"
        q = seg_durs[si]
        fc.append(f"[{tag}]apad,atrim=0:{q:.6f},asetpts=PTS-STARTPTS[A{si}]")
        seg_labels.append(f"[A{si}]")
    fc.append("".join(seg_labels) + f"concat=n={len(seg_labels)}:v=0:a=1[out]")
    subprocess.run([FF, "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc),
                    "-map", "[out]", "-c:a", "pcm_s24le", "-ar", "48000", "-ac", "2",
                    out_wav], check=True)
    return out_wav


lst = os.path.join(SEG, "concat.txt")
with open(lst, "w") as f:
    for p in made:
        f.write(f"file '{os.path.basename(p)}'\n")
silent = os.path.join(SEG, "_video.mp4")
subprocess.run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                "-c", "copy", "-an", silent], check=True)
durs = [seg_frames(p) / FPS for p in made]
print(f"video: {sum(seg_frames(p) for p in made)} frames = {sum(durs):.3f}s")
wav = build_audio(os.path.join(SEG, "_audio.wav"), durs)
final = os.path.join(BASE, "arcads-ad-v1.mp4")
meas = subprocess.run([FF, "-hide_banner", "-i", wav, "-af",
                       "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                      capture_output=True, text=True).stderr
m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
      f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
      f":offset={m['target_offset']}:linear=true:print_format=summary")
print(f"loudnorm pass 1: I={m['input_i']} TP={m['input_tp']} LRA={m['input_lra']}")
subprocess.run([FF, "-v", "error", "-y", "-i", silent, "-i", wav,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                "-af", f"{ln},alimiter=limit=0.891:level=disabled",
                "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                "-video_track_timescale", "30000", "-muxdelay", "0", "-muxpreload", "0",
                "-movflags", "+faststart", final], check=True)
print("FINAL", final)
