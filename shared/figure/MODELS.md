# The practice figures' models

`woman.vrm` and `man.vrm` are pixiv's VRoid Studio sample models
`HairSample_Female` and `HairSample_Male`, chosen by the owner on
2026-11-18 from the candidates in Breeze's
`plans/2026-11-18-figure-model-candidates.md`.

- Licence: CC0 1.0 (public domain dedication). Each file's own VRM
  metadata says `"licenseName": "CC0"`, `"commercialUssageName": "Allow"`
  and `"allowedUserName": "Everyone"`. pixiv's list of VRoid Studio sample
  models says of these: "The CC license for these models is CC0. This
  model can be edited and used freely. Copyright is waived, and there is no
  particular limit when using them." No attribution is needed.
- Source: pixiv's VRoid Studio sample models, as mirrored unchanged at
  <https://github.com/madjin/vrm-samples> (`vroid/beta/HairSample_Female.vrm`
  and `vroid/beta/HairSample_Male.vrm`).
- Original SHA-256:
  - `woman.vrm` adfd242317aaabc773f31f7fff7b013979fbb5baa47e97427a78913d9cb4e979
  - `man.vrm` 7aeca142dabbc26ba0f5b9c998c8f3cb6df341287d67788427ac837223785a3f
- Format: VRM 0.x (glTF 2.0 binary with the `VRM` extension), PNG textures,
  a VRM humanoid skeleton with hair spring bones. 27,068 and 24,858
  triangles.

On 2026-11-18 the owner requested simple, flat cloth Tai Chi slippers for
both figures. `figure/tools/prepare_slippers.py` removes only the original
shoe primitives and adds closed, rounded cloth slippers: matte stone grey
for the woman and charcoal for the man, a 3 mm edge and 57 mm upper, with
one level underside and no heel or platform. The rest of the mesh,
textures, skeleton and VRM metadata is retained. Output checksums and sole
measurements are in `slippers.json`; the CC0 dedication still applies.

Reproduce from the original files (checksums above), kept in the ignored
`backup/figure-source/` directory during development:

```sh
python3 figure/tools/prepare_slippers.py --source-dir backup/figure-source
python3 tests/slippers_test.py --source-dir backup/figure-source
```

The originals can also be recovered from this repository's pre-slipper
revision or the source URLs above. The pipeline refuses modified input,
so re-running it never compounds a previous edit. No texture regeneration
or changes to the other clothing, hair or face are part of this edit.

Kryon's importer loads these models through `figure_model`, using the
approved toon look. The retargeter measures actual sole vertices and fits
the foot length to the solver's heel/ball span, keeping both pivots fixed.
Only foot-only primitives use affine skinning for that length adjustment;
the rest retain volume-preserving dual-quaternion skinning.

## Traditional meditation attire

The owner's later request includes the clothes and explicitly keeps the
woman's skirt. `figure/tools/prepare_attire.py --source-dir
backup/figure-source` starts from the same checksummed originals, builds the
existing neutral flat slippers, and then replaces only clothing draw
primitives. The new matte linen colors, crossed cloth facings and fitted
sash form a calm traditional-inspired wrap. The woman retains the fitted
long-sleeve top and flared skirt silhouette; the man loses the hoodie/cord
geometry and gains a cross-collar tunic with relaxed trousers. Faces,
hair, bodies, skeleton, expressions, source texture bytes, CC0 metadata and
slipper geometry remain intact. Blended skin weights at the sleeves and
the trouser seat spread deformation through those joints. `attire.json`
records exact output identity and the source primitives replaced.

The skirt is its own `PracticeSkirt` mesh. `figure_cloth` and
`FigureModelCloth` constrain its lower portion under gravity, outside leg
capsules and above the floor, while preserving the skinned waist seam.
Short edge-length constraints distribute the drape below the waist during
forward folds and lunges. The constraints use the pose at the requested
time, so seeking to a frame gives the same drape as playing it. The
pre-attire slippers and original models remain in ignored recovery storage.

```sh
python3 figure/tools/prepare_attire.py --source-dir backup/figure-source
python3 tests/slippers_test.py --source-dir backup/figure-source
python3 tests/attire_test.py --source-dir backup/figure-source
```
