# Worked example (proving run)

A real delivery built with this exact workflow: a paid brand-deal edit for a
server-side ad-tracking SaaS. Study the SHAPE — every element generalizes. (The
brand is anonymized below; `[brand]` is the client, `[tool]` is the incumbent ad
platform being attacked.) The project consisted of exactly the files this skill
teaches you to build: a hand-authored `index-template.html` (and a v2 template
after client feedback), a build script that injects generated captions/SFX into
it, and `storyboard.json`.

A second proving run — a 4-round style-clone reel — exercised the newer machinery,
all of which now lives in this skill's references: the multi-take assembly cut with
per-segment isolated transcription (SKILL.md §1 + gotcha #18), EDL-chained revision
retimes across versions (references/variants.md §Revision cuts + gotcha #20),
per-clip frame-accurate captioning stitched through the EDL (gotcha #19), and the
here.now timestamped review page (SKILL.md §10). Nothing beyond those references is
needed to reproduce either delivery.

**Source:** 72s raw talking-head, 4K 16:9. **Brand:** dark navy site, electric-blue
accent, Inter. **References:** a swipe board of 15 winning ads (split-screen +
floating metric cards + bold short captions).

## The beat map that shipped (18 cards)

| # | Time | Line (gist) | Mode | Card |
|---|---|---|---|---|
| 1 | 0–3.1 | "the data in [tool] isn't correct" | split | real screenshot + red WRONG stamp on "correct" |
| 2 | 3.1–8.5 | "costing you $500 every single day" | split | red $0→$500 count-up on the word "$500", sub after |
| 3 | 8.6–13.0 | "you're lighting $500/day on fire" | **fullhim** | flame-gradient $500/DAY + 🔥 chip over full-bleed speaker |
| 4 | 13.0–17.4 | "[tool] will never tell you… 100% preventable" | solo | black banner + green "100% PREVENTABLE" pill above centered speaker |
| 5 | 17.5–20.0 | "from this to this" | split | metric screenshot BEFORE (red) slides on "this"₁, AFTER (green) on "this"₂ |
| 6 | 20.1–23.0 | "same ad, same spend, fixed tracking" | split | 3 chips popping word-synced, payoff chip brand-filled |
| 7 | 23.1–28.8 | "iOS, cookies, ad blockers hide 60% of sales" | split | 3 icon tiles word-synced → red 60% count-up |
| 8 | 28.9–33.5 | "the algorithm targets the wrong people, you pay" | split | person-dot grid, wrong ones flip red, STAMP over dimmed grid |
| 9 | 33.6–42.0 | "everyone screams more ads/creative/structure but…" | split | rows pop word-synced → strikethroughs → glowing answer row |
| 10 | 42.0–44.3 | "not as sexy as some AI trend" | **fullhim** | dismissive chip over speaker, grays out |
| 11 | 44.4–46.5 | "you know what is sexy? Money." | **full** | giant green MONEY. takeover on the word (card enters only after the framing cut — never over the face) |
| 12 | 46.5–48.9 | "in under two minutes" | solo | ring-timer draws above speaker |
| 13 | 49.0–53.7 | "[brand] finally fixed it" | split | wordmark pop + hero B-roll in browser frame |
| 14 | 53.7–57.1 | "server-side tracking is non-negotiable" | solo | headline + brand-blue chip above speaker |
| 15 | 57.2–61.7 | "5-star chef, rotten ingredients, garbage in/out" | split | emoji tiles + red pipeline chips, all word-synced |
| 16 | 61.8–65.5 | "9,000 stores, 4.9 stars" | split | reviews B-roll + green 9,000+ count-up + gold ★4.9 |
| 17 | 65.6–69.2 | "+20% ROAS or your money back" | split | green outlined shield, pulse on "20%" |
| 18 | 69.3–72.0 | "tap learn more, free 14-day trial" | **full** | CTA: logo, offer line, pulsing button, bounce arrow |

Audio: 45 SFX hits from a 12-effect kit; suspense bed at data-volume 0.10
(0dB-peak track under VO peaking −7dB).

## What was delivered

- `output.mp4` — v1 (no sound design) — kept untouched once approved
- `output-v2.mp4` — full edit + SFX + music + fullhim/solo grammar (72s)
- `output-v2-hookA.mp4` — hook 1 only ("the data is wrong…"), fire line cut (67.6s)
- `output-v2-hookB.mp4` — hook 2 only, opens full-bleed with a banner kicker (63.5s)

The raw cut had stacked BOTH hooks back-to-back — common in creator raw cuts, and
splitting them produced the A/B variant the brand's brief required anyway. Look for
this: two consecutive openings restating the same promise = ship two versions.

## Notes that transfer

- The client's reaction to v1 drove v2's brief: "more full-screen me for drama, more
  of that center-stage move, SFX on the motion." Deliver a strong v1 fast; the
  redirects write v2.
- Hook B's first draft opened on captions alone over a black screen (a build bug, but
  the note stands): **an opening frame must carry the speaker or a graphic**, never
  text alone.
- Real Ads-Manager screenshots (their asset folder) in white cards carried more
  credibility than any designed graphic — hunt for the brand's real numbers first.
