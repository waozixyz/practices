# The practice figure

The figure model is pending. The MakeHuman-based characters were removed on
2026-11-18 at the owner's request and must not come back, in any form
(MakeHuman, MPFB, Anny, MB-Lab or CharMorph). A new model, under a licence
that allows a commercial app, will be chosen by the owner; the candidates
are in Breeze's `plans/2026-11-18-figure-model-candidates.md`.

What stays here does not depend on a model and serves the next one:

- `figure_math`: vectors and quaternions.
- `figure_joints`: `FigureJoints`, the solver-neutral pose every practice
  reports (where each joint is and how the trunk, head, hands and feet
  turn), and `FigureBonePose`, one bone's bind-to-pose motion.
- `figure_skin`: dual-quaternion skinning of a Kryon `SceneSkin`, so folded
  hips, deep knees, turned wrists and raised arms keep their volume.
- `figure_finish`: setting a rendered figure into a practice's picture: a
  soft contact shadow, a backdrop covering the picture
  (`FigureBackdropCover`) and pictures laid over each other (`FigureOver`,
  `FigureOverOnto`).

The practices' backdrops are in `shared/figure/backdrops/`. The owner's
references for the render quality are in `design/reference/`.

## Tests

Run from the repository root through the build queue:

```sh
build-queue -- ziran build --project --target=c --exe --entry figure_parts_test:main -o build/figure-parts-test tests/figure_parts_test.zi
build-queue -- ./build/figure-parts-test/figure_parts_test
```

`figure_parts_test` checks that a skinned vertex follows its bone's motion,
the contact shadow, and a picture laid over a covering backdrop.
