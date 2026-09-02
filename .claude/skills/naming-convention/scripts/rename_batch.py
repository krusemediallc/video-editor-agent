#!/usr/bin/env python3
"""Rename a batch of deliverables from a field map + a pattern. Idempotent, never clobbers.

    # dry run first -- always
    python3 rename_batch.py --dir variants/ --map subjects.json \
        --pattern "hook-{index:02d}-{subject}-{style}-body-{treatment}" \
        --set treatment=unedited --manifest variants.json

    # then commit
    ... --apply

`--map` is a JSON file of per-item fields, keyed by index:

    {"items": {
      "1": {"subject": "cap",        "style": "cinematic"},
      "2": {"subject": "hyperfocus", "style": "cinematic"}
    }}

Anything in `--set k=v` is merged into every item, which is how a batch-wide axis
(`treatment=unedited`) stays out of the per-item map.

The map is kept as DATA on purpose. Batches get relabelled — a subject turns out to be
wrong, a client renames a product — and when the mapping is a JSON file that is a one-line
edit and a re-run. Baked into a rename script it is a rewrite, and buried in a chat
transcript it is gone.

Sources of filenames, in order of preference:
  --manifest <variants.json>   rename exactly the files a build produced (best: no guessing)
  --dir alone                  every media file in the folder, sorted, index = position
"""
import argparse, json, os, re, sys

MEDIA = (".mp4", ".mov", ".m4v", ".webm", ".png", ".jpg", ".jpeg", ".pdf", ".wav", ".mp3")


def slug(s):
    """Lowercase, ascii-ish, hyphen-separated. Keeps names shell- and URL-safe."""
    s = re.sub(r"[’'`]", "", str(s).lower())
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--map", help="JSON of per-item fields keyed by index")
    ap.add_argument("--pattern", required=True,
                    help='format string, e.g. "hook-{index:02d}-{subject}-{treatment}"')
    ap.add_argument("--set", action="append", default=[], metavar="K=V",
                    help="constant field merged into every item (repeatable)")
    ap.add_argument("--manifest", help="build manifest to rename from and keep in sync")
    ap.add_argument("--ext", default=None, help="output extension (default: keep each file's)")
    ap.add_argument("--apply", action="store_true", help="actually rename (default: dry run)")
    args = ap.parse_args()

    d = os.path.abspath(args.dir)
    consts = {}
    for kv in args.set:
        k, _, v = kv.partition("=")
        consts[k] = v

    fields = {}
    if args.map:
        raw = json.load(open(args.map))
        fields = raw.get("items", raw)

    # ---- work out (index, current filename) pairs -------------------------------------
    man = None
    if args.manifest:
        mp = args.manifest if os.path.isabs(args.manifest) else os.path.join(d, args.manifest)
        man = json.load(open(mp))
        rows = man["variants"] if isinstance(man, dict) and "variants" in man else man
        pairs = [(r.get("hook", r.get("index", i + 1)), r["file"]) for i, r in enumerate(rows)]
    else:
        files = sorted(f for f in os.listdir(d)
                       if f.lower().endswith(MEDIA) and not f.startswith("."))
        pairs = list(enumerate(files, 1))

    if not pairs:
        sys.exit(f"nothing to rename in {d}")

    # ---- build the plan ---------------------------------------------------------------
    plan, problems = [], []
    for index, cur in pairs:
        item = dict(consts)
        item.update(fields.get(str(index), {}))
        item = {k: (slug(v) if isinstance(v, str) else v) for k, v in item.items()}
        item["index"] = index
        try:
            stem = args.pattern.format(**item)
        except KeyError as e:
            problems.append(f"item {index}: pattern needs {e}, map/--set does not supply it")
            continue
        ext = args.ext or os.path.splitext(cur)[1]
        new = stem + (ext if ext.startswith(".") else "." + ext)

        src, dst = os.path.join(d, cur), os.path.join(d, new)
        if cur == new:
            plan.append((cur, new, "already named")); continue
        if not os.path.exists(src):
            # a previous run may already have renamed it
            if os.path.exists(dst):
                plan.append((cur, new, "already named")); continue
            problems.append(f"missing source: {cur}")
            continue
        if os.path.exists(dst):
            problems.append(f"target already exists and is a different file: {new}")
            continue
        plan.append((cur, new, "rename"))

    targets = [n for _, n, _ in plan]
    dupes = {t for t in targets if targets.count(t) > 1}
    if dupes:
        problems.append(f"pattern is not unique, these collide: {sorted(dupes)} — add a "
                        f"field that differs (an index usually does it)")

    if problems:
        print("REFUSING TO RUN:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    width = max(len(o) for o, _, _ in plan)
    for old, new, what in plan:
        mark = "" if what == "rename" else "  (skip, already named)"
        print(f"  {old:<{width}}  ->  {new}{mark}")

    n_ren = sum(1 for _, _, w in plan if w == "rename")
    if not args.apply:
        print(f"\ndry run: {n_ren} would be renamed, {len(plan) - n_ren} already named.")
        print("re-run with --apply")
        return

    for old, new, what in plan:
        if what == "rename":
            os.rename(os.path.join(d, old), os.path.join(d, new))

    if man is not None:
        rows = man["variants"] if isinstance(man, dict) and "variants" in man else man
        for r, (_, new, _) in zip(rows, plan):
            r["file"] = new
            idx = str(r.get("hook", r.get("index")))
            r.update({k: v for k, v in fields.get(idx, {}).items()})
            r.update(consts)
        json.dump(man, open(mp, "w"), indent=1)
        print(f"\nrenamed {n_ren}; {os.path.basename(mp)} updated")
    else:
        print(f"\nrenamed {n_ren}")

    print("If these were already published on a review canvas, rebuild and republish it so "
          "the canvas and the disk still match.")


if __name__ == "__main__":
    main()
