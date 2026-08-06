"""
Build the final standalone site by injecting src/data.json into src/template.html.

Usage:  python src/build.py
Reads:  src/template.html  (literal tokens __DATA__, __PHOTOS__, __GALLERY__, __ROUTES__)
        src/data.json
        src/photos.json    (face thumbnails as data URIs; python src/make_faces.py)
        src/routes.json    (road geometry between GPS points; python src/fetch_routes.py)
Writes: voyage-afrique.html  (self-contained, open directly in a browser)
        index.html           (identical copy so GitHub Pages serves it at the
                              repo root URL)
        version.json         (build id, so a published page can notice that a
                              newer one exists — see __BUILD__ in the template)

Full pipeline to rebuild from the raw CSV:
    python src/parse_csv.py   # CSV  -> src/data.json
    python src/build.py       # JSON -> voyage-afrique.html + index.html
"""
import hashlib
import json
import os

HERE = os.path.dirname(__file__)
TEMPLATE = os.path.join(HERE, "template.html")
DATA = os.path.join(HERE, "data.json")
PHOTOS = os.path.join(HERE, "photos.json")
GALLERY = os.path.join(HERE, "gallery.json")
ROUTES = os.path.join(HERE, "routes.json")
OUTS = [os.path.join(HERE, "..", "voyage-afrique.html"),
        os.path.join(HERE, "..", "index.html")]
VERSION = os.path.join(HERE, "..", "version.json")

def main():
    template = open(TEMPLATE, encoding="utf-8").read()
    with open(DATA, encoding="utf-8") as f:
        data_obj = json.load(f)
    data = json.dumps(data_obj, ensure_ascii=False)
    if os.path.exists(PHOTOS):
        with open(PHOTOS, encoding="utf-8") as f:
            photos_obj = json.load(f)
        # Do not embed portraits for people removed by site-overrides.json.
        active = set(data_obj.get("car1", [])) | set(data_obj.get("car2", []))
        active.update(data_obj.get("config", {}).get("observateurs") or [])
        for group in ("faces", "facesWide"):
            photos_obj[group] = {
                name: value
                for name, value in photos_obj.get(group, {}).items()
                if name in active
            }
        photos = json.dumps(photos_obj, ensure_ascii=False)
    else:
        photos = "{}"
    gallery = open(GALLERY, encoding="utf-8").read() if os.path.exists(GALLERY) else "[]"
    routes = open(ROUTES, encoding="utf-8").read() if os.path.exists(ROUTES) else "{}"
    # Identifiant de build : empreinte des ENTREES, pas de la sortie (la sortie
    # contient l'identifiant). Deux builds identiques donnent donc le meme id.
    build = hashlib.sha256(
        "\u0000".join([template, data, photos, gallery, routes]).encode("utf-8")
    ).hexdigest()[:12]
    html = (template.replace("__DATA__", data).replace("__PHOTOS__", photos)
            .replace("__GALLERY__", gallery).replace("__ROUTES__", routes)
            .replace("__BUILD__", build))
    with open(VERSION, "w", encoding="utf-8") as f:
        json.dump({"build": build}, f)
    for out in OUTS:
        open(out, "w", encoding="utf-8").write(html)
        print(f"Wrote {os.path.normpath(out)} ({len(html):,} chars)")
    print(f"Build {build} -> {os.path.normpath(VERSION)}")

if __name__ == "__main__":
    main()
