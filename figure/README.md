# The practice figure

The practice figures are pixiv's CC0 VRoid sample models, a young woman (the
default) and a young man, in `shared/figure/woman.vrm` and `man.vrm`
(licence and source in `shared/figure/MODELS.md`). The owner chose them on
2026-11-18. MakeHuman-based bodies (MakeHuman, MPFB, Anny, MB-Lab,
CharMorph) were removed and must not come back.

The modules:

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
- `figure_model`: a figure loaded from a glTF 2.0 or VRM file through
  Kryon's importer (`kryon/scene_gltf`) and posed from `FigureJoints`.
  Posed with the practice's time (`FigureModelPose(..., seconds)`), a VRM
  figure's hair and clothes swing on its spring bones (`kryon/scene_vrm`)
  as she moves and turns, and her eyes blink every few seconds
  (`FigureBlink`); a still pose has the hair hanging at rest. Its
  humanoid bones are found by name (VRoid's `J_Bip_*`, Mixamo's
  `mixamorig` and common Blender names). Each pose solves the limbs with
  the model's own segment lengths to reach the solver's wrists and ankles,
  keeping its proportions. It scales the model to the solver's leg length and stands
  its measured barefoot support on the solver's heel/ball contacts. The
  clavicles lift and move forward with the upper arms. The wrist follows the
  solver's palm frame and shares part of its axial turn with the forearm.
  The fingers curl gently unless the technique calls for a fist or hook.
  Eyes follow cued head
  turns gently. `FigureModelToon` gives it a
  cel-shaded look on its own textures.
- `figure_stage` retains the model and renders it to a transparent pixel
  buffer with a fixed orthographic camera. It accepts the bundled VRM
  bytes and shares the same camera geometry with the preview. It skips
  hidden outfits and poses eligible surfaces on the GPU, retaining CPU
  vertices for foot contacts, wrap clearances and cloth corrections. A failed
  GPU frame reposes those skins on the CPU before the CPU renderer draws.
  For live playback, `FigureStageSubmit` queues one frame and
  `FigureStagePoll` publishes it only when ready, without waiting for a GPU
  fence. `FigureStageCancel` discards it on a seek or size change; synchronous
  rendering also cancels pending work. Request IDs increase for the stage's
  lifetime, so hosts can associate completed pixels with the submitted pose.

The prepared models compact each primitive to the vertices its indices use,
including matching facial-expression deltas. Triangle order, skin weights,
normals and UVs stay the same; unreferenced vertices are never posed or uploaded.

The practices' backdrops are in `shared/figure/backdrops/`. The owner's
references for the render quality are in `design/reference/`.

## Tests

Run from the repository root in a managed Harmony command.

```sh
for suite in figure_parts_test figure_model_pose_test figure_model_sole_test figure_cloth_test; do
    ziran build --project --target=c --exe --entry "$suite:main" -o "build/$suite" "tests/$suite.zi" &&
        "build/$suite/$suite" || exit
done
python3 tests/attire_test.py --source-dir backup/figure-source
```

`figure_parts_test` checks that a skinned vertex follows its bone's motion,
the contact shadow, a picture laid over a covering backdrop, and that a
missing model file is refused cleanly.

`figure_model_pose_test` loads both selected VRM skeletons and checks the
rendered hand direction, wrist alignment and planted ankles as the pelvis
moves over fixed foot targets. It also checks clavicle motion on a high
reach, sweeps the palm through a full turn at a fixed wrist and elbow,
and measures skirt clearance as the forearm sweeps across a low reach.
For the Man it checks that his Workout T-shirt draws after his trousers
and covers their waistband through hinges, twists, side bends, a high knee
and a squat.

`figure_model_sole_test` measures actual skinned underside vertices for both
models during flat stances and heel/ball pivots, with a 1 mm floor,
flatness and pivot limit. It repeats them in the Workout outfit and checks
that the lowest drawn point of each figure is on the floor, so neither
stands higher than the other. `attire_test.py` checks the soles against the
original CC0 skin mesh and verifies the reconstructed figures' textures,
skeleton and clothing. See `shared/figure/MODELS.md` for reproduction.

`figure_cloth` drapes the skirt hem, resolves leg and sleeve contacts and
shares displacement across nearby fabric edges. `figure_model` applies
those constraints to the named skirt after skinning. The attire generator
grades sleeve weights across the elbow and fits the man's shoulder and
thigh weights to the underlying body. The Man's Workout T-shirt hangs
over his trousers: it clears their surface and takes the waistband's
skinning near the hem. `figure_cloth_test`
covers the fold through ninety degrees, waist anchoring and capsule
contacts. The preview's `--clothing-audit` checks actual named garment
surfaces throughout every timeline. Its private capture commands render
complete items and slow transitions for visual review.
