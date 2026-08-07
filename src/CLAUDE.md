# src/ — all source code

> Rule: whenever you modify/add a feature here, update this file (and the
> root `CLAUDE.md` if the architecture changes) in the same commit.

## Files

### `template.html` — the entire app (HTML + CSS + JS, ~2,000 lines)
Built into `index.html`/`voyage-afrique.html` by `build.py`, which replaces
three literal tokens:
- `__DATA__`    ← contents of `data.json`
- `__PHOTOS__`  ← contents of `photos.json`
- `__GALLERY__` ← contents of `gallery.json` (`[]` if absent)
- `__ROUTES__`  ← contents of `routes.json` (`{}` if absent)
- `__BUILD__`   ← the build id, a hash of those four inputs plus the template

`BUILD` powers the auto-refresh: the page fetches `version.json` uncached and
reloads once when a newer build is published, because GitHub Pages caches the
HTML for ten minutes and offers no header control. Hashing the **inputs** (not
the output, which contains the id) keeps the build idempotent.

The head carries a tiny inline SVG diamond favicon, so the self-contained page
does not generate a stray `/favicon.ico` 404 during browser checks.

Layout: CSS grid `header / map / panel`. The timeline section (`.sec-tl`)
lives in the header on BOTH breakpoints (`header .sec-tl` compact grid:
date + play left, full-width scrub over the ticks); the panel only holds
legs + cars. Desktop: map left, 392 px panel right. **Mobile (≤880 px)**:
app-style split — fixed map on top (38vh), the panel becomes a rounded
bottom sheet with its own scroll and the cars section (`.sec-cars`)
reorders before the legs list (CSS `order`). The header wraps to two rows
(brand + stats, then date/play/scrub; tagline, pax stat and the ticks row
hidden); the seats grid stays 2 columns but the seat cards compact
(smaller padding/chip/fonts, 42 px HP bar). When zoomed out on mobile
(`body.danger-far`) the danger stickers shrink to 38 % (vs 62 % desktop)
and the deco camels hide entirely, so they don't bury the small map.
On mobile the bottom sheet is **resizable**: `.panel-handle` (hidden on
desktop by a base `display:none`) drags the `--map-h` custom property between
15 vh and 85 vh. It uses Pointer Events with pointer capture, so the gesture
survives the finger leaving the handle, and `map.invalidateSize()` is deferred
to the next animation frame instead of firing on every move.

The `.map-toolbar` overlays the map; there is deliberately no
Prévu/Réel/Comparer switch, **no legend and no status line** (they were removed
to give the small map back its room — the per-traveler details they carried now
live in the fiche). The **Trace affichée** picker replaces the former 720 px
button rail: the popover is a `.track-cars` two-column grid, one
`.track-car-col` per vehicle. **The vehicle chip is the column head**
(`.track-choice.car`, faint fill + hairline) and its crew follows — that
structure replaced four label rows that only repeated what it already says.
Observers are not in the picker: they are not a trace to follow, and their fiche
still opens from the panel. One `aria-selected` choice, closes on
selection/outside/Escape, styling in the stylesheet rather than inline.

Leaflet's `zoomControl` is **off**: zooming is the wheel, pinch and double-tap,
and the freed top-left corner goes to the picker. On **mobile** the picker
occupies that corner. Closed, it drops the "Trace affichée" eyebrow — the avatar
and the name already say it — and shrinks to a 30 px pill. Open, the crew wraps
to two ranks and the menu spans the width, so all eleven names stay readable
with no scrolling; its `max-height` is derived from `--map-h`, the same custom
property the panel handle drags, so **it can never spill past the map** (145 px
tall over a 323 px map at the default size, versus 390 px before). If the
`+/-` buttons ever come back, the toolbar margin and that `max-height` offset
both have to move down by the control's height.

**Both cars always draw their travelled track**, and the selected subject is
redrawn on top at full weight with its dashed future and pulsing marker.
Selecting promotes, it never hides: following one person used to erase the other
crew from the map entirely. `addActualPath(points, color, {quiet})` carries the
two treatments — `quiet` is a thin pale 3 px line with no halo, added first so it
sits underneath. Only the **dashed future** stays single-subject, so there is one
forecast on screen at a time. Everyone else is still a `faceCluster` marker.

Key JS structures (all near the top of the script):
- `DATA.records` — one entry per day: `{date, iso, checkpoint, location,
  cap1, cap2, car1:{Name:state}, car2:{...}}`; states: `present | unknown |
  tentative | absent`.
- `DATA.config` — the parsed `data/Config.csv`; editorial content normally
  comes from it (`CFG` in the JS), then `site-overrides.json` applies the
  repo-side trip config on top:
  `textes` (titre — site name in the header/tab, tagline, foot,
  open-route labels), `checkpoints` (display names), `etapes` → `LEG_META`, `rpg` →
  `RPG`, `rpgVoitures` → `CAR_RPG`, `danger` → `DANGER`, `deco` (decorative stickers), `couleurs`.
  Fallbacks are minimal — edit `data/Config.csv`, not the JS.
- `DATA.route` — polyline points `{lat,lng, cp?}` (Config `## route`);
  points with `cp` are checkpoints (SUISSE, MALAGA, ALGECIRAS, DAKHLA,
  DAKAR, CONAKRY, **FREETOWN**). `data/Config.csv` still carries the abandoned
  Abidjan/Accra/Lomé continuation; `terminus` in `site-overrides.json` cuts it
  after Conakry at build time.
