"""
Parse the raw Google-Sheets export (presence calendar) into data.json.

Usage:  python src/parse_csv.py
Reads:  data/AfriqueCalendrier_-_Presences_Voyage.csv
Writes: src/data.json

The CSV is a presence grid. Two cars, one column block each, separated by a
"Capacité" column, plus a "Localisation / Checkpoint" column that is only
filled on arrival days (the location carries forward until the next checkpoint).

The layout is detected dynamically (header row, car-name row, roster columns,
data rows) so the parser keeps working when people are added/removed or rows
shift around — which matters because `refresh.py` re-pulls the live sheet.

Everything "configurable" (route waypoints, checkpoint labels, leg themes,
RPG stats, danger zones, UI texts, car colours) lives in the sheet's Config
tab, exported by refresh.py to data/Config.csv and embedded into data.json as
`config`. The ROUTE/CAR_COLORS constants below are only fallbacks for when
that file is missing.
"""
import csv, json, os, re

HERE = os.path.dirname(__file__)
CSV = os.path.join(HERE, "..", "data", "AfriqueCalendrier_-_Presences_Voyage.csv")
CONFIG_CSV = os.path.join(HERE, "..", "data", "Config.csv")
OUT = os.path.join(HERE, "data.json")

YEAR = 2025
MONTH = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5,
         "juin": 6, "juil": 7, "août": 8, "aout": 8, "sept": 9, "oct": 10,
         "nov": 11, "déc": 12, "dec": 12}

# Route waypoints. Only the entries with "cp" are official checkpoints matched
# against the sheet's Localisation column; the rest are intermediate points so
# the drawn line follows roads and the coast instead of cutting across the
# sea/desert. Edit freely — these are geography, not data from the sheet.
ROUTE = [
    {"name": "Genève",     "lat": 46.204, "lng":   6.143, "cp": "SUISSE"},
    {"name": "Montpellier","lat": 43.611, "lng":   3.877},
    {"name": "Barcelona",  "lat": 41.390, "lng":   2.170},
    {"name": "Valencia",   "lat": 39.470, "lng":  -0.376},
    {"name": "Granada",    "lat": 37.177, "lng":  -3.598},
    {"name": "Málaga",     "lat": 36.721, "lng":  -4.421, "cp": "MALAGA"},
    {"name": "Algeciras",  "lat": 36.130, "lng":  -5.453, "cp": "ALGECIRAS"},
    {"name": "Tanger Med", "lat": 35.885, "lng":  -5.510, "ferry": True},
    {"name": "Rabat",      "lat": 34.020, "lng":  -6.841},
    {"name": "Casablanca", "lat": 33.573, "lng":  -7.590},
    {"name": "Agadir",     "lat": 30.421, "lng":  -9.598},
    {"name": "Tan-Tan",    "lat": 28.438, "lng": -11.103},
    {"name": "Laâyoune",   "lat": 27.150, "lng": -13.203},
    {"name": "Dakhla",     "lat": 23.685, "lng": -15.957, "cp": "DAKHLA"},
    {"name": "Nouadhibou", "lat": 20.933, "lng": -17.040},
    {"name": "Nouakchott", "lat": 18.079, "lng": -15.978},
    {"name": "Dakar",      "lat": 14.693, "lng": -17.447, "cp": "DAKAR"},
]

# Per-car display colours (not in the sheet), applied in column order.
CAR_COLORS = ["#E8924A", "#4FB7B3", "#C77DC0", "#7E9CD8"]

SYMBOL = {"●": "present", "?": "unknown", "○": "tentative", "": "absent"}


