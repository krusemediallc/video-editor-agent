#!/usr/bin/env python3
"""plan_cuts.py - plan pause cuts for a NOISY talking-head take from VAD segments.

Why not ffmpeg silencedetect: it is a flat energy gate, and a noisy source
(car, cafe, fan, handheld outdoors) defeats it *quietly* — on one in-car take
with a -36 dB floor, `silencedetect=noise=-30dB:d=0.15` found 12 spans in 118s
and none at all past 70s, so the "silence cut" shipped having removed almost
nothing. Speech boundaries should come from voice-activity detection instead,
e.g. whisper.cpp's silero VAD:

    whisper-vad-speech-segments -f raw-audio.wav -vm ggml-silero-v5.1.2.bin -vt 0.5

(if the GPU path aborts on your build, drop any -ug flag). Convert its printed
segments to a JSON array of [start, end] pairs and pass it as --vad.

Two passes:

  A. JOINS between VAD speech segments. Instead of a fixed pad, target a FIXED
     RESIDUAL GAP: for each gap work out how much of the span is genuinely
     inaudible — walking outward past the VAD edge while breath is still above
     the floor, and reclaiming inward where the VAD edge over-included room
     tone — then keep exactly TARGET_GAP, split either side, and cut the rest.
     One number controls how run-on the whole edit feels, and every join lands
     at the same gap (it is the UNEVENNESS of fixed-pad joins, 70-270 ms apart,
     that stops an edit reading as one continuous take).

  B. WORD GAPS *inside* a VAD segment — TRIED AND ABANDONED, left here as a
     record. VAD merges over 120-330 ms beats between words and tightening
     those looks like free extra run-on feel. It is not. Energy cannot tell a
     beat between words from a word-initial stop closure, a word-final
     fricative, or a reduced function word. A two-transcript "is this run
     inside a word" guard caught 10 of 17 candidates on one paid deliverable,
     and the 7 that survived it still destroyed three words: "of" in "the
     importance OF quality" (which also left "importance" audible on both
     sides of the join), and both ends of "teams" plus the head of "driving".
     Seam QA went PASS -> FAIL, 0 HIGH -> 6 HIGH, every one a pass-B cut —
     while the flat pass-A joins in the same render were all clean.
     Verdict: not worth the ~1.35s it saves. INTRA_ENABLED stays False; to go
     tighter than pass A allows, refilm at pace. Do not enable without
     re-running verify_cuts.py AND a full seam QA on the result.

usage:
  python3 plan_cuts.py --wav raw-audio.wav --vad vad.json [--gap 0.03] [-v]
      [--flubs flubs.json] [--nudge nudges.json]
      [--cloud-words cloud-words.json] [--local-words words.json]
      [--out cuts]

inputs:
  --wav     mono 16-bit PCM wav of the source audio (extract with:
            ffmpeg -i clip.mp4 -ac 1 -ar 16000 -c:a pcm_s16le raw-audio.wav)
  --vad     JSON array of [start, end] speech segments in seconds
  --flubs   optional {"<segment index>": "note"} — VAD segments to DROP whole
            (false starts / bad takes, identified by isolating + transcribing them)
  --nudge   optional {"<segment index>": <new cut start seconds>} — per-join
            overrides where seam verification confirmed a clipped word (e.g. a
            /t/ closure VAD called non-speech; nudging the cut start ~135 ms
            later fixed "at" being heard as "add")
  --cloud-words / --local-words
            optional word-timing JSONs (OpenAI verbose_json / whisper.cpp -ojf)
            used only by the disabled pass B word guard
outputs:
  <out>.json            [[start, end]] — feed to the spec's "manual_cuts"
  <out>-annotated.json  same cuts with a "why" per cut (feeds verify_cuts.py)
"""
import argparse, json, wave, array, math, sys

ap = argparse.ArgumentParser()
ap.add_argument("--wav", required=True)
ap.add_argument("--vad", required=True)
ap.add_argument("--gap", type=float, default=0.03, help="residual gap at every join, seconds")
ap.add_argument("--flubs", default=None)
ap.add_argument("--nudge", default=None)
ap.add_argument("--cloud-words", default=None)
ap.add_argument("--local-words", default=None)
ap.add_argument("--out", default="cuts")
ap.add_argument("-v", "--verbose", action="store_true")
args = ap.parse_args()

TARGET_GAP = args.gap
BREATH_MARGIN = 10.0   # walking out past a VAD edge, stop once within this of the floor
QUIET_MARGIN  = 3.0    # reclaiming INTO a VAD edge, only this close to the floor
INTRA_ENABLED = False  # pass B — see the docstring. Leave off.
INTRA_MARGIN  = 6.0    # a word gap counts as quiet at floor + this
INTRA_MIN     = 0.13   # ignore shorter word gaps — that is articulation, not spacing
MAX_EXTEND    = 0.06   # cap on the outward walk (breath)
MAX_RECLAIM   = 0.07   # cap on the inward walk — keeps trailing fricatives safe
HEAD_KEEP     = 0.05
TAIL_KEEP     = 0.10
STEP          = 0.01

VAD = [tuple(x) for x in json.load(open(args.vad))]
FLUBS = {int(k): v for k, v in (json.load(open(args.flubs)) if args.flubs else {}).items()}
NUDGE_START = {int(k): float(v) for k, v in (json.load(open(args.nudge)) if args.nudge else {}).items()}

w = wave.open(args.wav, "rb"); sr = w.getframerate()
pcm = array.array("h"); pcm.frombytes(w.readframes(w.getnframes()))
SRC_DUR = len(pcm) / sr / max(1, w.getnchannels())

