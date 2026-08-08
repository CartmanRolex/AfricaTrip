"""
Precompute the road geometry between the trip's GPS points.

Usage:  python src/fetch_routes.py [--dry-run] [--limit N]
Reads:  Firestore (public read paths) + src/site-overrides.json
Writes: src/routes.json   -> injected into the site as __ROUTES__ by build.py

Covers the WHOLE line, past and future: the travelled track between GPS points,
the planned itinerary between its waypoints, and the join from the latest known
position to the next stop.

Why this exists
---------------
The site draws its real track by joining accepted points with straight lines.
Between two sparse points that reads as a road nobody took — Montpellier to
Barcelona in a straight line crosses the Gulf of Lion. This script asks a
routing engine for the actual driving geometry of each pair and commits the
result, so the published page needs no routing service at all: it looks the
pair up in `ROUTES` and falls back to the straight line when it is absent.

A routed geometry is a deduction, not a measurement — the convoy may have taken
another road. It is still far closer to the truth than a line through the sea.

What it does NOT do
-------------------
It deliberately does not reimplement the site's track reconstruction (bucketing
by minute, impossible-transition rejection, roster fallback, shared occupant
tracks). Duplicating that logic in Python would rot the moment the template
changes. Instead it groups the raw points the same way the site does at a
coarse level — per person and per vehicle, chronologically — and routes every
pair within a small window (`PAIR_WINDOW`), which covers the pairs the site
actually draws after it has dropped some points. Any pair it misses simply
stays a straight line on the map.
"""
import argparse, json, math, os, re, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FIREBASE_CONFIG = os.path.join(HERE, "..", "app", "www", "firebase-config.js")
SITE_OVERRIDES = os.path.join(HERE, "site-overrides.json")
OUT = os.path.join(HERE, "routes.json")
DATA_JSON = os.path.join(HERE, "data.json")

TRIP_ID = "africa-trip-01"
OSRM = "https://router.project-osrm.org/route/v1/driving/"

MIN_PAIR_KM = 1.0        # en dessous, la ligne droite est deja la bonne reponse
MAX_PAIR_KM = 1500.0     # au dela, ce n'est plus un trajet routier continu
MAX_DETOUR = 4.0         # route > 4x le vol d'oiseau = itineraire aberrant
SNAP_MAX_KM = 50.0       # au-dela, OSRM a repondu a une autre question
PAIR_WINDOW = 3          # relie i a i+1..i+3 : couvre les points ecartes ensuite
JOIN_STOPS = 3           # escales visees depuis la derniere position connue
COORD_DP = 4             # ~11 m, la meme cle que le front-end
SIMPLIFY_KM = 0.2        # tolerance du lissage : compromis fidelite / poids


# --------------------------------------------------------------------------
# Firestore : lecture publique, sans authentification (memes chemins que le site)
# --------------------------------------------------------------------------
def firebase_config():
    """Read projectId/apiKey from the app's public config — single source."""
    text = open(FIREBASE_CONFIG, encoding="utf-8").read()
    def field(name):
        m = re.search(rf'{name}\s*:\s*"([^"]+)"', text)
        if not m:
            raise RuntimeError(f"{name} introuvable dans {FIREBASE_CONFIG}")
        return m.group(1)
    return field("projectId"), field("apiKey")


def fs_list(project, key, path):
    """List a Firestore collection, following pagination."""
    base = (f"https://firestore.googleapis.com/v1/projects/{project}"
            f"/databases/(default)/documents/{path}")
    docs, token = [], None
    while True:
        url = f"{base}?key={key}&pageSize=300" + (f"&pageToken={token}" if token else "")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                payload = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return docs          # chemin absent ou non lisible : on ignore
            raise
        docs += payload.get("documents", [])
        token = payload.get("nextPageToken")
        if not token:
            return docs


def val(field):
    """Unwrap one Firestore typed value."""
    if field is None:
        return None
    for k in ("doubleValue", "integerValue", "stringValue", "booleanValue",
              "timestampValue"):
        if k in field:
            v = field[k]
            return float(v) if k in ("doubleValue", "integerValue") else v
    if "mapValue" in field:
        return {k: val(v) for k, v in field["mapValue"].get("fields", {}).items()}
    if "arrayValue" in field:
        return [val(v) for v in field["arrayValue"].get("values", [])]
    return None


def fields(doc):
    return {k: val(v) for k, v in (doc.get("fields") or {}).items()}


