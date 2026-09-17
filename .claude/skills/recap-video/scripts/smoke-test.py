#!/usr/bin/env python3
"""Local regression smoke test; temporary 4-second fixtures, no API calls."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("assemble.py")
spec = importlib.util.spec_from_file_location("recap_assemble", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FF = module.binary("FFMPEG", "FFMPEG_PATH")


def command(args, success=True):
    result = subprocess.run(args, capture_output=True, text=True)
    if success and result.returncode:
        raise AssertionError(result.stderr + result.stdout)
    if not success and result.returncode == 0:
        raise AssertionError("Expected failure: {}".format(args))
    return result


def write(path, value):
    path.write_text(json.dumps(value))


def frame(path, index):
    return subprocess.check_output([FF, "-nostdin", "-v", "error", "-i", str(path),
        "-vf", "select=eq(n\\,{})".format(index), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])


def main():
    lines = [
        {"id": "late", "in": 2, "out": 3, "raw": True},
        {"id": "first", "in": 0, "out": 1.01, "raw": True},
        {"id": "abut", "in": 1.01, "out": 2, "raw": True, "veto": [[1.45, 1.55]]},
        {"id": "repeat", "in": 0, "out": 1, "raw": True},
        {"id": "overlap", "in": .5, "out": 1.2, "raw": True},
        {"id": "silence", "in": 1, "out": 2},
    ]
    words = {"words": [
        {"word": "zero", "start": .1, "end": .3},
        {"word": "padded", "start": 1.18, "end": 1.65},
        {"word": "insidepause", "start": 1.35, "end": 1.4},
        {"word": "later", "start": 2.1, "end": 2.3},
        {"word": "", "start": 3.1, "end": 3.2},
    ]}
    with tempfile.TemporaryDirectory(prefix="recap-smoke-") as directory:
        root = Path(directory)
        for rate in (44100, 48000):
            project = root / str(rate)
            project.mkdir()
            source = project / "source.mov"
            command([FF, "-nostdin", "-v", "error", "-n", "-f", "lavfi", "-i",
                     "testsrc2=size=96x96:rate=30:duration=4", "-f", "lavfi", "-i",
                     "aevalsrc=if(between(t\\,1.2\\,1.6)\\,0\\,0.3*sin(2*PI*440*t)):s={}:d=4".format(rate),
                     "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                     "-c:a", "pcm_s16le", "-video_track_timescale", "30000", str(source)])
            write(project / "edl-lines.json", lines)
            write(project / "transcript.json", words)
            base = [sys.executable, str(SCRIPT), "--project", str(project), "--source", "source.mov",
                    "--fps", "30", "--sample-rate", str(rate), "--preset", "ultrafast"]
            command(base + ["--version", "v1"])
            work = project / "_cut_work" / "v1"
            edl = json.loads((work / "edl.json").read_text())
            spans = edl["spans"]
            assert spans[0]["src_in_f"] == 60, "List order lost"
            assert spans[1]["src_in_f"] == 0, "Backward reorder lost"
            for output_index, source_index in ((0, 60), (30, 0)):
                actual = frame(project / "base-cut-v1.mp4", output_index)
                expected = frame(source, source_index)
                assert len(actual) == len(expected) == 96 * 96 * 3
                assert sum(abs(a - b) for a, b in zip(actual, expected)) / len(actual) < 5, "Rendered pixels do not follow source reorder"
            abut = [s for s in spans if s["id"] == "abut"]
            assert abut[0]["src_in_f"] == 31, "Quantization overlap duplicated a frame"
            assert all(s["src_out_f"] <= 43 or s["src_in_f"] >= 47 for s in abut), "Raw mode ignored hard veto"
            overlap = next(s for s in spans if s["id"] == "overlap")
            assert overlap["src_in_f"] == 15, "Intentional overlap was clamped"
            silence = [s for s in spans if s["id"] == "silence"]
            assert len(silence) == 2, "Internal pause not cut"
            mapped = json.loads((work / "words-cut.json").read_text())
            assert mapped[0]["text"] == "later", "Words not in playback order"
            assert len([w for w in mapped if w["text"] == "zero"]) == 2, "Reused source word occurrence lost"
            assert any(w["text"] == "padded" and w["id"] == "silence" and w["alignment"] == "inspect" for w in mapped)
            warnings = json.loads((work / "alignment-warnings.json").read_text())
            assert any(w["kind"] == "empty_transcript_token" for w in warnings), "Blank placeholder not recorded"
            assert any(w.get("text") == "insidepause" and w.get("id") == "silence" and w["kind"] == "unmapped_word" for w in warnings), "Removed word silently lost"
            with wave.open(str(work / "dialogue.wav"), "rb") as wav:
                assert wav.getnframes() == edl["totalFrames"] * (rate // 30)
                assert wav.getframerate() == rate
            verification = json.loads((work / "render-verification.json").read_text())
            assert verification["frames"] == edl["totalFrames"]
            assert verification["full_decode"] == "passed"
            original = (project / "base-cut-v1.mp4").read_bytes()
            refusal = command(base + ["--version", "v1"], success=False)
            assert "already exists" in refusal.stderr
            assert original == (project / "base-cut-v1.mp4").read_bytes()
            command(base + ["--version", "plan", "--no-render"])
            assert not (project / "base-cut-plan.mp4").exists()
            assert (project / "_cut_work" / "plan" / "qa-edl.json").exists()
            command(base + ["--version", "plan", "--no-render"], success=False)
            # Resampling must occur before sample trims, not after them.
            opposite = 48000 if rate == 44100 else 44100
            command(base + ["--sample-rate", str(opposite), "--version", "resampled"])
            switched = json.loads((project / "_cut_work" / "resampled" / "render-verification.json").read_text())
            assert switched["pcm_samples"] == edl["totalFrames"] * (opposite // 30)
            # Fail preflight, before reserving or rendering a version.
            write(project / "bad-lines.json", [{"in": 0, "out": 99}])
            command(base + ["--version", "bad-range", "--lines", "bad-lines.json"], success=False)
            write(project / "duplicate-lines.json", [lines[0], lines[0]])
            duplicate = command(base + ["--version", "duplicate", "--lines", "duplicate-lines.json"], success=False)
            assert "unique nonempty id" in duplicate.stderr
            command(base + ["--version", "bad-rate", "--fps", "29"], success=False)
            noaudio = project / "noaudio.mov"
            command([FF, "-nostdin", "-v", "error", "-n", "-i", str(source), "-an", "-c:v", "copy", str(noaudio)])
            missing = command(base + ["--version", "noaudio", "--source", "noaudio.mov"], success=False)
            assert "video and audio" in missing.stderr
            # Same source name changed to silence: a new version must re-detect it.
            changed = project / "changed.mov"
            command([FF, "-nostdin", "-v", "error", "-n", "-i", str(source), "-af", "volume=0",
                     "-c:v", "copy", "-c:a", "pcm_s16le", str(changed)])
            os.replace(changed, source)
            command(base + ["--version", "changed", "--no-render"])
            changed_edl = json.loads((project / "_cut_work" / "changed" / "edl.json").read_text())
            assert not any(s["id"] == "silence" for s in changed_edl["spans"]), "Stale pause cache"
            print("PASS 30 fps / {} Hz: {} frames, {} samples; reorder/reuse/overlap/veto/raw/words/resampling/no-render/refusal/input-validation/fresh-source".format(
                rate, edl["totalFrames"], edl["totalSamples"]))
        print("All recap assembler smoke tests passed; temporary fixtures removed.")


if __name__ == "__main__":
    main()
