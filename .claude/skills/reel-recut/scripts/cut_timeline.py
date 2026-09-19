#!/usr/bin/env python3
"""Bounded-memory frame/sample-grid cuts. Lossless chunks, one final AAC encode."""
import argparse
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import wave


def binary(env):
    return os.environ.get(env) or os.environ.get(env + "_PATH") or shutil.which(env.lower()) or str(Path("/opt/homebrew/bin") / env.lower())


def run(argv):
    result = subprocess.run([str(v) for v in argv], text=True, capture_output=True)
    if result.returncode:
        raise ValueError(f"{Path(str(argv[0])).name} failed: {result.stderr[-4000:]}")
    return result.stdout


def plan(keeps, fps=30, sample_rate=48000):
    rate = Fraction(str(fps)).limit_denominator(100000)
    if rate <= 0 or rate > 240 or sample_rate < 8000:
        raise ValueError("Invalid frame rate or sample rate")
    spans, normalized, total = [], [], 0
    for start, end in keeps:
        if not all(math.isfinite(float(v)) for v in (start, end)) or start < 0 or end <= start:
            raise ValueError("Keep intervals must be finite, nonnegative and nonempty")
        # Keep only frames completely inside the retained interval. One common
        # grid drives captions, video and cumulative audio sample counts.
        first = math.ceil(Fraction(str(start)) * rate - Fraction(1, 1000000))
        last = math.floor(Fraction(str(end)) * rate + Fraction(1, 1000000))
        if last <= first:
            continue
        count = last - first
        sample_start = round(Fraction(total * sample_rate, 1) / rate)
        sample_end = round(Fraction((total + count) * sample_rate, 1) / rate)
        spans.append({"sourceStartFrame": first, "sourceEndFrame": last, "frames": count,
                      "outputStartFrame": total, "samples": sample_end - sample_start})
        normalized.append([float(first / rate), float(last / rate)])
        total += count
    if not spans:
        raise ValueError("Cut removes every frame")
    return {"keeps": normalized, "spans": spans, "totalFrames": total,
            "totalSamples": round(Fraction(total * sample_rate, 1) / rate),
            "fps": str(rate), "sampleRate": sample_rate}


