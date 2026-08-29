#!/usr/bin/env python3
"""Overlay edit-event markers on a waveform PNG (video-qa Layer 4).

Many ffmpeg builds lack drawtext, so labeled tick marks are drawn with PIL
(pip install Pillow). If PIL is unavailable, skip the overlay — the packet
still works with the bare waveform plus events.json as the legend.

usage: draw_markers.py waveform.png markers.json out.png
markers.json: {"start": s, "end": s, "markers": [{"t": sec, "label": str, "kind": str}]}
"""
import json
import sys

from PIL import Image, ImageDraw

COLORS = {
    "cut": (255, 80, 80),
    "caption": (80, 160, 255),
    "callout": (170, 110, 255),
    "sfx": (255, 200, 60),
    "graphic": (110, 220, 140),
    "broll": (110, 220, 140),
    "music": (255, 140, 200),
    "issue": (255, 40, 40),
}


def main(wave_path, markers_path, out_path):
    meta = json.load(open(markers_path))
    start, end = meta["start"], meta["end"]
    span = max(end - start, 1e-6)
    img = Image.open(wave_path).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)
    lanes = {}
    for m in meta.get("markers", []):
        x = int((m["t"] - start) / span * w)
        if x < 0 or x > w:
            continue
        color = COLORS.get(m.get("kind", ""), (200, 200, 200))
        d.line([(x, 0), (x, h)], fill=color, width=2)
        lane = lanes.get(m.get("kind", ""), len(lanes) % 4)
        lanes.setdefault(m.get("kind", ""), lane)
        label = f'{m.get("label", "")} @{m["t"]:.2f}'
        ty = 4 + lane * 16
        tw = d.textlength(label)
        tx = min(max(0, x + 4), w - tw - 2)
        d.rectangle([tx - 2, ty - 1, tx + tw + 2, ty + 13], fill=(0, 0, 0))
        d.text((tx, ty), label, fill=color)
    img.save(out_path)
    print(out_path)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    main(*sys.argv[1:])
