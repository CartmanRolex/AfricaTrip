# data/ — trip data snapshot

> Rule: update this file in the same commit as any feature change here.

`AfriqueCalendrier_-_Presences_Voyage.csv` and `Config.csv` are **downloaded
snapshots** of two tabs of the live Google Sheet "🌍 Voyage en Afrique —
Calendrier des Présences & Véhicules". Do not edit them by hand — they get
overwritten by `python src/refresh.py` (sheet link lives in the git-ignored
`.sheet-url` at the repo root). The sheet is writable via `src/sheet_edit.py`
(service-account key in the git-ignored `.sheet-credentials.json`).

`Config.csv` (tab "Config", gid hardcoded in `refresh.py`) carries all
editorial content as `## section` blocks (marker row, header row, data rows):
`textes`, `checkpoints`, `route`, `couleurs`, `etapes`, `rpg`,
`rpg_voitures`, `danger`. Parsed by `read_config()` in `src/parse_csv.py`
into `data.json` as `config`; edit the sheet, then rerun `refresh.py`.

Raw Sheet snapshot shape (then transformed by `src/parse_csv.py`):
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

If the sheet's structure changes (new traveler, new column layout), fix
`src/parse_csv.py` accordingly and document it in `src/CLAUDE.md`.

The raw public Sheet snapshot still contains the former 2025 calendar text,
Thomas and its old capacity formulas. The published result deliberately applies
`src/site-overrides.json` after reading these files: dates/weekdays/tagline are
pinned to the confirmed 2026 trip, Thomas is removed from `car2`/RPG,
capacities and totals are recomputed, and car 2's renderer fills the fourth slot
with **Place disponible**. The same override supplies formatted phone numbers.
This post-Sheet layer is necessary until Sheet write credentials are installed;
do not "fix" the generated `src/data.json` by editing these snapshots manually.
