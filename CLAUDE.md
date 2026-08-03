# Voyage en Afrique — Carnet de route

Interactive one-page site tracking a friends' road trip from Switzerland to
Dakar and on to **Freetown** (Aug 2 – Sep 30, 2026): a Leaflet map with the
route, a day-by-day timeline scrubber, and RPG-flavored dashboards for the two
cars and their crews. Everything is tongue-in-cheek (XP, HP bars, skills,
danger zones) — keep that tone when adding features.

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
   edit them by hand (see Build pipeline). Editing `src/template.html` without
   rebuilding and committing them means the published site does not have your
   change: that is the single most common way this repo goes stale.
5. **The repo stays clean.** Never commit `node_modules/`, an APK (GitHub
   Releases distributes it), a screenshot, or a throwaway script. Debug scripts
   belong outside the repo — and never paste the private Sheet id/URL into one,
   it is git-ignored in `.sheet-url` precisely so it never reaches GitHub.

## Build pipeline (all scripts in `src/`, run from repo root)

```
Google Sheet (live, private link in .sheet-url, git-ignored)
   │  python src/refresh.py        # downloads CSV export + runs the two steps below
   ▼
data/AfriqueCalendrier_-_Presences_Voyage.csv
   + src/site-overrides.json       # confirmed year/text + roster/phone overrides
   │  python src/parse_csv.py      # CSV + overrides -> src/data.json
   ▼
src/data.json ──┐
src/photos.json ─┤ python src/build.py   # injects both into src/template.html
                 ▼
index.html + voyage-afrique.html   (identical, self-contained, ~500 KB)
```

- `src/photos.json` (face/car/sticker images as data URIs) is produced by
  `python src/make_faces.py` from the images in `photos/`.
- `src/site-overrides.json` is a small, committed final layer applied after
  every Sheet download. It pins the confirmed 2026 trip year/tagline and
  recomputes weekday labels, removes Thomas from the published roster
  (so car 2 exposes a fourth **Place disponible**), supplies the formatted
  phone numbers shown in traveler fiches, and ends the trip at **Freetown**
  after Conakry (`terminus`) because the Sheet still describes the abandoned
  Abidjan/Accra/Lomé continuation. `parse_csv.py` also recomputes car
  capacities/totals after a removal, so stale Sheet formulas cannot count the
  removed column. This exists because Sheet write credentials are not present
  on the build machine; a future `refresh.py` must not undo the published site.
  Anything of this kind belongs here — **never hardcoded inside
  `parse_csv.py`**, where a refresh would silently disagree with the docs.