def render_base(source, output, work, keeps, fps=30, sample_rate=48000, crf=18,
                preset="veryfast", ffmpeg=None, ffprobe=None):
    source, output, work = Path(source).resolve(), Path(output).resolve(), Path(work).resolve()
    ffmpeg, ffprobe = ffmpeg or binary("FFMPEG"), ffprobe or binary("FFPROBE")
    if output.exists():
        raise ValueError(f"Output already exists; choose a new version: {output}")
    if work.exists():
        raise ValueError(f"Cut work directory already exists; choose a fresh directory: {work}")
    timeline = plan(keeps, fps, sample_rate)
    rate = Fraction(timeline["fps"])
    metadata = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", source]))
    if not any(s["codec_type"] == "video" for s in metadata["streams"]) or not any(s["codec_type"] == "audio" for s in metadata["streams"]):
        raise ValueError("Cut source needs video and audio streams")
    duration = float(metadata["format"]["duration"])
    if any(float(s["sourceEndFrame"] / rate) > duration + 1e-5 for s in timeline["spans"]):
        raise ValueError("Keep interval exceeds the source duration")
    work.mkdir(parents=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    (work / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")
    chunks = []
    for offset in range(0, len(timeline["spans"]), 16):
        batch = timeline["spans"][offset:offset + 16]
        inputs, filters = [], []
        for i, span in enumerate(batch):
            start = float(span["sourceStartFrame"] / rate)
            seconds = float(span["frames"] / rate)
            inputs.extend(["-threads", "1", "-ss", f"{start:.12f}", "-t", f"{seconds + .25:.12f}", "-i", source])
            filters.append(f"[{i}:v:0]setpts=PTS-STARTPTS,fps=fps={rate}:start_time=0,trim=end_frame={span['frames']},setpts=PTS-STARTPTS[v{i}]")
            fade = min(round(sample_rate * .003), max(1, span["samples"] // 2))
            filters.append(f"[{i}:a:0]asetpts=PTS-STARTPTS,aresample={sample_rate}:first_pts=0,atrim=end_sample={span['samples']},asetpts=PTS-STARTPTS,afade=t=in:ss=0:ns={fade},afade=t=out:ss={span['samples'] - fade}:ns={fade}[a{i}]")
        filters.append("".join(f"[v{i}]" for i in range(len(batch))) + f"concat=n={len(batch)}:v=1:a=0[joinedv]")
        # A one-frame video-only concat segment has no timestamp delta. Rebuild
        # the batch grid before the encoder can collapse coincident timestamps.
        filters.append(f"[joinedv]setpts=N/({rate}*TB)[v]")
        filters.append("".join(f"[a{i}]" for i in range(len(batch))) + f"concat=n={len(batch)}:v=0:a=1[a]")
        graph = work / f"batch-{len(chunks):04}.txt"
        graph.write_text(";\n".join(filters))
        chunk = work / f"batch-{len(chunks):04}.mkv"
        run([ffmpeg, "-nostdin", "-v", "error", "-n", *inputs, "-filter_complex_threads", "1",
             "-filter_complex_script", graph, "-map", "[v]", "-map", "[a]", "-c:v", "ffv1", "-threads", "1",
             "-pix_fmt", "yuv420p", "-r", str(rate), "-c:a", "pcm_s16le", "-ar", sample_rate, chunk])
        chunks.append(chunk)
    # Relative generated filenames avoid quoting arbitrary source paths in concat syntax.
    playlist = work / "chunks.ffconcat"
    playlist.write_text("ffconcat version 1.0\n" + "".join(f"file '{p.name}'\n" for p in chunks))
    pcm = work / "dialogue.wav"
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-n", "-f", "concat", "-safe", "1", "-i", playlist,
           "-filter_complex", f"[0:v]setpts=N/({rate}*TB)[v];[0:a]asetpts=N/SR/TB,asplit=2[a][pcm]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", crf, "-preset", preset, "-r", str(rate),
           "-pix_fmt", "yuv420p", "-video_track_timescale", rate.numerator,
           "-c:a", "aac", "-b:a", "192k", "-ar", sample_rate, "-movie_timescale", sample_rate,
           "-movflags", "+faststart", output, "-map", "[pcm]", "-c:a", "pcm_s16le", pcm]
    (work / "render-command.json").write_text(json.dumps([str(v) for v in cmd], indent=2))
    run(cmd)
    final = json.loads(run([ffprobe, "-v", "error", "-count_frames", "-show_streams", "-of", "json", output]))
    video = next(s for s in final["streams"] if s["codec_type"] == "video")
    audio = next(s for s in final["streams"] if s["codec_type"] == "audio")
    with wave.open(str(pcm)) as wav:
        samples = wav.getnframes()
    frames = int(video["nb_read_frames"])
    if frames != timeline["totalFrames"] or samples != timeline["totalSamples"]:
        raise ValueError(f"Render differs from planned grid: frames {frames}/{timeline['totalFrames']}, samples {samples}/{timeline['totalSamples']}")
    expected_duration = float(Fraction(frames, 1) / rate)
    if abs(float(audio["duration"]) - expected_duration) > 1 / sample_rate + 1e-6:
        raise ValueError("Encoded audio presentation duration does not match the planned grid")
    run([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", output, "-f", "null", "-"])
    receipt = {"frames": frames, "pcmSamples": samples, "duration": expected_duration, "fps": str(rate),
               "sampleRate": sample_rate, "spans": len(timeline["spans"]), "fullDecode": "passed"}
    (work / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "work", "keeps"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--fps", default="30")
    p.add_argument("--sample-rate", type=int, default=48000)
    a = p.parse_args()
    try:
        print(json.dumps(render_base(a.source, a.output, a.work, json.loads(Path(a.keeps).read_text()), a.fps, a.sample_rate), indent=2))
    except (ValueError, OSError) as exc:
        p.exit(2, f"cut-timeline: {exc}\n")
