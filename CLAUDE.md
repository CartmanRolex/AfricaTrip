# Voyage en Afrique — Carnet de route

Interactive one-page site tracking a friends' road trip from Switzerland to
Dakar (Aug 1 – Sep 30, 2025): a Leaflet map with the route, a day-by-day
timeline scrubber, and RPG-flavored dashboards for the two cars and their
crews. Everything is tongue-in-cheek (XP, HP bars, skills, danger zones) —
keep that tone when adding features.

## Golden rules

1. **Always commit AND push to `main` after every change.** The site is
   served by GitHub Pages from `main` (https://github.com/CartmanRolex/AfricaTrip);
   a change is not "done" until pushed. Never ask for permission first.
2. **Update the `CLAUDE.md` of every folder you touch, in the same commit,
   whenever you add or modify a feature.** These files must let any agent
   understand the project without opening the source files.
3. **Never commit `photos/gal.enc`** (unknown encrypted local file,
   git-ignored). Beware of `git add -A photos` — it once picked it up.
4. The two built HTML files at the root are **generated artifacts** — never
   edit them by hand (see Build pipeline).

## Build pipeline (all scripts in `src/`, run from repo root)

```
Google Sheet (live, private link in .sheet-url, git-ignored)
   │  python src/refresh.py        # downloads CSV export + runs the two steps below
   ▼
data/AfriqueCalendrier_-_Presences_Voyage.csv
   │  python src/parse_csv.py      # CSV -> src/data.json
   ▼
src/data.json ──┐
src/photos.json ─┤ python src/build.py   # injects both into src/template.html
                 ▼
index.html + voyage-afrique.html   (identical, self-contained, ~500 KB)
```

- `src/photos.json` (face/car/sticker images as data URIs) is produced by
  `python src/make_faces.py` from the images in `photos/`.
- `src/gallery.json` (shared trip photos shown as bubbles on the map) is
  produced by `python src/fetch_photos.py`, which pulls new images from the
  shared Google Drive folder (`.drive-folder`, git-ignored), geolocates them
  (EXIF GPS, else convoy position on the photo's date), saves resized copies
  in `photos/uploads/`, and rebuilds. Injected as `__GALLERY__`. It also
  reads **`.zip` files** dropped in the folder and processes the photos
  inside — this is the supported way for friends to upload with GPS intact,
  because Android (since April 2026) strips EXIF location on normal uploads
  but not from photos inside a zip (see `COMMENT-UPLOADER.md`).
- The site is **fully self-contained**: all images are embedded as data URIs
  so `voyage-afrique.html` opens from disk; only map tiles/fonts/Leaflet come
  from CDNs.
- **One-shot update for the user**: `python src/sync.py` (or double-clicking
  `sync.bat` at the root) chains refresh.py + fetch_photos.py, then commits
  and pushes ONLY the pipeline outputs (explicit whitelist — safe wrt
  `photos/gal.enc`). No-op if nothing changed.

## Folder map

| Path        | Contents                                                        |
|-------------|-----------------------------------------------------------------|
| `src/`      | All source: pipeline scripts + `template.html` (the whole app)  |
| `data/`     | CSV snapshot downloaded from the Google Sheet                   |
| `photos/`   | Source images (traveler photos, sticker sheets) + generated subfolders |
| `index.html`, `voyage-afrique.html` | Generated site (do not edit)            |
| `sync.bat`  | Double-click updater for the user (runs `src/sync.py`)         |
| `COMMENT-UPLOADER.md` | Friend-facing note: how to upload photos keeping GPS (zip method) |
| `app/`      | Crew Android app (Capacitor + Firebase): live position, PV/XP, photo upload keeping GPS. See `app/CLAUDE.md` |
| `.sheet-url`| Local only, git-ignored: link to the live Google Sheet          |
| `.drive-folder` | Local only, git-ignored: link to the shared Drive photo folder |

## Verifying changes (headless, no dev server needed)

Screenshot with Edge headless (the repo has no test suite; visual checks):

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless \
  --disable-gpu --window-size=1500,950 --screenshot=out.png \
  --virtual-time-budget=10000 "file:///C:/Users/wachi/Documents/AfricaTrip/index.html"
```

Gotchas learned the hard way:
- Edge headless clamps the window to ~500 px wide. To test mobile widths,
  render the page inside an `<iframe style="width:360px">` wrapper file and
  screenshot that.
- To test a specific day/state, copy `index.html` to a scratch file and
  patch it (e.g. replace `setIndex(0);` with `setIndex(12);`, or
  `map.fitBounds(...)` with `map.setView([16.5,-3],5);`).
- To debug JS, inject `window.onerror` writing to `document.title` and use
  `--dump-dom`, or append a fixed-position debug `<div>`.

## Data access

- **Read**: `python src/refresh.py` pulls the sheet's public CSV export and
  rebuilds the site.
- **Write**: `python src/sheet_edit.py` (tabs/get/set/setrows/clear) edits
  the live sheet through the Sheets API using a service-account key stored
  in the git-ignored `.sheet-credentials.json` (setup steps in its
  docstring). After writing to the sheet, run `refresh.py` so the site
  reflects the change.
- **Shared photos**: friends upload images to a shared Drive folder;
  `python src/fetch_photos.py` syncs them onto the map (service account with
  `drive.readonly` scope; folder link in the git-ignored `.drive-folder`).
- Google Drive MCP connector: read/search/copy/create only, no editing —
  use `sheet_edit.py` / `fetch_photos.py` instead for scripted access.
