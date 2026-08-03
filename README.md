# Voyage en Afrique — interactive trip map

A self-contained website showing a two-car overland convoy from Switzerland to
Senegal (Aug–Sep 2026). Pick a leg or scrub the timeline to see the route on a
map and who is in each car on any given day.

## Open it

Open **`voyage-afrique.html`** in any browser. No build step or server needed —
it's a single file. It loads Leaflet, map tiles (CARTO), and Google Fonts from
CDNs, so it needs an internet connection to render the map.

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
voyage-afrique.html          <- the deliverable (open this)
data/
  AfriqueCalendrier_-_Presences_Voyage.csv   <- presence grid (the trip data)
  Config.csv       <- route, textes, RPG, danger zones… (the trip data)
src/
  site-overrides.json <- repo-side config: year, roster, phones, terminus
  parse_csv.py     <- CSV  -> src/data.json   (parses the presence grid)
  data.json        <- structured trip data, embedded into the site at build time
  template.html    <- the full HTML/CSS/JS with a literal __DATA__ token
  build.py         <- injects data.json into template.html -> voyage-afrique.html
app/               <- Capacitor crew app: mode/car choice, GPS, PV and media
firebase.json      <- deploys app/firestore.rules to africatrip-eea1a
```

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
  Dakar. Checkpoint↔record matching is normalized (`norm()`) because the sheet
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
  crew changes and difficulty levels are still to be refined in the sheet. The
  Conakry → Freetown segment is a single straight waypoint pair — add
  intermediate points in the Config tab if the drawn line should follow the
  coast like the rest of the route.
- Crew composition changes *within* legs (e.g. Malen→Edouard around Dakhla,
  Arthur leaves at Dakar, several go unconfirmed in September), which is why the
  seats update per day rather than per leg.
