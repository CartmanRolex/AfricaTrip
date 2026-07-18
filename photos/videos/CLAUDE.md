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

To add one: drop `<name>_live.mp4` here, add the entry to `LIVE` in
`src/template.html` (tune w/l/t by screenshot), rebuild.
