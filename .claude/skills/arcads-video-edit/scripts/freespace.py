#!/usr/bin/env python3
"""Where can a graphic land in each shot without covering the creator's face or the proof?

Two measured layers, both from the RENDERED cut:
  importance = temporal-max Sobel magnitude (UI text, product detail, faces are high-edge;
               sky, walls and the creator's black shirt are not)
  subject    = temporal std (the creator moves, the room does not). Warm-pixel detection was tried
               first and failed: the creator's amber key light and the shelf LEDs read as "skin" and
               inflated the box to the whole frame.
A card placement is scored as mean importance under the card + a hard penalty for any
overlap with the subject box, so the placer always returns something and the penalty is
visible.
"""
import json, subprocess
import numpy as np
import os, shutil

FF = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
W, H = 1080, 1920
SW, SH = 135, 240
CIRCLE = (60, 1418, 380, 380)


def stack(t0, t1, n, fmt='gray', ch=1):
    ts = np.linspace(t0 + 0.12, t1 - 0.12, n)
    out = []
    for t in ts:
        p = subprocess.run([FF, '-v', 'error', '-ss', f'{t:.3f}', '-i', 'arcads-ad-v5.mp4',
                            '-frames:v', '1', '-vf', f'scale={SW}:{SH},format={fmt}',
                            '-f', 'rawvideo', '-'], capture_output=True)
        out.append(np.frombuffer(p.stdout, np.uint8).reshape(SH, SW, ch).squeeze())
    return np.stack(out).astype(np.float32)


def analyse(t0, t1, layout):
    a = stack(t0, t1, 9)
    imp = np.zeros((SH, SW), np.float32)
    for f in a:
        gx = np.abs(np.diff(f, axis=1, prepend=f[:, :1]))
        gy = np.abs(np.diff(f, axis=0, prepend=f[:1, :]))
        imp = np.maximum(imp, np.hypot(gx, gy))
    if layout == 'screen':
        return imp, CIRCLE
    mot = a.std(axis=0)
    y0, y1 = (0, SH) if layout == 'cam' else (SH // 2, SH)
    m = mot.copy(); m[:y0] = 0; m[y1:] = 0
    thr = max(4.0, float(np.percentile(m[y0:y1], 88)))
    ys, xs = np.nonzero(m > thr)
    if len(ys) < 20:
        return imp, (0, y0 * H // SH, W, (y1 - y0) * H // SH)
    x0, x1 = np.percentile(xs, [3, 97]); yy0, yy1 = np.percentile(ys, [3, 97])
    pad = 5
    return imp, (max(0, int((x0 - pad) * W / SW)), max(0, int((yy0 - pad) * H / SH)),
                 int((x1 - x0 + 2 * pad) * W / SW), int((yy1 - yy0 + 2 * pad) * H / SH))


def place(imp, box, cw, ch, margin=42, prefer='top'):
    sw, sh = max(1, cw * SW // W), max(1, ch * SH // H)
    ii = np.pad(np.cumsum(np.cumsum(imp, 0), 1), ((1, 0), (1, 0)))
    bx, by, bw, bh = box
    best = None
    for y in range(margin * SH // H, SH - sh - margin * SH // H + 1):
        for x in range(margin * SW // W, SW - sw - margin * SW // W + 1):
            cx, cy = x * W // SW, y * H // SH
            ox = max(0, min(cx + cw, bx + bw) - max(cx, bx))
            oy = max(0, min(cy + ch, by + bh) - max(cy, by))
            s = float(ii[y + sh, x + sw] - ii[y, x + sw] - ii[y + sh, x] + ii[y, x]) / (sw * sh)
            s += (ox * oy) / (cw * ch) * 300                       # overlap with the creator = expensive
            s += (y / SH if prefer == 'top' else 1 - y / SH) * 10  # tie-break
            if best is None or s < best[0]:
                best = (s, cx, cy, round(ox * oy / (cw * ch), 3))
    return best


if __name__ == '__main__':
    edl = json.load(open('edl.json'))
    rows = json.load(open('qa/v5-timeline.json'))
    lay = {s['id']: s['layout'] for s in edl['segments']}
    out = {}
    for a, b, sid in rows:
        imp, box = analyse(a, b, lay[sid])
        rec = {'t0': a, 't1': b, 'layout': lay[sid], 'subject': [int(v) for v in box]}
        for tag, pref in (('top', 'top'), ('bot', 'bot')):
            r = place(imp, box, 800, 280, prefer=pref)
            rec['card_' + tag] = [r[1], r[2], round(r[0], 1), r[3]]
        rec['band'] = [round(float(imp[i * SH // 16:(i + 1) * SH // 16].mean()), 1) for i in range(16)]
        out[sid] = rec
        print(f'{sid:16s} {lay[sid]:6s} the creator={str(rec["subject"]):24s} '
              f'top={rec["card_top"][:2]} c={rec["card_top"][2]:5.1f} ov={rec["card_top"][3]:.2f}  '
              f'bot={rec["card_bot"][:2]} c={rec["card_bot"][2]:5.1f} ov={rec["card_bot"][3]:.2f}')
    json.dump(out, open('mg/freespace.json', 'w'), indent=1)
