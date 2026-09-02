#!/usr/bin/env python3
"""build_mix.py — per-scene sound-design engine for AI-generated videos.

TEMPLATE: the tables at the top (SCENES / LAYERS / EVENTS / AMB_FX / BLEEPS /
AMB_MASTER_DB) are the project file — everything below them is the engine and
rarely needs touching. The values shipped here are the proven 10-scene AI-actor project
(2026-08, 5 approved rounds); replace them with your project's scene map.
Usage: python3 build_mix.py <ambience_dir> <master_audio.wav 48k stereo> <out.wav>

Chain per scene: slice dialog → mute bleeped words (pre-reverb, so the word
never rings into the tail) → highpass → synthetic-IR convolution reverb
(wet mixed under dry) → hard cut at the picture cut (30 ms fade).
Ambience beds are placed per scene, cut with the picture like a real editor
would, with short edge fades. Bleep tone is dry, gain-matched to local dialog.
Final mix is loudness-matched to the source master.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"

# scene table: (name, t0, t1, bed_file, bed_gain_db, rt60, damp_hz, wet_db, predelay_ms, hp_hz)
# wet_db None = no reverb (outdoor). Bed gain applied to the peak-normalized (-3 dB) bed.
SCENES = [
    ("night-street",   0.0,      3.7667,  "s01-night-street-v2-trim.mp3", -20.5, None, None, None, None, 90),
    ("kitchen-modern", 3.7667,   7.5667,  "s02-kitchen-modern.mp3",  -30, 0.35, 5000, -16, 12, 90),
    ("sunny-lawn",     7.5667,  10.3667,  "s03-sunny-lawn.mp3",      -26, None, None, None, None, 100),
    ("dark-bedroom",  10.3667,  13.0,     "s04-ac-unit.mp3",         -31, 0.18, 2800, -20,  8, 80),
    ("bathroom",      13.0,     15.5333,  "s05-bathroom.mp3",        -31, 0.70, 6500, -13, 10, 100),
    ("waiting-area",  15.5333,  18.6,     "s06-waiting-area.mp3",    -27, 0.55, 3800, -15, 15, 90),
    ("living-room",   18.6,     21.0667,  "s07-living-room.mp3",     -22, 0.42, 3800, -13, 10, 90),  # V4: room-size reverb
    ("morning-kitchen", 21.0667, 22.7333, "s09-morning-kitchen.mp3", -19, 0.40, 4200, -16, 12, 90),
    ("bedroom-mirror", 22.7333, 26.2333,  "s10-bedroom-mirror.mp3",  -31, 0.30, 3600, -17, 10, 90),
    ("office-loft",   26.2333,  28.3,     "s11-office-loft.mp3",     -29, 0.45, 4500, -15, 12, 90),
]

# extra beds layered on top of a scene's main bed (V1 canvas feedback: keep what
# worked, add the missing element) — {scene: [(bed_file, gain_db), ...]}
LAYERS = {
    "sunny-lawn": [("s03-lawnmower.mp3", -27)],   # V4: "increase the lawnmower volume 2x" (+6 dB)
    "morning-kitchen": [("s09-fridge.mp3", -29)],
    "office-loft": [("s11-printer.mp3", -30), ("s11-fluorescent.mp3", -33)],  # V4 note
}

# one-shot diegetic events placed on the ambience stem (no looping):
# (start_t, file, gain_db, clip_end_t) — clipped at the picture cut like the beds
EVENTS = [
    (1.5, "sfx-car-passby.mp3", -22, 3.7667),  # V4: car driving by in the night scene
]

# absolute bleep spans (padded: whisper word starts run ~100ms late on this source)
BLEEPS = [(1.26, 1.72), (4.78, 5.30), (11.54, 12.08), (16.90, 17.82)]
BLEEP_HZ = 1000.0

# global trim on the whole ambience stem, on top of per-bed gains
# (V3: the client asked for louder ambience across the board)
AMB_MASTER_DB = 4.0

# V5: outdoor distance treatment per ambience source (keyed by file).
# "far" = crowd/traffic across the street: dark (air absorption), LF rumble lift,
# heavy urban-canyon wash. "mid" = passing car: brighter, lighter wash.
AMB_FX = {
    "s01-night-street-v2-trim.mp3": "far",
    "sfx-car-passby.mp3": "mid",
}


def db(x):
    return 10 ** (x / 20)


def load_wav(path):
    sr, data = wavfile.read(path)
    assert sr == SR, f"{path}: {sr}"
    return data.astype(np.float64) / 32768.0


def decode_bed(mp3, out):
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", mp3, "-ac", "2", "-ar", str(SR), out], check=True)
    return load_wav(out)


def make_ir(rt60, damp_hz, predelay_ms, seed):
    pre = int(SR * predelay_ms / 1000)
    n = pre + int(SR * rt60 * 1.3)
    rng = np.random.default_rng(seed)
    t = np.arange(n - pre) / SR
    env = 10 ** (-3.0 * t / rt60)  # -60 dB at rt60
    ir = np.zeros((n, 2))
    for ch in range(2):
        ir[pre:, ch] = rng.standard_normal(n - pre) * env
    sos_lp = butter(2, damp_hz, "low", fs=SR, output="sos")
    sos_hp = butter(2, 150, "high", fs=SR, output="sos")
    ir = sosfilt(sos_lp, ir, axis=0)
    ir = sosfilt(sos_hp, ir, axis=0)
    ir /= np.sqrt((ir ** 2).sum() / 2)  # unit energy per channel avg
    return ir


def outdoor_wash_ir(seed, rt=1.1, damp=2200, pre_ms=25):
    """Urban-canyon wash: a handful of sparse facade echoes + a dark low-density
    diffuse tail. Unlike a room IR: long predelay, no dense early field, heavy HF damping."""
    rng = np.random.default_rng(seed)
    pre = int(SR * pre_ms / 1000)
    n = pre + int(SR * rt * 1.2)
    ir = np.zeros((n, 2))
    for ch in range(2):
        for k in range(12):  # facade bounces, 5-90 ms after predelay
            d = pre + int(rng.uniform(0.005, 0.09) * SR)
            ir[d, ch] += rng.uniform(0.4, 1.0) * (0.7 ** k) * rng.choice([-1, 1])
        t = np.arange(n - pre) / SR
        ir[pre:, ch] += 0.35 * rng.standard_normal(n - pre) * 10 ** (-3.0 * t / rt)
    ir = sosfilt(butter(2, damp, "low", fs=SR, output="sos"), ir, axis=0)
    ir = sosfilt(butter(2, 120, "high", fs=SR, output="sos"), ir, axis=0)
    ir /= np.sqrt((ir ** 2).sum() / 2)
    return ir


def apply_outdoor(x, kind, seed):
    """Distance cues for outdoor sources; RMS-matched so approved levels don't move."""
    rms0 = np.sqrt((x ** 2).mean())
    if rms0 == 0:
        return x
    if kind == "far":
        y = sosfilt(butter(2, 3200, "low", fs=SR, output="sos"), x, axis=0)
        y = y + 0.6 * sosfilt(butter(2, 160, "low", fs=SR, output="sos"), x, axis=0)  # traffic rumble lift
        wet_gain = db(-8)
    else:  # mid
        y = sosfilt(butter(2, 7500, "low", fs=SR, output="sos"), x, axis=0)
        wet_gain = db(-13)
    ir = outdoor_wash_ir(seed)
    wet = np.stack([fftconvolve(y[:, c], ir[:, c])[: len(y)] for c in range(2)], axis=1)
    y = y + wet * wet_gain
    y *= rms0 / max(np.sqrt((y ** 2).mean()), 1e-12)
    return y


