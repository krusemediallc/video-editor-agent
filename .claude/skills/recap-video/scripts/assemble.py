#!/usr/bin/env python3
"""Build a frame/sample-aligned recap base cut. Python stdlib + ffmpeg/ffprobe.

Lines are a JSON list in PLAYBACK order: {"id":"intro", "in":1.2, "out":3.4,
"text":"optional editorial label", "raw":false, "veto":[[2.0,2.3]]}.
Transcript is {"words":[{"word":"Hello", "start":1.2, "end":1.5}]} ("text"
also accepted). All input times are seconds relative to the source's beginning.

Every invocation reserves a new _cut_work/<version>/ directory, including
--no-render. Use a NEW version after changing inputs or after a failed run.
The source must be a CFR mezzanine at --fps with synchronized video and audio;
this helper does not invent silence. Input sample rate may differ from output.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


class CutError(Exception):
    pass


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise CutError("Command failed: {}\n{}".format(cmd[0], result.stderr[-5000:]))
    return result


def binary(name, alternate):
    value = os.environ.get(name) or os.environ.get(alternate) or name.lower()
    found = shutil.which(value)
    if not found:
        raise CutError("{} executable not found: {}".format(name, value))
    return found


def probe(ffprobe, path):
    return json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format",
                           "-of", "json", str(path)]).stdout)


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CutError("{} must be a finite number".format(label))
    return float(value)


def interval(value, label, duration):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise CutError("{} must contain [start, end]".format(label))
    a, b = (number(value[i], label) for i in range(2))
    if not 0 <= a < b <= duration + 1e-6:
        raise CutError("{} [{}, {}] is outside source duration {:.6f}, or empty".format(label, a, b, duration))
    return a, min(b, duration)


def load_inputs(lines_path, transcript_path, duration):
    lines = json.loads(lines_path.read_text())
    if not isinstance(lines, list) or not lines:
        raise CutError("Lines JSON must be a nonempty list in playback order")
    clean = []
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            raise CutError("Line {} must be an object".format(i))
        a, b = interval([line.get("in"), line.get("out")], "Line {}".format(i), duration)
        if "raw" in line and not isinstance(line["raw"], bool):
            raise CutError("Line {} raw must be true or false".format(i))
        veto = line.get("veto", [])
        if not isinstance(veto, list):
            raise CutError("Line {} veto must be a list".format(i))
        veto = [interval(v, "Line {} veto".format(i), duration) for v in veto]
        clean.append(dict(line, id=str(line.get("id", "line-{:03d}".format(i + 1))),
                          line_index=i, **{"in": a, "out": b, "veto": veto}))
    ids = [line["id"] for line in clean]
    if any(not identity.strip() for identity in ids) or len(set(ids)) != len(ids):
        raise CutError("Each line needs a unique nonempty id, including repeated source occurrences")
    transcript = json.loads(transcript_path.read_text())
    words = transcript.get("words") if isinstance(transcript, dict) else transcript
    if not isinstance(words, list):
        raise CutError("Transcript must be a words list or an object containing words")
    cleaned_words, input_warnings = [], []
    for i, word in enumerate(words):
        if not isinstance(word, dict):
            raise CutError("Word {} must be an object".format(i))
        a, b = number(word.get("start"), "Word start"), number(word.get("end"), "Word end")
        if not 0 <= a <= b <= duration + 1e-6:
            raise CutError("Word {} timestamps are outside source or reversed".format(i))
        text = word.get("word", word.get("text"))
        if not isinstance(text, str):
            raise CutError("Word {} needs string word/text".format(i))
        if not text.strip():
            input_warnings.append({"kind": "empty_transcript_token", "source_word_index": i,
                                   "src_start": a, "src_end": b,
                                   "message": "Empty transcript placeholder omitted from word maps."})
            continue
        cleaned_words.append({"text": text.strip(), "start": a, "end": b, "source_word_index": i})
    return clean, cleaned_words, input_warnings


def find_pauses(ffmpeg, source, noise, minpause, duration, log_path):
    result = run([ffmpeg, "-nostdin", "-hide_banner", "-i", str(source),
                  "-map", "0:a:0", "-vn", "-af",
                  "silencedetect=noise={}dB:d={}".format(noise, minpause), "-f", "null", "-"])
    log_path.write_text(result.stderr)
    pauses, pending = [], None
    for match in re.finditer(r"silence_(start|end):\s*([-+0-9.eE]+)", result.stderr):
        kind, value = match.group(1), max(0.0, min(duration, float(match.group(2))))
        if kind == "start":
            pending = value
        elif pending is not None:
            if value > pending:
                pauses.append((pending, value))
            pending = None
    if pending is not None and pending < duration:
        pauses.append((pending, duration))
    return pauses


def subtract(a, b, cuts):
    kept, cursor = [], a
    for start, end in sorted(cuts):
        start, end = max(start, a), min(end, b)
        if end <= start:
            continue
        if start > cursor:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    if b > cursor:
        kept.append((cursor, b))
    return kept


def build_spans(lines, pauses, fps, max_frames, edge, minpause):
    spans, notes = [], []
    floor = lambda t: math.floor(t * fps + 1e-7)
    ceil = lambda t: math.ceil(t * fps - 1e-7)
    for line in lines:
        a, b = line["in"], line["out"]
        cuts = list(line["veto"])
        if not line.get("raw", False):
            for ps, pe in pauses:
                s, e = max(ps, a), min(pe, b)
                if e - s + 1e-9 < minpause:
                    continue
                cs, ce = s + edge, e - edge
                if s <= a + 1e-3:
                    cs = a
                if e >= b - 1e-3:
                    ce = b
                if ce > cs:
                    cuts.append((cs, ce))
        quantized = []
        for s, e in subtract(a, b, cuts):
            fa, fb = max(0, floor(s)), min(max_frames, ceil(e))
            # Silence cuts keep a little boundary air. Explicit vetoes are hard
            # exclusions: discard every frame touching one, even in raw mode.
            hard_cuts = [(floor(vs), ceil(ve)) for vs, ve in line["veto"]]
            for qa, qb in subtract(fa, fb, hard_cuts):
                if qb > qa:
                    if quantized and qa <= quantized[-1][1]:
                        quantized[-1] = (quantized[-1][0], max(qb, quantized[-1][1]))
                    else:
                        quantized.append((qa, qb))
        for fa, fb in quantized:
            if spans:
                previous = spans[-1]
                earlier_line = lines[previous["line_index"]]
                # Clamp ONLY accidental rounding overlap between nonoverlapping,
                # forward source ranges. Preserve deliberate overlap/reuse/reorder.
                if (previous["line_index"] != line["line_index"] and
                        earlier_line["out"] <= a + 1e-7 and
                        previous["src_in_f"] <= fa < previous["src_out_f"]):
                    notes.append({"kind": "quantization_overlap_clamped", "line_index": line["line_index"],
                                  "from_frame": fa, "to_frame": previous["src_out_f"]})
                    fa = previous["src_out_f"]
            if fb > fa:
                spans.append({"id": line["id"], "line_index": line["line_index"],
                              "src_in_f": fa, "src_out_f": fb})
    cursor = 0
    for i, span in enumerate(spans):
        frames = span["src_out_f"] - span["src_in_f"]
        span.update(span_index=i, out_in_f=cursor, out_out_f=cursor + frames,
                    src_in=span["src_in_f"] / fps, src_out=span["src_out_f"] / fps,
                    out_in=cursor / fps, out_out=(cursor + frames) / fps)
        cursor += frames
    if not spans:
        raise CutError("The selected lines contain no kept frames")
    return spans, notes


def remap_words(lines, words, spans, sample_rate):
    """Map once per line occurrence, including reused and reordered source ranges."""
    mapped, warnings = [], []
    for line in lines:
        kept = [s for s in spans if s["line_index"] == line["line_index"]]
        for word in words:
            wa, wb = word["start"], word["end"]
            # Only transcript words belonging to the declared editorial range;
            # incidental outward frame padding must not add a neighboring word.
            if wb <= line["in"] or wa >= line["out"]:
                continue
            pieces = []
            for span in kept:
                s, e = max(wa, span["src_in"]), min(wb, span["src_out"])
                if wa == wb and span["src_in"] <= wa < span["src_out"]:
                    e = min(span["src_out"], s + 1 / sample_rate)
                if e > s:
                    pieces.append((span, s, e))
            identity = {"text": word["text"], "source_word_index": word["source_word_index"],
                        "line_index": line["line_index"], "id": line["id"], "src_start": wa, "src_end": wb}
            if not pieces:
                reason = "explicit_veto" if any(va <= wa and wb <= vb for va, vb in line["veto"]) else "removed_interval"
                warnings.append(dict(identity, kind="unmapped_word", reason=reason,
                                     message="Word has no kept samples; inspect source audio/timestamps before captions."))
                continue
            first, last = pieces[0], pieces[-1]
            start = first[0]["out_in"] + first[1] - first[0]["src_in"]
            end = last[0]["out_in"] + last[2] - last[0]["src_in"]
            retained = sum(e - s for _, s, e in pieces)
            uncertain = wa == wb or retained < wb - wa - 1e-6 or len(pieces) > 1
            mapped.append(dict(identity, start=start, end=end,
                               alignment="inspect" if uncertain else "mapped"))
            if uncertain:
                warnings.append(dict(identity, kind="trimmed_word_alignment", out_start=start, out_end=end,
                                     message="Timestamp crosses a removed boundary; clipped to kept samples, not an invented duration."))
    mapped.sort(key=lambda w: (w["start"], w["line_index"], w["source_word_index"]))
    return mapped, warnings


def verify_cfr(ffprobe, source, video, fps):
    from fractions import Fraction
    for key in ("r_frame_rate", "avg_frame_rate"):
        if Fraction(video.get(key, "0/1")) != fps:
            raise CutError("Source must be a normalized CFR mezzanine at {} fps; {} is {}".format(fps, key, video.get(key)))
    # Packet timestamps are cheap to read, and unlike avg_frame_rate alone they
    # detect variable cadence. Sort for B-frames, then require a uniform grid.
    result = run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                  "packet=pts_time", "-of", "csv=p=0", str(source)])
    times = sorted(float(line.split(",")[0]) for line in result.stdout.splitlines() if line.strip())
    if len(times) < 2 or any(abs(b - a - 1 / fps) > 2e-5 for a, b in zip(times, times[1:])):
        raise CutError("Source has variable or missing video timestamps; prepare a CFR mezzanine at {} fps first".format(fps))


def render(ffmpeg, ffprobe, source, outfile, work, spans, fps, sample_rate, crf, preset):
    inputs, parts = [], []
    samples_per_frame = sample_rate // fps
    total_frames = spans[-1]["out_out_f"]
    total_samples = total_frames * samples_per_frame
    for i, span in enumerate(spans):
        count = span["src_out_f"] - span["src_in_f"]
        samples = count * samples_per_frame
        inputs += ["-ss", "{:.9f}".format(span["src_in_f"] / fps),
                   "-t", "{:.9f}".format(count / fps + .4), "-i", str(source)]
        # Accurate input seeking on the verified CFR mezzanine avoids rescanning
        # the entire source per span. Normalize BEFORE exact frame/sample trims.
        parts.append("[{}:v:0]setpts=PTS-STARTPTS,fps=fps={}:start_time=0,trim=end_frame={},setpts=PTS-STARTPTS[v{}]".format(i, fps, count, i))
        fade = min(round(sample_rate * .003), samples)
        parts.append("[{}:a:0]asetpts=PTS-STARTPTS,aresample={}:first_pts=0,atrim=end_sample={},asetpts=PTS-STARTPTS,afade=t=in:ss=0:ns={},afade=t=out:ss={}:ns={}[a{}]".format(
            i, sample_rate, samples, fade, max(0, samples - fade), fade, i))
    parts.append("".join("[v{}][a{}]".format(i, i) for i in range(len(spans))) +
                 "concat=n={}:v=1:a=1[v][joined]".format(len(spans)))
    # PCM is the sample-count authority; AAC carries encoder padding even when
    # its MP4 presentation duration is exact.
    parts.append("[joined]atrim=end_sample={},asplit=2[a][pcm]".format(total_samples))
    graph = work / "filter.txt"
    graph.write_text(";\n".join(parts) + "\n")
    pcm = work / "dialogue.wav"
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n", *inputs,
           "-filter_complex_script", str(graph), "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-crf", str(crf), "-preset", preset, "-g", str(fps),
           "-keyint_min", str(fps), "-pix_fmt", "yuv420p", "-r", str(fps),
           "-video_track_timescale", str(fps * 1000), "-c:a", "aac", "-b:a", "192k",
           "-ar", str(sample_rate), "-movie_timescale", str(sample_rate), "-movflags", "+faststart", str(outfile),
           "-map", "[pcm]", "-c:a", "pcm_s16le", "-ar", str(sample_rate), str(pcm)]
    write_json(work / "render-command.json", cmd)
    run(cmd)
    import wave
    with wave.open(str(pcm), "rb") as wav:
        if wav.getnframes() != total_samples or wav.getframerate() != sample_rate:
            raise CutError("PCM sample count mismatch: expected {}, got {}. Inspect short source streams.".format(total_samples, wav.getnframes()))
    meta = probe(ffprobe, outfile)
    video = next(s for s in meta["streams"] if s["codec_type"] == "video")
    audio = next(s for s in meta["streams"] if s["codec_type"] == "audio")
    if int(video.get("nb_frames", -1)) != total_frames:
        raise CutError("Final frame count differs from EDL")
    if abs(float(audio["duration"]) - total_frames / fps) > 1 / sample_rate + 1e-6:
        raise CutError("Final audio presentation duration {} differs from EDL {}".format(audio["duration"], total_frames / fps))
    run([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(outfile), "-f", "null", "-"])
    write_json(work / "render-verification.json", {"frames": total_frames,
               "pcm_samples": total_samples, "sample_rate": sample_rate,
               "duration": total_frames / fps, "full_decode": "passed", "probe": meta})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", type=Path, default=Path("source.mp4"))
    parser.add_argument("--lines", type=Path, default=Path("edl-lines.json"))
    parser.add_argument("--transcript", type=Path, default=Path("transcript.json"))
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--edge", type=float, default=.03)
    parser.add_argument("--noise", type=float, default=-30)
    parser.add_argument("--minpause", type=float, default=.13)
    parser.add_argument("--crf", type=int, default=16)
    parser.add_argument("--preset", default="medium", choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.version) or args.version in (".", ".."):
        raise CutError("Version must be a simple filename component, e.g. v1 or v1.1")
    if args.fps <= 0 or args.sample_rate <= 0 or args.sample_rate % args.fps:
        raise CutError("Sample rate must be a positive integer multiple of positive integer FPS (e.g. 44100/30 or 48000/30)")
    if (not all(math.isfinite(v) for v in (args.edge, args.noise, args.minpause)) or
            args.edge < 0 or args.minpause <= 0 or not 0 <= args.crf <= 51):
        raise CutError("Invalid cut/encode parameters: edge >= 0, minpause > 0, finite thresholds, CRF 0..51")
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise CutError("Project directory does not exist")
    paths = [(p if p.is_absolute() else project / p).resolve() for p in (args.source, args.lines, args.transcript)]
    source, lines_path, transcript_path = paths
    for path in paths:
        if not path.is_file():
            raise CutError("Input file does not exist: {}".format(path))
    work = project / "_cut_work" / args.version
    outfile = project / "base-cut-{}.mp4".format(args.version)
    if work.exists() or outfile.exists():
        raise CutError("Version/output already exists; choose a new --version. Nothing overwritten.")
    ffmpeg, ffprobe = binary("FFMPEG", "FFMPEG_PATH"), binary("FFPROBE", "FFPROBE_PATH")
    meta = probe(ffprobe, source)
    video = next((s for s in meta["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)
    if not video or not audio:
        raise CutError("Source must contain video and audio streams")
    vd = float(video.get("duration", meta["format"].get("duration", 0)))
    ad = float(audio.get("duration", meta["format"].get("duration", 0)))
    if not math.isfinite(vd) or not math.isfinite(ad) or min(vd, ad) <= 0:
        raise CutError("Cannot determine positive source video/audio duration")
    # Trims use streams rebased independently to zero. Offset streams require an
    # explicitly prepared/synchronised mezzanine, not a silent timing correction.
    if abs(float(video.get("start_time", 0)) - float(audio.get("start_time", 0))) > 1 / args.sample_rate + 1e-6:
        raise CutError("Source video/audio start times differ; synchronize a mezzanine first")
    verify_cfr(ffprobe, source, video, args.fps)
    duration = min(vd, ad)
    lines, words, input_warnings = load_inputs(lines_path, transcript_path, duration)
    max_frames = math.floor(duration * args.fps + 1e-7)
    work.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    write_json(work / "inputs.json", {"source": str(source), "sha256": digest.hexdigest(),
               "lines": lines, "transcript": words, "settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}})
    pauses = find_pauses(ffmpeg, source, args.noise, args.minpause, duration, work / "silencedetect.log")
    write_json(work / "pauses.json", pauses)
    spans, notes = build_spans(lines, pauses, args.fps, max_frames, args.edge, args.minpause)
    mapped, warnings = remap_words(lines, words, spans, args.sample_rate)
    warnings = input_warnings + warnings
    total_frames = spans[-1]["out_out_f"]
    edl = {"fps": args.fps, "sampleRate": args.sample_rate, "source": str(source), "spans": spans,
           "newDuration": total_frames / args.fps, "totalFrames": total_frames,
           "totalSamples": total_frames * (args.sample_rate // args.fps),
           "edge": args.edge, "noise": args.noise, "minPause": args.minpause}
    write_json(work / "edl.json", edl)
    write_json(work / "words-cut.json", mapped)
    write_json(work / "words-master.json", [{k: w[k] for k in ("text", "start", "end")} for w in mapped])
    write_json(work / "source-words.json", [{k: w[k] for k in ("text", "start", "end")} for w in words])
    write_json(work / "alignment-warnings.json", warnings)
    write_json(work / "qa-edl.json", {"fps": args.fps, "source": str(source), "windows": [
        {"src_in_f": s["src_in_f"], "src_out_f": s["src_out_f"],
         "master_in_f": s["out_in_f"], "master_out_f": s["out_out_f"],
         "raw_start": s["src_in"], "raw_end": s["src_out"],
         "master_start": s["out_in"], "master_end": s["out_out"]} for s in spans]})
    write_json(work / "quantization-notes.json", notes)
    report = ["{}: source [{:.4f}, {:.4f}] -> output [{:.4f}, {:.4f}]".format(
        s["id"], s["src_in"], s["src_out"], s["out_in"], s["out_out"]) for s in spans]
    report.append("{} spans; {} frames; {:.6f}s; {} alignment warnings".format(len(spans), total_frames, total_frames / args.fps, len(warnings)))
    (work / "cut-report.txt").write_text("\n".join(report) + "\n")
    print(report[-1], flush=True)
    print("Artifacts: {}".format(work), flush=True)
    if args.no_render:
        print("Plan only. This version is reserved; use a new version to render.")
        return
    render(ffmpeg, ffprobe, source, outfile, work, spans, args.fps, args.sample_rate, args.crf, args.preset)
    print("Verified: {}".format(outfile))


if __name__ == "__main__":
    try:
        main()
    except (CutError, OSError, ValueError, KeyError) as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
