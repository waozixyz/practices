# The practice figure

One painted character for every practice. Tai Chi, Sun Salutation, the
Workout and astral projection each keep their own choreography and solver;
they report where her joints are, and this package turns those joints into
the same slim young Chinese woman with sleek black hair in a high bun, in a
jade silk mandarin-collar top with cream frog-knot buttons, navy silk
trousers gathered at the ankle and black cloth shoes. She is drawn to match
Inner Breeze's own storybook illustrations: the style target is
`design/reference/style-target.webp` (made from the Tai Chi banner), and
`character-sheet.webp` beside it shows her in three poses.

It lives here, beside the media it draws (`shared/watercolor/`), so the
surface, its rig, its textures and the code that reads them change together
under one pinned commit. Kryon stays the general renderer (`kryon/scene`,
`kryon/scene_skin`, `kryon/shader`); a particular character and its
practices are not Kryon's.

## Modules

Import them from a project that depends on this repository:

- `figure_anatomy`: reads `anatomy.bin` (PFIG0002, described in
  `shared/watercolor/README.md`) and validates it whole: the body, its loose
  cloth shells, UVs that follow the form and where the face painting lies.
- `figure_joints`: `FigureJoints`, the solver-neutral joint pose, and
  `FigurePose`, which turns it into one motion per bone. Limbs start at the
  surface's own shoulder and hip sockets as the trunk carries them, follow
  their bend plane when bent and swing without twisting when straight. The
  forearm takes half of the hand's turn. Fingers close toward the middle
  finger; an open hand keeps a slight, even curl and a hook cups the whole
  finger instead of clawing the tips.
- `figure_skin`: dual-quaternion skinning, so folded hips, deep knees,
  turned wrists and raised arms keep their volume.
- `figure_shader`: the portable shaders. Each region's painted texture, and
  the face painting on the face, is shaded in soft steps (a cool shadow, or a
  warm rosy one on skin, the local colour, and a light where the paper
  shows) with a light fabric and brush texture. Cloth creases where it
  gathers, a fine dark line follows the inner contours, and there is no
  specular light.
- `figure_wash`: the finish on the rendered picture, by default clean with
  only a little texture: a slight softening of seams, faint dried edges,
  light granulation, paper grain, colour strength about each pixel's own lightness (so darks
  deepen instead of turning muddy), and a sepia ink line on the silhouette
  and the seams between regions that changes width and breaks off (never
  along the hairline). It
  also paints the ground shadow, covers a picture with a painted backdrop
  (`FigureBackdropCover`) and lays one picture over another (`FigureOver`).
- `figure_paint`: `FigureMediaLoad`, `FigurePainter` and `FigurePaint`. It
  renders every region of one skinned surface with its own material through
  Kryon's GPU path, or the CPU when there is none. The top's lower part
  swings towards the ground as the pelvis tips (a fold, a plank, downward
  dog) and lies closer on her as it does; cloth creases open and close with
  how far it is gathered. `painter.times` holds how long each step of the
  last picture took. `FigureStyle` sets the finish, turns
  it or the shadow off, or paints a translucent luminous double.
  `FigureEffect` moves the whole body rigidly, for an astral exit.

A practice converts its own solved joints into `FigureJoints` (Breeze's
`design/figure-preview/preview_practices.zi` does it for all four practices),
paints into `painter.pixels` over its backdrop
(`shared/watercolor/backdrops/`) and shows that picture however its UI draws
images.

At the pinned Kryon a sampler texture first uploaded during a frame can take
another sampler's unit, so the first picture is painted twice (reported to
Kryon).

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
keep their volume without tearing the surface or its clothes.
`figure_paint_test` paints from the real media and checks her coverage, the
clear background, that top, trousers and skin take their painted colours,
the ink line round her silhouette, the ground shadow, the top's hem hanging
towards the ground when the pelvis tips, a backdrop covering the picture,
the bare look and the translucent double.
