# Inner Breeze practices

The media Inner Breeze builds its practices from: Sun Salutation character
frames, Tai Chi course data and figures, narration recordings in every
language, Lumi's guide narration, and each practice's banners and previews.

[Inner Breeze](https://github.com/waozixyz/breeze) pins this repository by
commit in `ziran.toml` and `ziran.lock` and links it at
`build/packages/practices`. Its build stages these files under
`assets/practices/` and packs each practice, and each narration language, as
its own downloadable package. Narration receipts, voice settings and the text
the recordings are made from stay in Breeze's `design/` folder.

Each folder is one practice; `guide/` is Lumi's narration. To change media,
commit here, push, then run `ziran update practices` in Breeze and
commit its `ziran.lock`. Breeze's generators (narration, Sun Salutation
characters, the Tai Chi exporter) write into this checkout when Breeze's
ignored `ziran.local.toml` maps `practices` to it.

The files came from Breeze's `assets/practices/` on 2026-10-24; their earlier
history is in Breeze.

BSD 3-Clause. See [LICENSE](LICENSE).
