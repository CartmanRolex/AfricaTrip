# photos/ — images

> Rule: update this file in the same commit as any feature change here.

Only the **generated** crops/cutouts live here now; the pre-crop source
images (traveler photos, `voitures.jpg` car sheet, `terros.jpg` and
`chameaux.jpg` sticker sheets) were removed from the working tree — the site only ever embeds
the generated files, so the originals were dead weight. They remain in git
history: restore with

```
git checkout c172562 -- photos/
```

then rerun `python src/make_faces.py` (which errors with these same
instructions if the sources are missing), and delete the originals again
after re-cropping. To reframe a face, adjust `CROPS` in `src/make_faces.py`,
not the images.

## Contents

- `faces/` — travelers' face crops only. See `faces/CLAUDE.md`.
- `emojis/` — car + sticker cutouts with real alpha. See `emojis/CLAUDE.md`.
- `uploads/` — shared Drive trip photos (map bubbles), synced by
  `python src/fetch_photos.py`. See `uploads/CLAUDE.md`.
- `videos/` — living-portrait MP4 loops (committed, served by Pages).
  See `videos/CLAUDE.md`.
- `gal.enc` — **encrypted local file, unknown contents. NEVER COMMIT**
  (git-ignored; `git add -A photos` once caught it — avoid).

Historical note on the removed sheets: both were AI-generated with a FAKE
painted checkerboard background (the transparency pattern is painted INTO
the pixels); `make_faces.py` removes it (see `src/CLAUDE.md` for the
algorithm and its tuned thresholds). `voitures.jpg`: red Toyota RAV4 =
car 1 "HUGODOUARD", grey Subaru Outback = car 2 "PAUL POT". All 10 travelers
+ the observer Giordano have a photo; `mugshots.jpeg` (3 AI prison
mugshots, l→r Edouard/Younous/Giordano) replaced the old Edouard/Younous
portraits.
