#!/usr/bin/env bash
shopt -s nullglob
# Dense-GOP proxies of every generated Arcads clip so any of them can be a floating card or a
# montage cut without freezing on seek (branded-ad-edit gotcha #5). 720x1280 source -> 1080x1920.
# Usage: GEN=<generated-clip library> OUT=<project>/mg/comp/assets/clips bash transcode-clips.sh
GEN="${GEN:?set GEN to the generated-clip library root}"
OUT="${OUT:?set OUT to <project>/mg/comp/assets/clips}"
FFMPEG="${FFMPEG:-ffmpeg}"
mkdir -p "$OUT"
for f in "$GEN"/video-canvas/v/*.mp4 "$GEN"/seedance25-style-ads/*.mp4 "$GEN"/seedance25-storyboard-videos/*.mp4; do
  n=$(basename "$f" .mp4 | tr -c 'a-zA-Z0-9.\n' '-' | sed 's/-\{2,\}/-/g;s/^-//;s/-$//')
  [ -f "$OUT/$n.mp4" ] && continue
  "$FFMPEG" -v error -y -i "$f" -vf "scale=1080:1920:flags=lanczos" -r 30 -g 30 -keyint_min 30 -sc_threshold 0 \
    -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an -movflags +faststart "$OUT/$n.mp4"
done
ls "$OUT" | wc -l