- `LEGS` — derived legs between checkpoints (`s`/`e` = record indices,
  `ri0`/`ri1` = route indices; last leg is the open-ended stay at Freetown).
- `LEG_META` — per-leg theme emoji + difficulty 1-5 + label (◆ pips,
  color-coded green/amber/red via `DIFF_COLOR`, hex on purpose: reused as
  SVG stroke on the map where `var()` doesn't work).
- `RPG` — per-traveler `{xp, pv, skill, lien, tel, note}` (PV bar color
  thresholds ≥7 green, ≥4 amber, else red), from Config.csv's `## rpg`
  section (columns: nom, xp, pv, compétence, lien, téléphone, note).
  `lien` (optional URL) is NOT on the card any more — the card opens the
  fiche; the link lives there as the "Ouvrir le lien ↗" button.
- **Fiche aventurier** — clicking (tapping) any face chip REPLACES that
  person's car (or Observateurs) block in the panel with an in-place detail
  card (`ficheFor` state; `renderCar()`/`renderObs()` return `ficheHTML()`
  when the open name is in their roster — NOT a popup): big face, XP/PV/
  skill, embarkation/disembarkation + days aboard **derived from the
  presence grid** (`presenceOf()`, first/last present-or-tentative day;
  "route ouverte…" if still aboard at the end), plus Téléphone (`tel:` link)
  and Note rows when the sheet columns are filled, and a lien button.
  ✕ button or Escape closes (`closeFiche()`); the fiche survives day
  changes. On mobile `revealOpenFiche()` scrolls only `.panel-scroll` and
  aligns the card's top with the bottom sheet, so its title and ✕ never open
  clipped even when the card is taller than the viewport.
  Opening a fiche also selects that person in the map toolbar: their accepted
  GPS history and only their remaining planned presence range replace any
  previous subject. The chip click is captured (`capture:true`) so it beats the
  card's `<a>`; hover-zoom stays desktop-only sugar, the tap IS the mobile
  gesture.
- `OBS` — `CFG.observateurs` (Config.csv `## observateurs`, `nom` column): people
  following from home. Rendered ONCE into `#obs`/`.sec-obs` as a car-style
  box (🛰️, khaki accent) of seat cards with state `observer`; stats + lien
  come from their row in the `## rpg` section (Giordano).
- `CAR_RPG` — same for the cars + a `malus` line with their real-world
  afflictions (car 1 wheel bearings, car 2 holed exhaust −700 CHF).
- `DANGER` — Sahel danger zones `{lat, lng, img:'terroN', s:size_px, r:radius_m,
  t:label}`; drawn as red dashed circles + sticker `<img>` + label. Zones are
  real advisory geography (France Diplomatie / ACLED): NE-Mauritania military
  zone, east-Mauritanian axes, north & central Mali, Liptako-Gourma
  tri-border, east Burkina, Lake Chad. Stickers are ethnically matched to the
  dominant makeup of the region's armed groups (Arab-looking north,
  Black-looking Sahel/Lake Chad). Labels hide + stickers scale to 62 % below
  zoom 5 (`body.danger-far`, `dangerZoom()`). Includes the South-Bamako /
  Guinea-axis zone (JNIM pushed south-west in 2025 to isolate Bamako).
- `CFG.deco` — decorative stickers `{lat, lng, img:'chameauN', s}` (Config
  `## deco`): camels along the desert stretch, plain `<img>` markers reusing
  `.danger-img` (drop-shadow + danger-far scaling), no circle/label.
- `LIVE` — living portraits (name → `{src, w, l, t}`): MP4 loops in
  `photos/videos/` (relative paths, see that folder's CLAUDE.md). The `<video>`
  carries **`preload="none"`** — with `preload="metadata"` browsers pulled most
  of every visible clip on page load: 5.9 MB measured, 77 % of the whole page.
  Nothing is fetched until a hover or a fiche asks for it, and the static crop
  is already the designed fallback until `oncanplay` fires. The seat
  chip gets class `live`; delegated mouseover/mouseout toggle `.playing`
  (video plays inside the circle, replacing the hover-zoom img effect —
  the wrapper `.live-wrap` scales ×3.2 instead); the fiche face plays it
  continuously (autoplay muted loop). `oncanplay` adds `.vid-ok` so a
  missing/unloadable video falls back to the static photo.
- **Seat interaction** (`openFicheFor()`): clicking ANYWHERE on a seat card,
  including its portrait, opens that person's fiche in one click/tap. Desktop
  keeps its hover portrait/video preview under `@media (hover:hover)`; touch no
  longer needs the former two-tap `.preview` state.
- **Zoom-out on a face** (`faceMarkup()`, `liveZoom()`): hovering ANY face —
  seat chip or fiche portrait — enlarges it AND widens the framing. Live
  portraits widen their video's inline w/l/t (`liveZoom()`, head kept
  centered, clamped to the frame); static ones cross-fade to the `.f-wide`
  image from `PHOTOS.facesWide`. **Mobile has no hover**: tapping the
  fiche's portrait toggles `.wide`, which applies the same CSS — that's the
  touch equivalent (a chip tap is already taken: it opens the fiche).
