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
| `hugo_live.mp4`    | Hugo    | 800×1418 colonial-explorer loop (jungle, pith helmet), waist-up shot so the head sits high in frame → w:170% l:-36% t:-59.4% |
| `gal_live.mp4`     | Gal     | 800×1088 Touareg portrait (indigo chèche, camp + camels behind); tall head (turban→chin ≈ 390px) so the circle needs a LOOSE frame or its curve clips the jaw → w:151.5% l:-26.1% t:-28.6% |
| `arthur_live.mp4`  | Arthur  | 800x1088 desert portrait (beige djellaba, dunes + oasis) -> w:182% l:-43.2% t:-15.9% |
| `dorvan_live.mp4`  | Dorvan  | 800x1088 savanna sunset (zebras + giraffe) -> w:181.8% l:-40.9% t:-5.6% |
| `paul_live.mp4`    | Paul    | 800x773 (near-square source) rice paddy, conical hat: wide brim, framed to keep the face readable -> w:177.8% l:-38.9% t:0% |
| `giordano_live.mp4`| Giordano| 800x1088 physics lecture hall (blackboard of equations) -> w:160% l:-25% t:-64% |
| `jehan_live.mp4`   | Jehan   | 800x773 sailing boat at sea, captain's cap -> w:250% l:-75% t:-0.7% |
| `thomas_live.mp4`  | Thomas  | 800x773 favela rooftop at sunset, sunglasses -> w:227.3% l:-63.6% t:-49.5% |
| `malen_live.mp4`   | Malen   | 800×1015 soviet-square smoke break (lighter + cigarette in frame) → w:167% l:-35% t:-83% |

The STATIC face crops of live-portrait people come from the video's FIRST
FRAME (no visual jump on hover): extract it by loading the mp4 in headless
Edge at natural width and screenshotting (no ffmpeg on this machine), save
as `photos/<name>_frame.png`, and give `CROPS` the exact same square as the
LIVE framing — cx=(-l+50)/w, cy stays in height fractions, size=100/w of
the video width (see the values in make_faces.py).

To add one: drop `<name>_live.mp4` here, add the entry to `LIVE` in
`src/template.html` (tune w/l/t by screenshot), rebuild.

## Mouvement et clignements (leçon de génération)

Wan2.2 TI2V-5B ne produit presque jamais de clignement avec le prompt
"extremely subtle motion only" : vérifié image par image, ni Arthur ni
Dorvan ni Younous ne clignaient dans la première fournée. Ce qui marche :
demander explicitement que **les yeux restent ouverts** avec deux ou trois
clignements *brefs* (paupières qui se referment et se rouvrent aussitôt).
Attention à l'excès inverse — la consigne "blinks about once every two
seconds" a fait fermer les yeux à Younous pour tout le clip.
Pour juger, extraire des images entières (`full.py` sur la machine
Basement) : une planche de 12 vignettes rate un clignement, qui ne dure
que 3 à 6 images sur 121.
