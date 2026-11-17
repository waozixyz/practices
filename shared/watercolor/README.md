# Shared watercolor practice figure

The practice figure (`figure/` in this repository) draws every practice from this continuous CC0 MakeHuman surface. It is shaped by MakeHuman's own CC0 young-adult female macro targets and skinned with MakeHuman's own CC0 default rig weights, folded onto 46 bones. The hip and shoulder hand-overs are diffused across the surface, and the thighs stop at the hip crease. Clothing hems and the hairline are cut exactly along their planes and curves, so each region keeps clean painted edges while the skin stays continuous. Her head adds MakeHuman's eyeballs, a hair shell that rises from the hairline and a low bun, all following the head bone. Brows and lips are painted on the skin's own vertices. Attribution and pinned original source metadata are beside the mesh. The paper, pigment and luminous-wash images are the actual generated bitmap textures used by the reviewed Three.js prototype; generation provenance is in Breeze design/astral-projection/three/assets/README.md.

Regenerate from the canonical Breeze checkout:

```sh
build-queue -- python3 scripts/prepare-practice-human.py --output ../../modules/practices/shared/watercolor
```

`anatomy.bin` uses little endian PFIG0001. The 24-byte header contains magic (8 bytes), vertex/index/bone counts (u32 each), and rest height (f32). Each bone is 32 bytes: role/side/finger/segment (u8), parent (i32), rest origin and tip (three f32 each). Each vertex is 40 bytes: position (three f32), normal (three normalized i16), UV (two f32), four bone IDs (u8), four normalized u16 weights summing to 65535, material region (u8), padding (u8). Triangle indices are u16. Regions are 0 skin, 1 top, 2 trousers, 3 hair, 4 iris, 5 eye white, 6 lips and 7 brows. The native loader validates the whole stream before creating geometry.
