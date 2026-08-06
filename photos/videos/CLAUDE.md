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
| `hugo_live.mp4`    | Hugo    | 704×1248 colonial-explorer loop (jungle, pith helmet), waist-up shot so the head sits high in frame → w:170% l:-36% t:-59.4% |
| `gal_live.mp4`     | Gal     | 800×1088 Touareg portrait (indigo chèche, camp + camels behind); tall head (turban→chin ≈ 390px) so the circle needs a LOOSE frame or its curve clips the jaw → w:151.5% l:-26.1% t:-28.6% |
| `arthur_live.mp4`  | Arthur  | 800x1088 desert portrait (beige djellaba, dunes + oasis) -> w:182% l:-43.2% t:-15.9% |
| `dorvan_live.mp4`  | Dorvan  | 800x1088 savanna sunset; Dorvan + zebras + giraffe + grass all move -> w:181.8% l:-40.9% t:-5.6% |
| `paul_live.mp4`    | Paul    | 960×928 (near-square source) rice paddy, conical hat: wide brim, framed to keep the face readable -> w:177.8% l:-38.9% t:0% |
| `giordano_live.mp4`| Giordano| 800x1088 physics lecture hall (blackboard of equations) -> w:160% l:-25% t:-64% |
| `jehan_live.mp4`   | Jehan   | 960×928 sailing boat at sea, captain's cap -> w:250% l:-75% t:-0.7% |
| `thomas_live.mp4`  | Thomas  | 960×928 favela rooftop at sunset, sunglasses -> w:227.3% l:-63.6% t:-49.5% |
| `malen_live.mp4`   | Malen   | 832×1056 soviet-square smoke break (lighter + cigarette in frame) → w:167% l:-35% t:-83% |

## Poids : encodage volontairement sobre (2026-08-06)

Les clips ont ete reencodes en H.264 CRF 23 (preset slow, `+faststart`), **sans
toucher a la resolution ni a la cadence**. Les originaux sortaient de Wan2.2 a
10-17 Mbit/s pour des images de 800 px de large, soit une dizaine de fois le
debit utile : 85 Mo au total. Ils font maintenant 11,9 Mo (-86 %).

Ce n'est PAS pour accelerer le deploiement — mesure faite, le checkout et
l'upload de tout le depot prennent 7 secondes. C'est pour l'equipage : ces
fichiers sont telecharges a l'ouverture d'une fiche, et ouvrir celle d'Arthur
coutait 10,6 Mo de data mobile en Mauritanie.

Verification faite avant remplacement, parce qu'un clignement ne dure que 3 a 6
images sur 121 : comparaison image par image entre original et version
compressee, **par blocs** pour qu'une petite zone comme une paupiere ne se noie
pas dans la moyenne. Ecart median 0,3-0,6 sur une echelle 0-255, maximum 1,5, et
le mouvement le plus marque de chaque clip conserve a 90-131 %. Aucun clignement
perdu. Les 121 images, les dimensions et les 24 fps sont identiques.

Attention au piege : une premiere metrique correlait la difference entre images
CONSECUTIVES. Elle criait au loup partout, parce qu'elle mesurait surtout la
disparition du bruit d'encodage de l'original, pas une perte de mouvement.
Comparer l'image i a l'image i est le bon test.

Pour recuperer les originaux : `git checkout 4be4660 -- photos/videos/`.

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

## Dorvan — arrière-plan de savane animé (2026-07-28)

La version actuelle de `dorvan_live.mp4` a été régénérée localement avec
Wan2.2 TI2V-5B depuis
`/home/students/Gal/video-gen/dorvan_savane.png`, avec le seed `4242`.
L'ancien prompt générique animait Dorvan mais laissait les animaux figés.
Le nouveau prompt verrouille Dorvan et la caméra tout en demandant un
mouvement explicite de chaque couche de l'arrière-plan :

```text
Bring this still photo to life as a seamless living portrait video. Keep the
man's face, identity, clothing, body, pose, hand, and framing exactly as in
the source image. His eyes stay open and look straight at the camera except
for two or three very quick natural blinks. He breathes subtly, with tiny
natural shifts of the head and shoulders and slight movement in the hair.
Neutral expression, mouth closed, no talking, no smiling, no gesture. The
entire savanna background is alive with clearly visible but gentle realistic
motion throughout the clip: the zebras in the left background slowly walk
and graze, naturally moving their legs, heads, ears, and tails; the giraffe
in the right background takes one or two slow steps, gently turns its head
and neck, and flicks its ears and tail; the more distant animals shift and
walk slowly; tall grass sways lightly and tiny dust motes drift in the warm
breeze. Every background animal moves independently and naturally, without
abrupt changes of species, count, shape, or position. No frozen animals.
Static locked-off camera, no zoom, no pan, no cut, no camera shake. Preserve
the original composition, warm sunset lighting, depth of field, and
photorealism. No new animals, no animal approaching or crossing in front of
the man, no deformation, no extra limbs. Photorealistic, HD.
```

Commande :

```bash
cd /home/students/Gal/video-gen
./generate.sh "<prompt ci-dessus>" --image dorvan_savane.png --base_seed 4242
```

Sortie validée : H.264/yuv420p, 800x1088, 24 fps, 121 images (5,041667 s),
sans audio. Contrôler le visage et les deux zones d'animaux sur les
121 images avant de remplacer l'asset du site ; une planche trop espacée
peut masquer un clignement ou une déformation brève.
