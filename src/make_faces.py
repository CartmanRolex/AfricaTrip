"""
Crop traveler photos to square face thumbnails and extract the car icons.

Usage:  python src/make_faces.py
Reads:  photos/<name>.jpeg      (traveler photos)
        photos/voitures.jpg     (two cartoon cars, fake painted checkerboard)
        photos/terros.jpg       (danger-zone sticker sheet, same fake checker)
Writes: photos/faces/<name>.jpg     (face crops ONLY — people live here)
        photos/emojis/car1.png, car2.png, terro<N>.png  (true-alpha cutouts)
        src/photos.json             ({faces, cars, terros} data URIs,
                                     injected by build.py)

Each face entry below frames the face by hand: (cx, cy) is the face center
and `size` the square side, all as fractions of the image WIDTH (cx, size)
and HEIGHT (cy).
"""
import base64
import io
import json
import os
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

HERE = os.path.dirname(__file__)
PHOTOS = os.path.join(HERE, "..", "photos")
FACES = os.path.join(PHOTOS, "faces")
EMOJIS = os.path.join(PHOTOS, "emojis")
OUT_JSON = os.path.join(HERE, "photos.json")

THUMB = 128  # px, plenty for a ~30px chip on retina

# Variante "large" de chaque visage : même centre, cadre 1.9x plus grand. Sert
# au dézoom au survol/tap — une pastille est un JPEG déjà recadré, il n'y a
# donc rien "autour" à révéler sans cette seconde image. (Les portraits
# vivants, eux, élargissent directement le cadrage de leur vidéo.)
WIDE = 1.9

# name-in-data -> (file, cx, cy, size_frac_of_width)
CROPS = {
    "Gal":     ("gal_frame.png", 0.5025, 0.3815, 0.66),
    "Arthur":   ("arthur_frame.png", 0.5125, 0.2665, 0.55),
    "Dorvan":   ("dorvan_frame.png", 0.50, 0.225, 0.55),
    # Edouard/Younous ont un portrait vivant : le crop statique vient de la
    # PREMIÈRE FRAME de leur vidéo (extraite en screenshot headless, voir
    # photos/videos/CLAUDE.md), avec EXACTEMENT le même carré que le cadrage
    # LIVE du template (w/l/t) => aucun saut visuel photo->vidéo au survol.
    "Edouard":  ("edouard_frame.png", 0.50,  0.35, 0.476),
    "Younous":  ("younous_frame.png", 0.506, 0.35, 0.59),
    "Hugo":     ("hugo_frame.png",    0.506, 0.363, 0.588),
    # mugshots.jpeg : 3 portraits façon prison, de gauche à droite (Giordano)
    "Giordano": ("giordano_frame.png", 0.469, 0.524, 0.625),
    "Jehan":    ("jehan_frame.png", 0.50, 0.21, 0.40),
    "Thomas":   ("thomas_frame.png", 0.50, 0.453, 0.44),
    "Malen":   ("malen_frame.png", 0.512, 0.63, 0.60),
    "Paul":     ("paul_frame.png", 0.50, 0.291, 0.5625),
}


def crop_face(path, cx, cy, size_frac):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    side = size_frac * w
    x = cx * w - side / 2
    y = cy * h - side / 2
    x = max(0, min(x, w - side))
    y = max(0, min(y, h - side))
    box = (round(x), round(y), round(x + side), round(y + side))
    return im.crop(box).resize((THUMB, THUMB), Image.LANCZOS)


# voitures.jpg: (left, top, right, bottom) around each car, clear of the
# bottom caption text. Car 1 = red RAV4 (HUGODOUARD), car 2 = grey Outback.
CAR_BOXES = {"1": (10, 60, 505, 545), "2": (505, 60, 1020, 545)}