def db(t):
    i, j = int(t * sr), int((t + STEP) * sr)
    s = pcm[i:j]
    if not s: return -120.0
    r = math.sqrt(sum(x * x for x in s) / len(s)) or 1e-9
    return 20 * math.log10(r / 32768.0)

# noise floor = 25th percentile of RMS levels inside the inter-segment gaps
gapdb = []
for (a0, a1), (b0, b1) in zip(VAD, VAD[1:]):
    t = a1
    while t < b0 - STEP:
        gapdb.append(db(t)); t += STEP
gapdb.sort()
if not gapdb:
    sys.exit("no inter-segment gaps found — check the VAD JSON")
FLOOR = gapdb[int(0.25 * len(gapdb))]

def cut_lo(a1, limit):
    x = a1
    while x < min(a1 + MAX_EXTEND, limit) and db(x) > FLOOR + BREATH_MARGIN:
        x += STEP
    if x <= a1 + 1e-9:
        while x > a1 - MAX_RECLAIM and db(x - STEP) <= FLOOR + QUIET_MARGIN:
            x -= STEP
    return x

def cut_hi(b0, limit):
    x = b0
    while x > max(b0 - MAX_EXTEND, limit) and db(x - STEP) > FLOOR + BREATH_MARGIN:
        x -= STEP
    if x >= b0 - 1e-9:
        while x < b0 + MAX_RECLAIM and db(x) <= FLOOR + QUIET_MARGIN:
            x += STEP
    return x

# ---- word tables, for the stop-closure guard (pass B only) ------------------------
cloud, local = [], []
if args.cloud_words:
    cloud = [(x["start"], x["end"], x["word"])
             for x in json.load(open(args.cloud_words))["words"]]
if args.local_words:
    for s in json.load(open(args.local_words))["transcription"]:
        o, t = s["offsets"], s["text"].strip()
        if t and t not in ".,?!-": local.append((o["from"] / 1000, o["to"] / 1000, t))

def inside_a_word(ra, rb):
    for table in (cloud, local):
        for a, b, t in table:
            if a <= ra and rb <= b: return t
    return None

# ---- pass A: joins between speech segments ----------------------------------------
keep = [(i, s) for i, s in enumerate(VAD) if i not in FLUBS]
cuts, joins = [], []

head = max(0.0, keep[0][1][0] - HEAD_KEEP)
if head > 0.02: cuts.append((0.0, head, "head dead air"))

for (ia, (a0, a1)), (ib, (b0, b1)) in zip(keep, keep[1:]):
    lo = cut_lo(a1, b0); hi = cut_hi(b0, lo)
    if hi - lo <= TARGET_GAP + 0.005:
        joins.append(max(0.0, hi - lo)); continue
    why = "pause"
    for fi, note in FLUBS.items():
        if a1 <= VAD[fi][0] and VAD[fi][1] <= b0: why = f"FLUB: {note}"
    cs, ce = lo + TARGET_GAP / 2, hi - TARGET_GAP / 2
    if ia in NUDGE_START and NUDGE_START[ia] > cs:
        cs = NUDGE_START[ia]; why = "pause (nudged: probe-confirmed clip)"
    if ce - cs < 0.02: continue
    cuts.append((cs, ce, why))
    joins.append(TARGET_GAP)

# ---- pass B: word gaps inside a segment (disabled — see docstring) ----------------
intra = skipped = 0
for a, b in (VAD if INTRA_ENABLED else []):
    t, run = a + 0.02, None
    while t < b:
        quiet = db(t) <= FLOOR + INTRA_MARGIN
        if quiet and run is None: run = t
        elif not quiet and run is not None:
            if t - run >= INTRA_MIN:
                w_ = inside_a_word(run, t)
                if w_: skipped += 1
                else:
                    cuts.append((run + TARGET_GAP / 2, t - TARGET_GAP / 2, "word gap"))
                    intra += 1; joins.append(TARGET_GAP)
            run = None
        t += STEP

tail = min(SRC_DUR, keep[-1][1][1] + TAIL_KEEP)
if SRC_DUR - tail > 0.02: cuts.append((tail, SRC_DUR, "tail room tone"))

cuts.sort()
cuts = [(round(a, 3), round(b, 3), w_) for a, b, w_ in cuts]
removed = sum(b - a for a, b, _ in cuts)
j = sorted(joins)
print(f"target gap {TARGET_GAP*1000:.0f} ms   floor {FLOOR:.1f} dB")
print(f"source {SRC_DUR:.2f}s  ->  {len(cuts)} cuts, {removed:.2f}s removed  ->  new {SRC_DUR-removed:.2f}s")
print(f"  segment joins {len(joins)-intra} · word gaps tightened {intra} · "
      f"stop closures protected {skipped}")
if j:
    print(f"  residual gap at every join: {j[0]*1000:.0f}-{j[-1]*1000:.0f} ms (median {j[len(j)//2]*1000:.0f})")
if args.verbose:
    print(f"\n{'#':>3} {'start':>8} {'end':>8} {'len':>6}  why")
    for i, (a, b, why) in enumerate(cuts, 1):
        print(f"{i:3d} {a:8.3f} {b:8.3f} {b-a:6.3f}  {why}")
json.dump([[a, b] for a, b, _ in cuts], open(f"{args.out}.json", "w"), indent=1)
json.dump([{"start": a, "end": b, "why": w_} for a, b, w_ in cuts],
          open(f"{args.out}-annotated.json", "w"), indent=1)
print(f"wrote {args.out}.json + {args.out}-annotated.json")
