# Edit spec fields (`spec.json`)

Paths are relative to the spec file unless absolute. See `../assets/spec.example.json`
for a full working example.

| field | type | notes |
|---|---|---|
| `source` | path | input vertical mp4 (default canvas 1080x1920) |
| `output` | path | rendered mp4 destination |
| `work_dir` | path | scratch dir for the font, overlay.mov, filt.txt (default `_reel_work`) |
| `font` | path | TTF to use; auto-downloaded from `style.font_url` if missing |
| `width` / `height` | number | canvas size (defaults 1080 / 1920) |
| `duration` | number | source seconds; omit to auto-probe with ffprobe |
| `style` | object | brand styling — see the style table below. Omit to accept the example-brand defaults |
| `banner` | [string] | **optional** — omit it (along with `captions`/`callouts`) for a graphics-free raw cut; the overlay pass is skipped entirely |
| `banner` (styling) | [string] | 1-2 pre-broken lines, uppercased automatically; auto-shrinks to fit width |
| `banner_cy` | number | banner box vertical center (default 320, ~13-23% from top) |
| `captions` | [{start,end,text}] | times in ORIGINAL seconds; text is the cleaned phrase. <= ~6 words, <= 2 lines |
| `callouts` | [{start,end,text,cy,size,suppress_captions}] | accent box shown over `[start,end]` (original time). `cy` default 620; `suppress_captions` = caption indices to hide while it's up so words aren't doubled |
| `silence_cut` | {enabled,noise_db,min_pause,edge} | remove pauses for the tight feel. defaults noise_db -30, min_pause 0.13, edge 0.035 (speech kept each side of a removed pause) |
| `manual_cuts` | [[start,end]] | explicit removals in ORIGINAL seconds (stumbles, bad takes, VAD-planned cuts); merged with silence cuts |
| `words` | path | optional word-timing JSON of the SOURCE (whisper.cpp `-ojf` output, OpenAI `verbose_json`, or a flat `[{text,start,end}]` array). When set, the QA manifest includes source words remapped onto the output timeline — the input seam checks need |
| `fps` | number or `"source"` | output frame rate (default 30). `"source"` probes the input — use it when handing a 60fps master to a client's editor |
| `crf` / `preset` | number / string | x264 quality/speed (defaults 18 / veryfast) |
| `qa_intentional` | object | free-form notes passed through to the QA manifest (things a checker should not flag) |

## `style` fields (all optional; defaults are the EXAMPLE brand)

| key | default | notes |
|---|---|---|
| `accent_color` | `#8030F8` | banner + callout box fill (the example brand's purple — use yours) |
| `text_color` | `#FFFFFF` | all text |
| `stroke_color` | `#000000` | caption outline color |
| `font_url` | Montserrat variable TTF (Google OFL) | downloaded to `work_dir` on first run; use a VARIABLE font so named weights work |
| `banner_weight` | `Black` | variable-font named instance for the banner |
| `caption_weight` | `ExtraBold` | for captions and callout text |
| `banner_size` | 76 | base px; auto-shrinks until the pre-broken lines fit |
| `caption_size` | 64 | base px; auto-shrinks/wraps to <= 2 lines |
| `callout_size` | 66 | base px; a callout's own `size` field overrides |
| `caption_stroke` | 11 | caption outline width, px |
| `caption_cy` | 1560 | caption block vertical center (bottom third of 1920) |

Capture these values off a reference reel when matching an existing style: sample the
box color from a frame, identify the font, note the banner/caption positions as a
fraction of frame height.

## How timing works when cutting
All caption/callout/manual times are in the ORIGINAL timeline. The script removes the
cut spans, then maps every caption/callout window through `new_t()` (cumulative kept
duration) onto the shortened timeline — so captions stay in sync with the tightened
audio automatically. You author times against the raw clip; the script handles the rest.

## Tuning the "talking over myself" feel
- Tighter: lower `edge` (e.g. 0.03) and/or `min_pause` (e.g. 0.11).
- Looser: raise `edge`.
- If the join clicks because of a music bed, raise/lower `noise_db` or set `silence_cut.enabled:false`
  and rely on `manual_cuts` only.
- For literal voice OVERLAP (one phrase crashing into the next), that needs an
  acrossfade chain — not built in; tell the user if they ask for more than butt-together.
