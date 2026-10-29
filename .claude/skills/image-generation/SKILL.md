---
name: image-generation
description: >
  GENERATE still images for free on a LOCAL ComfyUI server (Z-Image Turbo, no API key,
  no per-image cost) — covers, thumbnails, shot cards, backgrounds, product-free scene
  stills, mascot/character concept frames, and first frames to animate elsewhere. Use
  whenever an edit or post needs an image that does not exist yet ("gera uma imagem",
  "make a thumbnail/cover", "background for this card", "concept frame", "imagem para o
  post") and the user wants it free / without ChatGPT. NOT for real screenshots
  (broll-capture), generated VIDEO clips (openart-broll / arcads-broll), or editing a
  client's real product photo where fidelity matters.
---

# Image Generation (local ComfyUI, free)

Runs on the user's own GPU through ComfyUI's HTTP API. Nothing is billed and nothing
leaves the machine. One script does the whole call: `tools/image-gen/comfy_gen.py`
(stdlib Python, no install).

## Setup (once per machine)

1. **ComfyUI Portable** (NVIDIA build) from the official GitHub releases
   (`Comfy-Org/ComfyUI`, asset `ComfyUI_windows_portable_nvidia.7z`, ~2 GB). Extract
   anywhere; set `COMFYUI_DIR` in `.env` to the folder holding `run_nvidia_gpu.bat`.
2. **Z-Image Turbo** from the `Comfy-Org/z_image_turbo` Hugging Face repo
   (`split_files/…`), into the matching `ComfyUI/models/` subfolder:
   - `diffusion_models/` — `z_image_turbo_nvfp4` (4.3 GB, RTX 50-series native FP4),
     else `z_image_turbo_int8_convrot` (5.9 GB) or `_bf16` (11.7 GB, 16 GB+ VRAM)
   - `text_encoders/` — `qwen_3_4b_fp8_mixed` (5.4 GB)
   - `vae/` — `ae.safetensors` (0.3 GB)
   The script picks the first installed file per slot in that order.
3. Check: `python3 tools/image-gen/comfy_gen.py --check --start` → `OK … | <GPU> | <models>`.

License: Z-Image Turbo is Apache-2.0 — commercial use OK.

## Generate

```bash
python3 tools/image-gen/comfy_gen.py --start --prompt "<prompt>" --ratio 9:16 \
  --count 4 --out <project>/images --name cover
```

- `--ratio` 1:1 · 9:16 · 16:9 · 4:5 · 3:4 · 4:3 (long edge ~1344), or `--size WxH`
  (multiples of 16). Upscale/crop to delivery size in the edit, not in the prompt.
- `--count 4` = one batch of variations; pick, then `--seed <n>` to iterate on one.
- Prints one PNG path per line; timing and seed on stderr.
- `--start` launches ComfyUI from `COMFYUI_DIR` (headless, log in
  `comfy_gen_server.log`) when it is not already running. First call loads the models
  (~50 s for two 9:16 images on a 12 GB RTX 5070); later calls ~13 s per 1024² image.

## Prompting Z-Image Turbo

- Write in **English**, as a description of the photo, not a list of tags: subject,
  setting, light, lens/framing, mood, style. Turbo uses no negative prompt (cfg 1) —
  say what you want, not what you don't.
- **Text in the image:** put the exact words in quotes (`a sign reading "ABERTO"`).
  Short words render well; long sentences don't — add copy in the edit instead.
- **Brand colours:** name them as colours *and* hex ("lime green #C6FF00 accents on
  black"); verify in pixels, the model approximates.
- Format words leak into the picture: "poster", "card", "print" draw a border or
  frame around the scene. Describe the scene itself; say "full-bleed" if a frame shows.
- Never present a generated image as the client's real product, staff or premises.
  Generic scenes, backgrounds, concepts and mascots only.

## Verify before delivering

Open the PNGs (Read the files) and check: hands/faces, any rendered text spelled
right, the brand colour actually present, nothing that reads as a real logo or
person. Regenerate with a new seed rather than shipping a flawed frame.

## Troubleshooting

- `CUDA not available` / `Windows fatal exception: access violation` in
  `torch\cuda\__init__.py` at startup — the portable build's PyTorch targets a newer
  CUDA than the GPU driver supports (the default NVIDIA build ships cu130, which needs
  driver 580+; `nvidia-smi` shows the driver's max CUDA). Update the NVIDIA driver, or
  install a matching wheel into the embedded Python
  (`python_embeded\python.exe -m pip install torch torchvision torchaudio --index-url
  https://download.pytorch.org/whl/cu128` — cu128 is the oldest that has RTX 50-series
  kernels; that index stops at torch 2.11, so pin `torch==2.11.0 torchaudio==2.11.0`). Check: `python_embeded\python.exe -c "import torch; print(torch.cuda.is_available())"`.

- `ComfyUI rejected the graph` — the JSON names the bad node/input; usually a model
  file missing or misnamed. Run `--check`.
- Out of VRAM — use the smaller model files above, lower `--count`, or close other
  GPU apps.
- Slow first image — model load, not generation; keep the server running between calls.
