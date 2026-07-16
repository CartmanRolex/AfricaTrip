"""
Build the final standalone site by injecting src/data.json into src/template.html.

Usage:  python src/build.py
Reads:  src/template.html  (contains the literal tokens __DATA__ and __PHOTOS__)
        src/data.json
        src/photos.json    (face thumbnails as data URIs; python src/make_faces.py)
Writes: voyage-afrique.html  (self-contained, open directly in a browser)
        index.html           (identical copy so GitHub Pages serves it at the
                              repo root URL)

Full pipeline to rebuild from the raw CSV:
    python src/parse_csv.py   # CSV  -> src/data.json
    python src/build.py       # JSON -> voyage-afrique.html + index.html
"""
import os

HERE = os.path.dirname(__file__)
TEMPLATE = os.path.join(HERE, "template.html")
DATA = os.path.join(HERE, "data.json")
PHOTOS = os.path.join(HERE, "photos.json")
GALLERY = os.path.join(HERE, "gallery.json")
OUTS = [os.path.join(HERE, "..", "voyage-afrique.html"),
        os.path.join(HERE, "..", "index.html")]

def main():
    template = open(TEMPLATE, encoding="utf-8").read()
    data = open(DATA, encoding="utf-8").read()
    photos = open(PHOTOS, encoding="utf-8").read() if os.path.exists(PHOTOS) else "{}"
    gallery = open(GALLERY, encoding="utf-8").read() if os.path.exists(GALLERY) else "[]"
    html = (template.replace("__DATA__", data).replace("__PHOTOS__", photos)
            .replace("__GALLERY__", gallery))
    for out in OUTS:
        open(out, "w", encoding="utf-8").write(html)
        print(f"Wrote {os.path.normpath(out)} ({len(html):,} chars)")

if __name__ == "__main__":
    main()
