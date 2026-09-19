#!/usr/bin/env python3
"""Idempotent workspace setup and offline, workflow-specific dependency checks."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
LANES = ("local", "demo", "qa", "hyperframes", "sound-design", "all")


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def binary(name):
    return shutil.which(os.environ.get(name.upper()) or os.environ.get(name.upper() + "_PATH") or name)


def node_ready():
    node = shutil.which("node")
    if not node:
        return False
    try:
        return int(subprocess.check_output([node, "-p", "process.versions.node.split('.')[0]"], text=True).strip()) >= 20
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def qa_ready(root):
    node = shutil.which("node")
    if not node or not (root / "tools/video-qa/node_modules").is_dir():
        return False
    result = subprocess.run([node, "-e", "for (const p of ['tsx','typescript','dotenv','zod']) require.resolve(p)"],
                            cwd=root / "tools/video-qa", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def hyperframes_binary(root):
    for candidate in (root / "tools/hyperframes/node_modules/.bin/hyperframes",
                      root / "node_modules/.bin/hyperframes"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("hyperframes")


def has_key(root, name):
    # Never source .env as executable shell, and never print a secret.
    value = os.environ.get(name, "").strip()
    if not value and (root / ".env").is_file():
        for line in (root / ".env").read_text().splitlines():
            line = line.strip().removeprefix("export ")
            key, sep, item = line.partition("=")
            if sep and key.strip() == name:
                value = item.strip().strip("\"'")
    return bool(value and value.lower() not in {"your-key", "your_api_key", "replace_me", "..."})


def doctor(root, lane):
    results = []
    def check(ok, label, fix):
        results.append(bool(ok))
        print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + fix))
    print("Checking {} workflow (offline; {}):".format(lane, platform.system()))
    check(sys.version_info >= (3, 10), "Python 3.10+", "install a supported Python 3")
    for name in ("ffmpeg", "ffprobe"):
        check(binary(name), name, "install ffmpeg or set {} to the executable".format(name.upper()))
    check((root / "MASTER_CONTEXT.md").is_file(), "local project context", "run bash scripts/setup.sh --no-install")
    if lane != "local":
        check(node_ready(), "Node.js 20+", "install Node.js 20 or newer")
        check(shutil.which("npm"), "npm", "install npm with Node.js")
    if lane in ("demo", "qa", "all"):
        check(qa_ready(root), "video QA dependencies", "run bash scripts/setup.sh --lane " + lane)
    if lane in ("hyperframes", "all"):
        check(hyperframes_binary(root), "local HyperFrames CLI", "run bash scripts/setup.sh --lane hyperframes")
    if lane in ("sound-design", "all"):
        check(has_key(root, "ELEVENLABS_API_KEY"), "ElevenLabs key configured", "set ELEVENLABS_API_KEY in .env or the environment")
    else:
        print("SKIP  ElevenLabs, Gemini, transcription models and publishing credentials are optional for this workflow")
    failed = results.count(False)
    print("{} passed, {} required missing".format(sum(results), failed))
    return 1 if failed else 0


def copy_if_absent(source, destination, dry_run=False):
    # lexists includes dangling symlinks: an existing path is never replaced.
    if os.path.lexists(destination):
        print("KEEP  " + str(destination))
        return
    print(("PLAN  create " if dry_run else "CREATE  ") + str(destination))
    if not dry_run:
        with source.open("rb") as src, destination.open("xb") as dest:
            shutil.copyfileobj(src, dest)
        if destination.name == ".env":
            destination.chmod(0o600)


def link_skills(root, working_repo, dry_run=False):
    target = working_repo.expanduser().resolve()
    if not target.is_dir():
        raise ValueError("--link-skills must name an existing working directory: " + str(target))
    destination = target / ".claude/skills"
    sources = sorted(p for p in (root / ".claude/skills").iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
    for source in sources:
        link = destination / source.name
        if os.path.lexists(link):
            print("KEEP  existing skill " + str(link))
            continue
        relative = os.path.relpath(source, destination)
        print(("PLAN  link " if dry_run else "LINK  ") + str(link) + " -> " + relative)
        if not dry_run:
            destination.mkdir(parents=True, exist_ok=True)
            link.symlink_to(relative, target_is_directory=True)


def system_packages(lane, dry_run):
    missing = []
    if not binary("ffmpeg") or not binary("ffprobe"):
        missing.append("ffmpeg")
    if lane != "local" and (not node_ready() or not shutil.which("npm")):
        missing.append("node")
    if not missing:
        print("KEEP  system prerequisites already available")
        return
    if platform.system() == "Darwin" and shutil.which("brew"):
        command = ["brew", "install", *missing]
    elif platform.system() == "Linux" and shutil.which("apt-get"):
        packages = [p for name in missing for p in (["nodejs", "npm"] if name == "node" else [name])]
        command = (["sudo"] if os.geteuid() else []) + ["apt-get", "install", "-y", *packages]
    else:
        raise ValueError("Install ffmpeg and Node.js 20+ with your package manager, then rerun setup. Automatic system installation supports Homebrew and Debian/Ubuntu apt only.")
    print(("PLAN  " if dry_run else "RUN  ") + shlex.join(command))
    if not dry_run:
        run(command)


def install_dependencies(root, lane, dry_run):
    if lane in ("demo", "qa", "all"):
        qa = root / "tools/video-qa"
        lock = qa / "package-lock.json"
        fingerprint = hashlib.sha256(lock.read_bytes() + (qa / "package.json").read_bytes()).hexdigest()
        stamp = qa / "node_modules/.editor-setup-lock"
        if qa_ready(root) and stamp.is_file() and stamp.read_text().strip() == fingerprint:
            print("KEEP  video QA dependencies match package-lock.json")
        else:
            command = ["npm", "--prefix", str(qa), "ci", "--no-audit", "--no-fund"]
            print(("PLAN  " if dry_run else "RUN  ") + shlex.join(command))
            if not dry_run:
                if not node_ready() or not shutil.which("npm"):
                    raise ValueError("Node.js 20+ and npm are required before installing video QA dependencies.")
                run(command)
                stamp.write_text(fingerprint + "\n")
    if lane in ("hyperframes", "all"):
        if hyperframes_binary(root):
            print("KEEP  HyperFrames CLI available")
        else:
            command = ["npm", "install", "--prefix", str(root / "tools/hyperframes"),
                       "--no-save", "--no-package-lock", "--no-audit", "--no-fund", "hyperframes"]
            print(("PLAN  " if dry_run else "RUN  ") + shlex.join(command))
            if not dry_run:
                if not node_ready() or not shutil.which("npm"):
                    raise ValueError("Node.js 20+ and npm are required before installing HyperFrames.")
                run(command)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=LANES, help="default: local, or demo when --demo is used")
    parser.add_argument("--check", action="store_true", help="offline doctor only; never writes or installs")
    parser.add_argument("--dry-run", action="store_true", help="print actions without any writes or installs")
    parser.add_argument("--no-install", action="store_true", help="create local config/links but do not install dependencies")
    parser.add_argument("--install-system", action="store_true", help="explicitly allow Homebrew/apt system prerequisite installation")
    parser.add_argument("--link-skills", type=Path, metavar="WORKING_REPO", help="add missing relative .claude/skills symlinks")
    parser.add_argument("--demo", action="store_true", help="run the synthetic offline demo after setup")
    args = parser.parse_args(argv)
    lane = args.lane or ("demo" if args.demo else "local")
    if args.demo and lane not in ("demo", "all"):
        parser.error("--demo requires --lane demo or all")
    if args.no_install and args.install_system:
        parser.error("--no-install cannot be combined with --install-system")
    if args.check:
        return doctor(ROOT, lane)
    if sys.version_info < (3, 10):
        parser.error("Python 3.10+ is required")
    if args.install_system:
        system_packages(lane, args.dry_run)
    copy_if_absent(ROOT / ".env.example", ROOT / ".env", args.dry_run)
    copy_if_absent(ROOT / "MASTER_CONTEXT.template.md", ROOT / "MASTER_CONTEXT.md", args.dry_run)
    if args.link_skills:
        link_skills(ROOT, args.link_skills, args.dry_run)
    if not args.no_install:
        install_dependencies(ROOT, lane, args.dry_run)
    if args.dry_run:
        if args.demo:
            print("PLAN  run bash scripts/demo.sh")
        print("Dry run complete. No files, packages, or git configuration changed.")
        return 0
    status = doctor(ROOT, lane)
    if status:
        print("Install the missing prerequisites above, or rerun with --install-system where supported.")
        return status
    print("Setup ready. Personalize MASTER_CONTEXT.md before your first real edit.")
    if args.demo:
        run([sys.executable, ROOT / "scripts/demo.py"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