# --------------------------------------------------------------------------
# Points bruts
# --------------------------------------------------------------------------
def to_ms(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return None


def first(*values):
    for v in values:
        if v is not None and v != "":
            return v
    return None


def slug(name):
    import unicodedata
    s = unicodedata.normalize("NFD", str(name or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", s))


def vehicle_of(value):
    v = slug(value)
    if v in ("hugodouard", "1", "car-1", "voiture-1"):
        return "hugodouard"
    if v in ("paul-pot", "paulpot", "2", "car-2", "voiture-2"):
        return "paul-pot"
    return None


def point(name, lat, lng, at, vehicle):
    if None in (lat, lng, at) or not name:
        return None
    lat, lng = float(lat), float(lng)
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None
    return {"name": name, "lat": lat, "lng": lng, "at": float(at), "vehicle": vehicle}


def collect_points(project, key, roster, rosters):
    """Every raw point the site could draw, with its person and its vehicle."""
    out = []
    for doc in fs_list(project, key, f"trips/{TRIP_ID}/trackChunks"):
        f = fields(doc)
        name, vid = f.get("displayName"), vehicle_of(f.get("vehicleId"))
        for p in (f.get("points") or {}).values():
            if not isinstance(p, dict):
                continue
            out.append(point(first(p.get("displayName"), name),
                             p.get("lat"), p.get("lng"),
                             to_ms(first(p.get("capturedAtMs"), p.get("capturedAt"),
                                         p.get("atMs"), p.get("at"))),
                             vehicle_of(p.get("vehicleId")) or vid))
    for doc in fs_list(project, key, f"trips/{TRIP_ID}/latest"):
        f = fields(doc)
        out.append(point(f.get("displayName"), f.get("lat"), f.get("lng"),
                         to_ms(first(f.get("capturedAtMs"), f.get("capturedAt"),
                                     f.get("atMs"), f.get("at"))),
                         vehicle_of(f.get("vehicleId"))))
    for doc in fs_list(project, key, "positions"):
        f = fields(doc)
        out.append(point(first(f.get("displayName"), f.get("name")),
                         f.get("lat"), f.get("lng"),
                         to_ms(first(f.get("capturedAtMs"), f.get("capturedAt"),
                                     f.get("at"))), None))
    for name in roster:
        for doc in fs_list(project, key, f"tracks/{name}/points"):
            f = fields(doc)
            out.append(point(name, f.get("lat"), f.get("lng"), to_ms(f.get("at")),
                             rosters.get(name)))
    for doc in fs_list(project, key, "photos"):
        f = fields(doc)
        if not (f.get("gps") or f.get("locationSource") == "media-gps"):
            continue          # seul un GPS embarque infléchit une trace
        name = first(f.get("displayName"), f.get("name"))
        at = to_ms(first(f.get("capturedAtMs"), f.get("capturedAt"), f.get("at")))
        vid = vehicle_of(first(f.get("vehicleIdAtCapture"), f.get("car"))) or rosters.get(name)
        out.append(point(name, f.get("lat"), f.get("lng"), at, vid))
    return [p for p in out if p]


# --------------------------------------------------------------------------
# Paires et routage
# --------------------------------------------------------------------------
def hav(a, b):
    r, d = 6371.0, math.pi / 180
    dla, dlo = (b["lat"] - a["lat"]) * d, (b["lng"] - a["lng"]) * d
    h = (math.sin(dla / 2) ** 2
         + math.cos(a["lat"] * d) * math.cos(b["lat"] * d) * math.sin(dlo / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def key_of(a, b):
    return (f"{a['lat']:.{COORD_DP}f},{a['lng']:.{COORD_DP}f};"
            f"{b['lat']:.{COORD_DP}f},{b['lng']:.{COORD_DP}f}")


def add_pair(pairs, a, b):
    km = hav(a, b)
    if MIN_PAIR_KM <= km <= MAX_PAIR_KM:
        pairs.setdefault(key_of(a, b), (a, b, km))


# Cles des traversees maritimes, remplies par wanted_pairs() : elles ne peuvent
# pas etre routees et se dessinent en ligne droite, ce qui est exact.
FERRY_KEYS = set()


def wanted_pairs(points, track_start, route):
    """Every pair the map may have to draw, past and future alike.

    Three families:
    1. consecutive GPS points, per person and per vehicle (the travelled track);
    2. consecutive waypoints of the planned itinerary (the dashed future) —
       these are static, they come straight from data/Config.csv;
    3. each subject's latest position joined to the stops ahead of it, which is
       exactly what `addPlannedFuture()` draws between the last known point and
       the next escale.
    """
    pairs = {}

    # 1. trace parcourue
    groups = {}
    for p in points:
        if track_start and p["at"] < track_start.get(p["name"], track_start["*"]):
            continue
        groups.setdefault(("personne", p["name"]), []).append(p)
        if p["vehicle"]:
            groups.setdefault(("voiture", p["vehicle"]), []).append(p)
    for members in groups.values():
        members.sort(key=lambda p: p["at"])
        for i, a in enumerate(members):
            for b in members[i + 1:i + 1 + PAIR_WINDOW]:
                add_pair(pairs, a, b)

    # 2. itineraire prevu, waypoint par waypoint
    for a, b in zip(route, route[1:]):
        add_pair(pairs, a, b)
        # Une traversee en ferry n'a pas de route : le profil voiture d'OSRM
        # l'ignore, et sa reponse s'arretait a Tarifa. La ligne droite EST la
        # bonne geometrie ici — c'est ce que fait le bateau.
        # SEULE la paire qui ARRIVE sur l'escale marquee compte : le drapeau dit
        # « on atteint ce point par bateau ». Tester aussi le depart faisait de
        # Tanger Med -> Rabat une traversee, soit 240 km de route marocaine
        # remplaces par une ligne droite.
        if b.get("ferry"):
            FERRY_KEYS.add(key_of(a, b))

    # 3. raccord derniere position -> prochaines escales. Le front-end vise la
    #    premiere escale devant lui ; on en couvre quelques-unes pour rester
    #    juste quand la position avance entre deux executions.
    stops = [(i, p) for i, p in enumerate(route) if p.get("cp")]
    for members in groups.values():
        if not members:
            continue
        last = members[-1]
        near = min(range(len(route)), key=lambda i: hav(last, route[i]))
        for _, stop in [s for s in stops if s[0] > near][:JOIN_STOPS]:
            add_pair(pairs, last, stop)
    return pairs


def simplify(points, tol_km):
    """Douglas-Peucker, iteratif (une geometrie brute fait des milliers de
    points et la version recursive depasse la pile de Python)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = points[i], points[j]
        lat0 = math.radians((a[0] + b[0]) / 2)
        r, d = 6371.0088, math.pi / 180
        bx = (b[1] - a[1]) * d * math.cos(lat0) * r
        by = (b[0] - a[0]) * d * r
        seg = math.hypot(bx, by)
        far, best = -1.0, i
        for k in range(i + 1, j):
            px = (points[k][1] - a[1]) * d * math.cos(lat0) * r
            py = (points[k][0] - a[0]) * d * r
            if seg == 0:
                dist = math.hypot(px, py)
            else:
                t = max(0.0, min(1.0, (px * bx + py * by) / (seg * seg)))
                dist = math.hypot(px - bx * t, py - by * t)
            if dist > far:
                far, best = dist, k
        if far > tol_km:
            keep[best] = True
            stack.append((i, best))
            stack.append((best, j))
    return [p for p, k in zip(points, keep) if k]


def road_geometry(a, b):
    """Ask OSRM for the driving geometry. None when it is unusable.

    `overview=full` puis simplification maison a SIMPLIFY_KM. Le `simplified`
    d'OSRM raccourcit proportionnellement a la longueur du trajet : sur une
    etape de 900 km il rendait 59 points et coupait tout droit sur 77 km, a
    travers la campagne. Mesure sur Montpellier -> Barcelone : 28 points et
    46 km de raccourci avant, 126 points et 9 km apres, pour 0,6 -> 2,5 Ko.
    Changer SIMPLIFY_KM n'a d'effet que sur les NOUVELLES paires : supprimer
    routes.json est le seul moyen de refaire les anciennes.
    """
    url = (f"{OSRM}{a['lng']:.6f},{a['lat']:.6f};{b['lng']:.6f},{b['lat']:.6f}"
           "?overview=full&geometries=geojson")
    with urllib.request.urlopen(url, timeout=30) as r:
        payload = json.load(r)
    if payload.get("code") != "Ok" or not payload.get("routes"):
        return None, payload.get("code", "?")
    route = payload["routes"][0]
    straight = hav(a, b)
    if straight and route["distance"] / 1000 > MAX_DETOUR * straight:
        # un detour enorme signale un itineraire aberrant (contournement d'une
        # mer, point tombe sur une ile) : la ligne droite reste plus honnete.
        return None, "detour"
    full = [[round(lat, 5), round(lng, 5)]
            for lng, lat in route["geometry"]["coordinates"]]
    # OSRM ramene chaque extremite au point ROUTABLE le plus proche, et la
    # geometrie rendue s'arrete la. Son profil voiture ignorant les ferries,
    # Algeciras -> Tanger Med finissait a Tarifa, 16 km avant la cote
    # marocaine : le trace mourait dans le vide et le detroit de Gibraltar
    # n'etait jamais franchi.
    # On ANCRE donc le resultat sur les points demandes. Le raccord ainsi ajoute
    # est court — 3 a 14 km sur ce voyage — et il est honnete : au detroit c'est
    # la traversee elle-meme, ailleurs c'est un acces non cartographie.
    ends = max(hav(a, {"lat": full[0][0], "lng": full[0][1]}),
               hav(b, {"lat": full[-1][0], "lng": full[-1][1]}))
    if ends > SNAP_MAX_KM:
        return None, f"extremite a {ends:.0f} km du point demande"
    geom = simplify(full, SIMPLIFY_KM)
    ends_a = [round(a["lat"], 5), round(a["lng"], 5)]
    ends_b = [round(b["lat"], 5), round(b["lng"], 5)]
    if hav(a, {"lat": geom[0][0], "lng": geom[0][1]}) > 0.05:
        geom.insert(0, ends_a)
    if hav(b, {"lat": geom[-1][0], "lng": geom[-1][1]}) > 0.05:
        geom.append(ends_b)
    return geom, "ok"


def read_track_start():
    """Per-person first day, from the repo config, in epoch ms."""
    try:
        raw = json.load(open(SITE_OVERRIDES, encoding="utf-8")).get("track_start")
    except FileNotFoundError:
        return None
    if not raw:
        return None
    from datetime import datetime
    # `track_start` accepte une date seule OU une date+heure (quelqu'un qui
    # rejoint le convoi a une escale). Completer aveuglement en T00:00:00
    # fabriquait "2026-08-07T14:00T00:00:00" et faisait planter tout le script.
    day = lambda s: datetime.fromisoformat(
        s if "T" in s else f"{s}T00:00:00").timestamp() * 1000
    out = {"*": day(raw["default"]) if raw.get("default") else 0}
    for name, value in (raw.get("by_person") or {}).items():
        out[name] = day(value)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--dry-run", action="store_true", help="ne rien ecrire ni appeler")
    ap.add_argument("--limit", type=int, default=0, help="nombre max de nouvelles routes")
    args = ap.parse_args()

    data = json.load(open(DATA_JSON, encoding="utf-8"))
    rosters = {n: "hugodouard" for n in data["car1"]}
    rosters.update({n: "paul-pot" for n in data["car2"]})

    route = [p for p in data.get("route", []) if p.get("lat") is not None]
    project, key = firebase_config()
    points = collect_points(project, key, list(rosters), rosters)
    pairs = wanted_pairs(points, read_track_start(), route)
    print(f"{len(points)} points bruts + {len(route)} etapes d'itineraire "
          f"-> {len(pairs)} paires candidates")

    cache = {}
    if os.path.exists(OUT):
        cache = json.load(open(OUT, encoding="utf-8"))
    todo = [k for k in pairs if k not in cache]
    print(f"{len(cache)} deja en cache, {len(todo)} a calculer")
    if args.dry_run:
        return

    added = skipped = 0
    for k in todo[:args.limit or len(todo)]:
        a, b, km = pairs[k]
        if k in FERRY_KEYS:
            # Une traversee ne se route pas, et il ne faut meme pas demander :
            # le profil voiture longeait la cote jusqu'a Tarifa, et l'ancrage
            # transformait cette reponse en un detour de 37 km vers l'ouest
            # avant de revenir. La ligne droite EST le trajet du bateau.
            cache[k] = [[round(a["lat"], 5), round(a["lng"], 5)],
                        [round(b["lat"], 5), round(b["lng"], 5)]]
            added += 1
            print(f"  {k}: {km:.0f} km de traversee en ferry — ligne droite")
            continue
        try:
            geom, why = road_geometry(a, b)
        except Exception as e:
            print(f"  {k}: erreur reseau ({e}) — ignore")
            continue
        if geom:
            cache[k] = geom
            added += 1
        else:
            skipped += 1
            print(f"  {k}: {km:.0f} km a vol d'oiseau, pas de route utilisable ({why})")
        time.sleep(.2)          # service public : on reste courtois

    # Les paires disparues (points supprimes) sortent du cache pour qu'il ne
    # grossisse pas indefiniment.
    stale = [k for k in cache if k not in pairs]
    for k in stale:
        del cache[k]

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"), sort_keys=True)
    size = os.path.getsize(OUT) / 1024
    print(f"{added} routes ajoutees, {skipped} sans route, {len(stale)} obsoletes retirees")
    print(f"Ecrit {os.path.normpath(OUT)} : {len(cache)} routes, {size:.0f} Ko")
    print("Lancer ensuite : python src/build.py")


if __name__ == "__main__":
    main()
