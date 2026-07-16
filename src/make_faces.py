"""
Crop traveler photos to square face thumbnails.

Usage:  python src/make_faces.py
Reads:  photos/<name>.jpeg
Writes: photos/faces/<name>.jpg   (small square face crop, for inspection/reuse)
        src/photos.json           (name -> data URI, injected by build.py)

Each entry below frames the face by hand: (cx, cy) is the face center and
`size` the square side, all as fractions of the image WIDTH (cx, size) and
HEIGHT (cy).
"""
import base64
import io
import json
import os

from PIL import Image, ImageOps

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


def main():
    os.makedirs(FACES, exist_ok=True)
    uris = {}
    for name, (fname, cx, cy, size) in CROPS.items():
        face = crop_face(os.path.join(PHOTOS, fname), cx, cy, size)
        out = os.path.join(FACES, name.lower() + ".jpg")
        face.save(out, "JPEG", quality=85)
        buf = io.BytesIO()
        face.save(buf, "JPEG", quality=80)
        uris[name] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        print(f"{name:8s} -> {os.path.normpath(out)} ({buf.tell():,} B embedded)")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(uris, f)
    print(f"Wrote {os.path.normpath(OUT_JSON)}")


if __name__ == "__main__":
    main()
