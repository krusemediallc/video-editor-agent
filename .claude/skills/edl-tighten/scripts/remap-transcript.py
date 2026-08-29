#!/usr/bin/env python3
"""
remap-transcript.py — shift word-level transcript timestamps through an EDL of
removed source ranges, so captions stay word-synced after tightening a cut.

NEVER re-run whisper on the tightened media instead of using this script:
whisper timestamps on concatenated cuts drift late (worse toward the end of the
piece), which silently un-syncs karaoke captions. Remapping the ORIGINAL
transcript in code is exact.

Usage:
  python3 remap-transcript.py transcript.json --cuts edl.json -o transcript.tight.json
  python3 remap-transcript.py transcript.json --cut 41.400-41.833 --cut 55.200-55.700 -o out.json
  python3 remap-transcript.py --cuts edl.json --query 63.2,71.05        # map individual times (SFX hits, caption ranges)
  python3 remap-transcript.py --cuts edl.json --write-merged edl.merged.json

Cut list (--cuts file, or repeated --cut S-E): ranges of SOURCE time (seconds)
to REMOVE. Accepted JSON shapes:
  [[41.4, 41.833], [55.2, 55.7]]
  [{"start": 41.4, "end": 41.833}, ...]
  {"cuts": [ ...either of the above... ]}

Transcript: any JSON containing dicts with numeric "start"/"end" in seconds
(OpenAI whisper verbose_json, faster-whisper, most word-level formats), or
whisper.cpp dicts carrying "offsets": {"from": ms, "to": ms}. Structure is
preserved verbatim; only times change. A timed dict that falls entirely inside
a removed range is dropped by default (--keep-removed clamps it to the splice
point instead). A word whose END overshoots into a removed range — the normal
whisper behavior at pauses — gets its end clamped to the splice, never dropped.

Options:
  --fps N          quantize OUTPUT times to the frame grid (round to nearest 1/N s)
  --keep-removed   clamp fully-removed items to the splice point instead of dropping
  --query T[,T..]  print source→output mapping for loose times and exit
  --write-merged F write the sorted/merged EDL back out (bookkeeping round-trip)
  -o FILE          output transcript path (default: stdout)

Exit code 0 on success; a summary is printed to stderr.
"""

import argparse
import json
import math
import sys

EPS = 1e-6
DROP = object()  # sentinel


# ---------------------------------------------------------------- cut list ---

def load_cut_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "cuts" in data:
        data = data["cuts"]
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of cut ranges (or {{'cuts': [...]}})")
    cuts = []
    for item in data:
        if isinstance(item, dict):
            cuts.append((float(item["start"]), float(item["end"])))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            cuts.append((float(item[0]), float(item[1])))
        else:
            raise ValueError(f"unrecognized cut entry: {item!r}")
    return cuts


def parse_cut_arg(text):
    # "41.400-41.833" or "41.4:41.833" or "41.4,41.833"
    for sep in ("-", ":", ","):
        if sep in text:
            a, b = text.split(sep, 1)
            return (float(a), float(b))
    raise ValueError(f"--cut expects START-END, got {text!r}")


def merge_cuts(cuts, eps=0.001):
    """Sort and merge overlapping/adjacent ranges (adjacent within `eps` seconds).

    This is the bookkeeping primitive: every revision round appends its new
    ranges (in SOURCE time) to the one EDL, then merges, so media can always be
    regenerated from the original source in a single pass.
    """
    cleaned = []
    for s, e in cuts:
        if e - s <= EPS:
            continue  # zero/negative-length, ignore
        cleaned.append((min(s, e), max(s, e)))
    cleaned.sort()
    merged = []
    for s, e in cleaned:
        if merged and s <= merged[-1][1] + eps:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


# ------------------------------------------------------------- time mapping --

class TimeMapper:
    def __init__(self, cuts, fps=None):
        self.cuts = cuts  # merged, sorted
        self.fps = fps
        self.total_removed = sum(e - s for s, e in cuts)

    def _quantize(self, t):
        if self.fps:
            t = round(t * self.fps) / self.fps
        return max(0.0, t)

    def map(self, t):
        """Source time -> output time. Times inside a removed range collapse to
        that range's splice point."""
        removed = 0.0
        for s, e in self.cuts:
            if t < s - EPS:
                break
            if t <= e + EPS:
                return self._quantize(s - removed)
            removed += e - s
        return self._quantize(t - removed)

    def inside_cut(self, t):
        return any(s - EPS <= t <= e + EPS for s, e in self.cuts)

    def fully_removed(self, start, end):
        return any(s - EPS <= start and end <= e + EPS for s, e in self.cuts)


# ------------------------------------------------------- transcript walking --

def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def is_timed(d):
    return is_num(d.get("start")) and is_num(d.get("end"))


def has_ms_offsets(d):
    off = d.get("offsets")
    return isinstance(off, dict) and is_num(off.get("from")) and is_num(off.get("to"))


class Stats:
    def __init__(self):
        self.shifted = 0
        self.ends_clamped = 0
        self.dropped = 0
        self.max_end = 0.0


