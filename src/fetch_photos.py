"""
Sync the shared Google Drive photo folder onto the map.

Usage:
    python src/fetch_photos.py            # sync + rebuild the site
    python src/fetch_photos.py --dry-run  # list what would be downloaded

Everyone uploads photos to one shared Drive folder; this script downloads
the new ones, geolocates each photo (EXIF GPS, else Drive metadata, else the
convoy's interpolated position on the photo's date + a small deterministic
jitter), and writes:
    photos/uploads/<id>.jpg   resized copy (max 1600 px, served by Pages)
    src/gallery.json          manifest injected into the site as __GALLERY__
then rebuilds the site (build.py) so the photos appear as round bubbles on
the map.

One-time setup:
  1. Create a Drive folder; share it "anyone with the link: editor" with the
     friends so they can upload.
  2. Share it (Viewer is enough) with the service-account email from
     .sheet-credentials.json (same account as sheet_edit.py).
  3. Put the folder URL (or bare ID) in `.drive-folder` at the repo root —
     git-ignored, like .sheet-url.

Incremental: photos already in gallery.json are skipped; deleting an entry
from gallery.json (and its file in photos/uploads/) forgets it.
"""
import base64
import hashlib
import io
import json
import os
import re
import runpy
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from math import asin, cos, radians, sin, sqrt

from PIL import Image, ImageOps

from sheet_edit import access_token, load_key

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
FOLDER_FILE = os.path.join(ROOT, ".drive-folder")
UPLOADS = os.path.join(ROOT, "photos", "uploads")
GALLERY = os.path.join(HERE, "gallery.json")
DATA = os.path.join(HERE, "data.json")

SCOPE = "https://www.googleapis.com/auth/drive.readonly"
API = "https://www.googleapis.com/drive/v3"

MAX_SIDE = 1600   # px, full image committed to the repo
THUMB = 96        # px, square data-URI bubble
JITTER = 0.12     # deg, max offset for convoy-fallback positions

SETUP_HELP = """\
Missing {folder} — one-time setup:
  1. Create a Drive folder; share it "anyone with the link: editor" so the
     friends can upload photos into it.
  2. Share it (Viewer) with the service-account email from
     .sheet-credentials.json.
  3. Put the folder URL or ID in {folder} (one line, git-ignored)."""


