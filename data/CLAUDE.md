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

Shape (parsed by `src/parse_csv.py` into `src/data.json`):
- Decorative title/period rows at the top, then a header row with dates.
- One row per day (Aug 1 → Sep 30, 2025), one column per traveler, grouped
  in two car blocks (car 1 "HUGODOUARD": Gal, Hugo, Malen, Arthur, Edouard,
  Younous; car 2 "PAUL POT": Paul, Thomas, Jehan, Dorvan).
- Cell values encode presence: present / unknown ("?") / tentative /
  absent; the Localisation column marks arrival days at checkpoints
  (SUISSE, MALAGA, ALGECIRAS⛴️, DAKHLA, DAKAR, then the invented
  continuation CONAKRY, ABIDJAN, ACCRA, LOMÉ — all within September).

If the sheet's structure changes (new traveler, new column layout), fix
`src/parse_csv.py` accordingly and document it in `src/CLAUDE.md`.
