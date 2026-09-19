#!/usr/bin/env python3
"""Run local regression suites without installing dependencies or calling models."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from setup import binary, node_ready, qa_ready

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration", action="store_true", help="include recap assembler and complete demo with generated media")
    args = parser.parse_args()
    env = dict(os.environ, VIDEO_QA_LIVE_TESTS="0", EDITOR_INTEGRATION_TESTS="1" if args.integration else "0")
    commands = [[sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests", "-p", "test_*.py", "-v"]]
    if (ROOT / "tools/editor/tests").is_dir():
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tools/editor/tests", "-p", "test_*.py", "-v"])
    canvas_tests = sorted((ROOT / ".claude/skills/video-review-canvas").glob("tests/*.test.mjs"))
    if canvas_tests and node_ready():
        commands.append(["node", "--test", *map(str, canvas_tests)])
    elif canvas_tests:
        print("SKIP  review canvas suite: Node.js 20+ is unavailable", flush=True)
    if node_ready() and qa_ready(ROOT) and shutil.which("npm") and binary("ffmpeg") and binary("ffprobe"):
        commands.extend([["npm", "--prefix", "tools/video-qa", "run", "typecheck"],
                         ["npm", "--prefix", "tools/video-qa", "test"]])
    elif args.integration:
        print("FAIL: integration needs Node.js 20+, ffmpeg/ffprobe and QA dependencies. Run bash scripts/setup.sh --lane demo.", file=sys.stderr)
        return 1
    else:
        print("SKIP  video QA suite: install its prerequisites with bash scripts/setup.sh --lane qa", flush=True)
    if args.integration:
        commands.append([sys.executable, ".claude/skills/recap-video/scripts/smoke-test.py"])
    for command in commands:
        print("\nTEST  " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    print("\nAll available offline suites passed." if not args.integration else "\nAll offline and media integration suites passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
