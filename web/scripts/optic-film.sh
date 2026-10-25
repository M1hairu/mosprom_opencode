#!/usr/bin/env bash
# Renders the «Оптика» page-change film (optic-film.blender.py) for the phone and the wide screen
# and encodes it into web/public/film/. Run from web/: bash scripts/optic-film.sh [samples]
set -euo pipefail
cd "$(dirname "$0")/.."
samples=${1:-64}
tmp=$(mktemp -d)
mkdir -p public/film
# Variant a — the chase (optic-<aspect>), b — the crane, c — the macro orbit (optic-<v>-<aspect>).
for v in ${VARIANTS:-a b c}; do
  name=$([ "$v" = a ] && echo optic || echo "optic-$v")
  for aspect in portrait landscape; do
    VARIANT=$v blender -b --factory-startup --python scripts/optic-film.blender.py -- "$tmp/$v-$aspect" "$aspect" frames "$samples" >/dev/null
    ffmpeg -loglevel error -y -framerate 30 -start_number 0 -i "$tmp/$v-$aspect/$aspect-%04d.png" \
      -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 22 -preset slow -movflags +faststart -an \
      "public/film/$name-$aspect.mp4"
    ffmpeg -loglevel error -y -framerate 30 -start_number 0 -i "$tmp/$v-$aspect/$aspect-%04d.png" \
      -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 0 -crf 36 -row-mt 1 -deadline good -an "public/film/$name-$aspect.webm"
  done
done
rm -rf "$tmp"
ls -la public/film
