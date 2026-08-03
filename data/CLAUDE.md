# data/ — the trip data

> Rule: update this file in the same commit as any feature change here.

`AfriqueCalendrier_-_Presences_Voyage.csv` and `Config.csv` are **the trip
data**. They started life as exports of the Google Sheet "🌍 Voyage en Afrique
— Calendrier des Présences & Véhicules", but that sheet is **no longer the
reference**: these committed files are, and you edit them here.

Edit them by hand, then rebuild:

```bash
python src/parse_csv.py && python src/build.py
```

Nothing in the build downloads anything any more. `src/refresh.py --from-sheet`
still exists to re-import from a sheet, but it **overwrites both files** and
refuses to run without that explicit flag — precisely so a habit (or
`sync.py`) can never silently revert hand edits.

`Config.csv` carries all editorial content as `## section` blocks (marker row,
header row, data rows): `textes`, `checkpoints`, `route`, `couleurs`, `etapes`,
`rpg`, `rpg_voitures`, `danger`. Parsed by `read_config()` in
`src/parse_csv.py` into `data.json` as `config`. Adding a row (a new waypoint, a
new danger zone) is just adding a line here. Unknown sections pass through
untouched.

File shape (then transformed by `src/parse_csv.py`):
- Decorative title/period rows at the top, then a header row with dates.
- One row per day (Aug 2 → Sep 30; the raw snapshot still says 2025 but the
  confirmed `trip_year: 2026` override recomputes ISO dates and weekdays), one
  column per traveler, grouped
  in two car blocks (car 1 "HUGODOUARD": Gal, Hugo, Malen, Arthur, Edouard,
  Younous; car 2 "PAUL POT": Paul, Thomas, Jehan, Dorvan).
- Cell values encode presence: present / unknown ("?") / tentative /
  absent; the Localisation column marks arrival days at checkpoints
  (SUISSE, MALAGA, ALGECIRAS⛴️, DAKHLA, DAKAR, then the invented
  continuation CONAKRY, ABIDJAN, ACCRA, LOMÉ — all within September).
  **The published trip stops at Conakry then FREETOWN**: these CSVs still
  carry the old Abidjan/Accra/Lomé continuation, and `terminus` in
  `src/site-overrides.json` cuts it after Conakry at build time. Editing the
  CSVs directly and dropping that override would work too — the override is
  kept because it documents the decision in one readable place.

If the grid structure changes (new traveler, new column layout), the parser
detects the layout dynamically; if something no longer fits, fix
`src/parse_csv.py` and document it in `src/CLAUDE.md`.

These files still carry the former 2025 calendar text, Thomas, the old capacity
formulas and the Abidjan/Accra/Lomé continuation, inherited from the original
export. `src/site-overrides.json` is applied after they are read:
dates/weekdays/tagline are pinned to the confirmed 2026 trip, Thomas is removed
from `car2`/RPG, capacities and totals are recomputed, car 2's renderer fills the
fourth slot with **Place disponible**, the trip ends at Freetown, and the
formatted phone numbers are supplied. Correct either layer — but never "fix" the
generated `src/data.json`, it is overwritten on every build.
