# MASTER CONTEXT — Video Editor Agent

Copy this file to `MASTER_CONTEXT.md` and fill it in. Sessions read it first;
empty fields get offered for population as work reveals the answers.

## Brand

- **Brand name:**
- **Website:**
- **Logo file (path in repo or URL):**
- **Palette** (hex values):
  - Primary:
  - Secondary:
  - Accent:
  - Background / text:
- **Fonts** (display / body — and where they come from):
- **Voice / tone** (3–5 adjectives, plus anything to avoid):

## Defaults

- **Default aspect ratio:** (e.g. 9:16)
- **Default resolution / fps:**
- **Default video length target:** (e.g. 30–60s)

## Caption preferences

- **Style:** (karaoke word-sync / line-by-line / none)
- **Font + size:**
- **Placement:** (e.g. lower third, clear of cards)
- **Highlight color / emphasis rules:**
- **Casing / punctuation rules:** (e.g. sentence case, no trailing periods)

## Sound preferences

- **Music bed vibe:** (genre, energy, reference track if any)
- **Bed level vs voice:** (dB offset if you have a preference)
- **SFX density:** (every beat / sparse / only on cards)

## Projects directory (where the videos live)

- **Projects directory:** (absolute path; default = this pack's `outputs/`. Point it at your
  own working repo's media folder if the videos live elsewhere — the skills create
  `<projects dir>/<project-slug>/` and never move media into this pack)
- **Per-project layout conventions:** (e.g. `source.mp4`, `output-vN.mp4`, `review/`, `_qa/`)
- **Raw footage queue(s):** (where new recordings land)
- **Named past edits** (for "edit it like X" requests): (slug → what it was)

## Hard rules (the regimes this reviewer holds you to)

- **Face rule:** (e.g. "never place a graphic over the speaker's face")
- **Full-screen takeovers:** (organic feed vs brand-run ads — when are they expected, when banned?)
- **Approved copy on paid deliverables:** (e.g. "never trim for pacing; only marked alternates and flubs")
- **Copy rules for on-screen text:** (em dashes? hashtags? banned words? a required copy-review pass?)

## Reviewer workflow

- **Who reviews:** (role, not name — e.g. "the founder", "an editor")
- **Delivery channel:** (here.now canvas / file drop / both)
- **Review slug convention:** (e.g. `<project>-review`)
- **Revision expectations:** (e.g. "expect 3–5 rounds", "batch notes per round")
- **Sign-off signal:** (what counts as approved)
- **Canvas config defaults:** (`eyebrow`, `author`, accent colors for video-review-canvas)

## Machine and credentials

- **Binaries:** (ffmpeg/ffprobe/whisper paths if not on PATH; sandbox quirks; GPU render flag)
- **Where each key lives:** (which `.env` holds ELEVENLABS_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY /
  ARCADS_*; never paste the values here — paths only)

## Learnings

Accumulated gotchas and preferences discovered in sessions. Append, don't
rewrite.

- (e.g. "Reviewer prefers the straight zoom crop over blur-pad — show both,
  default to zoom.")

## Changelog

Dated entries: Decision / What changed / Why.

- YYYY-MM-DD — …
