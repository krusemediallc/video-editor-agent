#!/usr/bin/env python3
"""Build and verify a tiny synthetic edit, project state, library, QA and review canvas.

All media is generated locally. No model downloads, paid APIs, or publishing.
The colored card is a test fixture; composition.html describes its timed layout.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

from setup import binary, node_ready, qa_ready

ROOT = Path(__file__).resolve().parent.parent


def run(command, allowed=(0,), capture=False):
    command = [str(item) for item in command]
    print("RUN  " + shlex.join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, capture_output=capture, text=capture)
    if result.returncode not in allowed:
        if capture:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        raise RuntimeError("Command failed with exit {}: {}".format(result.returncode, command[0]))
    return result


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def check_prerequisites():
    missing = []
    if sys.version_info < (3, 10):
        missing.append("Python 3.10+")
    for name in ("ffmpeg", "ffprobe"):
        if not binary(name):
            missing.append(name)
    if not node_ready() or not shutil.which("npm"):
        missing.append("Node.js 20+ with npm")
    if not qa_ready(ROOT):
        missing.append("video QA dependencies")
    if missing:
        raise RuntimeError("Missing {}. Run bash scripts/setup.sh --lane demo first.".format(", ".join(missing)))
    required = ("tools/editor/editor.py", "tools/video-qa/cli/qa-storyboard.ts",
                ".claude/skills/video-review-canvas/scripts/build-canvas.mjs")
    for path in required:
        if not (ROOT / path).is_file():
            raise RuntimeError("Incomplete checkout: missing " + path)


def verify_overlay(ffmpeg, video, output):
    samples = []
    for time in (.5, 2, 3.5):
        pixels = subprocess.check_output([ffmpeg, "-nostdin", "-v", "error", "-ss", str(time),
                                          "-i", str(video), "-vf", "crop=64:16:32:32,format=rgb24",
                                          "-frames:v", "1", "-f", "rawvideo", "-"])
        if len(pixels) != 64 * 16 * 3:
            raise RuntimeError("Could not decode the demo overlay probe")
        rgb = [sum(pixels[channel::3]) / (64 * 16) for channel in range(3)]
        green = max(abs(a - b) for a, b in zip(rgb, (61, 220, 132))) < 15
        expected = time == 2
        if green != expected:
            raise RuntimeError("Demo proof card pixel check failed at {}s".format(time))
        samples.append({"time": time, "meanRGB": rgb, "expectedCardVisible": expected, "passed": True})
    write_json(output, {"status": "passed", "method": "decoded RGB sample of known synthetic card region", "samples": samples})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new output directory; existing paths are never overwritten")
    args = parser.parse_args()
    check_prerequisites()
    label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    requested = args.output.expanduser() if args.output else ROOT / "outputs" / ("demo-" + label)
    if os.path.lexists(requested):
        raise RuntimeError("Output already exists; choose a new --output. Nothing overwritten: " + str(requested))
    out = requested.resolve()
    out.mkdir(parents=True)
    ffmpeg, ffprobe = binary("ffmpeg"), binary("ffprobe")
    # Source: exactly 180 CFR frames and 288,000 presentation samples.
    run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
         "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
         "-af", "volume=8dB",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movie_timescale", "48000",
         "-movflags", "+faststart", out / "source.mp4"])
    write_json(out / "edl-lines.json", [
        {"id": "ending-first", "in": 4, "out": 6, "raw": True, "text": "Synthetic late source segment"},
        {"id": "opening-second", "in": 0, "out": 2, "raw": True, "text": "Synthetic early source segment"},
    ])
    write_json(out / "transcript.json", {"words": [], "note": "Synthetic tone; no spoken words or ASR needed."})
    run([sys.executable, ROOT / ".claude/skills/recap-video/scripts/assemble.py", "--project", out,
         "--version", "v1", "--fps", "30", "--sample-rate", "48000", "--preset", "ultrafast"])
    render = out / "output-v2.mp4"
    run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n", "-i", out / "base-cut-v1.mp4",
         "-vf", "drawbox=x=24:y=24:w=272:h=56:color=0x3ddc84:t=fill:enable='gte(t,1)*lt(t,3)'",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", render])
    # The fixture uses ffmpeg, so this HTML is an intent manifest rather than the renderer.
    (out / "composition.html").write_text('''<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Synthetic demo storyboard</title>
<body style="margin:0;background:#101010;color:white;font-family:system-ui">
<p>Test fixture: this HTML records intended output timing. The demo renderer is ffmpeg.</p>
<div class="clip" data-start="0" data-duration="4" style="position:relative;width:320px;height:180px">
<video src="base-cut-v1.mp4" controls style="width:320px;height:180px"></video>
<div id="proof-card" class="clip" data-start="1" data-duration="2"
style="position:absolute;left:24px;top:24px;width:272px;height:56px;background:#3ddc84"></div>
</div></body></html>\n''')
    write_json(out / "storyboard.json", {"version": 1, "elements": [
        {"id": "proof-card", "start": 1, "end": 3, "selector": "#proof-card"}
    ]})
    qa_dir = out / "_qa"
    qa_dir.mkdir()
    verify_overlay(ffmpeg, render, qa_dir / "demo-pixel-proof.json")
    qa_command = ["npm", "--prefix", ROOT / "tools/video-qa", "run"]
    run([*qa_command, "qa:storyboard", "--", "--storyboard", out / "storyboard.json",
         "--html", out / "composition.html", "--video", render, "--out", qa_dir / "storyboard"])
    # Tone fixture has no transcript. Semantic/model checks stay explicitly disabled.
    run([*qa_command, "qa:video", "--", "--video", render, "--skip-semantic", "--require-layers", "technical",
         "--out", qa_dir / "technical"], allowed=(0, 1))
    review = {
        "outDir": "review", "title": "Local editing demo", "version": "v2",
        "eyebrow": "SYNTHETIC FIXTURE · EDIT REVIEW", "author": "Reviewer",
        "blurb": "Compare the initial cut with the added green card. Audio is a synthetic tone.",
        "playerWidth": "min(84vw,800px)", "storage": {"mode": "local", "key": "demo-review-" + label},
        "versions": [
            {"version": "v1", "video": "base-cut-v1.mp4", "label": "Initial cut",
             "beats": [{"t": 0, "n": "Reordered source", "s": "Final two seconds first"}]},
            {"version": "v2", "video": "output-v2.mp4", "label": "Card added",
             "beats": [{"t": 1, "n": "Green card", "s": "Visible from 1 to 3 seconds"}]},
        ],
        "reviewData": {"comments": [{"id": "demo-note", "createdAt": "2026-01-01T12:00:00Z", "data": {
            "t": 2, "frame": 60, "fps": 30, "text": "Add a green card at this beat.", "author": "Reviewer", "version": "v1"}}],
            "events": [
                {"id": "demo-evidence", "createdAt": "2026-01-01T12:01:00Z", "data": {
                    "commentId": "demo-note", "kind": "evidence", "text": "Card is visible between 1 and 3 seconds; decoded pixels verified.",
                    "beforeVersion": "v1", "beforeT": 2, "beforeFrame": 60,
                    "afterVersion": "v2", "afterT": 2, "afterFrame": 60, "author": "Editor"}},
                {"id": "demo-resolved", "createdAt": "2026-01-01T12:02:00Z", "data": {
                    "commentId": "demo-note", "kind": "status", "status": "resolved", "author": "Editor"}}
            ]}
    }
    write_json(out / "review-config.json", review)
    run(["node", ROOT / ".claude/skills/video-review-canvas/scripts/build-canvas.mjs", out / "review-config.json"])
    editor = [sys.executable, ROOT / "tools/editor/editor.py"]
    run([*editor, "project", "init", out, "--name", "Local editing demo", "--lane", "recap-video", "--source", out / "source.mp4"], capture=True)
    run([*editor, "catalog", "ingest", out / "catalog.json", out / "source.mp4", "--transcript", out / "transcript.json", "--tag", "demo"], capture=True)
    run([*editor, "project", "checkpoint", out, "ingest", "--artifact", out / "catalog.json"], capture=True)
    run([*editor, "project", "render", out, out / "base-cut-v1.mp4", "--version", "v1"], capture=True)
    run([*editor, "project", "render", out, render, "--version", "v2"], capture=True)
    run([*editor, "project", "checkpoint", out, "edit", "--artifact", render], capture=True)
    run([*editor, "project", "checkpoint", out, "qa", "--artifact", qa_dir / "storyboard/storyboard-report.json",
         "--artifact", qa_dir / "technical/qa-report.json", "--artifact", qa_dir / "demo-pixel-proof.json"], capture=True)
    run([*editor, "project", "checkpoint", out, "review", "--artifact", out / "review/index.html"], capture=True)
    status = run([*editor, "project", "status", out, "--json"], capture=True)
    (out / "project-status.json").write_text(status.stdout)
    search = run([*editor, "catalog", "search", out / "catalog.json", "demo", "--json"], capture=True)
    (out / "catalog-search.json").write_text(search.stdout)
    meta = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(render)], text=True))
    video_stream = next(stream for stream in meta["streams"] if stream["codec_type"] == "video")
    if int(video_stream["nb_frames"]) != 120:
        raise RuntimeError("Expected 120 demo output frames")
    write_json(out / "demo-result.json", {"status": "passed", "frames": 120, "duration": 4,
        "video": "output-v2.mp4", "review": "review/index.html", "project": "project.json",
        "catalog": "catalog.json", "storyboard": "_qa/storyboard/storyboard-report.json",
        "pixelProof": "_qa/demo-pixel-proof.json", "paidCalls": 0, "modelDownloads": 0})
    serve_command = "python3 " + shlex.quote(str(ROOT / "scripts/serve-review.py")) + " --directory " + shlex.quote(str(out / "review")) + " --port 8765"
    (out / "README.md").write_text("# Local synthetic demo\n\nServe the review with `" + serve_command + "`, "
        "then open http://127.0.0.1:8765 to compare v1/v2 and inspect the resolved note. "
        "Review notes persist in this browser; use Export revisions to share them. No upload was performed.\n\n"
        "`output-v2.mp4` is a 4-second edit of locally generated footage. Its green card is visible from 1–3 seconds. "
        "The synthetic tone has no speech. `composition.html` is the timing manifest for the ffmpeg-rendered test card.\n\n"
        "`_qa/` contains storyboard samples, a decoded-pixel check and technical QA. "
        "Missing transcript/semantic layers are explicitly skipped; this fixture does not establish speech or editorial quality.\n")
    print("\nDemo complete: " + str(out))
    print("Review: " + str(out / "review/index.html"))
    print("Serve review: " + serve_command)
    print("Then open http://127.0.0.1:8765 (Ctrl-C stops the server; --port 0 chooses a free port).")
    print("Project status: python3 tools/editor/editor.py project status " + shlex.quote(str(out)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
