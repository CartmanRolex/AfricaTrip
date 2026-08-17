# Voyage en Afrique — interactive trip map

### ▶ [**Open the live map**](https://cartmanrolex.github.io/AfricaTrip/)

Nothing to install, works on a phone. That link is the site — everything below
is for people who want to change it.

A website following a two-car overland convoy from Switzerland to **Freetown,
Sierra Leone** (Aug–Sep 2026). Pick a leg or scrub the timeline to see the route
on a map and who is in each car on any given day.

## Open it

The published site is <https://cartmanrolex.github.io/AfricaTrip/>, served by
GitHub Pages from `index.html` at the repo root.

`voyage-afrique.html` is the same page as a standalone file you can open from
disk — handy offline, though it still needs the network for map tiles and
fonts, and `file://` blocks the live Firebase feed (the page falls back to the
history it already carries).

The map presents one hybrid route instead of separate planned/actual modes. For
each subject, the GPS path already covered is solid and the rest is dashed —
and the dashed line always starts at the most recent GPS point, so you can
always see where someone is heading next. A subject with no GPS data keeps the
full planned route. Cars are drawn exactly like people: same round marker, same
clustering when several land on the same spot.
Selecting a traveler highlights only that person's own route and frames their
whole planned trace; tap their head on the map to fly in on them instead. The
timestamp remains visible so an old point is never presented as fresh. Shared
photos are filtered by the timeline only, never by the selected subject.

**Sliding the timeline moves the map through time.** Tracks, faces and photos
are limited to what was known at the end of the selected day. Pick a day still
to come and the site shows where each subject is *planned* to be — always drawn
with a dashed outline and labelled "position prévue", never disguised as a real
GPS fix.

## Download the Android app

The current APK is published in GitHub Releases so every crew member can
download it without building the project:

- [Download `expedition-afrique.apk`](https://github.com/CartmanRolex/AfricaTrip/releases/latest/download/expedition-afrique.apk)
- [Open the release page](https://github.com/CartmanRolex/AfricaTrip/releases/latest)

Android may ask for permission to install an app downloaded outside the Play
Store. Existing installations must be replaced manually when a new APK is
published.

## Project layout

```
index.html               <- what GitHub Pages serves (generated)
voyage-afrique.html      <- same page, standalone copy (generated)
data/
  AfriqueCalendrier_-_Presences_Voyage.csv   <- presence grid (the trip data)
  Config.csv             <- route, textes, RPG, danger zones… (the trip data)
src/
  template.html          <- the whole app: HTML + CSS + JS, with __TOKEN__ slots
  build.py               <- injects the JSON below into the template -> both pages
  parse_csv.py           <- CSV + site-overrides.json -> src/data.json
  site-overrides.json    <- repo-side config: year, roster, phones, terminus,
                            car changes (`vehicle_from`), disowned GPS points
  fetch_routes.py        <- road geometry for every drawn pair -> routes.json
  fetch_tracks.py        <- snapshots the Firestore history -> tracks.json
  fetch_photos.py        <- shared Drive photos -> gallery.json
  make_faces.py          <- portraits and stickers -> photos.json
  check_continuity.mjs   <- the map invariant, run after ANY map change
  check_overrides.py     <- alerts when a `vehicle_from` override went stale
  sync.py                <- one-shot: rebuild, fetch photos, commit, push
app/                     <- Capacitor crew app: car choice, GPS, gauges, media
  build-android.sh       <- reproducible APK build
  release.sh             <- publishes it (never publish a release by hand)
.github/workflows/routes.yml  <- hourly: routes + history snapshot + rebuild
firebase.json            <- deploys app/firestore.rules to africatrip-eea1a
```

The `*.json` files in `src/` are generated and committed, so a rebuild never
depends on the private Sheet, Drive or Firestore being reachable.

## Actual-trip data

The planned route stays in `src/data.json`. Actual data is isolated in Firestore
under `trips/africa-trip-01`:

- `assignmentEvents`: immutable changes of car/mode (crew-only read);
- `trackChunks`: public, append-only point maps, split by person/session/
  assignment and two-hour window;
- `latest`: one public reliable latest point per person;
- root `photos`: legacy-compatible media enriched with trip/person/vehicle
  context and capture/location-source metadata.

The app never invents a car position: each person explicitly chooses
Hugodouard, Paul Pot, À pied/autre, or Pause. The site derives each car route
from the points declared in that car, using one-minute buckets and rejecting
inaccurate fixes, impossible speeds and long gaps.

Deploy only the rules (the site itself remains on GitHub Pages):

```bash
firebase deploy --only firestore:rules
```

## How the site stays fresh

`.github/workflows/routes.yml` runs **hourly** and needs no key: it recomputes
the trip data, routes any new GPS pair through OSRM, snapshots the Firestore
history, rebuilds the pages and commits only if something changed.

That snapshot is the important part. The page used to open fourteen live
listeners and read 235 documents **per visit** — the Firestore free tier allows
50 000 reads a day, so the site could serve about 210 visitors before the whole
project started returning quota errors, taking the crew's GPS uploads down with
it. A site that succeeds was breaking itself.

So the history is shipped inside the page, and the page subscribes only to what
is live plus the **catch-up** — whatever was written after the snapshot's own
cursors. Reading cost no longer grows with the audience or with the trip's
length. New photos still appear within seconds, not at the next hourly run.

The last step of the workflow is deliberately blocking: `check_overrides.py`
fails the job when a manual car-assignment override has outlived the fact it
described, which turns a silent wrong display into a build-failure email.

## Browsing and downloading media

Photo pins open a viewer; a pile opens that pile's series. A discreet button in
the viewer downloads a single medium at full original quality.

**📥 Télécharger les médias** in the panel downloads them in bulk. Everything is
selected on opening — the selection exists to *remove* — and one chip per author
toggles a whole person. The result is a **ZIP** (built in the page, no library,
stored not deflated since JPEG and MP4 are already compressed): one download
prompt instead of one per photo, which is what iOS was doing. Peak memory is one
file, not the archive, so a phone can package 900 MB. Archives are cut at
400 MB. On iOS the archive lands in Files, not the Photo Library — no web API
can write to Photos; unzip it there and use Share → "Save Images".

## Editing the trip

**The Google Sheet is no longer the reference.** The trip data lives in this
repo and is edited here:

| What | Where |
|------|-------|
| Who is in which car, day by day | `data/AfriqueCalendrier_-_Presences_Voyage.csv` |
| Route, checkpoints, legs, RPG stats, danger zones, texts | `data/Config.csv` |
| Trip year, removed travelers, phone numbers, final checkpoint | `src/site-overrides.json` |

Then rebuild:

```bash
python src/parse_csv.py && python src/build.py
```

Or run `python src/sync.py` (double-click `sync.bat`) to rebuild, pull new Drive
photos and publish in one go.

### Config.csv

Everything "editorial" lives here so it can be changed without touching code:
route waypoints & checkpoint labels, per-leg emoji + difficulty, traveler and
car RPG stats (XP/PV/compétences/malus), danger-zone stickers, car colours, and
UI texts (tagline, footer, "itinéraire ouvert"…). The file is a stack of
sections — a `## nom` marker row, a header row, then data rows. Edit cells or
add rows; unknown sections pass through `parse_csv.py` untouched.

### Importing from a Google Sheet (legacy)

`src/refresh.py` and `src/sheet_edit.py` still exist for a one-off import from
a sheet, but they are outside the build. `refresh.py` **overwrites**
`data/*.csv`, so it refuses to run without an explicit flag:

```bash
python src/refresh.py --from-sheet                  # sheet URL/ID in .sheet-url
python src/refresh.py --from-sheet "<url-or-id>" --gid 123456
```

The sheet link is kept out of the repo on purpose, in the git-ignored
`.sheet-url` at the root; `sheet_edit.py` additionally needs a service-account
key in the git-ignored `.sheet-credentials.json` and `pip install google-auth`.

## Rebuild details

The two build steps:

```bash
python src/parse_csv.py   # CSV + site-overrides.json -> src/data.json
python src/build.py       # JSON -> index.html + voyage-afrique.html
```

After **any** change touching the map, run the invariant checker:

```bash
node src/check_continuity.mjs   # the line breaks only where the data breaks
```

It walks every subject × every day and fails if the drawn track is cut anywhere
the data does not justify. It exists because gaps were chased one by one for
days, each fix leaving others, while the watchdog of the time looked at two
junctions and reported "no gap" with 39 subject-days broken.

`parse_csv.py` only needs the Python standard library and detects the grid
layout (header row, car rosters, data rows) dynamically, so it tolerates rows
or people being added/removed. If you just want to tweak the page (styles,
layout, behaviour), edit `src/template.html` and re-run `build.py`.

## Data model (`data.json`)

- `records[]` — one per day: `date`, `iso`, `checkpoint` (only on arrival days),
  `location` (carried forward), `cap1`/`cap2`/`total`, and `car1`/`car2` maps of
  `person -> state`.
- `state` is one of `present` (●), `unknown` (?), `tentative` (○), `absent` (blank).
- `route[]` — ordered waypoints `{name, lat, lng}` from the Config tab. Seven
  carry a `cp` field and are the official checkpoints matched against the grid
  (SUISSE, MALAGA, ALGECIRAS, DAKHLA, DAKAR, CONAKRY, FREETOWN); the rest are
  intermediate points so the drawn line follows roads/coast. The Config tab
  still lists the abandoned Abidjan/Accra/Lomé continuation — `terminus` in
  `src/site-overrides.json` cuts the plan after Conakry at build time.
- `car1`/`car2` — roster arrays. `cars` — display metadata (name, emoji, colour).
- `config` — the parsed Config tab (`textes`, `checkpoints`, `route`, `couleurs`,
  `etapes`, `rpg`, `rpgVoitures`, `danger`), consumed by the front-end.

## How the front-end works (`template.html`)

All logic is vanilla JS in one `<script>` at the bottom:

- **Legs** are derived from consecutive checkpoints, plus a final "stay" leg in
  Freetown. Checkpoint↔record matching is normalized (`norm()`) because the sheet
  writes `ALGECIRAS⛴️` with a ferry emoji.
- **Convoy position** (`posAt`) interpolates along the route by elapsed days
  between the surrounding checkpoints, using haversine segment distances.
- **Car dashboards** (`renderCar`) draw a 4-seat layout; occupants fill seats
  coloured by state and remaining seats show as empty. People not aboard that
  day are simply not listed.
- A timeline scrubber + play button drive everything off a single `idx`.

## Notes / assumptions to revisit

- "SUISSE" was placed at Geneva; intermediate waypoints (Spain, Morocco,
  Mauritania, Guinea) are plausible guesses, not confirmed stops. Correct
  coordinates in the sheet's Config tab (`## route` section); the `ROUTE`
  constant in `src/parse_csv.py` is only a fallback.
- The September continuation (Dakar → Conakry → Freetown) is a scenario: dates,
  crew changes and difficulty levels are still to be refined.
- Crew composition changes *within* legs (e.g. Malen→Edouard around Dakhla,
  Arthur leaves at Dakar, several go unconfirmed in September), which is why the
  seats update per day rather than per leg.