def cut_car(im, box):
    """Crop one car and turn the painted checkerboard into real alpha."""
    im = im.crop(box).convert("RGB")
    w, h = im.size
    px = im.load()
    # candidate background = light, unsaturated pixels (white/grey checker)
    cand = Image.new("L", (w, h), 0)
    cpx = cand.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn < 18 and (r + g + b) > 3 * 165:
                cpx[x, y] = 255
    # keep only the candidate region connected to the borders: flood-fill the
    # binary mask from the edges so light pixels inside the car survive
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                 (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if cand.getpixel(seed) == 255:
            ImageDraw.floodfill(cand, seed, 128)
    alpha = cand.point(lambda v: 0 if v == 128 else 255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    bb = alpha.getbbox()
    out = out.crop((max(0, bb[0] - 6), max(0, bb[1] - 6),
                    min(w, bb[2] + 6), min(h, bb[3] + 6)))
    scale = 120 / out.height
    return out.resize((round(out.width * scale), 120), Image.LANCZOS)


def outside_mask(im, bg="checker"):
    """Boolean array of pixels belonging to the border-connected fake
    background (unsaturated, reachable from the edges). bg="checker" for the
    painted grey checkerboard sheets, bg="white" for plain white sheets."""
    w, h = im.size
    a = np.asarray(im, dtype=np.int16)
    mx, mn = a.max(2), a.min(2)
    if bg == "white":
        cand = ((mx - mn < 25) & (mx > 235)).astype(np.uint8) * 255
    else:
        # 105..230 : gris du damier + ombres, mais PAS les liserés blancs (>=230)
        cand = ((mx - mn < 20) & (mx > 105) & (mx < 230)).astype(np.uint8) * 255
    # .copy() unshares the numpy buffer, else floodfill writes are lost
    candim = Image.fromarray(cand, "L").copy()
    seeds = [(x, y) for x in range(0, w, 48) for y in (0, h - 1)]
    seeds += [(x, y) for y in range(0, h, 48) for x in (0, w - 1)]
    for s in seeds:
        if candim.getpixel(s) == 255:
            ImageDraw.floodfill(candim, s, 128)
    return np.asarray(candim) == 128


def cut_stickers(path, thumb_h=120, bg="checker", rows=3):
    """Split a sticker sheet into individual RGBA images (row-major order;
    `rows` = number of sticker rows on the sheet, for the ordering bands)."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    outside = outside_mask(im, bg)
    # find sticker blobs on a 2x downscale, dilated so close parts merge
    # (dilation radius ~2 small px = merges gaps under ~8 full px)
    ds = 2
    fg = Image.fromarray((~outside[::ds, ::ds]).astype(np.uint8) * 255, "L")
    fg = np.asarray(fg.filter(ImageFilter.MaxFilter(5))) > 0
    sh, sw = fg.shape
    seen = np.zeros_like(fg, dtype=bool)
    boxes = []
    for y0 in range(sh):
        for x0 in range(sw):
            if not fg[y0, x0] or seen[y0, x0]:
                continue
            q = deque([(y0, x0)]); seen[y0, x0] = True
            ys, xs, ye, xe, area = y0, x0, y0, x0, 0
            while q:
                y, x = q.popleft(); area += 1
                ys, xs, ye, xe = min(ys, y), min(xs, x), max(ye, y), max(xe, x)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < sh and 0 <= nx < sw and fg[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True; q.append((ny, nx))
            if area * ds * ds > 3000:  # drop specks
                boxes.append((xs * ds, ys * ds, xe * ds + ds, ye * ds + ds))
    # row-major order: cluster by vertical band, then left to right
    boxes.sort(key=lambda b: (round((b[1] + b[3]) / 2 / (h / float(rows))), b[0]))
    alpha_full = Image.fromarray(((~outside) * 255).astype(np.uint8), "L") \
        .filter(ImageFilter.GaussianBlur(0.8))
    rgba = im.convert("RGBA"); rgba.putalpha(alpha_full)
    out = []
    for (x0, y0, x1, y1) in boxes:
        crop = rgba.crop((max(0, x0 - 8), max(0, y0 - 8), min(w, x1 + 8), min(h, y1 + 8)))
        bb = crop.getchannel("A").getbbox()
        crop = crop.crop(bb)
        scale = thumb_h / crop.height
        out.append(crop.resize((max(1, round(crop.width * scale)), thumb_h), Image.LANCZOS))
    return out


# artefacts de la planche à gommer : sticker -> rectangles (fractions l,t,r,b)
CLEAN = {7: [(0.92, 0.0, 1.0, 0.18), (0.0, 0.92, 0.42, 1.0)],
         9: [(0.0, 0.0, 0.05, 1.0)]}  # bande du sticker voisin, à gauche de l'hélico


def clean_rects(img, rects):
    a = np.asarray(img).copy()
    h, w = a.shape[:2]
    for (l, t, r, b) in rects:
        a[int(t*h):int(b*h), int(l*w):int(r*w), 3] = 0
    out = Image.fromarray(a, "RGBA")
    return out.crop(out.getchannel("A").getbbox())


SOURCES_HELP = """\
The source images (photos/<name>.jpeg, voitures.jpg, terros.jpg) are no
longer kept in the working tree — the generated crops in photos/faces/ and
photos/emojis/ are committed, so the site never needs them. To re-crop,
restore them from git history first:
    git checkout 20d79de -- photos/
then rerun this script (and delete the restored originals again after)."""


def main():
    missing = [f for f in ["voitures.jpg", "terros.jpg", "chameaux.jpg"]
               + [c[0] for c in CROPS.values()]
               if not os.path.exists(os.path.join(PHOTOS, f))]
    if missing:
        raise SystemExit(f"Missing source images: {', '.join(missing)}\n\n"
                         + SOURCES_HELP)
    os.makedirs(FACES, exist_ok=True)
    os.makedirs(EMOJIS, exist_ok=True)
    faces, faces_wide = {}, {}
    for name, (fname, cx, cy, size) in CROPS.items():
        src = os.path.join(PHOTOS, fname)
        for key, dest, frac, suffix in (
                (faces, name, size, ""),
                (faces_wide, name, min(size * WIDE, 1.0), "_wide")):
            face = crop_face(src, cx, cy, frac)
            out = os.path.join(FACES, name.lower() + suffix + ".jpg")
            face.save(out, "JPEG", quality=85)
            buf = io.BytesIO()
            face.save(buf, "JPEG", quality=80)
            key[dest] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            print(f"{name+suffix:14s} -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    cars = {}
    voitures = Image.open(os.path.join(PHOTOS, "voitures.jpg"))
    for no, box in CAR_BOXES.items():
        car = cut_car(voitures, box)
        out = os.path.join(EMOJIS, f"car{no}.png")
        car.save(out, "PNG", optimize=True)
        buf = io.BytesIO()
        car.save(buf, "PNG", optimize=True)
        cars[no] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        print(f"car{no}     -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    terros = {}
    sheet = os.path.join(PHOTOS, "terros.jpg")
    if os.path.exists(sheet):
        for i, st in enumerate(cut_stickers(sheet, thumb_h=96), 1):
            if i in CLEAN:
                st = clean_rects(st, CLEAN[i])
            out = os.path.join(EMOJIS, f"terro{i}.png")
            st.save(out, "PNG", optimize=True)
            buf = io.BytesIO()
            st.save(buf, "PNG", optimize=True)
            terros[f"terro{i}"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            print(f"terro{i}   -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    chameaux = {}
    sheet = os.path.join(PHOTOS, "chameaux.jpg")
    if os.path.exists(sheet):
        for i, st in enumerate(cut_stickers(sheet, thumb_h=72, bg="white",
                                            rows=4), 1):
            # aplats cartoon -> palette 64 couleurs, ~4x plus léger en data URI
            st = st.quantize(colors=64, method=Image.FASTOCTREE)
            out = os.path.join(EMOJIS, f"chameau{i}.png")
            st.save(out, "PNG", optimize=True)
            buf = io.BytesIO()
            st.save(buf, "PNG", optimize=True)
            chameaux[f"chameau{i}"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            print(f"chameau{i} -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"faces": faces, "facesWide": faces_wide, "cars": cars,
                   "terros": terros, "chameaux": chameaux}, f)
    print(f"Wrote {os.path.normpath(OUT_JSON)}")


if __name__ == "__main__":
    main()
