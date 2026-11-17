#!/bin/bash
# Final assembly: composite video in parallel chunks, mix audio, mux to 1080p MP4.
#   WORK=<scratch dir with renders/> SRC=<green screen mp4> ./assemble.sh <out.mp4>
set -euo pipefail
cd "$(dirname "$0")"
OUT=${1:-$WORK/DMart_Facts_Final.mp4}
N=${WORKERS:-4}
DUR=225.5253
CH="$WORK/chunks"
mkdir -p "$CH"

# 1) video: N parallel compositor workers
pids=()
for i in $(seq 0 $((N-1))); do
  python3 compose.py $i $N "$CH" > "$CH/log_$i.txt" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait $p; done
: > "$CH/list.txt"
for i in $(seq 0 $((N-1))); do printf "file 'chunk_%02d.mp4'\n" $i >> "$CH/list.txt"; done
ffmpeg -v error -y -f concat -safe 0 -i "$CH/list.txt" -c copy "$CH/video.mp4"

# 2) audio: score + SFX (synthesised), original narration untouched
python3 compose.py sfx "$WORK/sfx.json"
python3 audio.py music "$WORK/music.wav" $DUR
python3 audio.py sfx "$WORK/sfx.json" "$WORK/sfx.wav" $DUR

# music sits ~14 dB under the voice and ducks a further few dB while he speaks
ffmpeg -v error -y -i "$SRC" -i "$WORK/music.wav" -i "$WORK/sfx.wav" -filter_complex "
  [0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][key];
  [1:a]volume=-16dB[mus];
  [mus][key]sidechaincompress=threshold=0.03:ratio=3:attack=60:release=600:makeup=1[duck];
  [2:a]volume=-9dB[fx];
  [voice][duck][fx]amix=inputs=3:normalize=0:duration=first,alimiter=limit=0.89:level=false[a]" \
  -map "[a]" -c:a pcm_s16le "$WORK/mix.wav"

# 3) mux
ffmpeg -v error -y -i "$CH/video.mp4" -i "$WORK/mix.wav" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k \
  -movflags +faststart -shortest "$OUT"
ffprobe -v error -show_entries format=duration,size -of compact "$OUT"
