# src/ — all source code

> Rule: whenever you modify/add a feature here, update this file (and the
> root `CLAUDE.md` if the architecture changes) in the same commit.

## Files

### `template.html` — the entire app (HTML + CSS + JS, ~600 lines)
Built into `index.html`/`voyage-afrique.html` by `build.py`, which replaces
three literal tokens:
- `__DATA__`    ← contents of `data.json`
- `__PHOTOS__`  ← contents of `photos.json`
- `__GALLERY__` ← contents of `gallery.json` (`[]` if absent)

Layout: CSS grid `header / map / panel`. Desktop: map left, 392 px panel
right. **Mobile (≤880 px)**: app-style split — fixed map on top (38vh), the
panel becomes a rounded bottom sheet with its own scroll; the timeline
section (`.sec-tl`) is sticky inside it and the cars section (`.sec-cars`)
reorders before the legs list (CSS `order`). Header compacts to one row
(tagline hidden, pax stat hidden, seats grid goes 1-column).

Key JS structures (all near the top of the script):
- `DATA.records` — one entry per day: `{date, iso, checkpoint, location,
  cap1, cap2, car1:{Name:state}, car2:{...}}`; states: `present | unknown |
  tentative | absent`.
- `DATA.config` — the parsed Config sheet tab; **all editorial content
  comes from it** (`CFG` in the JS): `textes` (tagline, foot, open-route
  labels), `checkpoints` (display names), `etapes` → `LEG_META`, `rpg` →
  `RPG`, `rpgVoitures` → `CAR_RPG`, `danger` → `DANGER`, `couleurs`.
  Fallbacks are minimal — edit the sheet, not the JS.
- `DATA.route` — polyline points `{lat,lng, cp?}` (Config `## route`);
  points with `cp` are checkpoints (SUISSE, MALAGA, ALGECIRAS, DAKHLA,
  DAKAR, CONAKRY, ABIDJAN, ACCRA, LOMÉ).
- `LEGS` — derived legs between checkpoints (`s`/`e` = record indices,
  `ri0`/`ri1` = route indices; last leg is the open-ended stay at Lomé).
- `LEG_META` — per-leg theme emoji + difficulty 1-5 + label (◆ pips,
  color-coded green/amber/red via `DIFF_COLOR`, hex on purpose: reused as
  SVG stroke on the map where `var()` doesn't work).
- `RPG` — per-traveler `{xp, pv, skill}` (PV bar color thresholds ≥7
  green, ≥4 amber, else red).
- `CAR_RPG` — same for the cars + a `malus` line with their real-world
  afflictions (car 1 wheel bearings, car 2 holed exhaust −700 CHF).
- `DANGER` — Sahel danger zones `{lat, lng, img:'terroN', s:size_px, r:radius_m,
  t:label}`; drawn as red dashed circles + sticker `<img>` + label. Zones are
  real advisory geography (France Diplomatie / ACLED): NE-Mauritania military
  zone, east-Mauritanian axes, north & central Mali, Liptako-Gourma
  tri-border, east Burkina, Lake Chad. Stickers are ethnically matched to the
  dominant makeup of the region's armed groups (Arab-looking north,
  Black-looking Sahel/Lake Chad). Labels hide + stickers scale to 62 % below
  zoom 5 (`body.danger-far`, `dangerZoom()`).
- `PHOTOS` — `{faces:{Name:dataURI}, cars:{1:…,2:…}, terros:{terroN:…}}`.
  Faces render in seat chips (30 px circle, status-colored ring, hover zoom
  ×3.2 via `.seat-chip.photo:hover img`); missing faces (Thomas, Jehan) fall
  back to the initial letter.
