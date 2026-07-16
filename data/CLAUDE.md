# data/ — trip data snapshot

> Rule: update this file in the same commit as any feature change here.

`AfriqueCalendrier_-_Presences_Voyage.csv` is a **downloaded snapshot** of
the live Google Sheet "🌍 Voyage en Afrique — Calendrier des Présences &
Véhicules". Do not edit it by hand — it gets overwritten by
`python src/refresh.py` (sheet link lives in the git-ignored `.sheet-url`
at the repo root; the sheet is read-only for us via its public CSV export).

Shape (parsed by `src/parse_csv.py` into `src/data.json`):
- Decorative title/period rows at the top, then a header row with dates.
- One column per day (Aug 1 → Sep 30, 2025), one row per traveler, grouped
  in two car blocks (car 1 "HUGODOUARD": Gal, Hugo, Malen, Arthur, Edouard,
  Younous; car 2 "PAUL POT": Paul, Thomas, Jehan, Dorvan).
- Cell values encode presence: present / unknown ("?") / tentative /
  absent; checkpoint rows mark where the convoy is (SUISSE, MALAGA,
  ALGECIRAS⛴️, DAKHLA, DAKAR).

If the sheet's structure changes (new traveler, new column layout), fix
`src/parse_csv.py` accordingly and document it in `src/CLAUDE.md`.
