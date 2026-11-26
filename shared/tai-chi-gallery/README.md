# Tai Chi lesson covers

The PNG files are the original generated artwork recorded in `prompts.json`.
Keep their bytes unchanged. `thumbnails/lesson-*.webp` are 512 × 384 runtime
copies for lesson cards, which avoid decoding the full artwork while scrolling.

Generate each runtime copy with FFmpeg's libwebp encoder at quality 90:

```sh
ffmpeg -i lesson-1.png -vf scale=512:384:flags=lanczos -frames:v 1 \
  -c:v libwebp -compression_level 6 -q:v 90 thumbnails/lesson-1.webp
```

Package the thumbnail copies for the gallery; retain the originals here for
future uses that need their full resolution.

The six `foundation-*.png` covers illustrate the expandable Foundations groups.
Their original prompts, generation IDs and checksums are in `foundation-prompts.json`.
The matching `thumbnails/foundation-*.webp` use the same 512 × 384 conversion above.