def read_config():
    """Parse data/Config.csv (the sheet's Config tab) into a structured dict.

    The tab is a stack of sections: a `## name` marker row, a header row, then
    data rows until a blank row or the next marker. Unknown sections pass
    through as raw lists of dicts so new ones can be added sheet-side first.
    """
    try:
        with open(CONFIG_CSV, encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        return {}

    sections, name, header = {}, None, None
    for r in rows:
        first = (r[0] if r else "").strip()
        if first.startswith("## "):
            name, header = first[3:].strip(), None
            sections[name] = []
        elif name and header is None:
            if first:
                header = [c.strip() for c in r]
        elif name and first:
            sections[name].append({h: (r[i].strip() if i < len(r) else "")
                                   for i, h in enumerate(header) if h})
        elif not first:
            name, header = None, None  # blank row closes the section

    def num(v, cast=float, default=0):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default

    cfg = {}
    cfg["textes"] = {r["clé"]: r["valeur"] for r in sections.get("textes", [])}
    cfg["checkpoints"] = {r["cp"]: r["label"] for r in sections.get("checkpoints", [])}
    cfg["route"] = []
    for r in sections.get("route", []):
        pt = {"name": r["nom"], "lat": num(r["lat"]), "lng": num(r["lng"])}
        if r.get("cp"):
            pt["cp"] = r["cp"]
        if r.get("ferry"):
            pt["ferry"] = True
        cfg["route"].append(pt)
    cfg["couleurs"] = {r["voiture"]: r["couleur"] for r in sections.get("couleurs", [])}
    cfg["etapes"] = [{"emoji": r["emoji"], "diff": num(r["difficulté"], int, 3),
                      "lbl": r["label"]} for r in sections.get("etapes", [])]
    cfg["rpg"] = {r["nom"]: {"xp": num(r["xp"], int), "pv": num(r["pv"], int, 5),
                             "skill": r["compétence"]} for r in sections.get("rpg", [])}
    cfg["rpgVoitures"] = {r["voiture"]: {"xp": num(r["xp"], int),
                                         "pv": num(r["pv"], int, 5),
                                         "skill": r["compétence"],
                                         "malus": r.get("malus", "")}
                          for r in sections.get("rpg_voitures", [])}
    cfg["danger"] = [{"lat": num(r["lat"]), "lng": num(r["lng"]), "img": r["img"],
                      "s": num(r["taille"], int, 47), "r": num(r["rayon"], int, 200000),
                      "t": r["label"]} for r in sections.get("danger", [])]
    # purely decorative map stickers (camels in the desert…): no circle, no label
    cfg["deco"] = [{"lat": num(r["lat"]), "lng": num(r["lng"]), "img": r["img"],
                    "s": num(r["taille"], int, 36)} for r in sections.get("deco", [])]
    return cfg


def state(cell):
    return SYMBOL.get(cell.strip(), "absent")


def parse_date(cell):
    """'Ven 1 août' / 'Mar 30 sept.' -> ('Ven 1 août', '2025-08-01') or None."""
    parts = cell.split()
    if len(parts) < 3 or not parts[1].isdigit():
        return None
    month = MONTH.get(re.sub(r"[^a-zà-ÿ]", "", parts[2].lower()))
    if not month:
        return None
    return cell.strip(), f"{YEAR}-{month:02d}-{int(parts[1]):02d}"


def split_emoji(title):
    """'🚗 HUGODOUARD' -> ('🚗', 'HUGODOUARD'). Falls back to ('', title)."""
    t = (title or "").strip()
    m = re.match(r"^([^\w\s]+)\s+(.+)$", t)
    if m:
        return m.group(1), m.group(2).strip()
    return "", t


def find_header(rows):
    """Locate the grid header row (the one whose first cell is 'Date')."""
    for i, r in enumerate(rows):
        if r and r[0].strip().lower() == "date":
            return i
    raise ValueError("Could not find the 'Date' header row in the CSV.")


def main():
    config = read_config()
    route = config.get("route") or ROUTE
    colors = [config.get("couleurs", {}).get(str(i + 1), c)
              for i, c in enumerate(CAR_COLORS)]

    with open(CSV, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    h = find_header(rows)
    header = rows[h]
    title_row = rows[h - 1] if h > 0 else [""] * len(header)

    # The two "Capacité" columns delimit the car blocks.
    cap_cols = [i for i, c in enumerate(header) if "capacit" in c.strip().lower()]
    if len(cap_cols) < 2:
        raise ValueError("Expected two 'Capacité' columns to delimit the cars.")
    total_col = next((i for i, c in enumerate(header)
                      if "total" in c.strip().lower()), len(header) - 1)

    car1_cols = [i for i in range(2, cap_cols[0]) if header[i].strip()]
    car2_cols = [i for i in range(cap_cols[0] + 1, cap_cols[1]) if header[i].strip()]
    CAR1 = [header[i].strip() for i in car1_cols]
    CAR2 = [header[i].strip() for i in car2_cols]

    e1, n1 = split_emoji(title_row[car1_cols[0]] if car1_cols else "")
    e2, n2 = split_emoji(title_row[car2_cols[0]] if car2_cols else "")
    CARS = {
        "1": {"name": n1 or "VOITURE 1", "emoji": e1 or "🚗", "color": colors[0]},
        "2": {"name": n2 or "VOITURE 2", "emoji": e2 or "🚙", "color": colors[1]},
    }

    records, location = [], None
    for r in rows[h + 1:]:
        if not r or not r[0].strip():
            continue
        parsed = parse_date(r[0])
        if not parsed:
            break  # reached the legend / end of the grid
        date, iso = parsed

        def cell(i):
            return r[i].strip() if i < len(r) else ""

        if cell(1):
            location = cell(1)
        records.append({
            "date": date,
            "iso": iso,
            "checkpoint": cell(1),                       # set only on arrival days
            "location": location,                        # carried forward
            "cap1": cell(cap_cols[0]),
            "cap2": cell(cap_cols[1]),
            "total": cell(total_col),
            "car1": {p: state(cell(i)) for p, i in zip(CAR1, car1_cols)},
            "car2": {p: state(cell(i)) for p, i in zip(CAR2, car2_cols)},
        })

    data = {"records": records, "route": route, "car1": CAR1, "car2": CAR2,
            "cars": CARS, "config": config}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"Wrote {os.path.normpath(OUT)}: {len(records)} day-records, "
          f"{len(route)} route points ({'config' if config.get('route') else 'fallback'}), "
          f"cars {CAR1} / {CAR2}")


if __name__ == "__main__":
    main()
