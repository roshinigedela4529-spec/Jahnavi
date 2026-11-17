# DMart Facts – edit pipeline

Scripts that turn the green-screen DMart Facts recording into a fully edited 1080p documentary-style video.

- `scenes3d.py` – procedural 3D scenes (store exterior, aisles, cart, expansion grid, coin stacks, warehouse, podium…) rendered with Blender Cycles via `bpy`.
- `render_all.sh` – renders every scene at 15 fps and motion-interpolates to 30 fps.
- `compose.py` – timeline/EDL synced to the Telugu narration: chroma-keyed presenter, motion graphics, kinetic typography, transitions, grade.
- `audio.py` – synthesised documentary score and sound effects.
- `assemble.sh` – parallel compositing, audio mix (original narration untouched, music ducked underneath) and final MP4 mux.
