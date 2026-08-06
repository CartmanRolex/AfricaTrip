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

**The Google Sheet is no longer the reference.** The trip data lives in the
repo and is edited there; nothing in the build reads the sheet any more.
`src/refresh.py` survives only as a deliberate one-off import and refuses to
run without `--from-sheet`, because it overwrites `data/*.csv`.

```
data/AfriqueCalendrier_-_Presences_Voyage.csv   (committed, hand-editable)
data/Config.csv                                 (committed, hand-editable)
   + src/site-overrides.json       # repo-side trip config (year, roster, phones, terminus)
   │  python src/parse_csv.py      # CSV + config -> src/data.json
   ▼
src/data.json ───┐
src/photos.json ─┤ python src/build.py   # injects all four into src/template.html
src/gallery.json ┤
src/routes.json ─┘
                 ▼
index.html + voyage-afrique.html   (identical, self-contained, ~790 KB)
version.json                       (build id, for the auto-refresh below)
```

- `src/photos.json` (face/car/sticker images as data URIs) is produced by
  `python src/make_faces.py` from the images in `photos/`.
- `src/site-overrides.json` is the committed repo-side trip config, applied
  after the CSVs are parsed. It pins the confirmed 2026 trip year/tagline and
  recomputes weekday labels, removes Thomas from the published roster
  (so car 2 exposes a fourth **Place disponible**), supplies the formatted
  phone numbers shown in traveler fiches, and ends the trip at **Freetown**
  after Conakry (`terminus`) because the imported CSV still describes the
  abandoned Abidjan/Accra/Lomé continuation. `parse_csv.py` also recomputes car
  capacities/totals after a removal, so stale CSV formulas cannot count the
  removed column. Anything of this kind belongs here — **never hardcoded inside
  `parse_csv.py`**, where it would silently disagree with the docs.
- `src/gallery.json` (shared trip photos shown as bubbles on the map) is
  produced by `python src/fetch_photos.py`, which pulls new images from the
  shared Google Drive folder (`.drive-folder`, git-ignored), geolocates them
  (EXIF GPS, else convoy position on the photo's date), saves resized copies
  in `photos/uploads/`, and rebuilds. Injected as `__GALLERY__`. It also
  reads **`.zip` files** dropped in the folder and processes the photos
  inside — this is the supported way for friends to upload with GPS intact,
  because Android (since April 2026) strips EXIF location on normal uploads
  but not from photos inside a zip (see `COMMENT-UPLOADER.md`).
- **The map is one hybrid planned/actual truth per subject.** `DATA.route`
  remains the untouched editorial plan. The public site now merges
  the v2 chunks/latest GPS, the readable v1 `tracks/{name}/points` history from
  the first trip day onward, and genuinely GPS-geolocated media into a
  chronological personal route. Manual media pins and Drive photos whose
  position was estimated from the plan stay visible as photos but never become
  “real” track points. A point that carries **no** captured car falls back to
  the person's roster car (`rosterVehicleId()`): the app writes `car:"obs"` for
  “À pied / autre” *and* for its own default, so crew members' photos used to
  land outside their vehicle.
- **The travelled track is made of GPS points and photos, nothing else.** It
  joins the accepted points in order — no road is ever reconstructed from the
  itinerary, and no straight line is invented to fill a gap.
- **Between two points it follows the actual road.** `src/routes.json`
  (produced by `python src/fetch_routes.py`) holds the driving geometry of each
  pair of consecutive points, keyed by their rounded coordinates. It is
  **precomputed and committed**, so the published page calls no routing service:
  it looks the pair up and falls back to the straight line when it is missing.
  Without it, sparse points join through the sea — Montpellier to Barcelona in a
  straight line crosses the Gulf of Lion. A routed geometry is a deduction, not
  a measurement, but it is far closer to the truth than that.
- **People riding together share one track.** Occupants of a car describe the
  same movement, so each of them gets the car's merged track for the days the
  presence grid puts them aboard, plus their own points outside those days. One
  phone left on is enough for the whole crew. Nobody inherits a car they are not
  in, and an inherited point still has to be later than that person's own
  `track_start`. Short teleports are
  rejected and a long impossible jump opens a separate section.
- **The future is one interpolation: last known position → next stop, then the
  plan.** `addPlannedFuture()` starts the dashed line exactly at the most recent
  point and joins the next checkpoint (`nextStopKm()`), then follows the
  itinerary to the end of the subject's range.
- **Each person's track starts on their own date** (`track_start` in
  `site-overrides.json`: `default` 2026-08-02, with Jehan and Dorvan from
  2026-07-30). Anything older is a pre-trip leftover — test photos, commutes —
  and is dropped before any reconstruction. This is the single place that
  decides it; there is no hardcoded departure constant any more.
