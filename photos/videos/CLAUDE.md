# photos/videos/ — portraits vivants (Harry Potter style)

> Rule: update this file in the same commit as any feature change here.

Short MP4 loops used as "living portraits": the seat chip shows the static
face crop, hovering it (desktop) plays the video inside the circle, and the
fiche aventurier plays it continuously. Referenced by RELATIVE path from the
`LIVE` map in `src/template.html` (name → {src, w/l/t framing of the head
inside the circle, in % of the circle) — NOT embedded as data URIs (too
big); GitHub Pages serves them, and the standalone `voyage-afrique.html`
falls back to the static photo (`oncanplay` gate → `.vid-ok`).

| File               | Who     | Framing notes                          |
|--------------------|---------|----------------------------------------|
| `edouard_live.mp4` | Edouard | 800×1088, 5 s mugshot loop; head ≈ (50%, 35%) → w:210% l:-55% t:-50% |
| `younous_live.mp4` | Younous | 800×1088 mugshot loop; big curly hair → w:170% l:-36% t:-31% |
| `hugo_live.mp4`    | Hugo    | 800×1418 colonial-explorer loop (jungle, pith helmet) → w:182% l:-44% t:-72% |
| `gal_live.mp4`     | Gal     | 800×1088 Touareg portrait (indigo chèche, camp + camels behind) → w:174% l:-39% t:-38% |
| `malen_live.mp4`   | Malen   | 800×1015 soviet-square smoke break (lighter + cigarette in frame) → w:167% l:-35% t:-83% |

The STATIC face crops of live-portrait people come from the video's FIRST
FRAME (no visual jump on hover): extract it by loading the mp4 in headless
Edge at natural width and screenshotting (no ffmpeg on this machine), save
as `photos/<name>_frame.png`, and give `CROPS` the exact same square as the
LIVE framing — cx=(-l+50)/w, cy stays in height fractions, size=100/w of
the video width (see the values in make_faces.py).

To add one: drop `<name>_live.mp4` here, add the entry to `LIVE` in
`src/template.html` (tune w/l/t by screenshot), rebuild.