def fade_edges(x, fin, fout):
    a, b = int(SR * fin), int(SR * fout)
    if a > 0 and len(x) > a:
        x[:a] *= np.linspace(0, 1, a)[:, None] ** 2
    if b > 0 and len(x) > b:
        x[-b:] *= np.linspace(1, 0, b)[:, None] ** 2
    return x


def main(amb_dir, master_wav, out_wav):
    master = load_wav(master_wav)
    total = len(master)
    dialog_out = np.zeros_like(master)
    amb_out = np.zeros_like(master)
    bleep_out = np.zeros_like(master)

    for i, (name, t0, t1, bed, bed_db, rt60, damp, wet_db, pre_ms, hp) in enumerate(SCENES):
        s0, s1 = int(round(t0 * SR)), min(int(round(t1 * SR)), total)
        seg = master[s0:s1].copy()

        # mute bleeped words BEFORE reverb (5 ms edge ramps to avoid clicks)
        for (b0, b1) in BLEEPS:
            if b0 >= t0 and b0 < t1:
                r = int(0.005 * SR)
                m0, m1 = int(round(b0 * SR)) - s0, min(int(round(b1 * SR)) - s0, len(seg))
                seg[m0 + r:m1 - r] = 0
                seg[m0:m0 + r] *= np.linspace(1, 0, r)[:, None]
                seg[max(m1 - r, 0):m1] *= np.linspace(0, 1, min(r, m1))[:, None]

        sos = butter(2, hp, "high", fs=SR, output="sos")
        seg = sosfilt(sos, seg, axis=0)
        # steep LP: every source clip carries a tonal AI whine at 13.3-15.6 kHz;
        # phone mics roll off here anyway, so this reads as realism, not loss
        seg = sosfilt(butter(8, 13000, "low", fs=SR, output="sos"), seg, axis=0)

        if rt60 is not None:
            ir = make_ir(rt60, damp, pre_ms, seed=1000 + i)
            wet = np.stack([fftconvolve(seg[:, c], ir[:, c])[: len(seg)] for c in range(2)], axis=1)
            seg = seg + wet * db(wet_db)

        seg = fade_edges(seg, 0.004, 0.030)  # hard-ish cut at the picture cut
        dialog_out[s0:s1] += seg

        need = s1 - s0
        for j, (bed_file, gain) in enumerate([(bed, bed_db)] + LAYERS.get(name, [])):
            bed_wav = decode_bed(f"{amb_dir}/{bed_file}", f"{amb_dir}/_{name}-{j}.wav")
            if len(bed_wav) < need:  # loop if bed is short
                reps = int(np.ceil(need / len(bed_wav))) + 1
                bed_wav = np.tile(bed_wav, (reps, 1))
            bed_seg = bed_wav[:need].copy() * db(gain)
            if bed_file in AMB_FX:
                bed_seg = apply_outdoor(bed_seg, AMB_FX[bed_file], seed=7000 + i)
            # kill ElevenLabs mosquito whine (~15.6 kHz lines in the hum beds)
            bed_seg = sosfilt(butter(4, 14000, "low", fs=SR, output="sos"), bed_seg, axis=0)
            bed_seg = fade_edges(bed_seg, 0.060, 0.040)
            amb_out[s0:s1] += bed_seg

    # bleep tones: dry, RMS-matched to surrounding dialog (+1 dB), 8 ms cos fades
    for (b0, b1) in BLEEPS:
        c0, c1 = int(max(0, (b0 - 0.8)) * SR), int(min(total / SR, b1 + 0.8) * SR)
        ref = master[c0:c1]
        ref_rms = np.sqrt((ref ** 2).mean())
        n0, n1 = int(round(b0 * SR)), int(round(b1 * SR))
        t = np.arange(n1 - n0) / SR
        tone = np.sin(2 * np.pi * BLEEP_HZ * t) * ref_rms * np.sqrt(2) * db(1.0)
        tone = np.stack([tone, tone], axis=1)
        r = int(0.008 * SR)
        tone[:r] *= (np.sin(np.linspace(0, np.pi / 2, r)) ** 2)[:, None]
        tone[-r:] *= (np.cos(np.linspace(0, np.pi / 2, r)) ** 2)[:, None]
        bleep_out[n0:n1] += tone

    for (et, ef, eg, eclip) in EVENTS:
        ev = decode_bed(f"{amb_dir}/{ef}", f"{amb_dir}/_ev-{ef}.wav") * db(eg)
        e0 = int(round(et * SR))
        e1 = min(e0 + len(ev), int(round(eclip * SR)), total)
        ev = ev[: e1 - e0]
        if ef in AMB_FX:
            ev = apply_outdoor(ev, AMB_FX[ef], seed=8000)
        ev = sosfilt(butter(4, 14000, "low", fs=SR, output="sos"), ev, axis=0)
        ev = fade_edges(ev, 0.050, 0.060)
        amb_out[e0:e1] += ev

    amb_out *= db(AMB_MASTER_DB)
    mix = dialog_out + amb_out + bleep_out
    # FFT brick-wall (cosine edge 13.0-13.5 kHz): butterworth slopes only shave
    # ~13 dB off the 13.3-15.6 kHz AI whine tones; this removes them completely
    F = np.fft.rfft(mix, axis=0)
    freqs = np.fft.rfftfreq(len(mix), 1 / SR)
    gain = np.ones_like(freqs)
    gain[freqs >= 13500] = 0
    band = (freqs >= 13000) & (freqs < 13500)
    gain[band] = 0.5 * (1 + np.cos(np.pi * (freqs[band] - 13000) / 500))
    mix = np.fft.irfft(F * gain[:, None], n=len(mix), axis=0)
    peak = np.abs(mix).max()
    print(f"pre-limit peak: {20*np.log10(peak):.2f} dBFS")
    if peak > db(-1.0):
        mix *= db(-1.0) / peak
        print("peak-normalized to -1.0 dBFS")

    wavfile.write(out_wav, SR, (np.clip(mix, -1, 1) * 32767).astype(np.int16))
    # stems for debugging / level tuning
    for stem, arr in [("dialog", dialog_out), ("amb", amb_out), ("bleeps", bleep_out)]:
        wavfile.write(out_wav.replace(".wav", f"-{stem}.wav"), SR, (np.clip(arr, -1, 1) * 32767).astype(np.int16))
    print("wrote", out_wav)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