- **Cars are characters, not a special case.** They use the same round avatar
  marker as people, and the same `faceCluster` handles their overlaps — no
  bespoke shape, no bespoke spreading. Only the image framing differs
  (`.wide-art`), because a car cut-out is landscape and would otherwise be
  cropped to nothing in a circle.
- **Choosing a subject frames their journey; only clicking a head zooms in.**
  Picking someone in the toolbar, or opening their fiche from the panel, fits
  their whole planned trace. Tapping their head on the map flies to them.
- **The gallery belongs to the trip, not to the subject.** Photos are filtered
  by the timeline only — switching trace never makes a photo disappear.
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
- **A published page notices when a newer one exists.** GitHub Pages serves
  `index.html` with `cache-control: max-age=600` and gives no way to change
  headers, so a browser keeps the page for ten minutes without asking. Each
  build stamps a `__BUILD__` id into the HTML and writes the same id to
  `version.json`; on load the page fetches that tiny file uncached and reloads
  **once** if the ids differ (a `sessionStorage` mark makes a loop impossible).
  Verified against a `max-age=600` server: the reload really does return the new
  HTML, not the cached copy. It is skipped on `file://` and silent on any
  failure. `version.json` must stay published — it is in `sync.py`'s whitelist.
- **Deploying takes about a minute**, sometimes much longer, and that is the
  other half of "I don't see my change". `.nojekyll` at the root stops GitHub
  Pages from running Jekyll over the whole 138 MB repo (the videos dominate);
  builds were 45-65 s typically but one took 434 s. Never delete that file.
- **One-shot update for the user**: `python src/sync.py` (or double-clicking
  `sync.bat` at the root) chains parse_csv + fetch_routes + build + fetch_photos
  (routing is non-blocking: offline, known routes are kept and new segments stay
  straight), then commits
  and pushes ONLY the whitelisted pipeline inputs/outputs (including
  `src/site-overrides.json`, safe wrt `photos/gal.enc`). No-op if nothing
  changed. It deliberately does **not** call `refresh.py` any more: a
  double-click must never overwrite the repo's trip data with an abandoned
  sheet.

## Folder map

| Path        | Contents                                                        |
|-------------|-----------------------------------------------------------------|
| `src/`      | All source: pipeline scripts + `template.html` + persistent `site-overrides.json` |
| `data/`     | **The trip data** (presence grid + Config), committed and hand-editable |
| `photos/`   | Source images (traveler photos, sticker sheets) + generated subfolders |
| `index.html`, `voyage-afrique.html` | Generated site (do not edit)            |
| `sync.bat`  | Double-click updater for the user (runs `src/sync.py`)         |
| `COMMENT-UPLOADER.md` | Friend-facing note: how to upload photos keeping GPS (zip method) |
| `app/`      | Crew Android app (Capacitor + Firebase): live position, PV/XP, photo & video upload keeping GPS. See `app/CLAUDE.md` |
| `firebase.json`, `.firebaserc` | Reproducible Firebase Rules target (`app/firestore.rules`, project `africatrip-eea1a`) |
| `package.json` | Headless-check tooling only (puppeteer/jsdom). `node_modules/` is git-ignored — never commit it |
| `.sheet-url`| Local only, git-ignored: sheet link, for the legacy import only |
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
  markers, one per selected subject), `.track-now.planned` (planned positions),
  `personPoints(name)` / `vehiclePoints(id)` (what feeds a track),
  `lbList.length` after a click (the pile the gallery is scoped to), and walking
  `actualTrackLayer.eachLayer` to read every drawn polyline's style — that is
  how the ghost leg line was found.

## Data access

- **Trip data**: edit `data/AfriqueCalendrier_-_Presences_Voyage.csv` (presence
  grid) or `data/Config.csv` (route, checkpoints, RPG, danger zones, texts)
  directly, plus `src/site-overrides.json` for year/roster/phones/terminus,
  then `python src/parse_csv.py && python src/build.py`. The repo is the
  reference — there is no live source to sync back to.
- **Legacy sheet tools**: `src/refresh.py --from-sheet` re-imports from a
  Google Sheet and **overwrites** `data/*.csv`; `src/sheet_edit.py` writes to a
  sheet through the Sheets API. Both are kept for a one-off migration only and
  are outside the build path. Do not wire them back into `sync.py`.
- **Shared photos**: friends upload images to a shared Drive folder;
  `python src/fetch_photos.py` syncs them onto the map (service account with
  `drive.readonly` scope; folder link in the git-ignored `.drive-folder`).
- Google Drive MCP connector: read/search/copy/create only, no editing —
  use `fetch_photos.py` for scripted photo access.
- **Firestore Rules**: authenticate the Firebase CLI, then run
  `firebase deploy --only firestore:rules`. The committed `.firebaserc` pins
  the project and `firebase.json` pins the rules file; never deploy Hosting
  from Firebase because the public site is hosted by GitHub Pages.