- `PHOTOS` — `{faces:{Name:dataURI}, facesWide:{Name:dataURI}, cars:{1:…,2:…},
  terros:{terroN:…}, chameaux:{chameauN:…}}`. `facesWide` is the SAME crop
  1.9× wider (`WIDE` in make_faces.py): a chip is a pre-cropped JPEG, so
  without it there is nothing "around" to reveal on zoom.
  Faces render in seat chips (30 px circle, status-colored ring, hover zoom
  ×3.2 via `.seat-chip.photo:hover img`). The source bundle contains portraits
  for the original roster; a missing face falls back to the initial letter.
  `build.py` embeds only active roster/observer faces, so a generated portrait
  may remain in `photos.json` without keeping a removed traveler on the
  published site.
- **Odomètre** (`odoSet()`, `.odo*` CSS): the header's km stat is a mechanical
  counter — one 0-9 reel per digit in a `overflow:hidden` window, rolled by
  `transform: translateY(calc(-N * var(--oh)))` with a CSS transition, so
  scrubbing makes the digits spin. `--oh` (cell height) is the single source
  of truth. Reels are rebuilt only when the number's *shape* changes
  (digit count / separators), then roll in from 0. Gotcha: the digits are
  `<span>`s inside `.stat`, so ALL THREE classes (`.odo-d`, `.odo-r`,
  `.odo-sep`) must override `.stat span` (9.5px, muted) — forgetting the
  reel alone silently shrinks everything it contains.
- **The timeline drives the whole map** (`dayWindowEnd()`, `dayIsFuture()`,
  `stateAtDay()`): scrubbing is time travel. `render()` calls
  `renderHybridTracks()`, `refreshFaces()` and `refreshPhotos()`, and every one
  of them only keeps what was known by the **end of the selected local day**
  (the last record stays open-ended at `Infinity` so live points appear at
  once). `stateAtDay(realPoint, onPlan)` is the single rule for "where is this
  subject that day": past and present use the last accepted GPS point; a future
  day — or a day with no reality at all — falls back to the **planned**
  interpolated position and returns `planned:true`. That flag is what keeps the
  promise that the site never passes an invented position off as a real one:
  `.track-now.planned` / `.map-face.planned` draw a dashed outline, drop the
  pulse and say "position prévue" in `title`/`aria-label`, and the fiche adds a
  "Sur la carte" row. An observer is never placed on the route (`onPlan` false)
  because they are not travelling.
- Planning rendering in `render()`: the timeline is explicitly labelled
  **prévu**. There is **no leg polyline on the map**: the pale animated dashed
  line that used to highlight the selected leg read as a ghost third path next
  to the real track and the dashed future. The leg is identified by `leg-chip`
  (label/pips at its midpoint) and by its card in the Étapes list. Numbered `cp-badge`
  milestones stay neutral because two real cars may have different progress;
  name pills hide below zoom 5 via `body.danger-far`. The final selected
  planning leg still shows the editorial "open route" zone/label.
- The Étapes list is a horizontal scroll-snap slider (`.legs`), ‹ › buttons
  (`#legs-prev/next`), and `render()` auto-scrolls the active card into view.
  An Étape is always planned data: clicking one changes the planning timeline
  and fits that leg without hiding or modifying the selected hybrid trace.
