# Layer 3 — whole-video semantic QA (Gemini watches AND listens)

Optional layer. A multimodal model reviews the whole render — video **and** audio
together — and returns candidate issues as schema-enforced JSON. Its timestamps are
approximate (±1–2s): its job is to tell you WHERE to look. L4 verifies before anything
is changed. Gemini-only findings never exceed HIGH; corroboration with a deterministic
finding is what raises confidence.

**Auth:** `GEMINI_API_KEY` read from the `.env` at repo root (e.g.
`set -a; . ./.env; set +a`). Missing → mark the layer `skipped` with the reason and move
on — never crash, never block the run. Model: `GEMINI_QA_MODEL` env var, default
`gemini-flash-latest` (the alias tracks the current Flash model and avoids id churn).

## 1. Build a 480p proxy — with the audio intact

Half of real editing mistakes are audible. Never strip or downsample the audio to
nothing:

```bash
"$FF" -nostdin -y -i "$VIDEO" -vf "scale=-2:480,fps=15" \
  -c:v libx264 -preset veryfast -crf 30 -c:a aac -b:a 128k \
  -movflags +faststart "$QA/proxy.mp4"
```

## 2. Upload via the Files API (resumable), poll until ACTIVE

```bash
BASE=https://generativelanguage.googleapis.com
SIZE=$(wc -c < "$QA/proxy.mp4" | tr -d ' ')
# start → the upload URL comes back in the x-goog-upload-url response header
curl -si -X POST "$BASE/upload/v1beta/files" \
  -H "X-goog-api-key: $GEMINI_API_KEY" \
  -H "X-Goog-Upload-Protocol: resumable" -H "X-Goog-Upload-Command: start" \
  -H "X-Goog-Upload-Header-Content-Length: $SIZE" \
  -H "X-Goog-Upload-Header-Content-Type: video/mp4" \
  -H "Content-Type: application/json" \
  -d '{"file":{"display_name":"qa-proxy.mp4"}}'
# upload + finalize against that URL:
curl -s -X POST "<upload-url>" \
  -H "X-Goog-Upload-Command: upload, finalize" -H "X-Goog-Upload-Offset: 0" \
  --data-binary @"$QA/proxy.mp4"
# poll GET $BASE/v1beta/<file.name> (X-goog-api-key header) every ~4s until
# state == ACTIVE (videos need server-side processing; give up after 5 min)
```

## 3. generateContent with an ENFORCED response schema

JSON output is enforced via `responseSchema`, not prompt-please. Request body:

```json
{
  "contents": [{ "parts": [
    { "file_data": { "file_uri": "<file.uri>", "mime_type": "video/mp4" },
      "video_metadata": { "fps": 5 } },
    { "text": "<the prompt, below>" }
  ]}],
  "generationConfig": {
    "temperature": 0.2,
    "responseMimeType": "application/json",
    "responseSchema": { "type": "object", "required": ["issues"], "properties": {
      "issues": { "type": "array", "items": { "type": "object",
        "required": ["startSec","endSec","severity","category","objective","description"],
        "properties": {
          "startSec": {"type":"number"}, "endSec": {"type":"number"},
          "severity": {"type":"string","enum":["high","medium","low"]},
          "category": {"type":"string","enum":["abrupt_cut","clipped_dialogue","audio_glitch","music_balance","sync_issue","dead_air","caption_error","visual_glitch","duplicate_footage","framing_crop","graphic_timing","pacing","content_error","other"]},
          "objective": {"type":"boolean"}, "confidence": {"type":"number"},
          "description": {"type":"string"} } } },
      "overallNotes": {"type":"string"} } }
  }
}
```

POST to `$BASE/v1beta/models/$MODEL:generateContent` with the `X-goog-api-key` header.
**`video_metadata.fps: 5`** for videos under ~3 minutes (Gemini's 1fps default misses
fast visual events); 1fps for long ones. **Retry 503/429 ×3** with growing backoff
(~15s, 30s, 45s), then degrade the layer to `skipped` with the reason.

## 4. The prompt (calibration lines matter — keep them)

> You are a professional short-form video editor doing final QA on an export before it
> ships. The file has BOTH video and audio. Review them TOGETHER — listen while you
> watch. Roughly half of real editing mistakes are audible, not visible (clipped words at
> cuts, duplicate phrases, abrupt music, dead air, clicks at splices, SFX drowning the
> voice).
>
> Report across both modalities:
> - VISUAL: glitches, stray/duplicate frames, wrong or repeated footage, jarring
>   transitions, bad crop or framing, subject cut off, graphics appearing/disappearing at
>   wrong times, captions covering the speaker's face, caption timing/text problems,
>   unintended blank space, abrupt start or ending, b-roll that doesn't match what is
>   being said.
> - AUDIO & AUDIO-VISUAL: words cut off mid-syllable, dialogue repeated across a cut,
>   audio/video desync, dead air, unintentional silence, music starting/stopping
>   abruptly, music/dialogue balance, sound effects mistimed or masking speech, pacing.
>
> Calibration — follow exactly:
> - Zero issues is a valid and expected outcome for a clean video. Do not invent problems.
> - Report mistakes, unintended behavior, deviations from instructions, and obvious
>   quality problems. Do not fail the video because you would make a different creative
>   choice.
> - Separate objective errors (objective=true) from subjective suggestions
>   (objective=false) and label each.
> - Fast jump cuts, karaoke captions, and bold graphic cards are the INTENTIONAL style of
>   these edits — only flag a cut if something is audibly or visibly broken at it.
> - Your timestamps may be off by ±2 seconds; report your best estimate without agonizing
>   over precision.
>
> Edit intent (from the editing system — treat as ground truth for what is deliberate):
> `<summary: lane, expected duration, cut seam times, caption count, placed elements,
> INTENTIONAL black/silent regions from the manifest>`
>
> Original editing request/instructions: `<the user's brief, when available>`
>
> Return JSON only, matching the response schema.

Feeding the manifest summary in is what stops the model from flagging deliberate jump
cuts and intentional silences. Feeding the original brief lets it catch deviations from
instructions.

## 5. Post-process

For each returned issue: clamp times into [0, duration]; map severity
high/medium/low → HIGH/MEDIUM/LOW; anchor to the nearest manifest event within 2s; keep
the raw reported window in evidence. Pad windows ±1.5s before building an L4 packet.
Layer status: any HIGH → `fail` · any issue → `warn` · else `pass`.
