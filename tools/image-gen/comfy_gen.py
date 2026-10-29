#!/usr/bin/env python3
"""Generate still images on a local ComfyUI server (free, no API key).

Stdlib only. Talks to ComfyUI's HTTP API, builds a Z-Image Turbo text-to-image
graph, waits for the job and copies the PNGs into --out.

  python3 tools/image-gen/comfy_gen.py --prompt "..." --ratio 9:16 --out <dir>
  python3 tools/image-gen/comfy_gen.py --check          # server + models present?

Env: COMFYUI_URL (default http://127.0.0.1:8188), COMFYUI_DIR (portable install
root, used by --start to launch the server when it is not running).
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")

# Long-edge 1024 sizes, multiples of 16 (what the model was trained around).
RATIOS = {
    "1:1": (1024, 1024),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
    "4:5": (896, 1120),
    "3:4": (864, 1152),
    "4:3": (1152, 864),
}

# Preferred file per slot, first one installed wins.
MODELS = {
    "unet": ["z_image_turbo_nvfp4.safetensors", "z_image_turbo_int8_convrot.safetensors",
             "z_image_turbo_bf16.safetensors"],
    "clip": ["qwen_3_4b_fp8_mixed.safetensors", "qwen_3_4b_fp4_mixed.safetensors",
             "qwen_3_4b.safetensors"],
    "vae": ["ae.safetensors"],
}


def api(path, data=None, timeout=30):
    req = urllib.request.Request(URL + path)
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body[:1] in (b"{", b"[") else body


def server_up():
    try:
        api("/system_stats", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


def start_server():
    root = os.environ.get("COMFYUI_DIR")
    if not root:
        sys.exit("ComfyUI is not running and COMFYUI_DIR is not set; start it by hand "
                 "(run_nvidia_gpu.bat) or set COMFYUI_DIR to the portable folder.")
    py = os.path.join(root, "python_embeded", "python.exe")
    main = os.path.join(root, "ComfyUI", "main.py")
    log = open(os.path.join(root, "comfy_gen_server.log"), "ab")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([py, "-s", main, "--windows-standalone-build", "--disable-auto-launch"],
                     cwd=root, stdout=log, stderr=log, creationflags=flags)
    for _ in range(120):
        if server_up():
            return
        time.sleep(2)
    sys.exit("ComfyUI did not come up in 4 min; see comfy_gen_server.log in COMFYUI_DIR.")


def installed(node, field):
    info = api(f"/object_info/{node}")
    return info[node]["input"]["required"][field][0]


def pick_models():
    have = {
        "unet": installed("UNETLoader", "unet_name"),
        "clip": installed("CLIPLoader", "clip_name"),
        "vae": installed("VAELoader", "vae_name"),
    }
    chosen = {}
    for slot, prefs in MODELS.items():
        hit = next((m for m in prefs if m in have[slot]), None)
        if not hit:
            sys.exit(f"No {slot} model found. Expected one of {prefs} in ComfyUI/models "
                     f"(see .claude/skills/image-generation/SKILL.md, Setup).")
        chosen[slot] = hit
    return chosen


def graph(prompt, w, h, seed, steps, batch, models, prefix):
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": models["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": models["clip"], "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": models["vae"]}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": w, "height": h, "batch_size": batch}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "seed": seed, "steps": steps, "cfg": 1.0,
                         "sampler_name": "res_multistep", "scheduler": "simple",
                         "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def run(g, timeout):
    client = uuid.uuid4().hex
    try:
        pid = api("/prompt", {"prompt": g, "client_id": client})["prompt_id"]
    except urllib.error.HTTPError as e:
        sys.exit("ComfyUI rejected the graph:\n" + e.read().decode(errors="replace"))
    t0 = time.time()
    while time.time() - t0 < timeout:
        hist = api(f"/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                sys.exit("Generation failed:\n" + json.dumps(status.get("messages"), indent=1))
            return [img for out in entry["outputs"].values() for img in out.get("images", [])]
        time.sleep(1)
    sys.exit(f"Timed out after {timeout}s (job {pid} may still be running).")


def fetch(img, dest):
    q = urllib.parse.urlencode({k: img[k] for k in ("filename", "subfolder", "type")})
    with urllib.request.urlopen(f"{URL}/view?{q}", timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", help="what to draw (English prompts follow best)")
    ap.add_argument("--ratio", default="1:1", choices=sorted(RATIOS))
    ap.add_argument("--size", help="WxH override, e.g. 1080x1920 (multiples of 16)")
    ap.add_argument("--count", type=int, default=1, help="images in one batch")
    ap.add_argument("--seed", type=int, help="fix for reproducible output")
    ap.add_argument("--steps", type=int, default=8, help="Turbo is tuned for ~8")
    ap.add_argument("--out", default=".", help="folder to copy the PNGs into")
    ap.add_argument("--name", default="img", help="output file prefix")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--start", action="store_true", help="launch ComfyUI from COMFYUI_DIR if down")
    ap.add_argument("--check", action="store_true", help="report server + models and exit")
    a = ap.parse_args()

    if not server_up():
        if a.start or a.check and os.environ.get("COMFYUI_DIR"):
            start_server()
        else:
            sys.exit(f"ComfyUI not reachable at {URL}. Start it, or pass --start with COMFYUI_DIR set.")
    models = pick_models()
    if a.check:
        stats = api("/system_stats")
        dev = stats.get("devices", [{}])[0]
        print(f"OK {URL} | {dev.get('name', '?')} | " + " | ".join(models.values()))
        return
    if not a.prompt:
        ap.error("--prompt is required")

    w, h = RATIOS[a.ratio]
    if a.size:
        w, h = (int(v) for v in a.size.lower().split("x"))
    seed = a.seed if a.seed is not None else random.randint(0, 2**32 - 1)
    t0 = time.time()
    imgs = run(graph(a.prompt, w, h, seed, a.steps, a.count, models, f"comfy_gen/{a.name}"), a.timeout)
    os.makedirs(a.out, exist_ok=True)
    for i, img in enumerate(imgs):
        dest = os.path.join(a.out, f"{a.name}_{seed}_{i}.png")
        fetch(img, dest)
        print(dest)
    print(f"{len(imgs)} image(s) {w}x{h} seed={seed} in {time.time() - t0:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