- **Clicking the route** jumps the timeline: `routeHit` is an invisible
  22 px-wide polyline over the whole route whose click handler finds the
  record index whose `posAt()` position is closest (equirectangular metric)
  and calls `setIndex()`. The numbered `cp-badge` circles are clickable too
  (jump to that checkpoint's arrival day; the name pill stays click-through).
- **One hybrid map truth** (`renderHybridTracks()`, `vehicleStateAtDay()`):
  `plannedLayer` contains only editorial context (selected leg, neutral
  checkpoints, dangers/deco, clickable route and open-zone annotation).
  `actualTrackLayer` draws the focused subject's accepted GPS history as a
  solid coloured line plus the remaining planned suffix as a dashed line; with
  zero points the whole plan is dashed. **Both cars always get a marker** —
  the focused one pulses, the other stays `quiet` — so following one crew never
  hides where the other is. A car's marker comes from `vehicleGpsPoints()`
  only: a geolocated photo enriches the *line* but must never become the
  vehicle's current position.
  **Both cars' tracks are drawn here, always** (`{quiet:true}`), then the
  selected subject on top at full weight with its dashed future and pulsing
  marker. Everyone else — people *and* cars — is a `faceCluster` marker built
  by `refreshFaces()`, so cars get the same round avatar as travelers and the
  cluster's own fan-out handles overlaps. There is deliberately no vehicle
  shape and no bespoke spreading code: a car is one more character on the map.
  The single concession is `.wide-art`, which only changes `background-size`
  because a car cut-out is landscape (170×120) and 140 % would crop it to a
  patch of bodywork. `addActualMarker()` picks the round avatar from the
  presence of an image, not from the presence of a name.
  `addActualPath()` draws **only** the accepted points, joined in order: no
  road is invented from the itinerary to fill a gap in the data.
- **Every line follows real roads, past and future** (`ROUTES`, `routeKey()`,
  `roadPath()`, `roadTo()`, `trimRoad()`, `segmentLatLngs()`). `roadPath()`
  takes any list of positions and joins them along the driving geometry
  precomputed in `routes.json`, falling back to a straight line **per pair**
  when one is missing. It serves the travelled track *and* `addPlannedFuture()`.
  The key is `lat,lng;lat,lng` rounded to four decimals (~11 m) —
  `fetch_routes.py` must keep producing exactly that string. A planned range can
  end **between** two waypoints (a traveler's disembarkation day), so its last
  vertex is not a waypoint and has no entry: `roadTo()` then takes the full
  leg's geometry and `trimRoad()` cuts it at the right fraction, which removed a
  300 km straight line. Nothing is fetched at display time, so
  `voyage-afrique.html` still works from disk and offline.
- **The dashed future never draws a chord** (`predictedRoad()`,
  `nearestOnSegment()`). The pair "current position → next stop" is never in
  `routes.json` at its exact key: that key carries the live position, which
  changes with every GPS point, so the generator can only ever cache it for a
  position already left. The fix is not to compute a new route but to **reuse
  the one already routed** from an earlier position of the same drive: as long
  as the crew drives the shortest way — which is what the router picked too —
  that geometry passes within metres of them. Measured on Gal: **80 m** from a
  join computed an hour earlier, and 80 m again from one computed 200 km back.
  `predictedRoad()` therefore takes every cached join ending at the stop, finds
  the nearest point across their geometries, and resumes there.
  This is a **prediction drawn as dashes**: being a little stale does not matter,
  the next four-hourly run corrects it, whereas a chord is never a road at any
  moment. Do not add a proximity guard — an earlier `NEAR_ROAD_KM` version was
  removed, because it measured against `projectOnPlannedRoute()` and the
  editorial route is a coarse 23-waypoint polygon: Gal reads 128 km off it while
  sitting 80 m from the actual routed path, so the guard rejected precisely the
  case it was meant to serve. With no cached join at all, the tail falls back to
  the planned itinerary from the projection — cached roads again, still no
  chord. Verified on live data: 217 km of road drawn where the chord was 161 km,
  starting 75 m from the marker; a fresh routing of the same segment returns
  239 km, so a reused prediction runs about 9 % off — well inside what a dashed
  forecast is for.
  `addPlannedFuture()` **always** begins the dashed tail at the most recent GPS
  point (`tail.unshift`) and interpolates straight to the **next stop**
  (`nextStopKm()`, a checkpoint), then follows the route to the end of the
  subject's range. Two rules, each fixing a real artefact:
  - the continuity is unconditional (an earlier version drew a thin connector
    only within 50 km of the plan, leaving a far-off subject's marker floating
    with no path at all);
  - with a real point, the resume is that point's own progress, **never**
    `startKm` (the planned-range start). Bounding by `startKm` teleported the
    line to a traveler's theoretical embarkation — 159 km of straight line laid
    over the itinerary for someone already standing on it;
  - the resume is the next *stop*, not the perpendicular foot, otherwise an
    off-route subject drew a spur out to the road and then doubled back.
  Without any real point the tail starts exactly at `startKm`, so a traveler who
  has sent nothing still shows their planned leg from their embarkation.
  The tail must not start from the *planned* progress of the displayed day —
  that erases a stretch nobody has driven yet and opens a hole on every future
  day.
  `projectOnPlannedRoute()` uses local equirectangular projection plus
  cumulative-distance tie-breaking to find that suffix. The join from the real
  point to the plan is unconditional and part of the dashed line itself — there
  is no separate connector and no distance cutoff, so a subject far off the plan
  is still visibly heading somewhere. Route data is sparse, so the off-itinerary
  warning starts at 150 km and is reported in the fiche ("Écart au plan"),
  the toolbar status line being gone. Only the selected subject draws a future,
  so there is one dashed line at a time. `actualTrackPane` and
  `actualMarkerPane` keep hybrid lines and current markers above context.
- **Subject filters** (`trackSubject`, `setTrackSubject()`, default
  `vehicle:hugodouard` — there is no "Convoi" subject any more): a vehicle
  button renders that derived vehicle hybrid; a person button renders only that
  person's own accepted points plus the remaining part of their planned
  presence range. `plannedRangeForVehicle()` is the union of its roster's
  ranges (`VEHICLES[id].roster`) — the 03/08 pass looked the car's *name* up as
  a person, always found nothing, and silently deleted both cars' dashed
  future. Person buttons come from each vehicle's own roster; observers are not
  in the picker (they are not a trace to follow) but their fiche still opens
  from the panel. The picker uses native buttons, focus styles and listbox
  semantics. Choosing a different picker subject closes any stale fiche;
  opening a fiche selects the matching person.
- **Actual route model** (`TRIP_ID = "africa-trip-01"`): stable person ids are
  normalized to active display names by `slug()`/`NAME_BY_ID`; coordinates are
  rejected before number coercion when null, blank, non-finite or outside
  latitude/longitude bounds. `MAX_ACCURACY_M = 250` is shared by current
  markers and track points. `normalisePoint()` accepts Firestore Timestamp,
  ISO string or millisecond values and tolerates `trackChunks.points` as either
  the current idempotent map `{pointId: point}` or an older array. A point keeps
  its own `personId`, `vehicleId`, `mode`, time, coordinates, accuracy and
  source. `allTrackPoints()` merges v2 chunks/latest, v1 personal tracks and
  `mediaTrackPoint()` anchors. There is **no departure-date gate**: media and
  points from before the first trip day count — there is no global departure
  constant, only the per-person `track_start`. Only
  media with embedded GPS (`gps`/`media-gps`) qualify; manual pins and
  planned+jittered Drive positions do not. **Each person's points count only
  from their own `track_start`** (`trackStartFor()`, `beforeOwnStart()`, fed by
  `site-overrides.json`): everything older is a pre-trip leftover. That is the
  only date gate — there is no global departure constant. A point with no captured vehicle
  falls back to `rosterVehicleId(name)` — the roster car — because the app
  writes `car:"obs"` both for “À pied / autre” and as its own default, so crew
  photos were landing outside their own vehicle. Near-duplicates are coalesced
  without losing an explicit vehicle assignment.
- **Nobody sits in a car before they get in** (`momentOfDay()`, `joinedBy()`).
  The reference instant of a displayed day is the **end** of that day, except
  today where it is now: a past or future day is judged whole (the dashed
  future keeps its full crew) while the current day stops at the clock.
  `joinedBy()` compares it to `trackStartFor()`, and gates `onboardAt()`,
  `renderCar()`'s seats and `aboardVehicleAt()`. `renderCar()` recounts the
  `X/4` header from the seats really shown, since the grid's own figure would
  contradict the faces beside it. `presenceOf()` and `plannedRangeForPerson()`
  are deliberately NOT gated: they describe the whole trip window, and clipping
  them at "now" would truncate the planned future.
- **Occupants share their car's track** (`personTrack()`, `aboardVehicleAt()`):
  people riding together describe the *same* movement, so one phone's points
  serve everyone aboard. `personPoints(name)` is the car's **derived** track
  (one observation per minute, chosen among all occupants) for the periods the
  person is aboard, plus their own points outside those periods — deduplicated
  by 60-second bucket so two near-simultaneous readings never stack. Dorvan goes
  from a single point to his car's full nine.
  Two guards keep it honest: `aboardVehicleAt()` reads the **presence grid** for
  days inside the calendar (falling back to the roster only outside it), so
  nobody inherits a car they are not in; and an inherited point must still be
  later than the inheriting person's own `track_start`, otherwise Paul's track
  would start on 30 July through Jehan's photos.
  `vehiclePoints(vehicleId)` gathers only
  points whose captured mode is `vehicle` and whose captured `vehicleId`
  matches, buckets them into 60-second windows, then chooses one observation
  using GPS accuracy plus median distance to the other occupants' observations.
  `impossibleTransition()` rejects any jump farther than a 220 km/h travel
  allowance plus a 120 m anti-jitter floor or 1.5× the two GPS accuracy radii.
  Thus a sub-2 km teleport over a few seconds is caught without cutting two
  noisy neighbouring fixes. A time gap alone no longer cuts the route: sparse
  plausible fixes hours apart remain joined. A short impossible jump is
  discarded; after six hours an impossible jump starts a separate section.
  Old Android media placed artificially at noon are evaluated with day-level
  time uncertainty. `vehicleGpsPoints()`/`personGpsPoints()` remain separate
  from media anchors so current markers never jump to an old photo. Caches are
  also invalidated by v1-track and media snapshots.
- **Two focus modes** (`focusTrackSubject(mode)`, `subjectFocusData()`):
  choosing a subject — from the picker or by opening a fiche in the panel —
  uses mode `'route'` and frames that subject's **whole planned trace** (its
  range plus its current position, so the marker never falls off-screen when it
  is far from the plan). Selecting someone is for seeing their journey, not for
  gluing the map to their position of the day. Mode `'point'` flies to them at
  a stable zoom 13 (vehicle 11), offset to the visible map area below the
  toolbar, and is reserved for **clicking their head on the map**. The previous
  zoom can no longer leave the next person stuck at zoom 18. `openFicheFor()`
  takes the mode as its second argument. A
  usable current point is chosen from accepted GPS evidence and the legacy
  position fallback, never from a media anchor;
  points worse than 250 m or a short impossible latest jump are not used for the
  marker/zoom. The fiche reads the **same day window as the map** so the two can
  never disagree: it prints coordinates/age from that reliable point, adds
  `Sur la carte` when the shown position is planned, `Écart au plan` beyond
  150 km, and a `Dernier fix écarté` row for a rejected latest — that last row
  only at the present, since a rejected "latest" is meaningless in the past.
  If only one old v1 position exists the
  site shows a position without inventing a historical line; with no GPS at all
  the planned fiche remains and says explicitly that no point was received.
  The wording is historical (`Au dernier point GPS`), because a pause or
  assignment change after that fix cannot be inferred from map data. Elements
  with `data-live-at` are refreshed every 30 seconds by one visibility-aware
  timer, stopped on `pagehide`, so ages continue changing without a snapshot or
  timer leak.
- **The gallery browses one pile at a time.** A photo marker opens the lightbox
  on that single photo (no arrows); a **pile** opens it on that pile's photos,
  in chronological order, and the arrows stay inside that subset.
  `photoCluster` therefore sets `zoomToBoundsOnClick:false` and
  `spiderfyOnMaxZoom:false` — clicking a pile must show the series it depicts,
  not do something else — and each marker carries its `galleryIndex`
  (`pileIndices()`). `openLightbox()` refuses an empty list and `lbStep()` is a
  no-op below two items, so a pile that yields no index cannot open a blank
  viewer.
- `GALLERY` starts with shared Drive/build media `[{id, name, date, lat, lng,
  gps, thumb, file}]` from `fetch_photos.py`. **`photoVisible()` filters on the
  timeline only** — a medium shows once the displayed day has reached it. The
  gallery belongs to the trip, not to the selected subject: changing trace must
  never make photos disappear from the map, so there is deliberately no
  per-subject media filtering. `refreshPhotos()` renders the allowed
  indices into `photoCluster`; the `#lightbox` it opens is scoped to one pile
  (see above). **The viewer is served a display-sized version, never the
  original** (`mediaDisplay()`: `w_1400,c_limit,q_auto,f_auto` for images,
  `q_auto,w_1280,c_limit` for videos), falling back to the original then the
  thumbnail. Measured on the trip's real media: −80 to −90 % on images, −50 to
  −78 % on videos, for no visible difference — opening one photo used to pull
  5 MB. Only Cloudinary URLs are rewritten; Drive photos served by Pages keep
  their path. Image/video support,
  captions, date, location provenance and thumbnail fallback. Firebase v2
  media remain in the existing root `photos` collection for compatibility but
  carry `tripId`, `personId`, `vehicleIdAtCapture`, `mode`, `assignmentId`,
  `capturedAt` and `locationSource`. Only documents for this trip with a known
  active person become `_v2` actual media. Attributable legacy root photos from
  the trip period may also appear under their person/car; anonymous embedded
  Drive files remain convoy-only. A GPS media point may bend the chronological
  actual line, while manual/estimated positions remain markers only. Media
  without valid coordinates are omitted until their location is added.
- **Live Firebase listeners** (dynamic import at the end of the classic
  script):

  - `trips/africa-trip-01/latest/{personId}` contains the latest v2 Point plus
    `schemaVersion`; the snapshot is rebuilt from scratch so deletions cannot
    leave a stale current head.
  - `trips/africa-trip-01/trackChunks/{chunkId}` contains
    `{schemaVersion, tripId, personId, displayName, sessionId, deviceId,
    bucketStartAt, bucketStartMs, points}`. `docChanges()` updates
    `trackChunkDocs` incrementally (`removed` deletes the cached chunk); a full
    snapshot fallback exists for non-standard clients.
  - root `positions` is a read-only **legacy fallback** with no trip/vehicle
    scope. It supplies at most a last-position marker when no usable v2/latest
    personal point exists; it must never be treated as a car assignment or
    historical trace. Removed roster names are ignored.
  - each active roster member's `tracks/{name}/points` v1 subcollection is read
    live, with no date filter. Its `{lat,lng,at}` points carry no car, so they
    take that person's roster vehicle.
  - root `photos` is rebuilt on each media snapshot after preserving the
    build-time `GALLERY` prefix, which also handles deleted Firebase media.
  - root `crew` remains the live PV source: numeric `pv` overwrites the CSV
    value in `RPG` and rerenders seats/fiches.

  Every listener ends on `refreshLiveLayers()`, which simply redraws the map
  layers (or delegates to `render()` when a fiche is open, so the layers are not
  rebuilt twice). There is deliberately **no `livePositions` cache**: positions
  are derived on demand from the accepted points through `currentForPerson()`,
  so a cache can never disagree with the day window the timeline selected.
  `refreshFaces()` places every roster member on the trip that day — real point
  if there is one, planned position otherwise — plus every non-selected vehicle,
  which is why `photoCluster` and `faceCluster` remain independent
  `Leaflet.markercluster` groups.
  `pileHTML()` draws up to three real
  thumbnails/faces in a fan plus a small count, with photos anchored below and
  faces above the same coordinate. Faces are still restricted to current
  car/observer rosters, so stale data cannot resurrect a removed traveler.
  Firebase access is read-only from this site, uses the public config for
  project `africatrip-eea1a`, fails quietly offline, and requires HTTPS/the app
  because `file://` blocks the dynamic module import.

### `build.py`
Reads `template.html` + `data.json` + `photos.json` + `gallery.json`,
writes the two root HTML files. Before injection it filters `faces` et
`facesWide` to the active `car1` + `car2` + observer names from `data.json`,
so retired portraits are not embedded. Run after ANY change to template or
JSON.

### `site-overrides.json`
The committed repo-side trip config. `trip_year: 2026` is the confirmed year and
drives every generated ISO date plus a recomputation of the French weekday
token; `textes.titre`/`textes.tagline` pin both header strings so a future CSV
edit cannot recreate a year mismatch. `removed_travelers` removes names from
the parsed rosters — it means "no longer in a car", **not** "erased". A removed
name listed in Config.csv's `## observateurs` **keeps its `rpg` row**: someone
who steps off the trip may still follow it from home, and the observer card
reads its stats from that very section, so dropping the row would empty the card
of everything already known about them (Thomas: 42 XP, "Apparition surprise +1",
portrait re-embedded by `build.py` because observers are in its face whitelist).
Only a name removed *and* absent from the observers list loses its RPG row.
When a removed name still has a raw presence column,
`parse_csv.py` recomputes both `X/4` capacities and the total from confirmed
`present` states. `phones` replaces `config.rpg[name].tel` while preserving the
human-readable `+CC …` formatting used by the fiche and its sanitized `tel:`
link. `track_start` `{default, by_person}` sets, per person, the instant they join
the trip: their GPS points and photos build their route from it, and they are
not shown aboard a car before it either. Values are `YYYY-MM-DD`, or
`YYYY-MM-DDTHH:MM` for someone who meets the convoy at a stop instead of
travelling from dawn — the presence grid only knows whole days, so without the
hour they would be seated hundreds of kilometres before getting in. One
mechanism gates both the track and the seat, deliberately: an arrival is then
corrected in exactly one place. Current value: everyone from 2026-08-02, Jehan
and Dorvan from 2026-07-30, Hugo and Paul from 2026-08-07T14:00 (they join at
Malaga in the afternoon).
`terminus` `{after, cp, label, lat, lng}` shortens the plan to a single
confirmed final checkpoint: `apply_terminus()` cuts the route right after the
`after` checkpoint, appends the terminus waypoint, drops the abandoned
checkpoint labels, clears the abandoned arrival cells and makes the last day the
terminus arrival, then **recomputes the carried-forward `location`** so the days
in between still read the last checkpoint actually reached. The cut is derived
from the `after` arrival record — no date is hardcoded. Current override removes
Thomas, defines the eight requested numbers and ends the trip at **Freetown**
after Conakry (`data/Config.csv` still describes the old Abidjan/Accra/Lomé
continuation, inherited from the original export).

### `parse_csv.py`
`data/AfriqueCalendrier_-_Presences_Voyage.csv` (+ `data/Config.csv`, the
Config tab: `read_config()` parses its `## section` blocks) → `data.json`.
`read_site_overrides()` applies `site-overrides.json` last, after the CSV
config and before records are emitted, so the inherited 2025 year/tagline, the
removed traveler, a stale phone number or the abandoned Abidjan/Accra/Lomé
continuation cannot come back
(`apply_terminus()`, `cp_norm()` compares checkpoints the way the front-end's
`norm()` does, so a decorated cell like `ALGECIRAS⛴️` still matches).
`parse_date()` parses the day/month from the raw cell, creates an
ISO date with `trip_year`, and replaces the raw weekday with the correct French
weekday for that year while preserving the cell's month spelling/punctuation.
The `ROUTE`/`CAR_COLORS` constants are only fallbacks for a missing
Config.csv. Rerun it (then `build.py`) whenever you edit `data/*.csv` or
`site-overrides.json` — that is now the normal way to change the trip.

### `refresh.py` — legacy import, OUTSIDE the build
The Google Sheet is no longer the reference: `data/*.csv` are. This script only
re-imports from a sheet (presence grid + Config tab `CONFIG_GID`) and
**overwrites both CSVs**, so it refuses to run without `--from-sheet`. It then
runs parse_csv + build in-process. Stdlib only. Do not wire it back into
`sync.py`: a double-click must never revert the repo's data to an abandoned
sheet.

### `sheet_edit.py` — legacy, OUTSIDE the build
Kept for a one-off migration only; writing to the sheet no longer affects the
site. CLI to read and **write** a Google Sheet (`tabs`, `get "A1:E5"`,
`set "B3" value…`, `setrows "A10:C12" rows.json`, `clear "Z100"`; A1 ranges,
optional `Tab!` prefix, first tab by default). Auth is a Google Cloud
service account: JSON key in the git-ignored `.sheet-credentials.json` at
the repo root, sheet shared with the service-account email as Editor
(one-time setup steps in the docstring). Sheet ID comes from `.sheet-url`
like `refresh.py`. Writing to a sheet no longer affects the site: the trip
data is `data/*.csv` in this repo.

### `fetch_routes.py`
Precomputes the road geometry of every pair the map may join into
`routes.json`, injected as
`__ROUTES__`. Reads Firestore through its **public REST API** with the
`projectId`/`apiKey` taken from `app/www/firebase-config.js` (single source, no
extra credential, stdlib only), then asks OSRM for each pair.

It generates three families of pairs: consecutive GPS points per person and per
vehicle (the travelled track), consecutive waypoints of `data.json`'s `route`
(the dashed future — static, straight from `data/Config.csv`), and each
subject's latest position joined to the `JOIN_STOPS` stops ahead of it, which is
the pair the future line starts with.

It deliberately does **not** reimplement the front-end's reconstruction
(minute bucketing, impossible-transition rejection, roster fallback, shared
occupant tracks): duplicating that in Python would rot on the next template
change. It groups the raw points coarsely — per person and per vehicle,
chronologically — and routes every pair within `PAIR_WINDOW` (3), which covers
the pairs the site actually draws once it has dropped some points. Coverage is
measurable: walk the drawn segments in the browser and count the pairs
`roadTo()` resolves — currently **25/25 on the travelled track and 83/83 on the
future**.

It is run automatically by `.github/workflows/routes.yml` every four hours,
because the cache goes stale by design: each new GPS point adds a pair it does
not know, and that segment reverts to a straight line. Coverage was measured
falling from 100 % to 58 % in a few hours of travel. Do not rely on a human
remembering to run it.

**Geometry is fetched at `overview=full` then simplified locally**
(`simplify()`, Douglas-Peucker, `SIMPLIFY_KM = 0.2`). OSRM's own `simplified`
overview thins in proportion to route length, so a 900 km leg came back as 59
points that cut 77 km straight across country. The local pass keeps the stored
line within a fixed tolerance instead: measured on Montpellier → Barcelona, 126
points whose worst deviation from the true road is **196 m** (55 m average).
Long straight sub-segments remain — 24 km on the A62 near Toulouse — and that is
correct: the road there really is straight, and the tolerance bounds the error,
not the segment length. Cost of the whole cache: 84 KB → 233 KB, published page
532 KB → 671 KB. The DP pass is **iterative on purpose**: a raw geometry holds
thousands of points and the recursive form blows Python's stack.
`SIMPLIFY_KM` only affects pairs fetched from then on — **delete `routes.json`**
to re-cut the existing ones, as was done when this landed.

Guards: pairs under 1 km keep the straight line, pairs over 1500 km are not a
continuous drive, and a route more than 4× the great-circle distance is treated
as an aberration (a detour around a sea, a point landing on an island) and
dropped. Pairs whose points have disappeared are pruned from the cache. Ferries
are covered — Algeciras → Tanger Med resolves to the 23 km crossing.

### `fetch_photos.py`
Syncs the shared Drive photo folder onto the map (`--dry-run` to preview).
Folder URL/ID in the git-ignored `.drive-folder` (same pattern as
`.sheet-url`); auth reuses `sheet_edit.load_key()`/`access_token()` with the
`drive.readonly` scope. The core is `process_image(im, entry_id, name, …)`:
dates it (EXIF `DateTimeOriginal` → Drive `imageMediaMetadata.time` →
`createdTime`), locates it (EXIF GPS → Drive location → **convoy position on
that date**: `convoy_position()` is a Python port of the template's
`posAt()`/`legOf()` interpolation, plus a deterministic ±0.12° `jitter()`
seeded by `entry_id`), then writes `photos/uploads/<safe>.jpg` (max 1600 px)
+ a 96 px square thumb as data URI into `src/gallery.json`, and reruns
`build.py`. Two input kinds (`list_files` returns both):
- **direct images** — `entry_id` = the Drive file id (incremental via ids
  already in `gallery.json`);
- **`.zip` files** — `process_zip` extracts each member and processes it
  with `entry_id = '<zip id>__<inner name>'`. Why zips at all: **since April
  2026 Android strips EXIF GPS on almost every share/upload path, but a
  photo inside a zip is shielded** (the OS filter is image-extension based).
  So the friend-facing instruction (see root `COMMENT-UPLOADER.md`) is
  "select photos → Compress → drop the .zip in Drive", and this keeps the
  real GPS. A zip is downloaded once then never again (its members' ids
  carry its `<zipid>__` prefix, so `done_zips` skips it). HEIC (iPhone
  default) works if `pillow-heif` is installed; else HEIC members are
  skipped. Setup: share the folder with the service account as Viewer.

### `sync.py`
The user-facing one-shot updater (`python src/sync.py`, or `sync.bat` at the
root for double-click): parse_csv.py → fetch_routes.py (non-blocking) →
build.py → fetch_photos.py → `git add` of an
explicit whitelist of pipeline inputs/outputs, including
`site-overrides.json` (never `photos/gal.enc`) → commit → push. Exits
without committing when nothing changed.

### `make_faces.py`
Produces `photos.json` + the generated image folders. **The source images
were removed from the working tree** (outputs are committed); the script
exits with restore instructions (`git checkout 20d79de -- photos/`) if they
are missing — see `photos/CLAUDE.md`. Three parts:
1. **Faces**: hand-tuned square crops via the `CROPS` dict (cx, cy, size as
   fractions; tweak these to reframe someone) → `photos/faces/<name>.jpg`,
   128 px. Several names can share one source file: `mugshots.jpeg` carries
   Edouard, Younous and Giordano (3 prison mugshots, left to right).
2. **Cars**: `cut_car()` crops the two cars out of `photos/voitures.jpg`
   (boxes in `CAR_BOXES`) and removes the FAKE painted checkerboard
   background by flood-filling light unsaturated pixels from the borders.
3. **Stickers**: `cut_stickers()` splits sticker sheets into individual RGBA
   stickers: background mask (`outside_mask`) → connected-component labeling
   on a 2× downscale (pure-python BFS, no scipy) → per-blob crop. Two sheets:
   `photos/terros.jpg` (grey fake-checkerboard bg) and `photos/chameaux.jpg`
   (plain white bg → `bg="white"` mask, `rows=4` ordering bands, quantized
   to 64-colour palette PNGs).

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
  next to a sticker (currently terro7 and terro9). (A `defringe()` halo-peeler
  used to live here; it became unreachable once the white outlines were
  preserved, and was deleted — see git history if a sheet ever needs it.)

### `data.json` / `photos.json` / `gallery.json` / `routes.json`
Generated. Never edit by hand; regenerate with the scripts above. All are
committed so a rebuild doesn't depend on the private sheet or Drive.
To remove a photo permanently, delete it from the Drive folder AND from
`gallery.json` + `photos/uploads/` (a sync re-adds any Drive file whose id
is missing from `gallery.json`).
