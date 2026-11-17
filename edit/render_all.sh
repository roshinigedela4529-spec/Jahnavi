#!/bin/bash
# Render every 3D scene (Cycles at 30/STEP fps) then motion-interpolate each to 30 fps PNGs.
# Env: RENDERS (output dir), RES (e.g. 1024x576), SAMPLES, STEP. Already-rendered frames are kept.
R=${RENDERS:-/tmp/renders}
STEP=${STEP:-2}
cd "$(dirname "$0")"
for v in studioA studioB; do
  [ -f "$R/studio/$v.png" ] || python3 scenes3d.py $v "$R/studio" > "$R/log_$v.txt" 2>&1
done
for s in ${SCENES:-exterior aisleA twin growth money three aisleB cart owned warehouse podium}; do
  [ -d "$R/$s" ] && continue
  find "$R/raw_$s" -size 0 -delete 2>/dev/null
  python3 scenes3d.py $s "$R/raw_$s" > "$R/log_$s.txt" 2>&1
  step=$(cat "$R/raw_$s/.step" 2>/dev/null || echo $STEP)
  mkdir -p "$R/$s.tmp"
  ffmpeg -v error -y -framerate $((30 / step)) -pattern_type glob -i "$R/raw_$s/f_*.png" \
    -vf "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" -start_number 1 "$R/$s.tmp/f_%04d.png" \
    && mv "$R/$s.tmp" "$R/$s"
  echo "done $s $(date +%T)"
done
