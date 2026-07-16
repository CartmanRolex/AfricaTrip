# src/ — all source code

> Rule: whenever you modify/add a feature here, update this file (and the
> root `CLAUDE.md` if the architecture changes) in the same commit.

## Files

### `template.html` — the entire app (HTML + CSS + JS, ~600 lines)
Built into `index.html`/`voyage-afrique.html` by `build.py`, which replaces
two literal tokens:
- `__DATA__`   ← contents of `data.json`
- `__PHOTOS__` ← contents of `photos.json`

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
- `DATA.route` — polyline points `{lat,lng, cp?}`; points with `cp` are
  checkpoints (SUISSE, MALAGA, ALGECIRAS, DAKHLA, DAKAR).
- `LEGS` — derived legs between checkpoints (`s`/`e` = record indices,
  `ri0`/`ri1` = route indices; last leg is the open-ended stay at Dakar).
- `LEG_META` — per-leg theme emoji + difficulty 1-5 + label (◆ pips,
  color-coded green/amber/red).
- `RPG` — per-traveler `{xp, pv, skill}` (fun, hand-written; PV bar color
  thresholds ≥7 green, ≥4 amber, else red).
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
  convoy, `legLine` sand-dashed polyline highlighting the ACTIVE leg (this is
  what makes a clicked leg visible — don't remove it), checkpoint dots,
  pulsing convoy marker (amber "?" variant past Dakar with the "open route"
  circle).

### `build.py`
Reads `template.html` + `data.json` + `photos.json`, writes the two root
HTML files. Trivial; run after ANY change to template or JSON.

### `parse_csv.py`
`data/AfriqueCalendrier_-_Presences_Voyage.csv` → `data.json`. Only needs
rerunning when the CSV changes (usually via `refresh.py`).

### `refresh.py`
Downloads the live Google Sheet as CSV (URL/ID from git-ignored
`.sheet-url`, or CLI arg), then runs parse_csv + build in-process. The sheet
must be shared "anyone with link can view". Stdlib only.

### `sheet_edit.py`
CLI to read and **write** the live Google Sheet (`tabs`, `get "A1:E5"`,
`set "B3" value…`, `setrows "A10:C12" rows.json`, `clear "Z100"`; A1 ranges,
optional `Tab!` prefix, first tab by default). Auth is a Google Cloud
service account: JSON key in the git-ignored `.sheet-credentials.json` at
the repo root, sheet shared with the service-account email as Editor
(one-time setup steps in the docstring). Sheet ID comes from `.sheet-url`
like `refresh.py`. After sheet writes, run `refresh.py` to sync the site.

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

### `data.json` / `photos.json`
Generated. Never edit by hand; regenerate with the scripts above. Both are
committed so a rebuild doesn't depend on the private sheet.
