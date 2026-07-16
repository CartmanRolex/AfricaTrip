# Voyage en Afrique — interactive trip map

A self-contained website showing a two-car overland convoy from Switzerland to
Senegal (Aug–Sep 2025). Pick a leg or scrub the timeline to see the route on a
map and who is in each car on any given day.

## Open it

Open **`voyage-afrique.html`** in any browser. No build step or server needed —
it's a single file. It loads Leaflet, map tiles (CARTO), and Google Fonts from
CDNs, so it needs an internet connection to render the map.

## Project layout

```
voyage-afrique.html          <- the deliverable (open this)
data/
  AfriqueCalendrier_-_Presences_Voyage.csv   <- source data (Google Sheets export)
  Config.csv       <- export of the sheet's "Config" tab (route, textes, RPG…)
src/
  refresh.py       <- pull the live Google Sheet + rebuild (one command)
  parse_csv.py     <- CSV  -> src/data.json   (parses the presence grid)
  data.json        <- structured trip data, embedded into the site at build time
  template.html    <- the full HTML/CSS/JS with a literal __DATA__ token
  build.py         <- injects data.json into template.html -> voyage-afrique.html
```

## Refresh from the live Google Sheet

The trip data lives in a shared Google Sheet. To pull the latest version and
regenerate the page in one step:

```bash
python src/refresh.py
```

This downloads the sheet as CSV (into `data/` — both the presence grid and the
**Config** tab), re-parses it, and rebuilds `voyage-afrique.html`. It uses only
the Python standard library, and the sheet must be shared as "anyone with the
link can view".

### The Config tab

Everything "editorial" lives in the sheet's **Config** tab so it can be changed
without touching code: route waypoints & checkpoint labels, per-leg emoji +
difficulty, traveler and car RPG stats (XP/PV/compétences/malus), danger-zone
stickers, car colours, and UI texts (tagline, footer, "itinéraire ouvert"…).
The tab is a stack of sections — a `## nom` marker row, a header row, then data
rows. Edit cells (or add rows) and run `python src/refresh.py`; new sections
pass through `parse_csv.py` untouched, so add the sheet side first.

**The sheet link is kept out of the repo on purpose** (so it isn't public on
GitHub). `refresh.py` reads it from a local, git-ignored file at the repo root:

```
.sheet-url      <- one line: the Google Sheets URL or ID (never committed)
```

Create it once on each machine (it's listed in `.gitignore`):

```bash
echo "https://docs.google.com/spreadsheets/d/<ID>/edit" > .sheet-url
```

Or skip the file and pass the sheet on the command line:

```bash
python src/refresh.py "https://docs.google.com/spreadsheets/d/<ID>/edit"
python src/refresh.py "<ID>" --gid 123456
```

## Editing the Google Sheet

`src/sheet_edit.py` can read **and write** the live sheet through the Sheets
API v4, so changes can be made at the source instead of the exported CSV:

```bash
python src/sheet_edit.py tabs                         # list tabs (name + gid)
python src/sheet_edit.py get  "A1:E5"                 # print a range
python src/sheet_edit.py set  "B3" "new value"        # write one cell
python src/sheet_edit.py set  "B3:D3" v1 v2 v3        # write one row
python src/sheet_edit.py setrows "A10:C12" rows.json  # write a 2-D JSON block
python src/sheet_edit.py clear "Z100"                 # clear a range
```

Ranges use A1 notation, optionally prefixed with a tab name (`"Feuille 1!B3"`).
After editing, run `python src/refresh.py` so the site picks up the change.

**One-time setup** — it authenticates as a Google Cloud *service account*:

1. In [Google Cloud console](https://console.cloud.google.com), create/pick a
   project and enable the **Google Sheets API**.
2. IAM & Admin → Service Accounts → create one (no roles needed), then
   Keys → Add key → **JSON** and download it.
3. Save the key as **`.sheet-credentials.json`** in the repo root — like
   `.sheet-url` it is git-ignored and never committed.
4. Share the trip sheet with the service account's email
   (`…@…iam.gserviceaccount.com`) as **Editor**.

Requires `pip install google-auth` (only for signing the auth token; the API
calls themselves are plain standard-library `urllib`).

## Rebuild from the local CSV

If you've edited `data/…csv` by hand and just want to rebuild without fetching:

```bash
python src/parse_csv.py   # CSV  -> src/data.json
python src/build.py       # JSON -> voyage-afrique.html
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
- `route[]` — ordered waypoints `{name, lat, lng}` from the Config tab. Nine
  carry a `cp` field and are the official checkpoints matched against the sheet
  (SUISSE, MALAGA, ALGECIRAS, DAKHLA, DAKAR, CONAKRY, ABIDJAN, ACCRA, LOMÉ);
  the rest are intermediate points so the drawn line follows roads/coast.
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
  coloured by state, remaining seats show as empty, absent members listed below.
- A timeline scrubber + play button drive everything off a single `idx`.

## Notes / assumptions to revisit

- "SUISSE" was placed at Geneva; intermediate waypoints (Spain, Morocco,
  Mauritania, Guinea, Côte d'Ivoire, Ghana) are plausible guesses, not confirmed
  stops. Correct coordinates in the sheet's Config tab (`## route` section);
  the `ROUTE` constant in `src/parse_csv.py` is only a fallback.
- The October continuation (Dakar → Conakry → Abidjan → Accra → Lomé) is an
  arbitrary scenario: dates, crew changes and difficulty levels are inventions
  to be refined in the sheet.
- Crew composition changes *within* legs (e.g. Malen→Edouard around Dakhla,
  Arthur leaves at Dakar, several go unconfirmed in September), which is why the
  seats update per day rather than per leg.
