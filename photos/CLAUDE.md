# photos/ — source images

> Rule: update this file in the same commit as any feature change here.

Inputs for `python src/make_faces.py` (which regenerates the `faces/` and
`emojis/` subfolders plus `src/photos.json`). Run it, then
`python src/build.py`, after changing anything here.

## Source files (committed)

| File            | What it is                                                    |
|-----------------|---------------------------------------------------------------|
| `<name>.jpeg`   | One photo per traveler (Gal, arthur, dorvan, edouard, hugo, malen, paul, younous). Thomas and Jehan have no photo → the site shows their initial. |
| `voitures.jpg`  | AI-generated sheet with the two cars: red Toyota RAV4 = car 1 "HUGODOUARD", grey Subaru Outback = car 2 "PAUL POT". Fake painted checkerboard background + caption text at the bottom. |
| `terros.jpg`    | AI-generated sticker sheet: 12 cartoon Sahel-militant stickers (white sticker outlines) used as danger-zone markers on the map. Fake painted checkerboard too. |
| `gal.enc`       | **Encrypted local file, unknown contents. NEVER COMMIT** (git-ignored; `git add -A photos` once caught it — avoid). |

“Fake checkerboard” means the transparency pattern is painted INTO the
image pixels; `make_faces.py` removes it (see `src/CLAUDE.md` for the
algorithm and its tuned thresholds).

## Generated subfolders (committed for convenience, never hand-edited)

- `faces/` — travelers' face crops only. See `faces/CLAUDE.md`.
- `emojis/` — car + sticker cutouts with real alpha. See `emojis/CLAUDE.md`.
- `uploads/` — shared Drive trip photos (map bubbles), synced by
  `python src/fetch_photos.py`. See `uploads/CLAUDE.md`.

To reframe a face, adjust `CROPS` in `src/make_faces.py`, not the images.