def remap_node(node, mapper, stats, keep_removed):
    if isinstance(node, list):
        out = []
        for item in node:
            r = remap_node(item, mapper, stats, keep_removed)
            if r is not DROP:
                out.append(r)
        return out

    if isinstance(node, dict):
        new = {}
        timed = is_timed(node)
        ms = has_ms_offsets(node)

        if timed or ms:
            if timed:
                s, e = float(node["start"]), float(node["end"])
            else:
                s, e = node["offsets"]["from"] / 1000.0, node["offsets"]["to"] / 1000.0

            if mapper.fully_removed(s, e):
                stats.dropped += 1
                if not keep_removed:
                    return DROP
                # clamp to the splice point (zero-length marker)
                ns = ne = mapper.map(s)
            else:
                ns = mapper.map(s)
                ne = mapper.map(e)
                if mapper.inside_cut(e) and not mapper.inside_cut(s):
                    stats.ends_clamped += 1  # whisper overshoot into the pause
                if ne < ns:
                    ne = ns
                if abs(ns - s) > EPS or abs(ne - e) > EPS:
                    stats.shifted += 1
            stats.max_end = max(stats.max_end, ne)

            for k, v in node.items():
                if timed and k == "start":
                    new[k] = round(ns, 4)
                elif timed and k == "end":
                    new[k] = round(ne, 4)
                elif ms and k == "offsets":
                    new[k] = dict(v)
                    new[k]["from"] = int(round(ns * 1000))
                    new[k]["to"] = int(round(ne * 1000))
                else:
                    new[k] = remap_node(v, mapper, stats, keep_removed)
                    if new[k] is DROP:
                        del new[k]
            return new

        for k, v in node.items():
            r = remap_node(v, mapper, stats, keep_removed)
            if r is not DROP:
                new[k] = r
        return new

    return node


# ------------------------------------------------------------------- main ----

def main():
    ap = argparse.ArgumentParser(
        description="Remap transcript word times through an EDL of removed ranges.",
    )
    ap.add_argument("transcript", nargs="?", help="word-level transcript JSON")
    ap.add_argument("--cuts", help="EDL JSON file of removed source ranges")
    ap.add_argument("--cut", action="append", default=[], metavar="S-E",
                    help="one removed range, e.g. 41.400-41.833 (repeatable)")
    ap.add_argument("--fps", type=float, default=None,
                    help="quantize output times to this frame rate's grid")
    ap.add_argument("--keep-removed", action="store_true",
                    help="clamp fully-removed items to the splice instead of dropping")
    ap.add_argument("--query", default=None,
                    help="comma-separated source times to map; prints mapping and exits")
    ap.add_argument("--write-merged", metavar="FILE",
                    help="write the sorted/merged EDL to FILE (JSON)")
    ap.add_argument("-o", "--output", default=None, help="output transcript path")
    args = ap.parse_args()

    cuts = []
    if args.cuts:
        cuts += load_cut_file(args.cuts)
    for c in args.cut:
        cuts.append(parse_cut_arg(c))
    if not cuts:
        ap.error("no cuts given — pass --cuts FILE and/or --cut S-E")

    merged = merge_cuts(cuts)
    if len(merged) != len(cuts):
        print(f"[edl] merged {len(cuts)} range(s) -> {len(merged)} "
              f"(overlapping/adjacent ranges combined)", file=sys.stderr)
    mapper = TimeMapper(merged, fps=args.fps)

    if args.write_merged:
        with open(args.write_merged, "w", encoding="utf-8") as f:
            json.dump({"cuts": [[round(s, 4), round(e, 4)] for s, e in merged]},
                      f, indent=2)
        print(f"[edl] wrote merged EDL -> {args.write_merged}", file=sys.stderr)

    print(f"[edl] {len(merged)} cut(s), total removed {mapper.total_removed:.3f}s",
          file=sys.stderr)
    for s, e in merged:
        print(f"[edl]   remove {s:9.3f} - {e:9.3f}  ({e - s:.3f}s)  "
              f"splice lands at output {mapper.map(s):.3f}s", file=sys.stderr)

    if args.query:
        for tok in args.query.split(","):
            t = float(tok)
            note = "  (inside a removed range -> collapses to splice)" \
                if mapper.inside_cut(t) else ""
            print(f"{t:.3f} -> {mapper.map(t):.3f}{note}")
        return

    if not args.transcript:
        ap.error("no transcript given (or use --query / --write-merged alone)")

    with open(args.transcript, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    stats = Stats()
    result = remap_node(transcript, mapper, stats, args.keep_removed)
    if result is DROP:
        result = {} if isinstance(transcript, dict) else []

    out_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json + "\n")
        print(f"[out] wrote {args.output}", file=sys.stderr)
    else:
        print(out_json)

    print(f"[out] items shifted: {stats.shifted}  "
          f"word-ends clamped at splices: {stats.ends_clamped}  "
          f"dropped (fully inside cuts): {stats.dropped}", file=sys.stderr)
    print(f"[out] last word ends at {stats.max_end:.3f}s "
          f"(new media duration should be ~source_duration - "
          f"{mapper.total_removed:.3f}s)", file=sys.stderr)
    if stats.dropped and not args.keep_removed:
        print("[out] WARNING: dropped items were timed entries entirely inside a "
              "removed range — verify those were silence, not speech.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
