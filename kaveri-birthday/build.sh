#!/usr/bin/env bash
# Renders Kaveri_Birthday.mp4 (1080x1920, 30 fps, H.264 + AAC).
# Needs: node + playwright (chromium), python3 + numpy, ffmpeg.
set -euo pipefail
cd "$(dirname "$0")"
OUT=${1:-Kaveri_Birthday.mp4}
WORKERS=${WORKERS:-4}
PORT=8765
TMP=$(mktemp -d)
python3 -m http.server $PORT --bind 127.0.0.1 >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$TMP"' EXIT
sleep 1

python3 music.py "$TMP/music.wav"

export NODE_PATH=${NODE_PATH:-$(npm root -g)}
FRAMES=$((63 * 30))
CHUNK=$(( (FRAMES + WORKERS - 1) / WORKERS ))
pids=()
for i in $(seq 0 $((WORKERS - 1))); do
  s=$((i * CHUNK)); e=$(( s + CHUNK < FRAMES ? s + CHUNK : FRAMES ))
  node render.js "$TMP/seg$i.mp4" $s $e $PORT &
  pids+=($!)
  echo "file '$TMP/seg$i.mp4'" >> "$TMP/list.txt"
done
for p in "${pids[@]}"; do wait $p; done

ffmpeg -y -loglevel error -f concat -safe 0 -i "$TMP/list.txt" -i "$TMP/music.wav" \
  -c:v copy -af "loudnorm=I=-14:TP=-1.0:LRA=11" -c:a aac -b:a 320k -ar 48000 \
  -movflags +faststart -shortest "$OUT"
echo "done -> $OUT"
