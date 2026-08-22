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
import csv, datetime, json, os, re

HERE = os.path.dirname(__file__)
CSV = os.path.join(HERE, "..", "data", "AfriqueCalendrier_-_Presences_Voyage.csv")
CONFIG_CSV = os.path.join(HERE, "..", "data", "Config.csv")
SITE_OVERRIDES = os.path.join(HERE, "site-overrides.json")
OUT = os.path.join(HERE, "data.json")

DEFAULT_TRIP_YEAR = 2026
MONTH = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5,
         "juin": 6, "juil": 7, "août": 8, "aout": 8, "sept": 9, "oct": 10,
         "nov": 11, "déc": 12, "dec": 12}
WEEKDAY = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")

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


def read_site_overrides():
    """Read deliberate repo-side overrides applied after every Sheet refresh.

    The Google Sheet remains the normal source of truth. This small final layer
    is for changes that must survive refreshes when Sheet write credentials are
    unavailable on the build machine (confirmed year/text, removed travelers
    and phone formatting).
    """
    try:
        with open(SITE_OVERRIDES, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {"trip_year": DEFAULT_TRIP_YEAR, "textes": {},
                "removed_travelers": set(), "phones": {}, "terminus": None,
                "track_start": None, "roles": {}, "vehicle_from": {},
                "excluded_points": [], "traversees": []}
    if not isinstance(raw, dict):
        raise ValueError("site-overrides.json must contain a JSON object")
    removed = raw.get("removed_travelers", [])
    phones = raw.get("phones", {})
    trip_year = raw.get("trip_year", DEFAULT_TRIP_YEAR)
    textes = raw.get("textes", {})
    if not isinstance(trip_year, int) or not 2000 <= trip_year <= 2100:
        raise ValueError("site-overrides.json trip_year must be an integer from 2000 to 2100")
    if not isinstance(textes, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in textes.items()):
        raise ValueError("site-overrides.json textes must map keys to strings")
    if not isinstance(removed, list) or not all(isinstance(v, str) for v in removed):
        raise ValueError("site-overrides.json removed_travelers must be a string list")
    if not isinstance(phones, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in phones.items()):
        raise ValueError("site-overrides.json phones must map names to strings")
    # Libelle de role par personne. Le site n'a que des formes masculines en dur
    # ("observateur", "aventurier") ; c'est le seul endroit ou nommer quelqu'un
    # autrement, sans deviner quoi que ce soit a partir d'un prenom.
    # Qui roule dans quelle voiture PEUT CHANGER en cours de route. La grille de
    # presence ne sait pas l'exprimer : une personne y occupe une colonne fixe
    # sous un bloc voiture. `vehicle_from` dit, par personne, a partir de quel
    # instant elle roule dans quelle voiture — meme forme que `track_start`, et
    # ca prime sur ce que l'appli a enregistre, parce qu'un equipier oublie de
    # changer son reglage (les points de Hugo alternaient entre les deux
    # voitures a deux secondes d'intervalle).
    vehicles = read_vehicle_from(raw.get("vehicle_from"))
    traversees = read_traversees(raw.get("traversees"))
    roles = raw.get("roles", {})
    # Points désavoués : l'équipage sait qu'ils sont faux (identité changée dans
    # l'appli au mauvais moment, position posée par erreur). On les nomme
    # explicitement plutôt que de deviner — un point écarté doit être un choix
    # écrit, jamais une heuristique qui peut jeter de la vraie donnée.
    excluded = raw.get("excluded_points") or []
    if not isinstance(excluded, list) or any(not isinstance(x, str) for x in excluded):
        raise ValueError("excluded_points must be a list of point ids")
    if not isinstance(roles, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in roles.items()):
        raise ValueError("site-overrides.json roles must map names to strings")
    return {"trip_year": trip_year,
            "textes": {k.strip(): v.strip() for k, v in textes.items() if k.strip()},
            "removed_travelers": {v.strip() for v in removed if v.strip()},
            "phones": {k.strip(): v.strip() for k, v in phones.items() if k.strip()},
            "terminus": read_terminus(raw.get("terminus")),
            "track_start": read_track_start(raw.get("track_start")),
            "roles": {k.strip(): v.strip() for k, v in roles.items() if k.strip()},
            "vehicle_from": vehicles,
            "traversees": traversees,
            "excluded_points": sorted({x.strip() for x in excluded if x.strip()})}


def read_traversees(raw):
    """Périodes où quelqu'un ne roule PAS : bateau, avion, train.

    Le site relie deux points GPS par la route quand il en connaît une. C'est
    juste pour une voiture, faux pour une traversée : Gal a fait Dakar →
    Ziguinchor en bateau et le site lui faisait parcourir 465 km de route
    côtière. La ligne droite EST la bonne géométrie ici — exactement le même
    raisonnement que le drapeau `ferry` de l'itinéraire prévu.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("traversees must be a list")
    out = []
    for e in raw:
        if not isinstance(e, dict) or not {"qui", "de", "a"} <= set(e):
            raise ValueError("chaque traversee veut 'qui', 'de' et 'a'")
        for cle in ("de", "a"):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", str(e[cle]).strip()):
                raise ValueError(f"traversee.{cle} : format YYYY-MM-DD[THH:MM] attendu")
        if str(e["de"]) >= str(e["a"]):
            raise ValueError("traversee : 'de' doit preceder 'a'")
        out.append({"qui": str(e["qui"]).strip(), "de": str(e["de"]).strip(),
                    "a": str(e["a"]).strip(), "moyen": str(e.get("moyen") or "bateau")})
    return out


def read_vehicle_from(raw):
    """Validate `vehicle_from`: {name: [{at, vehicle}]}, sorted by instant.

    `at` is `YYYY-MM-DDTHH:MM` (a car swap happens at an hour, not on a day
    boundary). `vehicle` is a car id as the site knows it.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("site-overrides.json vehicle_from must be a JSON object")
    # « aucune » = la personne n'est dans AUCUNE voiture a ce moment : elle est
    # restee sur place, ou elle voyage autrement. Sans cette valeur, on ne
    # pouvait dire QUE « il a change de voiture », jamais « il n'y est plus » —
    # et les photos de Gal restees a Dakar tiraient la trace de la voiture
    # 259 km en arriere, creant une boucle.
    cars = {"hugodouard", "paul-pot", "aucune"}
    out = {}
    for name, entries in raw.items():
        if not name.strip():
            continue
        if not isinstance(entries, list):
            raise ValueError(f"vehicle_from.{name} must be a list")
        clean = []
        for e in entries:
            if not isinstance(e, dict) or "at" not in e or "vehicle" not in e:
                raise ValueError(f"vehicle_from.{name} entries need 'at' and 'vehicle'")
            at = str(e["at"]).strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", at):
                raise ValueError(f"vehicle_from.{name}.at must be YYYY-MM-DD[THH:MM]")
            if e["vehicle"] not in cars:
                raise ValueError(f"vehicle_from.{name}.vehicle must be one of {sorted(cars)}")
            clean.append({"at": at, "vehicle": e["vehicle"]})
        if clean:
            out[name.strip()] = sorted(clean, key=lambda x: x["at"])
    return out


def read_track_start(raw):
    """Validate `track_start`: the instant a person joins the trip.

    Media and GPS older than that instant are ignored by the site — they are
    pre-trip leftovers, not part of the journey — and the person is not shown
    aboard a car before it either. `default` applies to everyone; `by_person`
    overrides it for those who leave earlier or join later.

    A bare `YYYY-MM-DD` means "from that day on". `YYYY-MM-DDTHH:MM` is for
    someone who meets the convoy at a stop rather than travelling from dawn:
    marking them present for the whole day would put them in a car hundreds of
    kilometres before they actually got in.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("site-overrides.json track_start must be a JSON object")

    def day(value, label):
        if not isinstance(value, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", value.strip()):
            raise ValueError(f"site-overrides.json track_start.{label} must be "
                             f"YYYY-MM-DD or YYYY-MM-DDTHH:MM")
        return value.strip()

    default = day(raw.get("default"), "default") if raw.get("default") is not None else None
    by_person = raw.get("by_person", {})
    if not isinstance(by_person, dict):
        raise ValueError("site-overrides.json track_start.by_person must be an object")
    return {"default": default,
            "by_person": {k.strip(): day(v, f"by_person.{k}") for k, v in by_person.items() if k.strip()}}


def read_terminus(raw):
    """Validate the optional `terminus` override (final checkpoint of the trip).

    The Sheet still describes the old editorial continuation
    (Conakry → Abidjan → Accra → Lomé). Until it can be edited at the source,
    this override shortens the plan to a single confirmed terminus reached
    after `after`, without hardcoding a date: the cut is derived from the
    arrival record of `after` itself.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("site-overrides.json terminus must be a JSON object")
    missing = {"after", "cp", "label", "lat", "lng"} - set(raw)
    if missing:
        raise ValueError(f"site-overrides.json terminus misses {sorted(missing)}")
    for key in ("after", "cp", "label"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise ValueError(f"site-overrides.json terminus.{key} must be a non-empty string")
    for key in ("lat", "lng"):
        if not isinstance(raw[key], (int, float)) or isinstance(raw[key], bool):
            raise ValueError(f"site-overrides.json terminus.{key} must be a number")
    return {"after": raw["after"].strip(), "cp": raw["cp"].strip(),
            "label": raw["label"].strip(), "lat": float(raw["lat"]), "lng": float(raw["lng"])}


def cp_norm(s):
    """Compare checkpoint names the way the front-end does (`norm()`).

    The sheet writes decorated cells such as `ALGECIRAS⛴️`.
    """
    return re.sub(r"[^A-Za-zÀ-ÿ]", "", s or "").upper()


def apply_terminus(records, config, terminus):
    """Shorten plan and records so the trip ends at `terminus`.

    Everything after the arrival at `terminus["after"]` belongs to the final
    leg: the abandoned continuation's checkpoints are cleared, the last day
    becomes the terminus arrival, and `location` is recomputed by carry-forward
    so the days in between still read the last checkpoint actually reached. The
    planned polyline is cut after `after` and closed by the terminus waypoint.
    """
    if not terminus or not records:
        return
    after, cp, label = terminus["after"], terminus["cp"], terminus["label"]

    route = config.get("route") or []
    cut = next((i for i, pt in enumerate(route) if cp_norm(pt.get("cp")) == cp_norm(after)), None)
    if cut is None:
        raise ValueError(f"site-overrides.json terminus.after ({after}) is not a route checkpoint")
    config["route"] = route[:cut + 1] + [
        {"name": label, "lat": terminus["lat"], "lng": terminus["lng"], "cp": cp}]

    kept = {cp_norm(pt.get("cp")) for pt in config["route"] if pt.get("cp")}
    config["checkpoints"] = {k: v for k, v in (config.get("checkpoints") or {}).items()
                             if cp_norm(k) in kept}
    config["checkpoints"][cp] = label

    arrival = next((i for i, r in enumerate(records) if cp_norm(r["checkpoint"]) == cp_norm(after)),
                   None)
    if arrival is None:
        raise ValueError(f"site-overrides.json terminus.after ({after}) is not a record checkpoint")
    for rec in records[arrival + 1:]:
        rec["checkpoint"] = ""
    records[-1]["checkpoint"] = cp

    location = None
    for rec in records:
        if rec["checkpoint"]:
            location = rec["checkpoint"]
        rec["location"] = location


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
    # mana/eveil : jauges 0-10 pilotees par les curseurs de l'app. Colonnes
    # optionnelles (`.get`) pour qu'un Config.csv qui ne les a pas encore
    # continue de se parser, avec 5 comme neutre — comme pv.
    cfg["rpg"] = {r["nom"]: {"xp": num(r["xp"], int), "pv": num(r["pv"], int, 5),
                             "mana": num(r.get("mana"), int, 5),
                             "eveil": num(r.get("eveil"), int, 5),
                             "skill": r["compétence"],
                             "lien": r.get("lien", ""),
                             "tel": r.get("téléphone", ""),
                             "note": r.get("note", "")} for r in sections.get("rpg", [])}
    cfg["rpgVoitures"] = {r["voiture"]: {"xp": num(r["xp"], int),
                                         "pv": num(r["pv"], int, 5),
                                         "skill": r["compétence"],
                                         "malus": r.get("malus", "")}
                          for r in sections.get("rpg_voitures", [])}
    cfg["danger"] = [{"lat": num(r["lat"]), "lng": num(r["lng"]), "img": r["img"],
                      "s": num(r["taille"], int, 47), "r": num(r["rayon"], int, 200000),
                      "t": r["label"]} for r in sections.get("danger", [])]
    # spectators following the trip from home; stats come from the rpg section
    cfg["observateurs"] = [r["nom"] for r in sections.get("observateurs", [])
                           if r.get("nom")]
    # purely decorative map stickers (camels in the desert…): no circle, no label
    cfg["deco"] = [{"lat": num(r["lat"]), "lng": num(r["lng"]), "img": r["img"],
                    "s": num(r["taille"], int, 36)} for r in sections.get("deco", [])]
    return cfg


def state(cell):
    return SYMBOL.get(cell.strip(), "absent")


def parse_date(cell, year=DEFAULT_TRIP_YEAR):
    """Parse a French date cell and recompute its weekday for the trip year."""
    parts = cell.split()
    if len(parts) < 3 or not parts[1].isdigit():
        return None
    month = MONTH.get(re.sub(r"[^a-zà-ÿ]", "", parts[2].lower()))
    if not month:
        return None
    day = int(parts[1])
    try:
        date = datetime.date(year, month, day)
    except ValueError:
        return None
    # The public Sheet snapshot may still carry weekday names from an older
    # year. Replace only that token and preserve its human month punctuation.
    label = re.sub(r"^\S+", WEEKDAY[date.weekday()], cell.strip(), count=1)
    return label, date.isoformat()


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
    overrides = read_site_overrides()
    config.setdefault("textes", {}).update(overrides["textes"])
    trip_year = overrides["trip_year"]
    removed = overrides["removed_travelers"]
    rpg = config.get("rpg", {})
    missing_phone_names = sorted(set(overrides["phones"]) - set(rpg))
    if missing_phone_names and os.path.exists(CONFIG_CSV):
        raise ValueError("Phone override targets missing RPG rows: "
                         + ", ".join(missing_phone_names))
    for name, phone in overrides["phones"].items():
        if name in rpg:
            rpg[name]["tel"] = phone
    if overrides["roles"]:
        config["roles"] = dict(overrides["roles"])
    if overrides["vehicle_from"]:
        config["vehicleFrom"] = overrides["vehicle_from"]
    if overrides["traversees"]:
        config["traversees"] = overrides["traversees"]
    if overrides["excluded_points"]:
        config["excludedPoints"] = overrides["excluded_points"]
    # `removed_travelers` veut dire « plus dans une voiture », pas « effacé ».
    # Quelqu'un qui descend du voyage peut continuer à le suivre depuis chez
    # lui : sa carte d'observateur lit ses stats dans cette même section `rpg`,
    # donc lui retirer sa ligne la viderait de tout ce qu'on sait déjà de lui.
    observers = {n for n in (config.get("observateurs") or []) if isinstance(n, str)}
    for name in removed:
        if name not in observers:
            rpg.pop(name, None)

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

    raw_car1_cols = [i for i in range(2, cap_cols[0]) if header[i].strip()]
    raw_car2_cols = [i for i in range(cap_cols[0] + 1, cap_cols[1]) if header[i].strip()]
    removed_in_grid = removed.intersection(header[i].strip()
                                           for i in raw_car1_cols + raw_car2_cols)
    car1_cols = [i for i in raw_car1_cols if header[i].strip() not in removed]
    car2_cols = [i for i in raw_car2_cols if header[i].strip() not in removed]
    CAR1 = [header[i].strip() for i in car1_cols]
    CAR2 = [header[i].strip() for i in car2_cols]

    e1, n1 = split_emoji(title_row[raw_car1_cols[0]] if raw_car1_cols else "")
    e2, n2 = split_emoji(title_row[raw_car2_cols[0]] if raw_car2_cols else "")
    CARS = {
        "1": {"name": n1 or "VOITURE 1", "emoji": e1 or "🚗", "color": colors[0]},
        "2": {"name": n2 or "VOITURE 2", "emoji": e2 or "🚙", "color": colors[1]},
    }

    records, location = [], None
    for r in rows[h + 1:]:
        if not r or not r[0].strip():
            continue
        parsed = parse_date(r[0], trip_year)
        if not parsed:
            break  # reached the legend / end of the grid
        date, iso = parsed

        def cell(i):
            return r[i].strip() if i < len(r) else ""

        if cell(1):
            location = cell(1)
        car1 = {p: state(cell(i)) for p, i in zip(CAR1, car1_cols)}
        car2 = {p: state(cell(i)) for p, i in zip(CAR2, car2_cols)}
        # The Sheet's capacity/total formulas may still count a removed column.
        # Once an override removes someone, recompute confirmed occupants so
        # the dashboard exposes the newly free seat and correct total.
        if removed_in_grid:
            present1 = sum(v == "present" for v in car1.values())
            present2 = sum(v == "present" for v in car2.values())
            cap1, cap2, total = f"{present1}/4", f"{present2}/4", str(present1 + present2)
        else:
            cap1, cap2, total = cell(cap_cols[0]), cell(cap_cols[1]), cell(total_col)

        records.append({
            "date": date,
            "iso": iso,
            "checkpoint": cell(1),                       # set only on arrival days
            "location": location,                        # carried forward
            "cap1": cap1,
            "cap2": cap2,
            "total": total,
            "car1": car1,
            "car2": car2,
        })

    apply_terminus(records, config, overrides["terminus"])
    if overrides["track_start"]:
        config["trackStart"] = overrides["track_start"]

    data = {"records": records, "route": config.get("route", route), "car1": CAR1, "car2": CAR2,
            "cars": CARS, "config": config}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"Wrote {os.path.normpath(OUT)}: {len(records)} day-records, "
          f"{len(route)} route points ({'config' if config.get('route') else 'fallback'}), "
          f"cars {CAR1} / {CAR2}")


if __name__ == "__main__":
    main()
