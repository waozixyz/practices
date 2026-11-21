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
  a VRM humanoid skeleton with hair spring bones.

## Bare feet and meditation attire

The figures use the original bare feet, including toe geometry, skin texture
and UV layout. The generator removes shoe primitives and levels the plantar
surface below the ankle. A gradual blend from foot to shin weights lets the
heel and instep retain their shape through deep knee bends. `attire.json` records the finished asset checksums,
triangle and contact counts, and each heel-to-ball span.

Kryon's importer loads these models through `figure_model`. The retargeter
measures the skinned soles and places the loaded heel or forefoot at the
solver's pivot. Each avatar keeps its original foot proportions. The toes
flex at the floor as the feet roll.

The matte linen colors, crossed facings and fitted sash form a traditional
wrap. The woman keeps the long-sleeve top and flared skirt. The man wears a
cross-collar tunic with relaxed trousers. Blended weights at the sleeves and
trouser seat spread deformation through each joint. The generator preserves
faces, hair, skeletons, expressions and CC0 metadata. The man’s skin uses a
copy of the original atlas with the painted sock colour removed at the ankles
and feet. The generator retains the original atlas in the model.

The separate `PracticeSkirt` mesh keeps its skinned waist seam. Its lower
portion drapes around the legs and sleeves, stays above the floor, and
spreads the displacement across neighboring fabric edges. The current pose
sets these constraints so seeking and playback produce the same drape.
Airborne drape opens with the legs. In a low prone pose, spare length follows
the legs along the floor.

Workout uses a crop top and lined sports skirt on the same woman.
`PracticeTrainingBody` assigns body faces to the crop top and undershorts.
`PracticeTrainingSkirt` has a fitted waist, shallow pleats and a contrasting hem.
Its front panels follow the thighs while the back stays close to the hips.
The renderer switches the wardrobe in the retained scene and shares the face,
hair, skin and bare feet across practices.

Reproduce from the checksummed originals in `backup/figure-source/` with NumPy
and Pillow installed.

```sh
python3 figure/tools/prepare_attire.py --source-dir backup/figure-source
python3 tests/attire_test.py --source-dir backup/figure-source
```
