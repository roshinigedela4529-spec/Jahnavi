#!/bin/bash
# Render every 3D scene (Cycles, 15 fps) then motion-interpolate each to 30 fps PNGs.
R=${RENDERS:-/tmp/renders}
cd "$(dirname "$0")"
for v in studioA studioB; do python3 scenes3d.py $v "$R/studio" > "$R/log_$v.txt" 2>&1; done
for s in exterior aisleA twin growth money three aisleB cart owned warehouse podium; do
  python3 scenes3d.py $s "$R/raw_$s" > "$R/log_$s.txt" 2>&1
  mkdir -p "$R/$s"
  ffmpeg -v error -y -framerate 15 -pattern_type glob -i "$R/raw_$s/f_*.png" \
    -vf "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" -start_number 1 "$R/$s/f_%04d.png"
  echo "done $s $(date +%T)"
done