- `src/gallery.json` (shared trip photos shown as bubbles on the map) is
  produced by `python src/fetch_photos.py`, which pulls new images from the
  shared Google Drive folder (`.drive-folder`, git-ignored), geolocates them
  (EXIF GPS, else convoy position on the photo's date), saves resized copies
  in `photos/uploads/`, and rebuilds. Injected as `__GALLERY__`. It also
  reads **`.zip` files** dropped in the folder and processes the photos
  inside — this is the supported way for friends to upload with GPS intact,
  because Android (since April 2026) strips EXIF location on normal uploads
  but not from photos inside a zip (see `COMMENT-UPLOADER.md`).
- **The map is one hybrid planned/actual truth per subject.** The Sheet/
  `DATA.route` remains the untouched editorial plan. The public site now merges
  the v2 chunks/latest GPS, the readable v1 `tracks/{name}/points` history from
  the first trip day onward, and genuinely GPS-geolocated media into a
  chronological personal route. Manual media pins and Drive photos whose
  position was estimated from the plan stay visible as photos but never become
  “real” track points. For each car, only points with an explicit captured car
  assignment are used; v1 points without one remain personal, so cars and people
  cannot contaminate one another. Sparse points several hours apart stay joined
  when the implied speed is plausible; short teleports are rejected and a long
  impossible jump starts a separate section instead of drawing a diagonal.
  The accepted history is solid and only the untravelled suffix of `DATA.route`
  remains dashed. Its endpoint is projected geometrically onto the plan; a very
  distant point is never joined by a misleading connector. Each subject is
  clipped by **its own** progress, never by the other car's lead. The current
  face/car marker still comes from GPS rather than from an old uploaded photo.
- **The timeline is a time machine, and a planned position always says so.**
  Scrubbing the frise restricts tracks, faces and photos to what was known by
  the end of the selected day. For a future day — or a day with no reality at
  all — the site interpolates the subject's *planned* position on the route and
  marks it as such (dashed outline, no pulse, "position prévue" in the tooltip
  and in the fiche). That flag is not optional: it is what keeps the promise
  that the site never presents an invented position as a real one. Observers
  are never placed on the route, since they are not travelling.
  The app starts in Pause for a person who has never chosen a mode, queues
  offline in IndexedDB, samples at most once/minute (five minutes while still),
  and groups immutable points by person/session/assignment in two-hour chunks.
- The site is **fully self-contained**: all images are embedded as data URIs
  so `voyage-afrique.html` opens from disk; only map tiles/fonts/Leaflet come
  from CDNs.
- **One-shot update for the user**: `python src/sync.py` (or double-clicking
  `sync.bat` at the root) chains refresh.py + fetch_photos.py, then commits
  and pushes ONLY the whitelisted pipeline inputs/outputs (including
  `src/site-overrides.json`, safe wrt `photos/gal.enc`). No-op if nothing
  changed.

## Folder map

| Path        | Contents                                                        |
|-------------|-----------------------------------------------------------------|
| `src/`      | All source: pipeline scripts + `template.html` + persistent `site-overrides.json` |
| `data/`     | CSV snapshot downloaded from the Google Sheet                   |
| `photos/`   | Source images (traveler photos, sticker sheets) + generated subfolders |
| `index.html`, `voyage-afrique.html` | Generated site (do not edit)            |
| `sync.bat`  | Double-click updater for the user (runs `src/sync.py`)         |
| `COMMENT-UPLOADER.md` | Friend-facing note: how to upload photos keeping GPS (zip method) |
| `app/`      | Crew Android app (Capacitor + Firebase): live position, PV/XP, photo & video upload keeping GPS. See `app/CLAUDE.md` |
| `firebase.json`, `.firebaserc` | Reproducible Firebase Rules target (`app/firestore.rules`, project `africatrip-eea1a`) |
| `package.json` | Headless-check tooling only (puppeteer/jsdom). `node_modules/` is git-ignored — never commit it |
| `.sheet-url`| Local only, git-ignored: link to the live Google Sheet          |
| `.drive-folder` | Local only, git-ignored: link to the shared Drive photo folder |

## Verifying changes (headless, no dev server needed)

There is no test suite; checks are visual + runtime. Puppeteer is the tool on
this machine (`npm install` at the root, `node_modules/` is git-ignored):

```js
const puppeteer = require('puppeteer');
const b = await puppeteer.launch({args:['--no-sandbox','--disable-setuid-sandbox']});
const p = await b.newPage();
p.on('pageerror', e => console.log('ERROR', e.message));   // ALWAYS listen
await p.goto('file:///home/students/africa-build/index.html', {waitUntil:'load'});
await new Promise(r => setTimeout(r, 3000));               // laisser Firebase répondre
await p.evaluate(() => { setTrackSubject('person:gal', false); setIndex(35); });
await p.screenshot({path:'/tmp/out.png'});
```

Gotchas learned the hard way:
- Never use `waitUntil:'networkidle0'` — map tiles keep streaming and the
  navigation times out. Use `'load'` plus an explicit wait.
- **Drive the page through its own functions** (`setIndex`, `setTrackSubject`,
  `openFicheFor`, `setTrackMenu`) inside `page.evaluate`. Do not patch a copy
  of `index.html`: it is a build artifact and the patch is lost on rebuild.
- Always attach `pageerror`/`console` listeners. A silent screenshot hides a
  ReferenceError that empties the whole map.
- The page reads Firestore live, so a run on a connected machine exercises
  real crew data; offline it must still render (it fails quietly).
- For mobile, `page.setViewport({width:420, height:860, isMobile:true,
  hasTouch:true})` works directly — no iframe wrapper needed.
- Useful assertions: `document.querySelectorAll('.track-now').length` (subject
  markers), `.track-now.planned` (planned positions), `legLine.getLatLngs()`
  (highlighted leg), `visibleGalleryIndices().length` (media filtering).

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
- **Firestore Rules**: authenticate the Firebase CLI, then run
  `firebase deploy --only firestore:rules`. The committed `.firebaserc` pins
  the project and `firebase.json` pins the rules file; never deploy Hosting
  from Firebase because the public site is hosted by GitHub Pages.
