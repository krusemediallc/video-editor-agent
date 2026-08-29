# Environment, dependencies, and machine gotchas

## Dependencies

- **ffmpeg / ffprobe** — any build works; the scripts deliberately avoid `drawtext`
  and `subtitles`. Found on PATH, or set `FFMPEG` / `FFPROBE` env vars.
- **python3 + Pillow (PIL)** — renders all text/graphics (`pip install pillow`).
- **whisper-cli (whisper.cpp) + a ggml model** — local transcription and per-seam
  verification. Set `WHISPER_MODEL` to the model path for `verify_cuts.py`.
  For VAD, whisper.cpp's `whisper-vad-speech-segments` with a silero VAD ggml model.
- **yt-dlp** (optional) — when the source is a URL (IG reel, TikTok, YouTube) rather
  than a local file, download it first and feed the local path in.
- **OPENAI_API_KEY** (optional) — cloud Whisper word timestamps, read from a `.env`
  at the repo root (never hardcode it). Local whisper-cli is the default route.
- **claude-video-vision plugin** (optional) — `video_analyze` / `video_watch` for
  scene/silence/loudness analysis and frame reading. Without it, use plain ffmpeg
  frame extraction + whisper transcription; everything still works.

## Hard-won gotchas (why the scripts are shaped this way)

- **Some ffmpeg builds have no libass and no libfreetype.** On such a build
  (`ffmpeg -filters | grep -E 'subtitles|drawtext'` returns nothing) burned-in text is
  impossible via the normal filters. `build_reel.py` therefore renders ALL text with
  PIL into transparent PNGs and composites with `overlay` — an approach that is fully
  portable and works on every ffmpeg build, so it was kept even where drawtext exists.
- **Pre-compose graphics into ONE overlay video.** Feeding many `-loop 1 -i x.png`
  inputs into one libx264 encode thrashes swap on a 16 GB machine (one such render ran
  ~55 min before being killed). The script composites banner+captions+callouts into a
  single qtrle/argb `overlay.mov`, so the final render is just 2 inputs and finishes
  in seconds. Do not hand-build a 30-input filtergraph.
- **Agent sandboxes can kill Node/ffmpeg** (SIGURG / odd exit codes like 144). If
  renders die inexplicably under a sandboxed shell, re-run with the sandbox disabled.

## Whisper word timestamps (two routes)

- **Local (default):** `whisper-cli -m <ggml-model> -f clip.wav -ojf` writes a full
  JSON with token-level offsets; `build_reel.py`'s `load_words()` reads it directly
  (point the spec's `words` field at it).
- **Cloud:** OpenAI API with `response_format=verbose_json` and
  `timestamp_granularities[]=word`:
  ```
  curl https://api.openai.com/v1/audio/transcriptions -H "Authorization: Bearer $OPENAI_API_KEY" \
    -F file=@clip.wav -F model=whisper-1 -F response_format=verbose_json \
    -F "timestamp_granularities[]=word"
  ```
  Extract a sub-clip with `-ss/-t` for long sources and add the offset back.

Extract audio for any of this with:
`ffmpeg -i clip.mp4 -ac 1 -ar 16000 -c:a pcm_s16le raw-audio.wav`

## Delivery conventions

- **Keep the original raw untouched** — render to a new file side-by-side.
- The user usually wants a phone-viewable link, not a file path: publish a review
  page (e.g. with the here-now skill — agent docs at https://here.now/docs, fetch
  with `User-Agent: claude`) or upload to any no-login file host and send the URL.
- Big masters (60fps, low CRF) want a 720p proxy for the review player; keep the
  full-quality master on disk for the client.
