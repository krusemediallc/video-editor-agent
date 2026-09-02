"""Shared config + tool paths for the hook-splitter scripts."""
import json, os, sys, subprocess, shutil

def _bin(env, name):
    """env var, else PATH, else the Homebrew location, else the bare name."""
    return (os.environ.get(env) or shutil.which(name)
            or (f"/opt/homebrew/bin/{name}" if os.path.exists(f"/opt/homebrew/bin/{name}") else name))

FFMPEG    = _bin("FFMPEG", "ffmpeg")
FFPROBE   = _bin("FFPROBE", "ffprobe")
WHISPER   = _bin("WHISPER_CLI", "whisper-cli")
WMODEL    = os.environ.get("WHISPER_MODEL",
                           os.path.expanduser("~/.claude-video-vision/models/ggml-large-v3.bin"))
VAD_BIN   = _bin("VAD_BIN", "whisper-vad-speech-segments")
VAD_MODEL = os.environ.get("VAD_MODEL",
                           os.path.expanduser("~/.claude-video-vision/models/ggml-silero-v5.1.2.bin"))
HOP = 0.010   # envelope resolution, seconds

DEFAULTS = {
    "work": "work", "out": "final", "review": "review",
    "audio": {"mic": 0, "system": 1},
    "mask":  {"silence_db": -80.0, "close_gap": 0.60, "min_dur": 0.50},
    "loop":  {"consensus": 10.15, "min_dur": 10.40,
              "window": [9.90, 10.40], "min_corr": 0.55,
              "ref": [0.15, 1.30]},
    "pacing": {"join_gap": 0.045, "video_gap": 0.120,
               "head_pad": 0.120, "tail_pad": 0.080,
               "active_margin": 14.0, "merge_gap": 0.22, "min_run": 0.10,
               "breath_margin": 10.0, "quiet_margin": 3.0,
               "max_extend": 0.06, "max_reclaim": 0.07,
               "max_word": 0.60, "word_guard": 0.02},
    "version": "v1",
}

def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out

def load(path=None):
    p = path or (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else "hooks.json")
    if not os.path.exists(p):
        sys.exit(f"config not found: {p}  (see assets/hooks.example.json)")
    cfg = _merge(DEFAULTS, json.load(open(p)))
    root = os.path.dirname(os.path.abspath(p)) or "."
    cfg["_root"] = root
    for k in ("work", "out", "review"):
        cfg[k] = os.path.join(root, cfg[k])
    cfg["source"] = os.path.join(root, cfg["source"])
    os.makedirs(cfg["work"], exist_ok=True)
    return cfg

def w(cfg, *parts):
    return os.path.join(cfg["work"], *parts)

def run(args, **kw):
    return subprocess.run(args, check=True, **kw)

def probe_dur(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out)
