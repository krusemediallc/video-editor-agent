# Brand safety and the copy-review gate

Every typeset word another human will see goes through the copy review (`sloppy-qa`) before it ships.
On this ad the copy review returned FIX twice and was right both times; the list below is what it caught
and the rules that fell out of it. Ask at intake **who runs the ad** — the bar for "the creator's own
feed" and "Arcads' ad account" is different, and the same card can be fine on one and a liability
on the other.

## The rules the copy review enforced

1. **Quote the creator's opinions.** "Easiest method possible", "So good", "I didn't have to do anything"
   are the creator's opinions on the creator's feed and the advertiser's claims in the brand's account. Every opinion
   line carries big “ ” glyphs and the creator's exact words ("the easiest method possible… out there right
   now", never a paraphrase like "I've found" that the creator did not say).
2. **No unsourced numbers at hero size.** The 99% line stays spoken (the creator's call); a 200px `99%`
   plate turns it into the advertiser's stat. Captions only, no count-up, no emphasis pop.
3. **Receipts for every product fact typeset.** Model names must match the vendor's styling and
   exist in the product: "Omni 1.1" (the creator's phrase) has no receipt anywhere; Arcads' help center
   documents *OmniHuman 1.5*, so that is what is typeset. The MCP server URL came from the Arcads
   help-center article ("Arcads MCP" → `https://mcp.arcads.ai`); the terminal shows the real URL and
   the protocol handshake, not an invented CLI flag. Credits attribute sound to Seedance 2.5 because
   the generation script hardcodes `audioEnabled: True` — "SOUND → ARCADS" was a mis-attribution.
   The prompt card streams the real prompt from `generate-storyboard-videos.py::build_prompt`
   (its head only — the template's truncation tails read as our typos).
4. **No banned patterns.** No em dashes anywhere (middle dots and colons instead); no "not X, it's
   Y" rendered as a designed visual (the spoken line is the creator's; the card is the advertiser's); no
   banned vocabulary ("elevating" replaced by the creator's own receipt "without insane creative budgets");
   no hashtags unless the brand supplies one; never call a paid community "free".
5. **Third-party marks as type only.** Claude Code, Seedance 2.5, GPT Image 2, Sora 2 Pro, Veo 3.1,
   Kling 3.0, Nano Banana Pro, Seedream appear as Inter type in the vendor's casing; no logos; only
   the official Arcads mark on screen. A two-name lockup with a connector line implied an official
   integration the creator built — use "Connect Arcads to Claude Code" (the creator's line) instead.
6. **Pixar and Lego** were kept out of on-screen text (blank bars on the rail) until the creator asked
   for them explicitly; when the creator did, they went in and the trademark point was noted once on the
   canvas for Arcads' team. Spoken asides are lower risk than authored on-screen text.
7. **Absolutes about the product** ("no more vocal drift", a strike-through of failure modes) are
   the advertiser's performance claims in their own account. Quote the creator's gripe list verbatim with
   ticks instead of striking problems out, and flag it as a sign-off item.

## The CTA problem (still open at hand-off)

The creator's locked line is "comment AI ads and I'll be sure to send it over". That automation lives on
**the creator's** Instagram. Run from Arcads' handle, every comment lands where nothing is listening
and "I'll send it over" becomes Arcads' promise. V6 removed the comment row from the end card;
V7/V8 restored a chip that mirrors the VO because the audio says it anyway — with the risk
restated on the canvas every round. It resolves only when the creator says how the ad runs
(Partnership Ad from the creator's handle → keep it; Arcads' account → change the card and re-record the CTA).
Do not decide this for the creator, and do not let it drop off the notes.

## Other things a brand team will look at

- Paid-partnership disclosure: none in the cut. Say so once.
- "New models" is the creator's line; some of the eight have been in Arcads for months. Acceptable, not fresh.
- Meta policy: no before/after, no ROI or income claims, no personal-attribute language — this
  script has none, keep it that way in any density pass.
- The example ads on screen are real generated work, muted (`-an` in the proxy transcode) — the
  viewer never hears the Seedance audio the credits mention. Fine, but do not claim otherwise.
