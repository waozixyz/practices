# Shared practice figure media

- `woman.vrm` (the default) and `man.vrm`: the practice figures, CC0 VRoid
  models; licence, source and checksums in `MODELS.md`. Load them with
  `figure_model` (`FigureModelLoad`).
- `backdrops/`: the practices' backdrops (1280 px), generated paintings in
  Inner Breeze's illustration style: a lake terrace for Tai Chi, a sunrise
  hill for Sun Salutation, a woodland deck for the Workout and a moonlit
  veranda for astral projection. Their originals, prompts and checks are
  in `source/` (`provenance.json`); the stored backdrops have their colour
  made about 1.3 times as strong and are sized for phones.

Each backdrop has a same-name JSON ground registration: source-image
horizon, a safe open-floor rectangle, cover crop, camera pitch and minimum
view height. Coordinates exclude the Tai Chi wall/stairs, Workout deck
edges/railings, Sun Salutation foliage and astral veranda railing. The
preview transforms these marks through the actual image crop and fits the
entire motion and contact shadow into the remaining floor.
