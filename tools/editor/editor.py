#!/usr/bin/env python3
"""Local project state and footage library. Run with --help for commands."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import catalog
import project


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    groups = p.add_subparsers(dest="group", required=True)
    projects = groups.add_parser("project", help="Durable edit state, checkpoints and resume")
    commands = projects.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    init.add_argument("path")
    init.add_argument("--name")
    init.add_argument("--lane", choices=project.LANES, default="reel-recut")
    init.add_argument("--source", action="append", required=True)
    init.add_argument("--style")
    init.add_argument("--sound", action="store_true", help="Include the sound-design stage")
    for name in ("status", "resume"):
        item = commands.add_parser(name)
        item.add_argument("path")
        item.add_argument("--json", action="store_true")
        if name == "resume":
            item.add_argument("--run", action="store_true", help="Execute just the next configured stage; default only prints context")
    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("path")
    checkpoint.add_argument("stage", choices=project.STAGES)
    checkpoint.add_argument("--artifact", action="append", default=[])
    checkpoint.add_argument("--skip", metavar="REASON")
    cfg = commands.add_parser("configure")
    cfg.add_argument("path")
    cfg.add_argument("stage", choices=project.STAGES)
    cfg.add_argument("--command", required=True, help='JSON argv, e.g. ["python3", "build.py"]; runs in project directory')
    cfg.add_argument("--artifact", action="append", default=[], help="Expected output path, relative to project")
    recover = commands.add_parser("recover")
    recover.add_argument("path")
    recover.add_argument("stage", choices=project.STAGES)
    recover.add_argument("--reason", required=True)
    render = commands.add_parser("render")
    render.add_argument("path")
    render.add_argument("video")
    render.add_argument("--version", required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("path")
    approve.add_argument("version")
    approve.add_argument("--reason", required=True, help="Record the user's actual sign-off")
    note = commands.add_parser("note")
    note.add_argument("path")
    note.add_argument("--text")
    note.add_argument("--id")
    note.add_argument("--status", choices=("open", "resolved"), default="open")
    note.add_argument("--version")
    note.add_argument("--evidence", action="append")
    imp = commands.add_parser("import-review")
    imp.add_argument("path")
    imp.add_argument("export")
    lib = groups.add_parser("catalog", help="Index, annotate and search reusable footage")
    commands = lib.add_subparsers(dest="action", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("path", help="Catalog JSON path")
    ingest.add_argument("media", nargs="+")
    ingest.add_argument("--recursive", action="store_true")
    ingest.add_argument("--transcript", help="Source-time word/segment JSON for one input")
    ingest.add_argument("--tag", action="append")
    ingest.add_argument("--transcribe", action="store_true", help="Run installed local whisper-cli; no cloud or downloads")
    ingest.add_argument("--whisper-model")
    ingest.add_argument("--whisper-bin")
    search = commands.add_parser("search")
    search.add_argument("path")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--tag")
    search.add_argument("--unused", action="store_true")
    search.add_argument("--json", action="store_true")
    annotate = commands.add_parser("annotate")
    annotate.add_argument("path")
    annotate.add_argument("asset")
    annotate.add_argument("--label")
    annotate.add_argument("--tag", action="append")
    annotate.add_argument("--interval", nargs=3, metavar=("START", "END", "LABEL"))
    annotate.add_argument("--restriction")
    use = commands.add_parser("use")
    use.add_argument("path")
    use.add_argument("asset")
    use.add_argument("--project", required=True)
    use.add_argument("--version")
    use.add_argument("--start", type=float)
    use.add_argument("--end", type=float)
    return p


def run(args):
    if args.group == "project":
        a = args.action
        if a == "init":
            return project.create(args.path, args.name, args.lane, args.source, args.style, args.sound)
        if a in ("status", "resume"):
            if getattr(args, "run", False):
                return project.run_next(args.path)
            result = project.status(args.path)
            if not args.json:
                print(f"{result['name']} · {result['lane']}")
                for stage in result["stages"]:
                    print(f"  {stage['id']:8} {stage['status']:9} {'; '.join(stage['reasons'])}")
                next_stage = result["nextStage"]
                print(f"Next: {next_stage['id']} → {next_stage['skill']}" if next_stage else "All stages complete.")
                print(f"Current render: {result['currentRender'] or 'none'} · open notes: {len(result['openNotes'])}")
                if a == "resume":
                    print("\nResume context (source paths relative to project.json):")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                return None
            return result
        if a == "checkpoint":
            return project.checkpoint(args.path, args.stage, args.artifact, args.skip)
        if a == "configure":
            return project.configure(args.path, args.stage, json.loads(args.command), args.artifact)
        if a == "recover":
            return project.recover(args.path, args.stage, args.reason)
        if a == "render":
            return project.render(args.path, args.video, args.version)
        if a == "approve":
            return project.approve(args.path, args.version, args.reason)
        if a == "note":
            return project.note(args.path, args.text, args.id, args.status, args.version, args.evidence)
        if a == "import-review":
            return project.import_review(args.path, args.export)
    if args.action == "ingest":
        return catalog.ingest(args.path, args.media, args.recursive, args.transcript, args.tag, args.transcribe, args.whisper_model, args.whisper_bin)
    if args.action == "annotate":
        return catalog.annotate(args.path, args.asset, args.label, args.tag, args.interval, args.restriction)
    if args.action == "use":
        return catalog.record_use(args.path, args.asset, args.project, args.version, args.start, args.end)
    matches = catalog.search(args.path, args.query, args.tag, args.unused)
    if args.json:
        return matches
    for asset in matches:
        print(f"{asset['id']}  {asset['label']}  {asset['duration']:.2f}s  uses={len(asset['uses'])}")
        print(f"  {asset['availablePath'] or 'Media offline'}")
        if asset["restrictions"]:
            print("  Restrictions: " + "; ".join(asset["restrictions"]))
        for segment in asset["matchingPhrases"]:
            print(f"  {segment['start']:.2f}–{segment['end']:.2f}: {segment['text']}")
    print(f"{len(matches)} matching asset(s)")


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
        if result is not None:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"editor: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("editor: interrupted; project status records any interrupted stage", file=sys.stderr)
        sys.exit(130)
