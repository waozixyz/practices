# The practice figure

One anatomical watercolor character for every practice. Tai Chi, Sun
Salutation, the Workout and astral projection each keep their own
choreography and solver; they report where her joints are, and this package
turns those joints into the same painted woman.

It lives here, beside the media it draws (`shared/watercolor/`), so the
surface, its rig, its textures and the code that reads them change together
under one pinned commit. Kryon stays the general renderer (`kryon/scene`,
`kryon/scene_skin`, `kryon/watercolor`); a particular character and its
practices are not Kryon's.

## Modules

Import them from a project that depends on this repository:

- `figure_anatomy`: reads `anatomy.bin` (PFIG0001, described in
  `shared/watercolor/README.md`) and validates it whole.
- `figure_joints`: `FigureJoints`, the solver-neutral joint pose, and
  `FigurePose`, which turns it into one motion per bone. Limbs start at the
  surface's own shoulder and hip sockets as the trunk carries them, follow
  their bend plane when bent and swing without twisting when straight. The
  forearm takes half of the hand's turn. Fingers close toward the middle
  finger and keep a slight curl.
- `figure_skin`: dual-quaternion skinning, so folded hips, deep knees,
  turned wrists and raised arms keep their volume.
- `figure_paint`: `FigureMediaLoad`, `FigurePainter` and `FigurePaint`. It
  renders through Kryon's GPU path, or the CPU when there is none. Two
  washes split along an uneven, pigment-driven edge, with a wet edge, paper
  showing through the fullest light, and grain. Kryon's brush, pooling and
  pencil finish follows, then a soft floor shadow. `FigureStyle` turns the
  finish or the shadow off, or paints a translucent luminous double.
  `FigureEffect` moves the whole body rigidly, for an astral exit.

A practice converts its own solved joints into `FigureJoints` (Breeze's
`design/figure-preview/preview_practices.zi` does it for all four practices),
paints into `painter.pixels` and shows that picture however its UI draws
images.

## Tests

Run from the repository root through the build queue:

```sh
build-queue -- ziran build --project --target=c --exe --entry figure_test:main -o build/figure-test tests/figure_test.zi
build-queue -- ./build/figure-test/figure_test
build-queue -- ziran build --project --target=c --exe --entry figure_paint_test:main -o build/figure-paint-test tests/figure_paint_test.zi
build-queue -- env -u DISPLAY EGL_PLATFORM=surfaceless ./build/figure-paint-test/figure_paint_test
```

`figure_test` checks that the rest joints reproduce the bind surface
exactly, and that a 150° wrist turn, a 120° knee fold and a 110° hip fold
keep their volume without tearing the surface. `figure_paint_test` paints
from the real media and checks her coverage, the clear background, the floor
shadow, the bare look and the translucent double.