def folder_id():
    try:
        with open(FOLDER_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    m = re.search(r"/folders/([A-Za-z0-9_-]+)", line)
                    return m.group(1) if m else line
    except FileNotFoundError:
        pass
    raise RuntimeError(SETUP_HELP.format(folder=os.path.normpath(FOLDER_FILE)))


def api_get(token, path, raw=False):
    req = urllib.request.Request(
        API + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read() if raw else json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)["error"]["message"]
        except Exception:
            msg = e.reason
        hint = ""
        if e.code in (403, 404):
            hint = (f"\nIs the folder shared with "
                    f"{load_key()['client_email']} (Viewer)?")
        raise RuntimeError(f"Drive API {e.code}: {msg}{hint}")


def list_images(token, fid):
    files, page = [], None
    q = urllib.parse.quote(f"'{fid}' in parents and mimeType contains 'image/'"
                           " and trashed = false")
    fields = urllib.parse.quote(
        "nextPageToken,files(id,name,createdTime,"
        "imageMediaMetadata(time,location))")
    while True:
        path = f"/files?q={q}&fields={fields}&pageSize=200"
        if page:
            path += f"&pageToken={page}"
        r = api_get(token, path)
        files += r.get("files", [])
        page = r.get("nextPageToken")
        if not page:
            return files


# ---- geolocation ----------------------------------------------------------

def exif_gps(im):
    """(lat, lng) from the EXIF GPS IFD, or None."""
    try:
        gps = im.getexif().get_ifd(0x8825)
        lat, lng = gps[2], gps[4]           # degrees/minutes/seconds tuples
        lat = float(lat[0]) + float(lat[1]) / 60 + float(lat[2]) / 3600
        lng = float(lng[0]) + float(lng[1]) / 60 + float(lng[2]) / 3600
        if gps.get(1) == "S":
            lat = -lat
        if gps.get(3) == "W":
            lng = -lng
        if lat or lng:
            return lat, lng
    except Exception:
        pass
    return None


def exif_date(im):
    ex = im.getexif()
    for tag in (36867, 306):                # DateTimeOriginal, DateTime
        v = ex.get(tag) or ex.get_ifd(0x8769).get(tag)
        if v:
            try:
                return datetime.strptime(str(v)[:10], "%Y:%m:%d").date()
            except ValueError:
                pass
    return None


def hav_km(a, b):
    dla, dlo = radians(b[0] - a[0]), radians(b[1] - a[1])
    h = sin(dla / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(dlo / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def convoy_position(iso_day):
    """Interpolated convoy position for an ISO date — the same maths as
    posAt()/legOf() in template.html, ported to Python."""
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    rec, route = d["records"], d["route"]
    days = [r["iso"] for r in rec]
    iso = min(max(iso_day, days[0]), days[-1])
    ri = next(i for i, r in enumerate(rec) if r["iso"] >= iso)

    norm = lambda s: re.sub(r"[^A-Za-zÀ-ÿ]", "", s or "").upper()
    cp_route = [(i, p["cp"]) for i, p in enumerate(route) if p.get("cp")]
    cp_rec = [next(k for k, r in enumerate(rec)
                   if norm(r["checkpoint"]) == norm(nm)) for _, nm in cp_route]

    # leg containing ri (last leg = stay at the final checkpoint)
    for leg in range(len(cp_route) - 1):
        if cp_rec[leg] <= ri < cp_rec[leg + 1]:
            break
    else:
        p = route[cp_route[-1][0]]
        return p["lat"], p["lng"]
    r0, r1 = cp_rec[leg], cp_rec[leg + 1]
    i0, i1 = cp_route[leg][0], cp_route[leg + 1][0]
    f = (ri - r0) / (r1 - r0)
    seg = [hav_km((route[i]["lat"], route[i]["lng"]),
                  (route[i + 1]["lat"], route[i + 1]["lng"])) for i in range(i0, i1)]
    target, acc = f * sum(seg), 0.0
    for i, sk in enumerate(seg):
        if acc + sk >= target or i == len(seg) - 1:
            lf = (target - acc) / sk if sk else 0
            A, B = route[i0 + i], route[i0 + i + 1]
            return (A["lat"] + (B["lat"] - A["lat"]) * lf,
                    A["lng"] + (B["lng"] - A["lng"]) * lf)
        acc += sk


def jitter(file_id):
    """Deterministic ±JITTER deg offset so fallback bubbles don't stack."""
    h = hashlib.sha1(file_id.encode()).digest()
    return ((h[0] / 255 - .5) * 2 * JITTER, (h[1] / 255 - .5) * 2 * JITTER)


# ---- main -----------------------------------------------------------------

def process(token, meta):
    raw = api_get(token, f"/files/{meta['id']}?alt=media", raw=True)
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))

    day = exif_date(im)
    if not day:
        for src in ((meta.get("imageMediaMetadata") or {}).get("time"),
                    meta.get("createdTime")):
            if src:
                try:
                    day = datetime.strptime(str(src)[:10].replace(":", "-"),
                                            "%Y-%m-%d").date()
                    break
                except ValueError:
                    pass
    day = day or date.today()

    pos, gps = exif_gps(im), True
    if not pos:
        loc = (meta.get("imageMediaMetadata") or {}).get("location")
        if loc and (loc.get("latitude") or loc.get("longitude")):
            pos = (loc["latitude"], loc["longitude"])
    if not pos:
        gps = False
        lat, lng = convoy_position(day.isoformat())
        dj = jitter(meta["id"])
        pos = (lat + dj[0], lng + dj[1])

    im = im.convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    im.save(os.path.join(UPLOADS, f"{meta['id']}.jpg"), "JPEG", quality=80)

    side = min(im.size)
    box = ((im.width - side) // 2, (im.height - side) // 2)
    thumb = im.crop((box[0], box[1], box[0] + side, box[1] + side)) \
              .resize((THUMB, THUMB), Image.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, "JPEG", quality=78)

    return {"id": meta["id"], "name": meta.get("name", ""),
            "date": day.isoformat(), "lat": round(pos[0], 5),
            "lng": round(pos[1], 5), "gps": gps,
            "thumb": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "file": f"photos/uploads/{meta['id']}.jpg"}


def main():
    dry = "--dry-run" in sys.argv
    gallery = []
    if os.path.exists(GALLERY):
        with open(GALLERY, encoding="utf-8") as f:
            gallery = json.load(f)
    known = {g["id"] for g in gallery}

    token = access_token(load_key(), scope=SCOPE)
    files = list_images(token, folder_id())
    new = [m for m in files if m["id"] not in known]
    print(f"{len(files)} image(s) in the Drive folder, {len(new)} new.")
    if dry:
        for m in new:
            print(f"  would fetch: {m.get('name', m['id'])}")
        return
    if not new:
        return

    os.makedirs(UPLOADS, exist_ok=True)
    for m in new:
        entry = process(token, m)
        gallery.append(entry)
        how = "GPS" if entry["gps"] else "convoy@" + entry["date"]
        print(f"  + {entry['name'] or entry['id']}  ({entry['lat']}, {entry['lng']}, {how})")

    gallery.sort(key=lambda g: g["date"])
    with open(GALLERY, "w", encoding="utf-8") as f:
        json.dump(gallery, f)
    print(f"Wrote {os.path.normpath(GALLERY)} ({len(gallery)} photo(s))")
    runpy.run_path(os.path.join(HERE, "build.py"), run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, urllib.error.URLError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
