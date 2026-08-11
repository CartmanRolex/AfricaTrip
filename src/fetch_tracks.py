"""
Snapshot the trip's HISTORY out of Firestore into src/tracks.json.

Usage:  python src/fetch_tracks.py [--dry-run]
Reads:  Firestore (public read paths)
Writes: src/tracks.json  -> injected into the site as __TRACKS__ by build.py

Why this exists
---------------
The published page used to open FOURTEEN live listeners and read 235 documents
*per visit*: 51 photos, 57 track chunks, 104 points across nine legacy v1
tracks, plus crew, positions and latest. The Firestore free tier allows 50 000
reads a day, so the site could serve about 210 visits before the whole project
returned RESOURCE_EXHAUSTED — which is exactly what happened on 2026-08-10,
taking the crew's GPS uploads down with it. The cost grew with the audience
against a fixed quota: a site that succeeds breaks itself.

Almost none of that data is live. A v1 track point written last month never
changes; a chunk from two days ago never changes; a photo changes when someone
edits its caption, a few times a day. Only the *current* position and the PV /
Mana / Eveil gauges are genuinely live.

So the history is snapshotted here, committed, and shipped inside the page —
the same pattern `fetch_routes.py` and `fetch_photos.py` already use. The page
then reads it for free and subscribes only to `latest` and `crew`: 14 documents
instead of 235, and a visitor costs nothing.

Run hourly by .github/workflows/routes.yml, next to the route refresh.
"""
import argparse, json, os, urllib.error

from fetch_routes import TRIP_ID, fields, firebase_config, fs_list

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tracks.json")
DATA_JSON = os.path.join(HERE, "data.json")


def roster():
    """Active traveler names, so a removed one is not snapshotted."""
    try:
        with open(DATA_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    names = list(data.get("car1", [])) + list(data.get("car2", []))
    return [n for n in names if n]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--dry-run", action="store_true", help="ne rien ecrire")
    args = ap.parse_args()

    project, key = firebase_config()
    snap = {"chunks": [], "photos": [], "v1": {}, "positions": []}

    def lire(path):
        """Firestore repond 429 des que le quota du jour est epuise. Ce n'est
        pas une erreur de programmation : on abandonne le tour proprement, sans
        casser le workflow ni toucher a l'instantane deja publie."""
        try:
            return fs_list(project, key, path)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise SystemExit("Firestore : quota epuise (429) — "
                                 "tracks.json laisse intact, nouvel essai au prochain tour.")
            raise

    # Chunks v2 : l'historique des points, immuable une fois la fenetre passee.
    for doc in lire(f"trips/{TRIP_ID}/trackChunks"):
        f = fields(doc)
        snap["chunks"].append({"id": doc["name"].rsplit("/", 1)[-1], "data": f})

    # Medias : leurs metadonnees (URL, position, legende, auteur).
    for doc in lire("photos"):
        snap["photos"].append({"id": doc["name"].rsplit("/", 1)[-1], "data": fields(doc)})

    # Traces v1 : format hérité, purement historique — il ne bouge plus.
    for name in roster():
        pts = [fields(d) | {"id": d["name"].rsplit("/", 1)[-1]}
               for d in lire(f"tracks/{name}/points")]
        if pts:
            snap["v1"][name] = pts

    # `positions` : dernier repli hérité, une ligne par personne.
    for doc in lire("positions"):
        snap["positions"].append({"id": doc["name"].rsplit("/", 1)[-1], "data": fields(doc)})

    # Curseurs de rattrapage. L'instantane date au pire d'une heure, et la page
    # ne doit PAS reprendre l'ecoute complete pour autant (141 medias + 129
    # tranches par visite, soit le probleme de quota qu'on vient de resoudre).
    # Elle ecoute le COMPLEMENT : ce qui a ete ecrit apres ces bornes.
    #
    # Pour les medias, la borne est `at` — un serverTimestamp pose a l'ENVOI —
    # et surtout pas `capturedAt` : Gal a pris huit photos hier apres-midi et
    # les a envoyees ce matin, un curseur sur la date de prise de vue les
    # aurait toutes ratees.
    # Les tranches n'ont pas d'equivalent serveur, seulement `bucketStartMs`
    # (derive de l'heure de capture). On recule d'une tranche entiere pour que
    # celle en cours de remplissage soit toujours reprise, meme si un autre
    # equipier en a ouvert une plus recente.
    BUCKET_MS = 2 * 60 * 60 * 1000
    photos_at = max((p["data"].get("at") or "" for p in snap["photos"]), default="")
    buckets = [int(c["data"].get("bucketStartMs") or 0) for c in snap["chunks"]]
    snap["cursors"] = {"photosAt": photos_at or None,
                       "chunksBucketMs": (max(buckets) - BUCKET_MS) if buckets else 0}

    total = (len(snap["chunks"]) + len(snap["photos"])
             + sum(len(v) for v in snap["v1"].values()) + len(snap["positions"]))
    print(f"curseurs : medias apres {snap['cursors']['photosAt']}, "
          f"tranches depuis {snap['cursors']['chunksBucketMs']}")
    print(f"chunks {len(snap['chunks'])}, medias {len(snap['photos'])}, "
          f"v1 {sum(len(v) for v in snap['v1'].values())} sur {len(snap['v1'])} personnes, "
          f"positions {len(snap['positions'])}")

    if args.dry_run:
        print(f"[DRY RUN] {total} documents — rien ecrit.")
        return

    # Un instantané vide écraserait l'historique embarqué : on refuse. C'est le
    # cas quand Firestore répond 429, et il ne faut surtout pas publier ça.
    if not total:
        raise SystemExit("Instantane vide (quota ? reseau ?) — tracks.json laisse intact.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    print(f"Ecrit {os.path.normpath(OUT)} : {total} documents, "
          f"{os.path.getsize(OUT)/1024:.0f} Ko")
    print("Lancer ensuite : python src/build.py")


if __name__ == "__main__":
    main()
