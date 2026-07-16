"""
Crop traveler photos to square face thumbnails and extract the car icons.

Usage:  python src/make_faces.py
Reads:  photos/<name>.jpeg
        photos/voitures.jpg  (two cartoon cars on a FAKE checkerboard
                              "transparency" painted into the JPEG)
Writes: photos/faces/<name>.jpg   (small square face crop, for inspection/reuse)
        photos/faces/car1.png, car2.png  (cars with real alpha transparency)
        src/photos.json           ({faces: {...}, cars: {...}} data URIs,
                                   injected by build.py)

Each face entry below frames the face by hand: (cx, cy) is the face center
and `size` the square side, all as fractions of the image WIDTH (cx, size)
and HEIGHT (cy).
"""
import base64
import io
import json
import os

from PIL import Image, ImageDraw, ImageFilter, ImageOps

HERE = os.path.dirname(__file__)
PHOTOS = os.path.join(HERE, "..", "photos")
FACES = os.path.join(PHOTOS, "faces")
OUT_JSON = os.path.join(HERE, "photos.json")

THUMB = 128  # px, plenty for a ~30px chip on retina

# name-in-data -> (file, cx, cy, size_frac_of_width)
CROPS = {
    "Gal":     ("Gal.jpeg",     0.66, 0.55, 0.50),
    "Arthur":  ("arthur.jpeg",  0.46, 0.42, 0.42),
    "Dorvan":  ("dorvan.jpeg",  0.72, 0.425, 0.22),
    "Edouard": ("edouard.jpeg", 0.50, 0.46, 0.42),
    "Hugo":    ("hugo.jpeg",    0.50, 0.49, 0.38),
    "Malen":   ("malen.jpeg",   0.52, 0.46, 0.42),
    "Paul":    ("paul.jpeg",    0.585, 0.44, 0.20),
    "Younous": ("younous.jpeg", 0.57, 0.62, 0.44),
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


def main():
    os.makedirs(FACES, exist_ok=True)
    faces = {}
    for name, (fname, cx, cy, size) in CROPS.items():
        face = crop_face(os.path.join(PHOTOS, fname), cx, cy, size)
        out = os.path.join(FACES, name.lower() + ".jpg")
        face.save(out, "JPEG", quality=85)
        buf = io.BytesIO()
        face.save(buf, "JPEG", quality=80)
        faces[name] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        print(f"{name:8s} -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    cars = {}
    voitures = Image.open(os.path.join(PHOTOS, "voitures.jpg"))
    for no, box in CAR_BOXES.items():
        car = cut_car(voitures, box)
        out = os.path.join(FACES, f"car{no}.png")
        car.save(out, "PNG", optimize=True)
        buf = io.BytesIO()
        car.save(buf, "PNG", optimize=True)
        cars[no] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        print(f"car{no}     -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"faces": faces, "cars": cars}, f)
    print(f"Wrote {os.path.normpath(OUT_JSON)}")


if __name__ == "__main__":
    main()