- Map rendering in `render()`: `traveled` orange polyline (+ glow) up to the
  convoy, `legLine` highlighting the ACTIVE leg (this is what makes a clicked
  leg visible — don't remove it) with animated dashes (`.leg-flow` CSS) and
  difficulty color, a floating `leg-chip` (emoji + label + pips) at the leg's
  mid-distance, numbered `cp-badge` milestones (done = orange fill, next
  destination pulses amber; name pills hide below zoom 5 via
  `body.danger-far`), pulsing convoy marker (amber "?" variant on the final
  stay leg with the "open route" circle).
- The Étapes list is a horizontal scroll-snap slider (`.legs`), ‹ › buttons
  (`#legs-prev/next`), and `render()` auto-scrolls the active card into view.
- `GALLERY` — shared Drive photos `[{id, name, date(iso), lat, lng,
  gps(bool), thumb(dataURI), file}]` (see `fetch_photos.py`). Each renders as
  a round `.photo-bubble` marker (34 px, sand border, 22 px when
  `body.danger-far`); click opens the `#lightbox` overlay showing
  `photos/uploads/<id>.jpg` (relative path; `onerror` falls back to the
  embedded thumb so the standalone file still works), with a date caption
  plus "position estimée (convoi)" when `gps` is false. Esc/click closes.

### `build.py`
Reads `template.html` + `data.json` + `photos.json` + `gallery.json`,
writes the two root HTML files. Trivial; run after ANY change to template
or JSON.

### `parse_csv.py`
`data/AfriqueCalendrier_-_Presences_Voyage.csv` (+ `data/Config.csv`, the
Config tab: `read_config()` parses its `## section` blocks) → `data.json`.
The `ROUTE`/`CAR_COLORS` constants are only fallbacks for a missing
Config.csv. Only needs rerunning when the CSVs change (usually via
`refresh.py`).

### `refresh.py`
Downloads the live Google Sheet as CSV (URL/ID from git-ignored
`.sheet-url`, or CLI arg) — both the presence grid and the Config tab
(`CONFIG_GID`) — then runs parse_csv + build in-process. The sheet must be
shared "anyone with link can view". Stdlib only.

### `sheet_edit.py`
CLI to read and **write** the live Google Sheet (`tabs`, `get "A1:E5"`,
`set "B3" value…`, `setrows "A10:C12" rows.json`, `clear "Z100"`; A1 ranges,
optional `Tab!` prefix, first tab by default). Auth is a Google Cloud
service account: JSON key in the git-ignored `.sheet-credentials.json` at
the repo root, sheet shared with the service-account email as Editor
(one-time setup steps in the docstring). Sheet ID comes from `.sheet-url`
like `refresh.py`. After sheet writes, run `refresh.py` to sync the site.

### `fetch_photos.py`
Syncs the shared Drive photo folder onto the map (`--dry-run` to preview).
Folder URL/ID in the git-ignored `.drive-folder` (same pattern as
`.sheet-url`); auth reuses `sheet_edit.load_key()`/`access_token()` with the
`drive.readonly` scope. For each NEW image (incremental via ids already in
`gallery.json`): downloads it, dates it (EXIF `DateTimeOriginal` → Drive
`imageMediaMetadata.time` → `createdTime`), locates it (EXIF GPS → Drive
location → **convoy position on that date**: `convoy_position()` is a Python
port of the template's `posAt()`/`legOf()` interpolation, plus a
deterministic ±0.12° `jitter()` seeded by the Drive id), then writes
`photos/uploads/<id>.jpg` (max 1600 px) + a 96 px square thumb as data URI
into `src/gallery.json`, and reruns `build.py`. Setup steps in the
docstring (share the folder with the service account as Viewer).

### `make_faces.py`
Produces `photos.json` + the generated image folders. Three parts:
1. **Faces**: hand-tuned square crops of `photos/<name>.jpeg` via the
   `CROPS` dict (cx, cy, size as fractions; tweak these to reframe someone)
   → `photos/faces/<name>.jpg`, 128 px.
2. **Cars**: `cut_car()` crops the two cars out of `photos/voitures.jpg`
   (boxes in `CAR_BOXES`) and removes the FAKE painted checkerboard
   background by flood-filling light unsaturated pixels from the borders.
3. **Stickers**: `cut_stickers()` splits `photos/terros.jpg` into individual
   RGBA stickers: background mask (`outside_mask`) → connected-component
   labeling on a 2× downscale (pure-python BFS, no scipy) → per-blob crop.

Hard-won gotchas (do not re-learn these):
- `Image.fromarray(np_array)` shares a **read-only** buffer —
  `ImageDraw.floodfill` writes are silently lost without `.copy()`.
- The checkerboard in `terros.jpg` spans greys **142–209** only. The
  background candidate is `saturation<20 AND 105<max<230`: the lower bound
  swallows the stickers' soft grey drop shadows (else they bridge neighbours
  into merged blobs), the upper bound **preserves the white sticker
  outlines** (eating them left muddy blend halos, e.g. old terro11 bug).
- Dilation before labeling is MaxFilter(5) on the 2× downscale ≈ merges
  gaps <8 px; bigger kernels merged adjacent stickers on the dense sheet.
- `CLEAN = {sticker_index: [fractional rects]}` erases sheet artifacts baked
  next to a sticker (currently terro7). `DEFRINGE` (halo peeling) exists but
  is unused since the outline fix.

### `data.json` / `photos.json` / `gallery.json`
Generated. Never edit by hand; regenerate with the scripts above. All are
committed so a rebuild doesn't depend on the private sheet or Drive.
To remove a photo permanently, delete it from the Drive folder AND from
`gallery.json` + `photos/uploads/` (a sync re-adds any Drive file whose id
is missing from `gallery.json`).
