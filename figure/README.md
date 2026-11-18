# The practice figures

Two characters for every practice: a petite young Chinese woman (the
default) and a young Chinese man. Tai Chi, Sun Salutation, the Workout and
astral projection each keep their own choreography and solver; they report
where the joints are, and this package turns those joints into either
figure. She wears a fitted jade top with a stand-up collar, cap sleeves and
cream frog knots, and slim navy trousers, with sleek black hair in a high
bun; he wears a loose indigo kung fu jacket with frog knots and wide black
trousers, with short black hair. Both go barefoot.

They are lit like the owner's reference sculptures
(`design/reference/body-female-sculpt.png` and `body-male-taichi.png`):
smooth surfaces and clean colours under a soft studio light, with no paint,
paper or grain. The backdrops keep Inner Breeze's illustration style.

They live here, beside the media they draw (`shared/figure/`), so the
surfaces, their rig, their texture maps and the code that reads them change
together under one pinned commit. Kryon stays the general renderer
(`kryon/scene`, `kryon/scene_skin`, `kryon/shader`); particular characters
and their practices are not Kryon's.

## Modules

Import them from a project that depends on this repository:

- `figure_anatomy`: reads a character's `anatomy.bin` (PFIG0002, described
  in `shared/figure/README.md`) and validates it whole: the body, its cloth
  shells and hair, UVs that follow the form and where the face map lies.
- `figure_joints`: `FigureJoints`, the solver-neutral joint pose, and
  `FigurePose`, which turns it into one motion per bone. Limbs start at the
  surface's own shoulder and hip sockets as the trunk carries them, follow
  their bend plane when bent and swing without twisting when straight. The
  forearm takes half of the hand's turn. Each foot keeps its own size and
  points down just enough for its toes to reach the solver's toe height, so
  they stay on the ground. Fingers close toward the middle
  finger; an open hand keeps a slight, even curl and a hook cups the whole
  finger instead of clawing the tips.
- `figure_skin`: dual-quaternion skinning, so folded hips, deep knees,
  turned wrists and raised arms keep their volume.
- `figure_shader`: the surface colour: each region's texture map, the face
  map over the face, and the colour strength. Kryon's standard material
  lights it.
- `figure_finish`: setting the rendered figure into a picture: a soft
  contact shadow under the feet, a backdrop covering a picture
  (`FigureBackdropCover`) and one picture laid over another (`FigureOver`,
  `FigureOverOnto`).
- `figure_paint`: `FigureMediaLoad` (`FIGURE_FEMALE` or `FIGURE_MALE`),
  `FigurePainter` and `FigurePaint`. It renders every region of one skinned
  surface with its own material through Kryon's GPU path, or the CPU when
  there is none, under a warm key light that casts soft shadows, a cool
  fill, a rim light from behind and a sky and ground. Normals are recomputed
  from the posed surface every frame, so bent joints and swinging cloth
  shade smoothly, and are shared across hems and texture seams. The jacket's
  skirt swings towards the ground as the pelvis tips (a fold, a plank,
  downward dog). `painter.times` holds how long each step of the last
  picture took. `FigureStyle` sets the colour strength, turns the shadows
  off, or paints a translucent luminous double. `FigureEffect` moves the
  whole body rigidly, for an astral exit. A painter is prepared for one
  character; release it to paint the other.

A practice converts its own solved joints into `FigureJoints` (Breeze's
`design/figure-preview/preview_practices.zi` does it for all four practices),
paints into `painter.pixels` over its backdrop (`shared/figure/backdrops/`)
and shows that picture however its UI draws images.

## Tests

Run from the repository root through the build queue:

```sh
build-queue -- ziran build --project --target=c --exe --entry figure_test:main -o build/figure-test tests/figure_test.zi
build-queue -- ./build/figure-test/figure_test
build-queue -- ziran build --project --target=c --exe --entry figure_paint_test:main -o build/figure-paint-test tests/figure_paint_test.zi
build-queue -- env -u DISPLAY EGL_PLATFORM=surfaceless ./build/figure-paint-test/figure_paint_test
```

`figure_test` checks, for both characters, that the rest joints reproduce
the bind surface exactly, and that a 150° wrist turn, a 120° knee fold and a
110° hip fold keep their volume without tearing the surface or its clothes.
`figure_paint_test` paints both from the real media and checks the coverage,
the clear background, that the clothes and skin take their colours, that
the surface is smooth and clean without grain, that the light models the
form, that the normals are recomputed whole, the contact shadow, the
jacket's hem hanging towards the ground when the pelvis tips (and that her
fitted top has none), a backdrop covering the picture and the translucent
double.
