# Shared watercolor practice figure

The native Tai Chi, Workout and astral painters share this continuous CC0 MakeHuman surface. Attribution and pinned original source metadata are beside the mesh. The paper, pigment and luminous-wash images are the actual generated bitmap textures used by the reviewed Three.js prototype; generation provenance is in Breeze design/astral-projection/three/assets/README.md.

Regenerate from the canonical Breeze checkout:

```sh
build-queue -- python3 scripts/prepare-practice-human.py --output ../../modules/practices/shared/watercolor
```

`anatomy.bin` uses little endian PFIG0001. The 24-byte header contains magic (8 bytes), vertex/index/bone counts (u32 each), and rest height (f32). Each bone is 32 bytes: role/side/finger/segment (u8), parent (i32), rest origin and tip (three f32 each). Each vertex is 40 bytes: position (three f32), normal (three normalized i16), UV (two f32), four bone IDs (u8), four normalized u16 weights summing to 65535, material region (u8), padding (u8). Triangle indices are u16. Regions are skin, tunic, trousers and hair. The native loader validates the whole stream before creating geometry.
